"""Batch Yidaizhang collection submission followed by serialized verification."""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, ".")

from src.cbj.verification import (
    fetch_backend_fields,
    report_has_errors,
    verify_annual_settlement_cbj,
    verify_personal_cbj,
)
from src.chanjet_admin.task_query import TASK_LIST_URL, ChanjetAdminTaskQuery
from src.coverage.analyzer import write_coverage_status
from src.coverage.registry import build_coverage_targets, normalize_tax_type as normalize_coverage_tax_type
from src.coverage.supplement import CoverageSupplementPlanner, apply_supplement_candidates_to_state
from src.runtime.process_lock import DEFAULT_TAX_BROWSER_LOCK, ProcessLock
from src.ydz.api import YdzApi
from src.ydz.collector import YdzCollector
from src.ydz.models import TERMINAL_COLLECT_STATUSES, YdzCollectResult
from src.ydz.session import YdzSession, get_env_credentials
from src.ydz.task_resolver import VerifyTaskResolver


LOGGER = logging.getLogger("batch_collect_verify")
PROBLEM_STATUSES = {"mismatch", "api_missing", "web_missing", "parse_error", "mapping_error"}
FORM_ORDER = [
    "vat_general_main",
    "vat_general_appendix1",
    "vat_general_appendix2",
    "vat_general_appendix3",
    "vat_general_appendix4",
    "vat_general_appendix5",
    "vat_small_main",
    "vat_small_appendix1",
    "vat_small_appendix2",
    "cit_a_main",
    "culture_fee_main",
    "culture_fee_deduction",
    "consumption_tax_main",
    "consumption_tax_surcharge",
    "cbj_personal",
    "cbj_personal_backend",
    "cbj_annual_settlement",
]
AREA_CODE_NAMES = {
    "11": "北京",
    "12": "天津",
    "13": "河北",
    "14": "山西",
    "15": "内蒙古",
    "21": "辽宁",
    "22": "吉林",
    "23": "黑龙江",
    "31": "上海",
    "32": "江苏",
    "33": "浙江",
    "34": "安徽",
    "35": "福建",
    "36": "江西",
    "37": "山东",
    "41": "河南",
    "42": "湖北",
    "43": "湖南",
    "44": "广东",
    "45": "广西",
    "46": "海南",
    "50": "重庆",
    "51": "四川",
    "52": "贵州",
    "53": "云南",
    "54": "西藏",
    "61": "陕西",
    "62": "甘肃",
    "63": "青海",
    "64": "宁夏",
    "65": "新疆",
}
TAX_TYPE_LABELS = {
    "VAT_GENERAL": "增值税（一般纳税人）",
    "VAT_SMALL": "增值税（小规模纳税人）",
    "CIT_A": "企业所得税（A类）",
    "CIT": "企业所得税",
    "CULTURE_FEE": "文化事业建设费",
    "CONSUMPTION_TAX": "消费税",
    "CBJ": "残保金",
    "CBJ_PERSONAL": "个税残保金",
    "CBJ_ANNUAL": "汇算清缴残保金",
}
YDZ_TAX_TYPE_ID_LABELS = {
    1: "增值税",
    2: "企业所得税",
    3: "文化事业建设费",
    5: "城市维护建设税",
    6: "教育费附加",
    7: "地方教育附加",
    11: "印花税",
    12: "房产税",
    13: "城镇土地使用税",
    14: "车船税",
    21: "环境保护税",
    26: "残保金",
    29: "消费税",
    31: "残疾人就业保障金",
    40: "社会保险费",
    48: "财务报表",
}

OPS_STAGE_LABELS = {
    "queued": "排队中",
    "collect_submitted": "发起取数",
    "collect_checked": "检查取数状态",
    "collect_session_failed": "登录易代账",
    "collect_failed": "发起取数",
    "collect_poll_retry": "等待取数完成",
    "collect_no_need": "无需取数",
    "collect_terminal": "取数完成",
    "collect_manual_required": "需人工处理",
    "collect_timeout": "等待取数完成",
    "task_resolved": "查询 taskId",
    "task_unresolved": "查询 taskId",
    "verifying": "验证数据",
    "verified": "完成验证",
    "skipped": "已跳过",
}


def previous_month_period(today: date | None = None) -> str:
    today = today or date.today()
    year = today.year
    month = today.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}{month:02d}"


def parse_tax_nos(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    for item in args.tax_no or []:
        values.extend(part.strip() for part in item.split(",") if part.strip())
    if args.tax_no_file:
        for line in Path(args.tax_no_file).read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#"):
                values.append(clean)
    seen: set[str] = set()
    duplicates: list[str] = []
    deduped: list[str] = []
    for value in values:
        if value in seen:
            duplicates.append(value)
            continue
        seen.add(value)
        deduped.append(value)
    if duplicates:
        LOGGER.warning("Duplicate tax numbers ignored: %s", ", ".join(unique_texts(duplicates)))
    return deduped


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch collect tax data, resolve taskIds, then verify serially.")
    parser.add_argument("--tax-no", action="append", help="Tax number. Can be repeated or comma-separated.")
    parser.add_argument("--tax-no-file", help="UTF-8 file containing one tax number per line.")
    parser.add_argument("--period", default=previous_month_period(), help="Tax period in YYYYMM. Default: previous month.")
    parser.add_argument("--enterprise", default="\u84dd\u5929\u4e4b\u7231", help="Yidaizhang enterprise name.")
    parser.add_argument("--run-id", default="", help="Batch run id. Defaults to current timestamp.")
    parser.add_argument("--output-dir", default="output/batch_runs")
    parser.add_argument("--skip-collect", action="store_true", help="Only verify taskIds already recorded in state.json.")
    parser.add_argument("--verify", action="store_true", help="Run main.py verification after resolving taskIds.")
    parser.add_argument("--rerun-verified", action="store_true", help="Run verification even if state already has a result.")
    parser.add_argument(
        "--reuse-existing-report",
        action="store_true",
        help="Skip verification when an existing summary report is already available for the same taskId.",
    )
    parser.add_argument("--force", action="store_true", help="Submit collection even if the account is already collected.")
    parser.add_argument("--targets", default="auto", help="Targets passed to main.py.")
    parser.add_argument("--skip-browser", action="store_true", help="Passed to main.py verification.")
    parser.add_argument("--skip-pdf", action="store_true", help="Passed to main.py verification.")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip network/CDP preflight checks before collection.")
    parser.add_argument(
        "--skip-coverage-supplement",
        action="store_true",
        help="Skip backend representative-task search for uncovered tax/status targets.",
    )
    parser.add_argument(
        "--coverage-supplement-page-size",
        type=int,
        default=50,
        help="Page size used when searching backend supplement tasks.",
    )
    parser.add_argument(
        "--cbj-mode",
        choices=["auto", "backend", "annual"],
        default="auto",
        help="CBJ verification mode. auto infers personal backend-only vs annual A100000; annual no-row does not fall back silently.",
    )
    parser.add_argument("--query-year", type=int, default=date.today().year, help="Query year for CBJ annual verification.")
    parser.add_argument("--tax-timeout", type=int, default=600, help="Tax bureau login and task-cookie timeout for verification.")
    parser.add_argument(
        "--tax-login-strategy",
        choices=["direct_first", "plugin_first"],
        default="direct_first",
        help="Tax bureau login strategy passed to main.py. direct_first avoids the fixed plugin wait when task cookies are ready.",
    )
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--user-data-dir", default="./browser_profile/etax_compare_forms")
    parser.add_argument("--plugin-path", default=r"C:\Users\Administrator\Downloads\EtaxPlugin")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--poll-timeout", type=int, default=600)
    parser.add_argument("--browser-lock-timeout", type=int, default=3600)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    tax_nos = parse_tax_nos(args)
    if not tax_nos:
        raise SystemExit("Provide --tax-no or --tax-no-file.")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state = load_or_create_state(args, tax_nos, run_id, run_dir)
    write_state(state, run_dir)

    exit_code = 0
    if not args.skip_collect:
        exit_code = run_collect_stream(args, tax_nos, state, run_dir)
    else:
        LOGGER.info("Skipping collection phase; using existing state: %s", run_dir / "state.json")
        if args.verify:
            exit_code = run_verify_phase(args, tax_nos, state, run_dir, final=True)
    if args.verify and not args.skip_coverage_supplement:
        exit_code = max(exit_code, run_coverage_supplement_phase(args, state, run_dir))
    render_summary(state, run_dir)
    return exit_code


def load_or_create_state(args: argparse.Namespace, tax_nos: list[str], run_id: str, run_dir: Path) -> dict[str, Any]:
    state_path = run_dir / "state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    else:
        state = {
            "runId": run_id,
            "period": args.period,
            "enterprise": args.enterprise,
            "createdAt": datetime.now().isoformat(timespec="seconds"),
            "items": {},
        }
    state["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    state["period"] = args.period
    state["enterprise"] = args.enterprise
    for tax_no in tax_nos:
        state.setdefault("items", {}).setdefault(
            tax_no,
            {"taxNo": tax_no, "period": args.period, "collect": None, "verify": None},
        )
    return state


def write_state(state: dict[str, Any], run_dir: Path) -> None:
    state["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    state_path = run_dir / "state.json"
    summary_path = run_dir / "batch_summary.json"
    text = json.dumps(state, ensure_ascii=False, indent=2)
    safe_write_json_text(state_path, text)
    safe_write_json_text(summary_path, text)
    try:
        write_ops_status(state, run_dir)
    except Exception as exc:
        LOGGER.warning("Could not write ops status for %s: %s", run_dir, exc)


def safe_write_json_text(path: Path, text: str, attempts: int = 5) -> bool:
    """Write JSON through a temp file so status persistence cannot stop a batch run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{int(time.time() * 1000)}.{attempt}.tmp")
        try:
            json.loads(text)
            tmp_path.write_text(text, encoding="utf-8")
            json.loads(tmp_path.read_text(encoding="utf-8"))
            tmp_path.replace(path)
            return True
        except Exception as exc:
            last_exc = exc
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            time.sleep(min(0.2 * attempt, 1.0))
    LOGGER.warning("Could not write JSON file %s after %s attempts: %s", path, attempts, last_exc)
    return False


def set_item_stage(
    state: dict[str, Any],
    run_dir: Path,
    tax_no: str,
    stage: str,
    status: str = "",
    message: str = "",
    reason: str = "",
) -> None:
    item = state.setdefault("items", {}).setdefault(tax_no, {"taxNo": tax_no})
    previous = item.get("stage")
    item["stage"] = stage
    item["stageUpdatedAt"] = datetime.now().isoformat(timespec="seconds")
    if status:
        item["stageStatus"] = status
    if reason:
        item["stageReason"] = reason
    if previous != stage or message or reason:
        append_ops_event(
            run_dir,
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "runId": state.get("runId"),
                "taxNo": tax_no,
                "stage": stage,
                "stageName": OPS_STAGE_LABELS.get(stage, stage),
                "status": status or stage_status_for_item(item),
                "message": message,
                "reason": reason,
            },
        )


def append_ops_event(run_dir: Path, event: dict[str, Any]) -> None:
    events_path = run_dir / "ops_events.jsonl"
    try:
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        LOGGER.warning("Could not append ops event to %s: %s", events_path, exc)


def write_ops_status(state: dict[str, Any], run_dir: Path) -> None:
    status = build_ops_status(state)
    safe_write_json_text(run_dir / "ops_status.json", json.dumps(status, ensure_ascii=False, indent=2))


def build_ops_status(state: dict[str, Any]) -> dict[str, Any]:
    items = []
    for tax_no, item in sorted((state.get("items") or {}).items()):
        collect = item.get("collect") or {}
        verify = item.get("verify") or {}
        handling = derive_handling_info(item, collect, verify)
        account = collect.get("account") or {}
        area_code = str(account.get("areaCode") or "")[:2]
        stage = str(item.get("stage") or "queued")
        status = stage_status_for_item(item)
        reason = (
            item.get("stageReason")
            or handling.get("manualReason")
            or direct_verify_reason(verify)
            or direct_collect_failure_reason("; ".join(str(x) for x in collect.get("errors") or []))
        )
        action = handling.get("manualAction") or suggested_stage_action(stage, reason)
        items.append(
            {
                "taxNo": item.get("taxNo") or tax_no,
                "itemKey": tax_no,
                "period": item.get("period") or state.get("period") or "",
                "region": region_name(area_code),
                "custName": account.get("custName") or "",
                "stage": stage,
                "stageName": OPS_STAGE_LABELS.get(stage, stage),
                "status": status,
                "statusLabel": ops_status_label(status),
                "taskId": collect.get("verifyTaskId") or "",
                "collectStatus": collect.get("status") or "",
                "verifyStatus": verify.get("status") or "",
                "manualCategory": handling.get("manualCategory") or "",
                "reason": compact_message(reason),
                "action": action,
                "summaryPath": verify.get("summaryPath") or "",
                "updatedAt": item.get("stageUpdatedAt") or verify.get("updatedAt") or "",
            }
        )
    return {
        "runId": state.get("runId") or "",
        "period": state.get("period") or "",
        "enterprise": state.get("enterprise") or "",
        "status": overall_ops_status(items),
        "updatedAt": state.get("updatedAt") or datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }


def stage_status_for_item(item: dict[str, Any]) -> str:
    collect = item.get("collect") or {}
    verify = item.get("verify") or {}
    stage = str(item.get("stage") or "")
    if bool(collect.get("manualRequired")) or stage in {"collect_session_failed", "collect_failed", "collect_timeout", "task_unresolved"}:
        return "manual"
    verify_status = str(verify.get("status") or "")
    if verify_status == "success":
        return "success"
    if verify_status == "completed_with_differences":
        return "warning"
    if verify_status == "failed":
        return "failed"
    if verify_status == "skipped":
        return "skipped"
    if stage in {"verified", "collect_no_need"}:
        return "success"
    if stage:
        return "running"
    return "queued"


def ops_status_label(status: str) -> str:
    return {
        "queued": "排队中",
        "running": "进行中",
        "success": "完成",
        "warning": "有差异",
        "manual": "需人工",
        "failed": "失败",
        "skipped": "跳过",
    }.get(status, status or "未知")


def overall_ops_status(items: list[dict[str, Any]]) -> str:
    if any(item.get("status") == "running" for item in items):
        return "running"
    if any(item.get("status") == "manual" for item in items):
        return "manual"
    if any(item.get("status") == "failed" for item in items):
        return "failed"
    if any(item.get("status") == "warning" for item in items):
        return "warning"
    if items:
        return "success"
    return "queued"


def direct_verify_reason(verify: dict[str, Any]) -> str:
    reason = str(verify.get("reason") or "")
    if "Annual CIT A100000 declaration query returned no row" in reason:
        return "\u672a\u67e5\u5230 A100000 \u5e74\u62a5\u7533\u62a5\u8bb0\u5f55\uff0c\u9700\u6838\u5bf9\u7533\u62a5\u8868\u79cd\u7c7b\u3001\u7533\u62a5\u65e5\u671f\u548c\u7a0e\u6b3e\u6240\u5c5e\u671f\u6761\u4ef6\u3002"
    if "Tax bureau login timeout" in reason:
        return "税局登录超时。"
    if "Could not navigate to declaration query page" in reason:
        return "未能进入申报信息查询页。"
    if "登录失效" in reason or "数字账户" in reason:
        return "数字账户登录失效。"
    return reason


def suggested_stage_action(stage: str, reason: str) -> str:
    if "税局" in reason or "数字账户" in reason:
        return "完成税局登录后点击继续验证。"
    if stage == "task_unresolved":
        return "在后台任务列表确认是否生成取数任务，必要时重新发起取数。"
    if "易代账" in reason or "账号密码" in reason:
        return "填写易代账账号密码后重新发起取数。"
    return ""


def collect_failure_result(
    tax_no: str,
    period: str,
    enterprise: str,
    exc: Exception,
) -> YdzCollectResult:
    result = YdzCollectResult(
        tax_no=tax_no,
        period=period,
        enterprise=enterprise,
        manual_required=True,
        status="COLLECTED_FAIL",
    )
    result.errors.append(friendly_collect_exception(exc))
    return result


def friendly_collect_exception(exc: Exception) -> str:
    text = compact_message(exc, limit=260)
    lower_text = text.lower()
    if "ydz_username" in lower_text or "ydz_password" in lower_text:
        return (
            "\u6613\u4ee3\u8d26\u767b\u5f55\u6001\u7f3a\u5931\uff0c\u4e14\u672a\u8bbe\u7f6e "
            "YDZ_USERNAME/YDZ_PASSWORD\u3002\u8bf7\u5148\u767b\u5f55\u6216\u5728\u5f53\u524d\u7ec8\u7aef\u8bbe\u7f6e\u51ed\u636e\u540e\u91cd\u8bd5\u3002"
        )
    if (
        "api context is not ready" in lower_text
        or "did not reach the batch declaration page" in lower_text
        or "not inside the cloud application" in lower_text
    ):
        return (
            "\u6613\u4ee3\u8d26\u672a\u8fdb\u5165\u4e91\u7aef\u5e94\u7528\u7684\u6279\u91cf\u62a5\u7a0e\u9875\uff0c"
            "\u5f53\u524d\u53ef\u80fd\u505c\u7559\u5728\u5b98\u7f51\u6216\u767b\u5f55\u6001\u5df2\u5931\u6548\u3002"
            f"\u8be6\u60c5\uff1a{text}"
        )
    if "failed to fetch" in lower_text or "browser fetch failed" in lower_text:
        return (
            "\u6613\u4ee3\u8d26\u63a5\u53e3\u8bf7\u6c42\u5931\u8d25\uff0c\u901a\u5e38\u662f\u9875\u9762\u4e0d\u5728\u4e91\u7aef\u5e94\u7528\u3001"
            "\u767b\u5f55\u6001\u5931\u6548\u6216\u7f51\u7edc\u8bf7\u6c42\u88ab\u62e6\u622a\u3002"
            f"\u8be6\u60c5\uff1a{text}"
        )
    if "timed out waiting for yidaizhang login" in lower_text:
        return (
            "\u6613\u4ee3\u8d26\u767b\u5f55\u540e\u672a\u8fdb\u5165\u4f01\u4e1a\u9009\u62e9\u6216\u4e91\u7aef\u5e94\u7528\u9875\uff0c"
            f"\u8bf7\u68c0\u67e5\u662f\u5426\u9700\u8981\u9a8c\u8bc1\u7801\u6216\u624b\u5de5\u786e\u8ba4\u3002\u8be6\u60c5\uff1a{text}"
        )
    return text or str(type(exc).__name__)


def run_collect_phase(args: argparse.Namespace, tax_nos: list[str], state: dict[str, Any], run_dir: Path) -> None:
    username, password = get_env_credentials()
    submitted_results: dict[str, YdzCollectResult] = {}

    with ProcessLock(
        DEFAULT_TAX_BROWSER_LOCK,
        timeout=args.browser_lock_timeout,
        owner={"kind": "batch-ydz-collect", "runId": state["runId"], "period": args.period, "taxNos": tax_nos},
    ):
        session = YdzSession(
            cdp_port=args.cdp_port,
            user_data_dir=args.user_data_dir,
            plugin_path=args.plugin_path,
            launch_if_needed=True,
        )
        try:
            context = session.connect()
            page = session.ensure_ready(username=username, password=password, enterprise=args.enterprise)
            api = YdzApi(page)
            resolver = VerifyTaskResolver(context)
            collector = YdzCollector(
                api=api,
                enterprise=args.enterprise,
                poll_interval=args.poll_interval,
                poll_timeout=args.poll_timeout,
            )

            for tax_no in tax_nos:
                item = state["items"][tax_no]
                collect = item.get("collect") or {}
                if collect.get("verifyTaskId") and not args.force:
                    LOGGER.info("Skipping collection for %s; taskId already resolved: %s", tax_no, collect["verifyTaskId"])
                    continue
                LOGGER.info("Submitting Yidaizhang collection for %s/%s", tax_no, args.period)
                result = collector.submit_collect_tax_no(tax_no=tax_no, period=args.period, force=args.force)
                submitted_results[tax_no] = result
                item["collect"] = result.to_dict()
                set_item_stage(
                    state,
                    run_dir,
                    tax_no,
                    "collect_submitted" if result.submitted else "collect_checked",
                    status="running",
                    message="已提交取数任务。" if result.submitted else "已检查取数状态。",
                )
                write_state(state, run_dir)

            stream_collect_and_resolve_tasks(
                collector=collector,
                resolver=resolver,
                results=submitted_results,
                state=state,
                run_dir=run_dir,
                poll_interval=args.poll_interval,
                poll_timeout=args.poll_timeout,
            )
        finally:
            session.close()


def run_collect_stream(args: argparse.Namespace, tax_nos: list[str], state: dict[str, Any], run_dir: Path) -> int:
    if not args.skip_preflight:
        preflight_error = preflight_error_reason(args)
        if preflight_error:
            LOGGER.error("Batch preflight failed: %s", preflight_error)
            for tax_no in tax_nos:
                item = state["items"][tax_no]
                collect = item.get("collect") or {}
                if collect.get("verifyTaskId") and not args.force:
                    continue
                result = collect_failure_result(tax_no, args.period, args.enterprise, RuntimeError(preflight_error))
                item["collect"] = result.to_dict()
                set_item_stage(state, run_dir, tax_no, "collect_session_failed", status="manual", reason=preflight_error)
            write_state(state, run_dir)
            return 2

    results = submit_collect_batch(args, tax_nos, state, run_dir)
    deadline = time.time() + args.poll_timeout
    last_status = {tax_no: result.status for tax_no, result in results.items()}
    exit_code = 0

    while True:
        resolved_this_round = poll_and_resolve_once(args, tax_nos, results, state, run_dir, last_status)
        if args.verify and has_verifiable_items(
            tax_nos,
            state,
            rerun_verified=args.rerun_verified,
            verified_task_ids=verified_task_ids_this_run(args),
        ):
            exit_code = max(exit_code, run_verify_phase(args, tax_nos, state, run_dir, final=False))
        pending = pending_collect_results(results)
        if not pending:
            break
        if time.time() >= deadline:
            for tax_no, result in pending.items():
                result.manual_required = True
                result.errors.append(f"Timed out waiting for collection terminal status; last status={result.status}.")
                state["items"][tax_no]["collect"] = result.to_dict()
                set_item_stage(state, run_dir, tax_no, "collect_timeout", status="manual", reason="取数任务长时间未完成，当前仍为取数中。")
            write_state(state, run_dir)
            break
        if not resolved_this_round:
            time.sleep(args.poll_interval)

    if args.verify:
        exit_code = max(exit_code, run_verify_phase(args, tax_nos, state, run_dir, final=True))
    if any(result.manual_required for result in results.values()):
        exit_code = max(exit_code, 2)
    return exit_code


def preflight_error_reason(args: argparse.Namespace) -> str:
    urls = [
        ("后台任务接口", TASK_LIST_URL),
        ("易代账官网", "https://ydz.chanjet.com/?a=sztqwl&c=sztqwl"),
    ]
    for label, url in urls:
        try:
            request = urllib.request.Request(url, method="GET", headers={"User-Agent": "tax-verify-preflight"})
            with urllib.request.urlopen(request, timeout=8) as response:
                # HTTP 401/405 can still mean network and TLS are healthy. urlopen raises for many
                # 4xx/5xx responses, so reaching here is sufficient.
                response.read(1)
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                continue
            return f"{label}网络预检失败：http={exc.code}"
        except Exception as exc:
            text = compact_message(exc, limit=220)
            if is_proxy_like_network_error(text):
                return f"{label}网络预检失败，疑似代理/VPN或证书拦截导致：{text}。请关闭代理后重试。"
            return f"{label}网络预检失败：{text}"

    diagnostics: list[dict[str, Any]] = []
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{args.cdp_port}/json/version", timeout=3):
            pass
    except Exception:
        # Chrome can be launched later by YdzSession. CDP is therefore only a warning-level check.
        LOGGER.info("Chrome CDP is not active on port %s before collection; it will be launched if needed.", args.cdp_port)
    return ""


def is_proxy_like_network_error(text: str) -> bool:
    lower = str(text or "").lower()
    return any(
        keyword in lower
        for keyword in (
            "ssl",
            "eof",
            "certificate",
            "proxy",
            "tunnel",
            "connection reset",
            "forcibly closed",
            "handshake",
        )
    )


def submit_collect_batch(
    args: argparse.Namespace,
    tax_nos: list[str],
    state: dict[str, Any],
    run_dir: Path,
) -> dict[str, YdzCollectResult]:
    submitted_results: dict[str, YdzCollectResult] = {}
    try:
        with open_ydz_session(args, {"kind": "batch-ydz-submit", "runId": state["runId"], "period": args.period}) as (
            _session,
            _resolver,
            collector,
        ):
            for tax_no in tax_nos:
                item = state["items"][tax_no]
                collect = item.get("collect") or {}
                if collect.get("verifyTaskId") and not args.force:
                    LOGGER.info("Skipping collection for %s; taskId already resolved: %s", tax_no, collect["verifyTaskId"])
                    continue
                LOGGER.info("Submitting Yidaizhang collection for %s/%s", tax_no, args.period)
                try:
                    result = collector.submit_collect_tax_no(tax_no=tax_no, period=args.period, force=args.force)
                    set_item_stage(
                        state,
                        run_dir,
                        tax_no,
                        "collect_submitted" if result.submitted else "collect_checked",
                        status="running",
                        message="已提交取数任务。" if result.submitted else "已检查取数状态。",
                    )
                except Exception as exc:
                    LOGGER.error("Yidaizhang collection submit failed for %s/%s: %s", tax_no, args.period, exc)
                    result = collect_failure_result(tax_no, args.period, args.enterprise, exc)
                    set_item_stage(state, run_dir, tax_no, "collect_failed", status="manual", reason=friendly_collect_exception(exc))
                submitted_results[tax_no] = result
                item["collect"] = result.to_dict()
                write_state(state, run_dir)
    except Exception as exc:
        LOGGER.error(
            "Yidaizhang session is not ready; marking unresolved tax numbers as manual required: %s",
            exc,
        )
        for tax_no in tax_nos:
            item = state["items"][tax_no]
            collect = item.get("collect") or {}
            if collect.get("verifyTaskId") and not args.force:
                continue
            result = collect_failure_result(tax_no, args.period, args.enterprise, exc)
            submitted_results[tax_no] = result
            item["collect"] = result.to_dict()
            set_item_stage(state, run_dir, tax_no, "collect_session_failed", status="manual", reason=friendly_collect_exception(exc))
        write_state(state, run_dir)
    return submitted_results


class open_ydz_session:
    def __init__(self, args: argparse.Namespace, owner: dict[str, Any]) -> None:
        self.args = args
        self.owner = owner
        self.lock: ProcessLock | None = None
        self.session: YdzSession | None = None
        self.resolver: VerifyTaskResolver | None = None
        self.collector: YdzCollector | None = None

    def __enter__(self):
        username, password = get_env_credentials()
        self.lock = ProcessLock(
            DEFAULT_TAX_BROWSER_LOCK,
            timeout=self.args.browser_lock_timeout,
            owner=self.owner,
        ).acquire()
        try:
            self.session = YdzSession(
                cdp_port=self.args.cdp_port,
                user_data_dir=self.args.user_data_dir,
                plugin_path=self.args.plugin_path,
                launch_if_needed=True,
            )
            context = self.session.connect()
            page = self.session.ensure_ready(username=username, password=password, enterprise=self.args.enterprise)
            api = YdzApi(page)
            self.resolver = VerifyTaskResolver(context)
            self.collector = YdzCollector(
                api=api,
                enterprise=self.args.enterprise,
                poll_interval=self.args.poll_interval,
                poll_timeout=self.args.poll_timeout,
            )
            return self.session, self.resolver, self.collector
        except Exception:
            if self.session:
                self.session.close()
            if self.lock:
                self.lock.release()
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.session:
            self.session.close()
        if self.lock:
            self.lock.release()


def poll_and_resolve_once(
    args: argparse.Namespace,
    tax_nos: list[str],
    results: dict[str, YdzCollectResult],
    state: dict[str, Any],
    run_dir: Path,
    last_status: dict[str, str | None],
) -> bool:
    did_resolve = False
    if not has_collect_poll_work(results):
        return False
    try:
        with open_ydz_session(args, {"kind": "batch-ydz-poll", "runId": state["runId"], "period": args.period}) as (
            _session,
            resolver,
            collector,
        ):
            for tax_no in tax_nos:
                result = results.get(tax_no)
                if result is None:
                    continue
                if result.verify_task_id:
                    continue
                if result.submitted and not result.terminal and not result.manual_required:
                    try:
                        collector.refresh_collect_status(result)
                    except Exception as exc:
                        LOGGER.warning("Could not refresh Yidaizhang status for %s/%s: %s", tax_no, result.period, exc)
                        append_unique(result.warnings, friendly_collect_exception(exc))
                        state["items"][tax_no]["collect"] = result.to_dict()
                        set_item_stage(state, run_dir, tax_no, "collect_poll_retry", status="running", reason=friendly_collect_exception(exc))
                        continue
                    if result.status != last_status.get(tax_no):
                        LOGGER.info(
                            "Yidaizhang collection status changed for %s: %s -> %s",
                            tax_no,
                            last_status.get(tax_no),
                            result.status,
                        )
                        last_status[tax_no] = result.status
                    state["items"][tax_no]["collect"] = result.to_dict()
                    set_item_stage(state, run_dir, tax_no, "collect_poll_retry", status="running", message=f"当前取数状态：{result.status}")
                if is_result_ready_for_task_resolution(result):
                    before = result.verify_task_id
                    resolve_task_id_for_result(resolver, tax_no, result, state, run_dir)
                    did_resolve = did_resolve or bool(result.verify_task_id and result.verify_task_id != before)
                elif str(result.status or "").upper() == "NO_NEED_COLLECTED":
                    set_item_stage(state, run_dir, tax_no, "collect_no_need", status="success", message="本期无需取数。")
                elif result.terminal:
                    set_item_stage(state, run_dir, tax_no, "collect_terminal", status="running", message=f"取数终态：{result.status}")
            write_state(state, run_dir)
    except Exception as exc:
        LOGGER.warning("Could not open Yidaizhang session while polling; will retry until timeout: %s", exc)
        for tax_no, result in pending_collect_results(results).items():
            append_unique(result.warnings, friendly_collect_exception(exc))
            state["items"][tax_no]["collect"] = result.to_dict()
            set_item_stage(state, run_dir, tax_no, "collect_poll_retry", status="running", reason=friendly_collect_exception(exc))
        write_state(state, run_dir)
    return did_resolve


def pending_collect_results(results: dict[str, YdzCollectResult]) -> dict[str, YdzCollectResult]:
    return {
        tax_no: result
        for tax_no, result in results.items()
        if result.submitted and not result.terminal and not result.manual_required
    }


def has_collect_poll_work(results: dict[str, YdzCollectResult]) -> bool:
    for result in results.values():
        if result.verify_task_id:
            continue
        if result.submitted and not result.terminal and not result.manual_required:
            return True
        if is_result_ready_for_task_resolution(result):
            return True
    return False


def verified_task_ids_this_run(args: argparse.Namespace) -> set[str]:
    task_ids = getattr(args, "_verified_task_ids_this_run", None)
    if task_ids is None:
        task_ids = set()
        setattr(args, "_verified_task_ids_this_run", task_ids)
    return task_ids


def mark_task_id_verified_this_run(args: argparse.Namespace, task_id: str) -> None:
    if task_id:
        verified_task_ids_this_run(args).add(str(task_id))


def has_verifiable_items(
    tax_nos: list[str],
    state: dict[str, Any],
    rerun_verified: bool = False,
    verified_task_ids: set[str] | None = None,
) -> bool:
    verified_task_ids = verified_task_ids or set()
    for tax_no in tax_nos:
        item = state["items"].get(tax_no) or {}
        collect = item.get("collect") or {}
        verify = item.get("verify") or {}
        task_id = str(collect.get("verifyTaskId") or "")
        if task_id and task_id not in verified_task_ids and (rerun_verified or not verify.get("status")):
            return True
    return False


def stream_collect_and_resolve_tasks(
    collector: YdzCollector,
    resolver: VerifyTaskResolver,
    results: dict[str, YdzCollectResult],
    state: dict[str, Any],
    run_dir: Path,
    poll_interval: int,
    poll_timeout: int,
) -> None:
    pending = {
        tax_no: result
        for tax_no, result in results.items()
        if result.submitted and not result.terminal and not result.manual_required
    }
    ready = {
        tax_no: result
        for tax_no, result in results.items()
        if tax_no not in pending and is_result_ready_for_task_resolution(result)
    }
    for tax_no, result in ready.items():
        resolve_task_id_for_result(resolver, tax_no, result, state, run_dir)

    deadline = time.time() + poll_timeout
    last_status = {tax_no: result.status for tax_no, result in pending.items()}
    while pending and time.time() < deadline:
        for tax_no, result in list(pending.items()):
            collector.refresh_collect_status(result)
            if result.status != last_status.get(tax_no):
                LOGGER.info("Yidaizhang collection status changed for %s: %s -> %s", tax_no, last_status.get(tax_no), result.status)
                last_status[tax_no] = result.status
            state["items"][tax_no]["collect"] = result.to_dict()
            if result.status in TERMINAL_COLLECT_STATUSES or result.manual_required:
                pending.pop(tax_no, None)
                if is_result_ready_for_task_resolution(result):
                    resolve_task_id_for_result(resolver, tax_no, result, state, run_dir)
                elif str(result.status or "").upper() == "NO_NEED_COLLECTED":
                    set_item_stage(state, run_dir, tax_no, "collect_no_need", status="success", message="本期无需取数。")
                else:
                    set_item_stage(
                        state,
                        run_dir,
                        tax_no,
                        "collect_manual_required" if result.manual_required else "collect_terminal",
                        status="manual" if result.manual_required else "running",
                    )
        write_state(state, run_dir)
        if pending:
            time.sleep(poll_interval)

    for tax_no, result in pending.items():
        result.manual_required = True
        result.errors.append(f"Timed out waiting for collection terminal status; last status={result.status}.")
        state["items"][tax_no]["collect"] = result.to_dict()
        set_item_stage(state, run_dir, tax_no, "collect_timeout", status="manual", reason="取数任务长时间未完成，当前仍为取数中。")
    if pending:
        write_state(state, run_dir)


def is_result_ready_for_task_resolution(result: YdzCollectResult) -> bool:
    if result.verify_task_id:
        return False
    if str(result.status or "").upper() == "NO_NEED_COLLECTED":
        return False
    if result.manual_required and not result.submitted:
        return False
    return bool(result.terminal or result.status in TERMINAL_COLLECT_STATUSES)


def resolve_task_id_for_result(
    resolver: VerifyTaskResolver,
    tax_no: str,
    result: YdzCollectResult,
    state: dict[str, Any],
    run_dir: Path,
) -> None:
    if result.verify_task_id:
        return
    try:
        result.verify_task_id = resolver.resolve(result.tax_no, result.period, submitted_at=result.submitted_at)
        if resolver.last_task:
            result.resolved_task = {
                "taskId": resolver.last_task.task_id,
                "taskTypeId": resolver.last_task.task_type_id,
                "taskTypeName": resolver.last_task.task_type_name,
                "status": resolver.last_task.status,
                "period": resolver.last_task.period,
                "createdStamp": resolver.last_task.created_stamp,
            }
    except Exception as exc:
        LOGGER.warning("Could not resolve collect taskId for %s/%s: %s", result.tax_no, result.period, exc)
        result.warnings.append(f"Could not resolve collect taskId: {exc}")
    state["items"][tax_no]["collect"] = result.to_dict()
    set_item_stage(
        state,
        run_dir,
        tax_no,
        "task_resolved" if result.verify_task_id else "task_unresolved",
        status="running" if result.verify_task_id else "manual",
        message=f"已解析 taskId：{result.verify_task_id}" if result.verify_task_id else "",
        reason="" if result.verify_task_id else "后台未解析到取数 taskId。",
    )
    write_state(state, run_dir)


def resolve_task_ids(
    resolver: VerifyTaskResolver,
    results: dict[str, YdzCollectResult],
    state: dict[str, Any],
    run_dir: Path,
) -> None:
    for tax_no, result in results.items():
        if result.verify_task_id:
            continue
        try:
            result.verify_task_id = resolver.resolve(result.tax_no, result.period, submitted_at=result.submitted_at)
            if resolver.last_task:
                result.resolved_task = {
                    "taskId": resolver.last_task.task_id,
                    "taskTypeId": resolver.last_task.task_type_id,
                    "taskTypeName": resolver.last_task.task_type_name,
                    "status": resolver.last_task.status,
                    "period": resolver.last_task.period,
                    "createdStamp": resolver.last_task.created_stamp,
                }
        except Exception as exc:
            LOGGER.warning("Could not resolve collect taskId for %s/%s: %s", result.tax_no, result.period, exc)
            result.warnings.append(f"Could not resolve collect taskId: {exc}")
        state["items"][tax_no]["collect"] = result.to_dict()
        set_item_stage(
            state,
            run_dir,
            tax_no,
            "task_resolved" if result.verify_task_id else "task_unresolved",
            status="running" if result.verify_task_id else "manual",
            message=f"已解析 taskId：{result.verify_task_id}" if result.verify_task_id else "",
            reason="" if result.verify_task_id else "后台未解析到取数 taskId。",
        )
        write_state(state, run_dir)


def run_verify_phase(
    args: argparse.Namespace,
    tax_nos: list[str],
    state: dict[str, Any],
    run_dir: Path,
    final: bool = False,
) -> int:
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    exit_code = 0

    for tax_no in tax_nos:
        item = state["items"][tax_no]
        collect = item.get("collect") or {}
        task_id = collect.get("verifyTaskId")
        if not task_id:
            if not final:
                continue
            no_need_collect = str(collect.get("status") or "").upper() == "NO_NEED_COLLECTED"
            item["verify"] = {
                "status": "skipped",
                "reason": no_task_skip_reason(item),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            if no_need_collect:
                set_item_stage(state, run_dir, tax_no, "collect_no_need", status="success", message="本期无需取数。")
            write_state(state, run_dir)
            if not no_need_collect:
                exit_code = max(exit_code, 2)
            continue

        existing_verify = item.get("verify") or {}
        if str(task_id) in verified_task_ids_this_run(args):
            LOGGER.info("Skipping verification for %s taskId=%s; already verified in this batch run", tax_no, task_id)
            duplicate_reason = "同一批次已验证相同 taskId，已跳过重复执行。"
            if not existing_verify.get("status"):
                item["verify"] = {
                    "status": "skipped",
                    "returnCode": 0,
                    "reason": duplicate_reason,
                    "reportDir": str(Path("output") / "reports" / task_id),
                    "summaryPath": "",
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
                set_item_stage(
                    state,
                    run_dir,
                    tax_no,
                    "verified",
                    status="skipped",
                    reason=duplicate_reason,
                )
                write_state(state, run_dir)
            continue
        if existing_verify.get("status") and not args.rerun_verified:
            LOGGER.info("Skipping verification for %s; already recorded status=%s", tax_no, existing_verify["status"])
            continue

        if bool(collect.get("manualRequired")):
            reason = collect_failure_reason(collect) or "Collection requires manual handling; verification was skipped."
            item["verify"] = {
                "status": "skipped",
                "returnCode": 2,
                "reason": reason,
                "reportDir": str(Path("output") / "reports" / task_id),
                "summaryPath": "",
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            set_item_stage(state, run_dir, tax_no, "skipped", status="manual", reason=reason)
            write_state(state, run_dir)
            exit_code = max(exit_code, 2)
            continue

        LOGGER.info("Running verification for %s taskId=%s", tax_no, task_id)
        set_item_stage(state, run_dir, tax_no, "verifying", status="running", message=f"开始验证 taskId={task_id}")
        write_state(state, run_dir)
        stdout_path = logs_dir / f"{tax_no}_{task_id}.out.log"
        stderr_path = logs_dir / f"{tax_no}_{task_id}.err.log"
        cbj_kind = ""
        if item_requests_cbj_verification(item):
            cbj_kind = detect_cbj_task(task_id) or "cbj"
        report_dir = Path("output") / "reports" / task_id
        reused_result = reuse_existing_verify_result(args, task_id, cbj_kind)
        if reused_result:
            item["verify"] = {
                **reused_result,
                "reportDir": str(report_dir),
                "stdoutLog": str(stdout_path),
                "stderrLog": str(stderr_path),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            set_item_stage(
                state,
                run_dir,
                tax_no,
                "verified",
                status="success" if reused_result["returnCode"] == 0 else "warning",
                message="Reused existing verification report.",
            )
            write_state(state, run_dir)
            exit_code = max(exit_code, reused_result["returnCode"])
            mark_task_id_verified_this_run(args, str(task_id))
            continue
        if cbj_kind:
            cbj_mode = resolve_cbj_mode(args.cbj_mode, item)
            LOGGER.info("Detected CBJ task for %s taskId=%s; mode=%s resolvedMode=%s", tax_no, task_id, args.cbj_mode, cbj_mode)
            verify_result = run_cbj_verify(args, task_id, stdout_path, stderr_path, cbj_mode)
            item["verify"] = {
                "status": verify_result["status"],
                "returnCode": verify_result["returnCode"],
                "mode": verify_result["mode"],
                "reason": verify_result.get("reason", ""),
                "reportDir": str(Path("output") / "reports" / task_id),
                "summaryPath": verify_result.get("summaryPath", ""),
                "reportPath": verify_result.get("reportPath", ""),
                "stdoutLog": str(stdout_path),
                "stderrLog": str(stderr_path),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            set_item_stage(state, run_dir, tax_no, "verified", status="success" if verify_result["returnCode"] == 0 else "warning", message="残保金验证完成。")
            write_state(state, run_dir)
            exit_code = max(exit_code, verify_result["returnCode"])
            mark_task_id_verified_this_run(args, str(task_id))
            continue

        cmd = [
            sys.executable,
            "main.py",
            "--task-id",
            task_id,
            "--targets",
            args.targets,
            "--cdp-port",
            str(args.cdp_port),
            "--user-data-dir",
            args.user_data_dir,
            "--plugin-path",
            args.plugin_path,
            "--log-level",
            args.log_level,
            "--tax-timeout",
            str(args.tax_timeout),
            "--tax-login-strategy",
            args.tax_login_strategy,
            "--browser-lock-timeout",
            str(args.browser_lock_timeout),
        ]
        if args.skip_browser:
            cmd.append("--skip-browser")
        if args.skip_pdf:
            cmd.append("--skip-pdf")

        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            proc = subprocess.run(cmd, stdout=stdout, stderr=stderr)

        summary_path = latest_summary_path(report_dir)
        if summary_path:
            status = "success" if proc.returncode == 0 else "completed_with_differences"
            return_code = proc.returncode
            stage_status = "success" if proc.returncode == 0 else "warning"
            reason = "" if proc.returncode == 0 else compare_report_reason(task_id) or tail_error_reason(stderr_path)
        elif proc.returncode == 0:
            status = "skipped"
            return_code = 2
            stage_status = "manual"
            reason = no_targets_verify_reason(stdout_path, stderr_path)
        else:
            reason = tail_error_reason(stderr_path) or tail_error_reason(stdout_path)
            if is_no_targets_verify_reason(reason):
                status = "skipped"
                stage_status = "manual"
            else:
                status = "failed"
                stage_status = "failed"
            return_code = proc.returncode
        item["verify"] = {
            "status": status,
            "returnCode": return_code,
            "reason": reason,
            "reportDir": str(report_dir),
            "summaryPath": str(summary_path) if summary_path else "",
            "stdoutLog": str(stdout_path),
            "stderrLog": str(stderr_path),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        set_item_stage(
            state,
            run_dir,
            tax_no,
            "verified",
            status=stage_status,
            message="验证完成。",
            reason=reason,
        )
        write_state(state, run_dir)
        exit_code = max(exit_code, return_code)
        mark_task_id_verified_this_run(args, str(task_id))

    return exit_code


def run_coverage_supplement_phase(args: argparse.Namespace, state: dict[str, Any], run_dir: Path) -> int:
    coverage = write_coverage_status(run_dir)
    missing_rows = coverage.get("missingTargets") or []
    if not missing_rows:
        state["coverageSupplement"] = {
            "status": "not_needed",
            "message": "当前批次已覆盖全部目标。",
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 0

    targets_by_key = {target.key: target for target in build_coverage_targets()}
    missing_keys = {str(row.get("key") or "") for row in missing_rows}
    missing_targets = [target for key, target in targets_by_key.items() if key in missing_keys]
    if not missing_targets:
        state["coverageSupplement"] = {
            "status": "failed",
            "message": "覆盖缺口无法映射到当前支持税种目标。",
            "missingKeys": sorted(missing_keys),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 2

    start_time = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_time = datetime.now()
    LOGGER.info(
        "Searching backend supplement tasks for %s missing coverage target(s): %s",
        len(missing_targets),
        ", ".join(target.key for target in missing_targets),
    )
    state["coverageSupplement"] = {
        "status": "searching",
        "message": "正在后台查询未覆盖税种/申报状态的代表取数任务。",
        "missingKeys": [target.key for target in missing_targets],
        "startTime": start_time.isoformat(timespec="seconds"),
        "endTime": end_time.isoformat(timespec="seconds"),
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    write_state(state, run_dir)

    try:
        with ProcessLock(
            DEFAULT_TAX_BROWSER_LOCK,
            timeout=args.browser_lock_timeout,
            owner={"kind": "coverage-supplement", "runId": state["runId"], "period": args.period},
        ):
            session = YdzSession(
                cdp_port=args.cdp_port,
                user_data_dir=args.user_data_dir,
                plugin_path=args.plugin_path,
                launch_if_needed=True,
            )
            try:
                context = session.connect()
                planner = CoverageSupplementPlanner(ChanjetAdminTaskQuery(context))
                candidates = planner.find_candidates(
                    missing_targets,
                    start_time=start_time,
                    end_time=end_time,
                    page_size=args.coverage_supplement_page_size,
                )
                diagnostics = planner.last_diagnostics
            finally:
                session.close()
    except Exception as exc:
        message = f"后台补齐查询失败：{compact_message(exc, limit=260)}"
        LOGGER.warning(message)
        state["coverageSupplement"] = {
            "status": "failed",
            "message": message,
            "missingKeys": [target.key for target in missing_targets],
            "diagnostics": diagnostics,
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 2

    if not candidates:
        message = "后台未找到符合缺口税种和申报状态的成功取数任务。"
        LOGGER.info(message)
        state["coverageSupplement"] = {
            "status": "no_candidates",
            "message": message,
            "missingKeys": [target.key for target in missing_targets],
            "diagnostics": diagnostics,
            "candidateCount": 0,
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 0

    applied_keys = apply_supplement_candidates_to_state(state, candidates, enterprise=args.enterprise)
    state["coverageSupplement"] = {
        "status": "applied" if applied_keys else "not_applied",
        "message": f"已从后台补齐 {len(applied_keys)} 个代表任务。" if applied_keys else "找到候选任务，但未写入新的待验证项。",
        "missingKeys": [target.key for target in missing_targets],
        "diagnostics": diagnostics,
        "candidateCount": len(candidates),
        "appliedItemKeys": applied_keys,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    for item_key in applied_keys:
        item = state["items"].get(item_key) or {}
        task_id = ((item.get("collect") or {}).get("verifyTaskId")) or ""
        set_item_stage(
            state,
            run_dir,
            item_key,
            "task_resolved",
            status="running",
            message=f"后台补齐 taskId：{task_id}" if task_id else "后台补齐待验证任务。",
        )
    write_state(state, run_dir)
    if not applied_keys:
        return 0

    verify_exit = run_verify_phase(args, applied_keys, state, run_dir, final=True)
    state["coverageSupplement"]["status"] = "verified"
    state["coverageSupplement"]["verifyExitCode"] = verify_exit
    state["coverageSupplement"]["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    write_state(state, run_dir)
    return verify_exit


def detect_cbj_task(task_id: str) -> str:
    try:
        fields, response = fetch_backend_fields(task_id)
    except Exception as exc:
        LOGGER.info("Task %s is not ready for CBJ detection: %s", task_id, exc)
        return ""
    has_cbj_payload = bool((response.get("raw_resultJson") or {}).get("sz_cbj") or (response.get("data") or {}).get("sz_cbj"))
    has_cbj_fields = all(field.present for field in fields.values())
    return "cbj" if has_cbj_payload or has_cbj_fields else ""


def run_cbj_verify(
    args: argparse.Namespace,
    task_id: str,
    stdout_path: Path,
    stderr_path: Path,
    requested_mode: str | None = None,
) -> dict[str, Any]:
    report_path: Path | None = None
    mode = requested_mode or args.cbj_mode
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                if mode == "backend" or args.skip_browser:
                    report_path = verify_personal_cbj(task_id)
                    mode = "backend"
                elif mode == "annual":
                    report_path = verify_annual_settlement_cbj(task_id, cbj_browser_args(args))
                    mode = "annual"
                else:
                    try:
                        report_path = verify_annual_settlement_cbj(task_id, cbj_browser_args(args))
                        mode = "annual"
                    except Exception as exc:
                        if is_cbj_annual_no_row_error(exc):
                            raise RuntimeError(
                                "汇算清缴残保金未在税局查到年度申报记录；未自动回退后台字段校验。"
                            ) from exc
                        else:
                            raise
            except Exception as exc:
                LOGGER.exception("CBJ verification failed for taskId=%s", task_id)
                return {
                    "status": "failed",
                    "returnCode": 2,
                    "mode": mode,
                    "reason": str(exc),
                }
    if report_path is None:
        return {"status": "failed", "returnCode": 2, "mode": mode}
    has_errors = report_has_errors(report_path)
    summary_path = latest_cbj_summary_path(Path("output") / "reports" / task_id)
    return {
        "status": "completed_with_differences" if has_errors else "success",
        "returnCode": 1 if has_errors else 0,
        "mode": mode,
        "reportPath": str(report_path),
        "summaryPath": str(summary_path) if summary_path else "",
    }


def cbj_browser_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        cdp_port=args.cdp_port,
        mode="auto",
        user_data_dir=args.user_data_dir,
        plugin_path=args.plugin_path,
        chanjet_timeout=300,
        tax_timeout=args.tax_timeout,
        tax_login_strategy=args.tax_login_strategy,
        config_root="config",
        query_year=args.query_year,
    )


def resolve_cbj_mode(configured_mode: str, item: dict[str, Any]) -> str:
    if configured_mode != "auto":
        return configured_mode
    collect = item.get("collect") or {}
    text_parts: list[str] = [str(item.get("taxNo") or "")]
    account = collect.get("account") or {}
    text_parts.append(str(account.get("custName") or ""))
    for target in item.get("coverageSupplementTargets") or []:
        text_parts.append(str(target))
    for tax_item in collect.get("taxItems") or []:
        tax_type_id = str(tax_item.get("taxTypeId") or "")
        text_parts.append(tax_type_id)
        text_parts.extend(str(tax_item.get(key) or "") for key in ("taxTypeName", "taxName", "name", "message"))
        if tax_type_id == "31" and is_active_cbj_tax_item(tax_item):
            return "annual"
    combined = " ".join(text_parts)
    if "CBJ_ANNUAL" in combined:
        return "annual"
    if "CBJ_PERSONAL" in combined:
        return "backend"
    if any(keyword in combined for keyword in ("汇算清缴", "企业所得税年度", "A100000", "annual_settlement")):
        return "annual"
    if any(keyword in combined for keyword in ("个税", "个人所得税")):
        return "backend"
    for tax_item in collect.get("taxItems") or []:
        if str(tax_item.get("taxTypeId") or "") == "26" and is_active_cbj_tax_item(tax_item):
            return "backend"
    return "annual"


def item_requests_cbj_verification(item: dict[str, Any]) -> bool:
    for target in item.get("coverageSupplementTargets") or []:
        if str(target).startswith("CBJ_") or str(target).startswith("CBJ:"):
            return True
    collect = item.get("collect") or {}
    resolved = collect.get("resolvedTask") or {}
    if str(resolved.get("backendTaxTypeId") or "") in {"26", "31"}:
        return True
    for tax_item in collect.get("taxItems") or []:
        if str(tax_item.get("taxTypeId") or "") in {"26", "31"} and is_active_cbj_tax_item(tax_item):
            return True
    return False


def is_active_cbj_tax_item(tax_item: dict[str, Any]) -> bool:
    init_status = str(tax_item.get("initStatusEnum") or "").upper()
    status = str(tax_item.get("status") or "").upper()
    return init_status in {"COLLECTED", "COLLECTED_PART"} or status in {"SUCCESS", "SUCCEEDED"}


def is_cbj_annual_no_row_error(exc: Exception) -> bool:
    message = str(exc)
    return "Annual CIT A100000 declaration query returned no row" in message


def latest_cbj_summary_path(report_dir: Path) -> Path | None:
    if not report_dir.exists():
        return None
    summaries = sorted(report_dir.glob("cbj_summary_*.html"), key=lambda path: path.stat().st_mtime, reverse=True)
    return summaries[0] if summaries else None


def latest_summary_path(report_dir: Path) -> Path | None:
    if not report_dir.exists():
        return None
    summaries = sorted(report_dir.glob("compare_summary_*.html"), key=lambda path: path.stat().st_mtime, reverse=True)
    return summaries[0] if summaries else None


def reuse_existing_verify_result(args: argparse.Namespace, task_id: str, cbj_kind: str = "") -> dict[str, Any] | None:
    if not getattr(args, "reuse_existing_report", False):
        return None
    report_dir = Path("output") / "reports" / task_id
    summary_path = latest_cbj_summary_path(report_dir) if cbj_kind else latest_summary_path(report_dir)
    if not summary_path:
        return None
    has_errors = any_report_has_errors(load_compare_reports(task_id))
    return {
        "status": "completed_with_differences" if has_errors else "success",
        "returnCode": 1 if has_errors else 0,
        "reason": "Reused existing report for this taskId.",
        "summaryPath": str(summary_path),
        "reportPath": "",
        "reused": True,
    }


def no_targets_verify_reason(stdout_path: Path, stderr_path: Path) -> str:
    reason = tail_error_reason(stderr_path) or tail_error_reason(stdout_path)
    if reason:
        return reason
    return "No supported compare target was selected from backend API data; verification was skipped instead of treated as success."


def is_no_targets_verify_reason(reason: str) -> bool:
    text = str(reason or "")
    return "No compare targets selected" in text or "No compare targets have API field coverage" in text


def any_report_has_errors(reports: list[dict[str, Any]]) -> bool:
    for report in reports:
        summary = report.get("summary") or {}
        for key in ("mismatch_count", "api_missing_count", "web_missing_count", "parse_error_count", "mapping_error_count"):
            try:
                if int(summary.get(key, 0) or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def compare_report_reason(task_id: str, max_forms: int = 4) -> str:
    issue_labels = [
        ("mismatch_count", "\u4e0d\u4e00\u81f4"),
        ("api_missing_count", "\u63a5\u53e3\u7f3a\u5931"),
        ("web_missing_count", "\u7f51\u9875\u7f3a\u5931"),
        ("parse_error_count", "\u89e3\u6790\u5931\u8d25"),
        ("mapping_error_count", "\u6620\u5c04\u5f02\u5e38"),
    ]
    parts: list[str] = []
    for report in load_compare_reports(task_id):
        summary = report.get("summary") or {}
        issues = []
        for key, label in issue_labels:
            try:
                count = int(summary.get(key, 0) or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                issues.append(f"{label}{count}")
        if not issues:
            continue
        form_name = (
            report.get("form_name")
            or report.get("formName")
            or report.get("target_id")
            or report.get("form_id")
            or "\u672a\u77e5\u8868\u5355"
        )
        parts.append(f"{form_name}: " + "\u3001".join(issues))
    if not parts:
        return ""
    suffix = "" if len(parts) <= max_forms else f"\uff1b\u53e6\u6709{len(parts) - max_forms}\u5f20\u8868\u5b58\u5728\u95ee\u9898"
    return "\uff1b".join(parts[:max_forms]) + suffix


def tail_error_reason(log_path: Path, max_lines: int = 80) -> str:
    if not log_path.exists():
        return ""
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    for line in reversed(lines[-max_lines:]):
        text = line.strip()
        if not text:
            continue
        if is_benign_verify_log_line(text):
            continue
        if text.startswith(("RuntimeError:", "TimeoutError:", "ValueError:", "KeyError:", "FileNotFoundError:")):
            return text
    for line in reversed(lines[-max_lines:]):
        text = line.strip()
        if text and not is_benign_verify_log_line(text):
            return text[:500]
    return ""


def is_benign_verify_log_line(text: str) -> bool:
    markers = (
        "Playwright stopped",
        "Disconnected from Chrome",
        "[DEP0169] DeprecationWarning",
        "Use `node --trace-deprecation",
    )
    if any(marker in text for marker in markers):
        return True
    return bool(re.search(r"\bINFO\s+src\.login\.browser_manager:", text))


def no_task_skip_reason(item: dict[str, Any]) -> str:
    collect = item.get("collect") or {}
    handling = derive_handling_info(item, collect, {})
    category = handling.get("manualCategory") or "未获取taskId"
    reason = handling.get("manualReason") or "未在后台任务列表解析到取数 taskId。"
    return f"{category}: {reason}"


def derive_handling_info(
    item: dict[str, Any],
    collect: dict[str, Any],
    verify: dict[str, Any],
) -> dict[str, str]:
    collect_status = str(collect.get("status") or "").upper()
    verify_status = str(verify.get("status") or "")
    risks = verification_risks(verify)
    risk_reason = "；".join(risks[:3])

    category = ""
    reason = ""
    action = ""

    if collect_status == "NO_NEED_COLLECTED":
        category = "无需取数"
        reason = no_need_collect_reason(collect)
        action = "按未申报或无需申报记录，不等待 taskId。"
    elif bool(collect.get("manualRequired")):
        category = "需人工介入"
        reason = collect_failure_reason(collect) or "取数流程未自动完成。"
        action = suggested_manual_action(reason, collect_status)
    elif not collect.get("verifyTaskId") and verify_status == "skipped":
        category = "未获取taskId"
        reason = collect_failure_reason(collect) or str(verify.get("reason") or "") or "后台未解析到取数任务。"
        action = "在任务列表按税号、期间、任务类型“取数”确认是否生成成功任务。"
    elif verify_status == "skipped":
        category = "未覆盖"
        reason = str(verify.get("reason") or "") or "当前 taskId 没有自动选出项目已支持的可验证表单。"
        action = "确认该任务是否包含当前项目支持的税种、申报状态和接口字段；如需覆盖新税种，先补映射和解析规则。"
    elif verify_status == "failed":
        category = "验证失败"
        reason = direct_verify_reason(verify) or str(verify.get("reason") or "") or risk_reason or "验证命令执行失败。"
        action = "查看错误日志并重新进入税局验证。"
    elif risk_reason:
        category = "验证风险"
        reason = risk_reason
        action = "人工复核对应表单截图、网页字段解析和页面打开逻辑。"

    return {
        "manualCategory": category,
        "manualReason": compact_message(reason),
        "manualAction": action,
        "riskReason": risk_reason,
    }


def collect_failure_reason(collect: dict[str, Any]) -> str:
    candidates: list[str] = []
    for error in collect.get("errors") or []:
        if is_social_insurance_collect_message(error):
            continue
        reason = direct_collect_failure_reason(error)
        if reason:
            candidates.append(reason)

    for tax_item in collect.get("taxItems") or []:
        init_status = str(tax_item.get("initStatusEnum") or "").upper()
        status = str(tax_item.get("status") or "").upper()
        message = compact_message(tax_item.get("message"))
        if is_social_insurance_tax_item(tax_item) or is_social_insurance_collect_message(message):
            continue
        failed = init_status == "COLLECTED_FAIL" or status in {"FAILURE", "FAILED", "FAIL"}
        if not failed and not is_actionable_collect_message(message):
            continue
        reason = direct_collect_failure_reason(message, tax_item_display_name(tax_item))
        if reason:
            candidates.append(reason)
        elif failed:
            candidates.append(f"{tax_item_display_name(tax_item)}取数失败")

    for warning in collect.get("warnings") or []:
        if is_social_insurance_collect_message(warning):
            continue
        if not is_actionable_collect_message(warning):
            continue
        reason = direct_collect_failure_reason(warning)
        if reason:
            candidates.append(reason)

    return choose_collect_failure_reason(candidates)


def is_social_insurance_collect_message(value: Any) -> bool:
    text = str(value or "")
    return "社会保险费" in text or "social insurance" in text.lower()


def is_social_insurance_tax_item(item: dict[str, Any]) -> bool:
    try:
        tax_type_id = int(item.get("taxTypeId"))
    except (TypeError, ValueError):
        tax_type_id = None
    return tax_type_id == 40 or is_social_insurance_collect_message(tax_item_display_name(item))


def direct_collect_failure_reason(value: Any, tax_name: str = "") -> str:
    text = compact_message(value)
    if not text or is_post_submit_collect_notice(text):
        return ""
    lower_text = text.lower()
    if "timed out waiting for collection terminal status" in lower_text:
        return "取数任务长时间未完成，当前仍为取数中。"
    if "no yidaizhang account matched" in lower_text or "no account" in lower_text:
        return "未匹配到易代账账套。"
    if "failed to resolve verify task id" in lower_text or "未解析到取数" in text:
        return "后台未解析到取数 taskId。"
    if "needforcetax" in lower_text:
        return "税局强制登录或验证码阻塞。"
    if "社会保险费" in text or "social insurance" in lower_text:
        return "社会保险费不支持取数。"
    if "个人账号或密码错误" in text or ("账号" in text and "密码" in text and "错误" in text):
        return "税局个人账号或密码错误。"
    if "正在执行取数任务" in text or "请勿重复提交" in text:
        return "已有取数任务正在执行，请等待完成后再重试。"
    if "授权" in text or "authorization" in lower_text:
        return "账套授权未完成。"
    if "可以发起的期间范围" in text or ("期间" in text and "范围" in text):
        return text
    if tax_name and ("失败" in text or "错误" in text or "不支持" in text):
        return f"{tax_name}取数失败：{text}"
    return text


def is_actionable_collect_message(value: Any) -> bool:
    text = compact_message(value)
    if not text or is_post_submit_collect_notice(text):
        return False
    return any(
        keyword in text
        for keyword in (
            "失败",
            "错误",
            "不支持",
            "授权",
            "社会保险费",
            "个人账号或密码",
            "正在执行取数任务",
            "请勿重复提交",
            "可以发起的期间范围",
            "未解析到取数",
        )
    )


def is_post_submit_collect_notice(value: Any) -> bool:
    text = compact_message(value)
    if not text:
        return True
    if any(
        keyword in text
        for keyword in (
            "失败",
            "错误",
            "不支持",
            "授权",
            "社会保险费",
            "个人账号或密码",
            "正在执行取数任务",
            "请勿重复提交",
            "可以发起的期间范围",
            "未解析到取数",
        )
    ):
        return False
    return any(
        keyword in text
        for keyword in (
            "本期无需申报",
            "本期无需取数",
            "无需申报，请核对财税设置",
            "系统验证并采集通过后",
            "提交成功",
            "发起成功",
        )
    )


def choose_collect_failure_reason(reasons: list[str]) -> str:
    values = unique_texts([compact_message(reason) for reason in reasons])
    if not values:
        return ""
    for keyword in (
        "社会保险费",
        "个人账号或密码",
        "授权",
        "期间",
        "取数任务长时间未完成",
        "已有取数任务正在执行",
        "未匹配到易代账账套",
        "后台未解析到取数",
    ):
        for reason in values:
            if keyword in reason:
                return reason
    return values[0]


def no_need_collect_reason(collect: dict[str, Any]) -> str:
    taxes: list[str] = []
    for warning in collect.get("warnings") or []:
        taxes.extend(re.findall(r"【([^】]+)】本期无需申报", str(warning)))
    if taxes:
        return "本期无需申报或无需取数：" + "、".join(unique_texts(taxes)[:8])
    return "易代账返回本期无需取数。"


def suggested_manual_action(reason: str, collect_status: str) -> str:
    if "社会保险费" in reason:
        return "重新发起取数，确认提交税种不含社会保险费。"
    if "已有取数任务正在执行" in reason:
        return "等待当前取数任务结束后，再查询 taskId 或重新发起取数。"
    if "长时间未完成" in reason:
        return "在易代账任务列表确认取数是否仍在执行，必要时终止后重试。"
    if "个人账号或密码错误" in reason:
        return "更新税局个人账号或密码后重新发起取数。"
    if "未匹配到易代账账套" in reason:
        return "检查税号、企业范围和地区后重新发起取数。"
    if "后台未解析到取数" in reason:
        return "在后台任务列表确认是否生成取数任务，并按税号、期间、任务类型重新查询。"
    if "强制登录" in reason or "验证码" in reason:
        return "完成税局强制登录或验证码后重新发起取数。"
    if "授权" in reason or "authorization" in reason.lower():
        return "先在易代账完成账套授权，再重新发起取数。"
    if "期间" in reason or "窗口" in reason:
        return "按易代账提示的允许期间重新发起任务。"
    if collect_status == "COLLECTED_FAIL":
        return "在易代账查看失败原因，处理后重新发起取数。"
    return "处理提示原因后重新发起取数。"


def verification_risks(verify: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    stderr_log = verify.get("stderrLog")
    if stderr_log:
        for line in read_log_lines(Path(str(stderr_log)), max_lines=300):
            if "low web extraction coverage" in line:
                match = re.search(r"([A-Za-z0-9_]+) low web extraction coverage: ([^\r\n]+)", line)
                if match:
                    form_id = match.group(1)
                    coverage = match.group(2).strip()
                    risks.append(f"{form_id_display_name(form_id)}网页解析覆盖率低：{coverage}")
                else:
                    risks.append(compact_message(line))
            elif "Could not navigate to declaration query page" in line:
                risks.append("无法进入申报信息查询页")
            elif "Tax bureau login timeout" in line:
                risks.append("税局登录超时")
            elif "登录失效" in line or "数字账户" in line:
                risks.append(compact_message(line))
    return unique_texts([risk for risk in risks if risk])


def read_log_lines(path: Path, max_lines: int = 300) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-max_lines:]
    except Exception:
        return []


def form_id_display_name(form_id: str) -> str:
    names = {
        "vat_general_main": "增值税主表",
        "vat_general_appendix1": "增值税附表一",
        "vat_general_appendix2": "增值税附表二",
        "vat_general_appendix3": "增值税附表三",
        "vat_general_appendix4": "增值税附表四",
        "vat_general_appendix5": "增值税附表五",
        "culture_fee_main": "文化事业建设费",
        "cit_a_main": "企业所得税A类",
        "cbj_personal": "个税残保金",
        "cbj_annual_settlement": "汇算清缴残保金",
    }
    return names.get(form_id, form_id)


def tax_item_display_name(item: dict[str, Any]) -> str:
    tax_type_id = item.get("taxTypeId")
    try:
        tax_type_key = int(tax_type_id)
    except (TypeError, ValueError):
        tax_type_key = None
    return str(
        item.get("taxTypeName")
        or item.get("taxName")
        or item.get("name")
        or YDZ_TAX_TYPE_ID_LABELS.get(tax_type_key)
        or f"税种{tax_type_id}"
    )


def compact_message(value: Any, limit: int = 180) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[（(]\s*响应id[:：][^）)]*[）)]", "", text)
    text = re.sub(r"\s+", " ", text).strip("；;，, ")
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def unique_texts(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def append_unique(values: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in values:
        values.append(text)


def render_summary(state: dict[str, Any], run_dir: Path) -> Path:
    dashboard = build_dashboard(state, run_dir)
    write_dashboard_csvs(dashboard, run_dir)
    try:
        write_coverage_status(run_dir)
    except Exception as exc:
        LOGGER.warning("Could not write coverage status for %s: %s", run_dir, exc)

    form_columns = dashboard["form_columns"]
    tax_rows = render_tax_matrix_rows(dashboard["items"], form_columns, run_dir)
    problem_detail_sections = render_problem_detail_sections(dashboard["problem_details"], run_dir)
    problem_form_nav = render_problem_form_nav(dashboard["problem_details"])
    kpis = dashboard["kpis"]
    funnel = dashboard["funnel"]
    coverage_section = render_coverage_section(run_dir)

    output = run_dir / "batch_summary.html"
    output.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>批量取数验证汇总 - {escape_html(state.get("runId"))}</title>
  <style>
    body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 18px; color: #1f2933; background: #f8fafc; }}
    h1 {{ margin: 0 0 6px; font-size: 22px; }}
    h2 {{ margin: 22px 0 10px; font-size: 17px; }}
    a {{ color: #2563eb; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .meta {{ color: #52606d; margin-bottom: 12px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; margin-bottom: 12px; }}
    .kpi {{ background: #fff; border: 1px solid #d9e2ec; padding: 9px; }}
    .kpi .label {{ color: #52606d; font-size: 12px; }}
    .kpi .value {{ font-size: 22px; font-weight: 700; margin-top: 3px; }}
    .funnel {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; margin-bottom: 14px; }}
    .stage {{ background: #fff; border: 1px solid #d9e2ec; padding: 8px; text-align: center; }}
    .stage .name {{ color: #52606d; font-size: 12px; }}
    .stage .count {{ font-weight: 700; margin-top: 4px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 12px; line-height: 1.25; background: #fff; }}
    th, td {{ border: 1px solid #d9e2ec; padding: 4px 6px; text-align: left; vertical-align: middle; }}
    th {{ background: #f0f4f8; position: sticky; top: 0; z-index: 1; }}
    code {{ font-family: Consolas, monospace; font-size: 11px; }}
    .scroll {{ overflow-x: auto; border: 1px solid #d9e2ec; background: #fff; }}
    .summary-table td {{ white-space: nowrap; }}
    .summary-table td.reason-cell {{ white-space: normal; min-width: 240px; max-width: 380px; }}
    .problem-nav {{ display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 12px; }}
    .problem-nav a {{ display: inline-block; padding: 4px 7px; border: 1px solid #bcccdc; background: #fff; border-radius: 4px; color: #1f2933; font-size: 12px; }}
    .problem-section {{ margin: 14px 0 18px; }}
    .problem-title {{ display: flex; align-items: baseline; gap: 8px; margin: 0 0 6px; }}
    .problem-title h3 {{ margin: 0; font-size: 15px; }}
    .problem-title .meta-small {{ color: #697386; font-size: 12px; }}
    .problem-table {{ table-layout: fixed; min-width: 960px; }}
    .problem-table th:nth-child(1) {{ width: 250px; }}
    .problem-table th:nth-child(2) {{ width: 180px; }}
    .problem-table th:nth-child(3), .problem-table th:nth-child(4) {{ width: 160px; }}
    .problem-table th:nth-child(5) {{ width: 92px; }}
    .problem-table th:nth-child(6) {{ width: 60px; }}
    .problem-table td {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .account-row td {{ background: #f8fafc; font-weight: 700; }}
    .account-row .account-meta {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
    .account-row .account-company {{ max-width: 360px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .account-row .account-count {{ color: #697386; font-weight: 400; }}
    .status, .cell {{ display: inline-block; min-width: 0; padding: 2px 5px; border-radius: 4px; text-align: center; font-size: 12px; line-height: 1.2; }}
    .cell {{ min-width: 42px; }}
    .tax-count {{ display: inline-block; margin-right: 4px; padding: 2px 5px; border-radius: 4px; font-size: 12px; }}
    .ok {{ background: #e3fcef; color: #0f5132; }}
    .warn {{ background: #fff4d6; color: #7a4d00; }}
    .fail {{ background: #ffe3e3; color: #842029; }}
    .idle {{ background: #e5e7eb; color: #374151; }}
    .quiet {{ color: #697386; }}
    .nowrap {{ white-space: nowrap; }}
    .mono {{ font-family: Consolas, monospace; }}
    .csvs {{ margin: 10px 0 16px; color: #52606d; }}
    .company-cell {{ max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .problem-num {{ text-align: right; font-weight: 700; }}
    .problem-num.fail {{ background: #fff8f8; color: #842029; }}
    .value {{ font-family: Consolas, monospace; }}
    .field-meta {{ color: #697386; font-family: Arial, "Microsoft YaHei", sans-serif; font-size: 11px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .form-cell {{ text-align: center; }}
    .field-cell {{ font-family: Consolas, monospace; }}
    .reason-category {{ display: inline-block; margin-bottom: 2px; padding: 1px 5px; border-radius: 4px; background: #fff4d6; color: #7a4d00; font-weight: 700; }}
    .reason-main {{ color: #1f2933; }}
    .reason-action {{ margin-top: 2px; color: #52606d; }}
    .coverage-panel {{ background: #fff; border: 1px solid #d9e2ec; padding: 10px; margin: 12px 0 16px; }}
    .coverage-panel h2 {{ margin-top: 0; }}
    .coverage-panel .coverage-summary {{ margin-bottom: 8px; color: #52606d; }}
    .coverage-table th:nth-child(1) {{ width: 180px; }}
    .coverage-table th:nth-child(2) {{ width: 90px; }}
    .coverage-table th:nth-child(3) {{ width: 110px; }}
  </style>
</head>
<body>
  <h1>批量取数验证汇总</h1>
  <div class="meta">runId={escape_html(state.get("runId"))} · period={escape_html(state.get("period"))} · updatedAt={escape_html(state.get("updatedAt"))}</div>
  <div class="csvs">
    CSV：<a href="batch_summary.csv">税号汇总</a> · <a href="batch_problem_details.csv">不一致明细</a> · <a href="coverage_matrix.csv">覆盖矩阵</a> · <a href="coverage_missing.csv">覆盖缺口</a> · <a href="coverage_status.json">覆盖状态JSON</a>
  </div>
  <div class="kpis">{render_kpis(kpis)}</div>
  <div class="funnel">{render_funnel(funnel)}</div>
  {coverage_section}

  <h2>税号 × 表单矩阵</h2>
  <div class="scroll">
    <table class="summary-table">
      <thead>{render_tax_matrix_header(form_columns)}</thead>
      <tbody>{tax_rows}</tbody>
    </table>
  </div>

  <h2>差异明细（按表单 / 账户分组）</h2>
  {problem_form_nav}
  {problem_detail_sections}
</body>
</html>
""",
        encoding="utf-8",
    )
    LOGGER.info("Batch summary written to %s", output)
    return output


def build_dashboard(state: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    items = []
    form_columns: dict[str, str] = {}
    forms: dict[str, dict[str, Any]] = {}
    problems: dict[tuple[str, str], dict[str, Any]] = {}
    problem_details: list[dict[str, Any]] = []

    for tax_no, item in state.get("items", {}).items():
        collect = item.get("collect") or {}
        verify = item.get("verify") or {}
        account = collect.get("account") or {}
        display_tax_no = str(item.get("taxNo") or tax_no)
        area_code = str(account.get("areaCode") or "")[:2]
        region = region_name(area_code)
        task_id = collect.get("verifyTaskId") or ""
        reports = load_compare_reports(task_id)
        form_results = {}
        total_passed = 0
        total_denominator = 0
        raw_rates = []
        problem_count = 0

        for report in reports:
            form_id = str(report.get("batch_id") or "")
            form_name = str(report.get("form_name") or form_id)
            tax_type = normalize_coverage_tax_type(report.get("tax_type"), form_id=form_id)
            tax_type_name = tax_type_display_name(tax_type)
            declaration_status = declaration_status_for_report(report)
            summary = report.get("summary") or {}
            fields = report.get("field_results") or []
            form_problems = problem_fields(fields)
            passed, denominator, effective_rate = effective_pass_rate(summary, fields)
            raw_rate = float(summary.get("match_rate", 0) or 0)
            raw_rates.append(raw_rate)
            total_passed += passed
            total_denominator += denominator
            problem_count += len(form_problems)
            form_columns[form_id] = form_name
            form_results[form_id] = {
                "formId": form_id,
                "formName": form_name,
                "taxType": tax_type,
                "taxTypeName": tax_type_name,
                "declarationStatus": declaration_status,
                "rawRate": raw_rate,
                "effectiveRate": effective_rate,
                "passed": passed,
                "denominator": denominator,
                "problemCount": len(form_problems),
                "summary": summary,
            }

            form_stat = forms.setdefault(
                form_id,
                {
                    "formId": form_id,
                    "formName": form_name,
                    "taxCount": 0,
                    "rawRates": [],
                    "effectiveRates": [],
                    "problemTaxNos": set(),
                    "problemCount": 0,
                    "topFields": {},
                },
            )
            form_stat["taxCount"] += 1
            form_stat["rawRates"].append(raw_rate)
            form_stat["effectiveRates"].append(effective_rate)
            form_stat["problemCount"] += len(form_problems)
            if form_problems:
                form_stat["problemTaxNos"].add(display_tax_no)

            for problem in form_problems:
                field_id = str(problem.get("field_id") or "")
                problem_details.append(
                    build_problem_detail(
                        tax_no=display_tax_no,
                        cust_name=account.get("custName") or "",
                        task_id=task_id,
                        area_code=area_code,
                        region=region,
                        summary_path=verify.get("summaryPath") or "",
                        form_id=form_id,
                        form_name=form_name,
                        tax_type=tax_type,
                        tax_type_name=tax_type_name,
                        declaration_status=declaration_status,
                        field=problem,
                    )
                )
                key = (form_id, field_id)
                problem_stat = problems.setdefault(
                    key,
                    {
                        "formId": form_id,
                        "formName": form_name,
                        "fieldId": field_id,
                        "count": 0,
                        "taxNos": set(),
                        "statuses": {},
                        "diffs": [],
                    },
                )
                problem_stat["count"] += 1
                problem_stat["taxNos"].add(display_tax_no)
                status = str(problem.get("status") or "")
                problem_stat["statuses"][status] = problem_stat["statuses"].get(status, 0) + 1
                diff = problem.get("diff_value")
                if diff not in (None, ""):
                    problem_stat["diffs"].append(str(diff))
                form_stat["topFields"][field_id] = form_stat["topFields"].get(field_id, 0) + 1

        tax_item_statuses = summarize_verified_tax_statuses(form_results)
        effective_overall = round(total_passed / total_denominator * 100, 2) if total_denominator else None
        raw_overall = round(sum(raw_rates) / len(raw_rates), 2) if raw_rates else None
        handling = derive_handling_info(item, collect, verify)
        manual_required = bool(collect.get("manualRequired")) and str(collect.get("status") or "").upper() != "NO_NEED_COLLECTED"
        items.append(
            {
                "taxNo": display_tax_no,
                "itemKey": tax_no,
                "custName": account.get("custName") or "",
                "areaCode": area_code,
                "region": region,
                "taxItemStatuses": tax_item_statuses,
                "taxItemStatusText": format_tax_item_statuses(tax_item_statuses),
                "collectStatus": collect.get("status") or "",
                "manualRequired": manual_required,
                "taskId": task_id,
                "taskStatus": (collect.get("resolvedTask") or {}).get("status") or "",
                "verifyStatus": verify.get("status") or "",
                "returnCode": verify.get("returnCode"),
                "manualCategory": handling["manualCategory"],
                "manualReason": handling["manualReason"],
                "manualAction": handling["manualAction"],
                "riskReason": handling["riskReason"],
                "summaryPath": verify.get("summaryPath") or "",
                "stdoutLog": verify.get("stdoutLog") or "",
                "stderrLog": verify.get("stderrLog") or "",
                "rawRate": raw_overall,
                "effectiveRate": effective_overall,
                "problemCount": problem_count,
                "formResults": form_results,
                "errors": collect.get("errors") or [],
                "warnings": collect.get("warnings") or [],
            }
        )

    ordered_form_ids = sort_form_ids(form_columns)
    kpis = build_kpis(items)
    funnel = build_funnel(items)
    normalized_forms = normalize_form_stats(forms)
    normalized_problems = normalize_problem_stats(problems)
    problem_details = sort_problem_details(problem_details)
    return {
        "items": items,
        "form_columns": [(form_id, form_columns[form_id]) for form_id in ordered_form_ids],
        "forms": normalized_forms,
        "problems": normalized_problems,
        "problem_details": problem_details,
        "kpis": kpis,
        "funnel": funnel,
    }


def load_compare_reports(task_id: str) -> list[dict[str, Any]]:
    if not task_id:
        return []
    report_dir = Path("output") / "reports" / task_id
    if not report_dir.exists():
        return []
    reports = []
    for path in sorted(report_dir.glob("*_compare_*.json")):
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            LOGGER.warning("Could not load compare report %s: %s", path, exc)
    return reports


def problem_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    status_order = {"mismatch": 0, "parse_error": 1, "mapping_error": 2, "api_missing": 3, "web_missing": 4}
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for item in sorted(
        fields,
        key=lambda x: (
            status_order.get(str(x.get("status", "")), 99),
            str(x.get("line_no") or ""),
            str(x.get("field_id") or ""),
        ),
    ):
        if str(item.get("status")) not in PROBLEM_STATUSES:
            continue
        key = problem_field_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def problem_field_key(item: dict[str, Any]) -> tuple[str, ...]:
    return (
        str(item.get("field_id") or ""),
        str(item.get("status") or ""),
        str(item.get("line_no") or ""),
        str(item.get("row_name") or ""),
        str(item.get("column_name") or ""),
        str(item.get("api_normalized") if item.get("api_normalized") is not None else item.get("api_raw_value") or ""),
        str(item.get("web_normalized") if item.get("web_normalized") is not None else item.get("web_raw_value") or ""),
    )


def region_name(area_code: Any) -> str:
    code = str(area_code or "")[:2]
    if not code:
        return ""
    label = AREA_CODE_NAMES.get(code)
    return f"{label}({code})" if label else code


def tax_type_from_form_id(form_id: str) -> str:
    text = str(form_id or "").lower()
    if text.startswith("vat_general"):
        return "VAT_GENERAL"
    if text.startswith("vat_small"):
        return "VAT_SMALL"
    if text.startswith("cit_a"):
        return "CIT_A"
    if text.startswith("culture_fee"):
        return "CULTURE_FEE"
    if text.startswith("consumption_tax"):
        return "CONSUMPTION_TAX"
    if text.startswith("cbj_personal"):
        return "CBJ_PERSONAL"
    if text.startswith("cbj_annual"):
        return "CBJ_ANNUAL"
    if text.startswith("cbj_"):
        return "CBJ_PERSONAL"
    return str(form_id or "")


def tax_type_display_name(tax_type: Any) -> str:
    text = str(tax_type or "")
    return TAX_TYPE_LABELS.get(text, text)


def declaration_status_for_report(report: dict[str, Any]) -> str:
    status = report.get("declaration_status") or report.get("declarationStatus")
    if status:
        return str(status)
    current_period_flag = report.get("current_period_flag")
    if current_period_flag is False:
        return "未申报"
    if current_period_flag is True:
        return "已申报"
    if report.get("field_results"):
        return "已申报"
    return "未知"


def summarize_verified_tax_statuses(form_results: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    statuses: dict[str, dict[str, str]] = {}
    for form in form_results.values():
        tax_type = str(form.get("taxType") or form.get("formId") or "")
        if not tax_type:
            continue
        raw_status = str(form.get("declarationStatus") or "")
        status = normalize_declaration_status(raw_status)
        item = statuses.setdefault(
            tax_type,
            {
                "taxType": tax_type,
                "taxTypeName": short_tax_type_name(form.get("taxTypeName") or tax_type_display_name(tax_type)),
                "declarationStatus": "已申报",
                "rawStatuses": "",
            },
        )
        if status == "未申报":
            item["declarationStatus"] = "未申报"
        raw_statuses = [part for part in item.get("rawStatuses", "").split(" / ") if part]
        if raw_status and raw_status not in raw_statuses:
            raw_statuses.append(raw_status)
        item["rawStatuses"] = " / ".join(raw_statuses)
    return list(statuses.values())


def normalize_declaration_status(status: Any) -> str:
    text = str(status or "").strip()
    if text in {"未申报", "未申报/未取数", "未知", ""}:
        return "未申报"
    return "已申报"


def short_tax_type_name(name: Any) -> str:
    text = str(name or "")
    replacements = {
        "增值税（一般纳税人）": "增值税",
        "增值税（小规模纳税人）": "增值税",
        "企业所得税（A类）": "企业所得税",
        "文化事业建设费": "文建费",
        "消费税": "消费税",
        "残保金": "残保金",
        "个税残保金": "个税残保金",
        "汇算清缴残保金": "汇算残保金",
    }
    return replacements.get(text, text)


def summarize_tax_item_statuses(tax_items: list[dict[str, Any]]) -> list[dict[str, str]]:
    statuses = []
    for item in tax_items:
        tax_type_id = item.get("taxTypeId")
        try:
            tax_type_key = int(tax_type_id)
        except (TypeError, ValueError):
            tax_type_key = None
        name = (
            item.get("taxTypeName")
            or item.get("taxName")
            or item.get("name")
            or YDZ_TAX_TYPE_ID_LABELS.get(tax_type_key)
            or f"税种{tax_type_id}"
        )
        init_status = str(item.get("initStatusEnum") or "")
        statuses.append(
            {
                "taxTypeId": "" if tax_type_id is None else str(tax_type_id),
                "taxTypeName": str(name),
                "collectStatus": init_status,
                "declarationStatus": declaration_status_from_collect_status(init_status),
            }
        )
    return statuses


def declaration_status_from_collect_status(status: str) -> str:
    upper = str(status or "").upper()
    if upper in {"COLLECTED", "COLLECTED_PART"}:
        return "已申报"
    if upper == "NOT_COLLECTED":
        return "未申报/未取数"
    if upper == "COLLECTING":
        return "取数中"
    if upper == "COLLECTED_FAIL":
        return "取数失败"
    return upper or "未知"


def format_tax_item_statuses(statuses: list[dict[str, str]]) -> str:
    if not statuses:
        return ""
    return "; ".join(f"{item['taxTypeName']}:{item['declarationStatus']}" for item in statuses)


def build_problem_detail(
    tax_no: str,
    cust_name: str,
    task_id: str,
    area_code: str,
    region: str,
    summary_path: str,
    form_id: str,
    form_name: str,
    tax_type: str,
    tax_type_name: str,
    declaration_status: str,
    field: dict[str, Any],
) -> dict[str, Any]:
    direct_reason = problem_direct_reason(form_id, field)
    return {
        "taxNo": tax_no,
        "custName": cust_name,
        "taskId": task_id,
        "areaCode": area_code,
        "region": region,
        "summaryPath": summary_path,
        "formId": form_id,
        "formName": form_name,
        "formShortName": short_form_name(form_name),
        "taxType": tax_type,
        "taxTypeName": tax_type_name,
        "declarationStatus": declaration_status,
        "fieldId": field.get("field_id") or "",
        "displayName": field.get("display_name") or field.get("field_id") or "",
        "lineNo": field.get("line_no") or "",
        "rowName": field.get("row_name") or "",
        "columnName": field.get("column_name") or "",
        "status": field.get("status") or "",
        "detail": field.get("detail") or "",
        "directReason": direct_reason,
        "diffType": field.get("diff_type") or "",
        "diffValue": field.get("diff_value"),
        "apiRawValue": field.get("api_raw_value"),
        "apiNormalized": field.get("api_normalized"),
        "webRawValue": field.get("web_raw_value"),
        "webNormalized": field.get("web_normalized"),
        "pdfRawValue": field.get("pdf_raw_value"),
        "tolerance": field.get("tolerance"),
    }


def problem_direct_reason(form_id: str, field: dict[str, Any]) -> str:
    status = str(field.get("status") or "")
    api_value = field.get("api_raw_value") if field.get("api_raw_value") not in (None, "") else field.get("api_normalized")
    web_value = field.get("web_raw_value") if field.get("web_raw_value") not in (None, "") else field.get("web_normalized")
    if status == "api_missing" and web_value not in (None, ""):
        if form_id == "vat_general_appendix5":
            return "附表五网页有值，但接口未返回该字段，需接口侧补齐或确认字段不支持。"
        return "网页有值，但接口未返回该字段。"
    if status == "web_missing" and api_value not in (None, ""):
        return "接口有值，但网页解析未取得该字段。"
    if status == "mismatch":
        return "接口值与网页值不一致。"
    if status == "parse_error":
        return "字段解析失败。"
    if status == "mapping_error":
        return "字段映射配置异常。"
    return ""


def sort_problem_details(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    form_order = {form_id: index for index, form_id in enumerate(FORM_ORDER)}
    status_order = {"mismatch": 0, "parse_error": 1, "mapping_error": 2, "api_missing": 3, "web_missing": 4}

    def line_sort(value: Any) -> tuple[int, str]:
        text = str(value or "")
        try:
            return int(text), ""
        except ValueError:
            return 9999, text

    return sorted(
        details,
        key=lambda item: (
            str(item.get("taxNo") or ""),
            form_order.get(str(item.get("formId") or ""), 999),
            status_order.get(str(item.get("status") or ""), 99),
            line_sort(item.get("lineNo")),
            str(item.get("fieldId") or ""),
        ),
    )


def effective_pass_rate(summary: dict[str, Any], fields: list[dict[str, Any]]) -> tuple[int, int, float]:
    total = int(summary.get("total_fields", len(fields)) or 0)
    both_missing = int(summary.get("both_missing_count", 0) or 0)
    skip = int(summary.get("skip_count", 0) or 0)
    denominator = max(0, total - both_missing - skip)
    passed = int(summary.get("match_count", 0) or 0) + int(summary.get("tolerance_match_count", 0) or 0)
    rate = round(passed / denominator * 100, 2) if denominator else 100.0
    return passed, denominator, rate


def sort_form_ids(form_columns: dict[str, str]) -> list[str]:
    known = [form_id for form_id in FORM_ORDER if form_id in form_columns]
    extra = sorted(form_id for form_id in form_columns if form_id not in FORM_ORDER)
    return known + extra


def build_kpis(items: list[dict[str, Any]]) -> dict[str, int]:
    total = len(items)
    return {
        "total": total,
        "submitted": sum(1 for item in items if item.get("collectStatus")),
        "taskResolved": sum(1 for item in items if item.get("taskId")),
        "verified": sum(1 for item in items if item.get("verifyStatus")),
        "manualRequired": sum(1 for item in items if item.get("manualCategory") == "需人工介入"),
        "problemTaxNos": sum(1 for item in items if int(item.get("problemCount") or 0) > 0),
        "allClear": sum(1 for item in items if item.get("verifyStatus") == "success" and int(item.get("problemCount") or 0) == 0),
    }


def build_funnel(items: list[dict[str, Any]]) -> list[tuple[str, int]]:
    return [
        ("输入税号", len(items)),
        ("账套匹配", sum(1 for item in items if item.get("custName"))),
        ("取数发起/已有", sum(1 for item in items if item.get("collectStatus"))),
        ("taskId解析", sum(1 for item in items if item.get("taskId"))),
        ("验证完成", sum(1 for item in items if item.get("verifyStatus"))),
        ("无问题", sum(1 for item in items if item.get("verifyStatus") == "success" and int(item.get("problemCount") or 0) == 0)),
    ]


def normalize_form_stats(forms: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for form in forms.values():
        top_fields = sorted(form["topFields"].items(), key=lambda item: (-item[1], item[0]))[:5]
        normalized.append(
            {
                "formId": form["formId"],
                "formName": form["formName"],
                "taxCount": form["taxCount"],
                "avgRawRate": round(sum(form["rawRates"]) / len(form["rawRates"]), 2) if form["rawRates"] else None,
                "avgEffectiveRate": round(sum(form["effectiveRates"]) / len(form["effectiveRates"]), 2)
                if form["effectiveRates"]
                else None,
                "problemTaxCount": len(form["problemTaxNos"]),
                "problemCount": form["problemCount"],
                "topFields": top_fields,
            }
        )
    order = {form_id: index for index, form_id in enumerate(FORM_ORDER)}
    return sorted(normalized, key=lambda item: (order.get(item["formId"], 999), item["formId"]))


def normalize_problem_stats(problems: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for problem in problems.values():
        normalized.append(
            {
                "formId": problem["formId"],
                "formName": problem["formName"],
                "fieldId": problem["fieldId"],
                "count": problem["count"],
                "taxNos": sorted(problem["taxNos"]),
                "statuses": sorted(problem["statuses"].items(), key=lambda item: (-item[1], item[0])),
                "diffs": problem["diffs"][:5],
            }
        )
    return sorted(normalized, key=lambda item: (-item["count"], item["formId"], item["fieldId"]))


def write_dashboard_csvs(dashboard: dict[str, Any], run_dir: Path) -> None:
    summary_path = run_dir / "batch_summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "taxNo",
                "custName",
                "areaCode",
                "region",
                "taxItemStatusText",
                "collectStatus",
                "manualRequired",
                "manualCategory",
                "manualReason",
                "manualAction",
                "riskReason",
                "taskId",
                "taskStatus",
                "verifyStatus",
                "rawRate",
                "effectiveRate",
                "problemCount",
                "summaryPath",
            ],
        )
        writer.writeheader()
        for item in dashboard["items"]:
            writer.writerow({key: item.get(key, "") for key in writer.fieldnames})

    details_path = run_dir / "batch_problem_details.csv"
    with details_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "taxNo",
                "custName",
                "taskId",
                "areaCode",
                "region",
                "taxType",
                "taxTypeName",
                "declarationStatus",
                "formId",
                "formName",
                "fieldId",
                "displayName",
                "lineNo",
                "rowName",
                "columnName",
                "status",
                "detail",
                "directReason",
                "apiRawValue",
                "apiNormalized",
                "webRawValue",
                "webNormalized",
                "pdfRawValue",
                "diffType",
                "diffValue",
                "tolerance",
                "summaryPath",
            ],
        )
        writer.writeheader()
        for detail in dashboard["problem_details"]:
            writer.writerow({key: detail.get(key, "") for key in writer.fieldnames})

    for obsolete_name in ("batch_forms_matrix.csv", "batch_problem_fields.csv"):
        obsolete_path = run_dir / obsolete_name
        if obsolete_path.exists():
            obsolete_path.unlink()


def render_coverage_section(run_dir: Path) -> str:
    path = run_dir / "coverage_status.json"
    if not path.exists():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    summary = payload.get("summary") or {}
    missing = payload.get("missingTargets") or []
    supplement = payload.get("supplement") or {}
    diagnostics = {str(item.get("targetKey") or ""): item for item in supplement.get("diagnostics") or []}
    if not missing:
        text = (
            f"已覆盖 {summary.get('coveredTargets', 0)}/{summary.get('totalTargets', 0)} 个目标，"
            "当前没有未覆盖税种/申报状态。"
        )
        return f'<div class="coverage-panel"><h2>覆盖缺口说明</h2><div class="coverage-summary">{escape_html(text)}</div></div>'

    rows = []
    for target in missing:
        key = str(target.get("key") or "")
        diag = diagnostics.get(key) or {}
        reason = coverage_gap_reason(target, supplement, diag)
        rows.append(
            "<tr>"
            f"<td>{escape_html(target.get('taxTypeName') or target.get('taxType'))}<br><code>{escape_html(key)}</code></td>"
            f"<td>{escape_html(target.get('declarationStatusName') or target.get('declarationStatus'))}</td>"
            f"<td>{escape_html(','.join(str(item) for item in target.get('backendTaxTypeIds') or []))}</td>"
            f"<td>{escape_html(reason)}</td>"
            "</tr>"
        )
    summary_text = (
        f"已覆盖 {summary.get('coveredTargets', 0)}/{summary.get('totalTargets', 0)} 个目标，"
        f"仍有 {len(missing)} 个税种/申报状态未覆盖。后台补齐状态：{supplement.get('status') or 'not_run'}。"
    )
    return (
        '<div class="coverage-panel">'
        "<h2>覆盖缺口说明</h2>"
        f'<div class="coverage-summary">{escape_html(summary_text)}</div>'
        '<div class="scroll"><table class="coverage-table">'
        "<thead><tr><th>税种</th><th>状态</th><th>后台税种ID</th><th>直接原因</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
        "</div>"
    )


def coverage_gap_reason(target: dict[str, Any], supplement: dict[str, Any], diagnostic: dict[str, Any]) -> str:
    reason = str(diagnostic.get("reason") or "")
    queried = diagnostic.get("queriedCount")
    status_counts = diagnostic.get("statusCounts") or {}
    if reason == "no_success_collect_tasks":
        return f"后台当月没有查到该税种的成功取数任务（查询数量 {queried or 0}）。"
    if reason == "declaration_status_not_matched":
        return f"后台有成功任务，但申报状态不符合目标；解析分布：{status_counts}。"
    if reason == "declaration_status_unknown":
        return f"后台有成功任务，但未能从任务结果或执行日志解析申报状态（查询数量 {queried or 0}）。"
    if reason:
        return reason
    if supplement.get("status") in {"not_run", "failed", "no_candidates"}:
        return str(supplement.get("message") or "未找到可补齐的代表任务。")
    notes = target.get("notes")
    return str(notes or "本次输入税号和后台补齐任务均未覆盖该目标。")


def render_kpis(kpis: dict[str, int]) -> str:
    labels = [
        ("total", "税号总数"),
        ("submitted", "已发起/已有取数"),
        ("taskResolved", "已解析 taskId"),
        ("verified", "已完成验证"),
        ("manualRequired", "需人工介入"),
        ("problemTaxNos", "有问题税号"),
        ("allClear", "完全通过"),
    ]
    return "".join(
        f'<div class="kpi"><div class="label">{escape_html(label)}</div><div class="value">{escape_html(kpis.get(key, 0))}</div></div>'
        for key, label in labels
    )


def render_funnel(funnel: list[tuple[str, int]]) -> str:
    return "".join(
        f'<div class="stage"><div class="name">{escape_html(name)}</div><div class="count">{escape_html(count)}</div></div>'
        for name, count in funnel
    )


def render_tax_matrix_header(form_columns: list[tuple[str, str]]) -> str:
    form_headers = "".join(
        f'<th title="{escape_html(name)}">{escape_html(short_form_name(name))}</th>'
        for _, name in form_columns
    )
    return (
        "<tr><th>税号</th><th>taskId</th><th>地区</th><th>企业</th><th>税种概览</th><th>取数</th><th>验证</th><th>需处理原因</th><th>问题</th>"
        f"{form_headers}<th>报告</th></tr>"
    )


def render_tax_matrix_rows(items: list[dict[str, Any]], form_columns: list[tuple[str, str]], run_dir: Path) -> str:
    rows = []
    for item in items:
        form_cells = []
        for form_id, _ in form_columns:
            form = item["formResults"].get(form_id)
            form_cells.append(render_form_cell(form))
        summary_path = item.get("summaryPath") or ""
        report_link = f'<a href="{escape_html(relative_to(run_dir, Path(summary_path)))}">汇总</a>' if summary_path else ""
        task_id = item.get("taskId") or ""
        cust_name = item.get("custName") or ""
        problem_count = int(item.get("problemCount") or 0)
        problem_class = "fail" if problem_count else ""
        rows.append(
            "<tr>"
            f'<td class="mono"><code>{escape_html(item.get("taxNo"))}</code></td>'
            f'<td class="mono"><code>{escape_html(task_id or "-")}</code></td>'
            f'<td class="nowrap">{escape_html(item.get("region"))}</td>'
            f'<td class="company-cell" title="{escape_html(cust_name)}">{escape_html(cust_name)}</td>'
            f"<td>{render_tax_item_statuses(item.get('taxItemStatuses') or [])}</td>"
            f"<td>{status_badge(item.get('collectStatus'), item.get('manualRequired'))}</td>"
            f"<td>{status_badge(item.get('verifyStatus'))}</td>"
            f"{render_handling_cell(item)}"
            f'<td class="problem-num {problem_class}">{escape_html(problem_count)}</td>'
            f"{''.join(form_cells)}"
            f"<td>{report_link}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_handling_cell(item: dict[str, Any]) -> str:
    category = item.get("manualCategory") or ""
    reason = item.get("manualReason") or ""
    action = item.get("manualAction") or ""
    if not category and not reason and not action:
        return '<td class="reason-cell quiet">-</td>'
    title_parts = [part for part in (category, reason, action) if part]
    title = "；".join(title_parts)
    category_html = f'<span class="reason-category">{escape_html(category)}</span>' if category else ""
    reason_html = f'<div class="reason-main">{escape_html(reason)}</div>' if reason else ""
    action_html = f'<div class="reason-action">{escape_html(action)}</div>' if action else ""
    return f'<td class="reason-cell" title="{escape_html(title)}">{category_html}{reason_html}{action_html}</td>'


def render_form_cell(form: dict[str, Any] | None) -> str:
    if not form:
        return '<td class="form-cell"><span class="cell idle" title="未执行">-</span></td>'
    problem_count = int(form.get("problemCount") or 0)
    rate = form.get("effectiveRate")
    css = "ok" if problem_count == 0 else "warn"
    declaration_status = form.get("declarationStatus") or ""
    label = "通过" if problem_count == 0 else f"{problem_count}项"
    if declaration_status and declaration_status != "已申报" and problem_count == 0:
        label = declaration_status
        css = "warn"
    title = f"通过率：{format_rate(rate)}；问题数：{problem_count}"
    if declaration_status:
        title += f"；申报状态：{declaration_status}"
    return f'<td class="form-cell"><span class="cell {css}" title="{escape_html(title)}">{escape_html(label)}</span></td>'


def render_tax_item_statuses(statuses: list[dict[str, str]]) -> str:
    if not statuses:
        return '<span class="quiet">暂无</span>'
    chips = []
    for item in statuses:
        status = normalize_declaration_status(item.get("declarationStatus"))
        css = tax_item_status_css(status)
        name = item.get("taxTypeName") or item.get("taxType") or ""
        label = f"{name}: {status}" if name else status
        raw_statuses = item.get("rawStatuses") or status
        title = f"{name}: {raw_statuses}" if name else raw_statuses
        chips.append(f'<span class="tax-count {css}" title="{escape_html(title)}">{escape_html(label)}</span>')
    return "".join(chips)


def render_problem_form_nav(details: list[dict[str, Any]]) -> str:
    groups = group_problem_details_by_form(details)
    if not groups:
        return ""
    links = []
    for index, group in enumerate(groups, start=1):
        label = group["shortName"] or group["formName"] or group["formId"]
        count = len(group["details"])
        tax_count = len({detail.get("taxNo") for detail in group["details"] if detail.get("taxNo")})
        links.append(
            f'<a href="#{escape_html(problem_section_id(group["formId"], index))}" '
            f'title="{escape_html(group["formName"])}">{escape_html(label)} · {escape_html(count)}项/{escape_html(tax_count)}户</a>'
        )
    return f'<div class="problem-nav">{"".join(links)}</div>'


def render_problem_detail_sections(details: list[dict[str, Any]], run_dir: Path) -> str:
    groups = group_problem_details_by_form(details)
    if not groups:
        return '<div class="scroll"><table><tbody><tr><td class="quiet">暂无不一致字段。</td></tr></tbody></table></div>'

    sections = []
    for index, group in enumerate(groups, start=1):
        section_id = problem_section_id(group["formId"], index)
        tax_count = len({detail.get("taxNo") for detail in group["details"] if detail.get("taxNo")})
        status_counts = count_problem_statuses(group["details"])
        status_text = "，".join(f"{problem_status_label(status)} {count}" for status, count in status_counts)
        title = group["formName"] or group["formId"]
        short_name = group["shortName"] or title
        meta = f"{len(group['details'])} 项差异，{tax_count} 个税号"
        if status_text:
            meta += f"；{status_text}"
        sections.append(
            f'<section class="problem-section" id="{escape_html(section_id)}">'
            f'<div class="problem-title"><h3>{escape_html(short_name)}</h3>'
            f'<span class="meta-small" title="{escape_html(title)}">{escape_html(meta)}</span></div>'
            '<div class="scroll">'
            '<table class="problem-table">'
            '<thead><tr><th>字段</th><th>位置</th><th>接口值</th><th>网页值</th><th>状态</th><th>报告</th></tr></thead>'
            f'<tbody>{render_problem_detail_account_groups(group["details"], run_dir)}</tbody>'
            '</table>'
            '</div>'
            '</section>'
        )
    return "".join(sections)


def group_problem_details_by_form(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for detail in details:
        form_id = str(detail.get("formId") or "")
        group = grouped.setdefault(
            form_id,
            {
                "formId": form_id,
                "formName": detail.get("formName") or form_id,
                "shortName": detail.get("formShortName") or short_form_name(str(detail.get("formName") or form_id)),
                "details": [],
            },
        )
        group["details"].append(detail)

    order = {form_id: index for index, form_id in enumerate(FORM_ORDER)}
    status_order = {"mismatch": 0, "parse_error": 1, "mapping_error": 2, "api_missing": 3, "web_missing": 4}

    def line_sort(value: Any) -> tuple[int, str]:
        text = str(value or "")
        match = re.match(r"\d+", text)
        if match:
            return int(match.group(0)), text
        return 9999, text

    for group in grouped.values():
        group["details"] = sorted(
            group["details"],
            key=lambda item: (
                str(item.get("taxNo") or ""),
                status_order.get(str(item.get("status") or ""), 99),
                line_sort(item.get("lineNo")),
                str(item.get("fieldId") or ""),
            ),
        )

    return sorted(
        grouped.values(),
        key=lambda group: (
            order.get(str(group.get("formId") or ""), 999),
            str(group.get("formName") or ""),
            str(group.get("formId") or ""),
        ),
    )


def render_problem_detail_account_groups(details: list[dict[str, Any]], run_dir: Path) -> str:
    rows = []
    for account in group_problem_details_by_account(details):
        summary_path = account.get("summaryPath") or ""
        report_link = f'<a href="{escape_html(relative_to(run_dir, Path(summary_path)))}">汇总</a>' if summary_path else ""
        status_counts = count_problem_statuses(account["details"])
        status_text = "，".join(f"{problem_status_label(status)} {count}" for status, count in status_counts)
        account_meta = [
            f'<code>{escape_html(account.get("taxNo"))}</code>',
            f'<code>taskId={escape_html(account.get("taskId") or "-")}</code>',
            f'<span>{escape_html(account.get("region"))}</span>',
            f'<span class="account-company" title="{escape_html(account.get("custName"))}">{escape_html(account.get("custName"))}</span>',
            f'<span class="account-count">{escape_html(len(account["details"]))} 项差异{escape_html("；" + status_text if status_text else "")}</span>',
        ]
        rows.append(
            '<tr class="account-row">'
            f'<td colspan="6"><div class="account-meta">{"".join(account_meta)}<span>{report_link}</span></div></td>'
            '</tr>'
        )
        rows.append(render_problem_detail_group_rows(account["details"], run_dir, include_report=not bool(report_link)))
    return "".join(rows)


def group_problem_details_by_account(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for detail in details:
        tax_no = str(detail.get("taxNo") or "")
        task_id = str(detail.get("taskId") or "")
        key = (tax_no, task_id)
        group = grouped.setdefault(
            key,
            {
                "taxNo": tax_no,
                "taskId": task_id,
                "region": detail.get("region") or "",
                "custName": detail.get("custName") or "",
                "summaryPath": detail.get("summaryPath") or "",
                "details": [],
            },
        )
        group["details"].append(detail)

    status_order = {"mismatch": 0, "parse_error": 1, "mapping_error": 2, "api_missing": 3, "web_missing": 4}

    def line_sort(value: Any) -> tuple[int, str]:
        text = str(value or "")
        match = re.match(r"\d+", text)
        if match:
            return int(match.group(0)), text
        return 9999, text

    for group in grouped.values():
        group["details"] = sorted(
            group["details"],
            key=lambda item: (
                status_order.get(str(item.get("status") or ""), 99),
                line_sort(item.get("lineNo")),
                str(item.get("fieldId") or ""),
            ),
        )

    return sorted(
        grouped.values(),
        key=lambda group: (
            str(group.get("taxNo") or ""),
            str(group.get("custName") or ""),
            str(group.get("taskId") or ""),
        ),
    )


def render_problem_detail_group_rows(
    details: list[dict[str, Any]],
    run_dir: Path,
    include_report: bool = True,
) -> str:
    rows = []
    for detail in details:
        summary_path = detail.get("summaryPath") or ""
        report_link = (
            f'<a href="{escape_html(relative_to(run_dir, Path(summary_path)))}">汇总</a>'
            if include_report and summary_path
            else ""
        )
        field_label = detail.get("fieldId") or detail.get("displayName") or ""
        field_title = " / ".join(
            part
            for part in (
                str(detail.get("displayName") or ""),
                str(detail.get("fieldId") or ""),
                render_field_position(detail, plain=True),
            )
            if part
        )
        rows.append(
            "<tr>"
            f'<td class="field-cell"><span title="{escape_html(field_title)}">{escape_html(field_label)}</span></td>'
            f'<td>{render_field_position(detail)}</td>'
            f'<td class="value">{render_compare_value(detail.get("apiRawValue"), detail.get("apiNormalized"))}</td>'
            f'<td class="value">{render_compare_value(detail.get("webRawValue"), detail.get("webNormalized"))}</td>'
            f"<td>{render_problem_status(detail)}</td>"
            f"<td>{report_link}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_field_position(detail: dict[str, Any], plain: bool = False) -> str:
    parts = []
    if detail.get("lineNo"):
        parts.append(f"行 {detail.get('lineNo')}")
    if detail.get("rowName"):
        parts.append(str(detail.get("rowName")))
    if detail.get("columnName"):
        parts.append(str(detail.get("columnName")))
    text = " / ".join(parts)
    if plain:
        return text
    return f'<span title="{escape_html(text)}">{escape_html(text or "-")}</span>'


def count_problem_statuses(details: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for detail in details:
        status = str(detail.get("status") or "")
        counts[status] = counts.get(status, 0) + 1
    status_order = {"mismatch": 0, "parse_error": 1, "mapping_error": 2, "api_missing": 3, "web_missing": 4}
    return sorted(counts.items(), key=lambda item: (status_order.get(item[0], 99), item[0]))


def problem_status_label(status: str) -> str:
    return {
        "mismatch": "不一致",
        "api_missing": "接口缺失",
        "web_missing": "网页缺失",
        "parse_error": "解析失败",
        "mapping_error": "映射错误",
    }.get(status, status or "问题")


def problem_section_id(form_id: str, index: int) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]+", "-", str(form_id or "form")).strip("-")
    return f"diff-{index}-{safe or 'form'}"


def render_problem_detail_rows(details: list[dict[str, Any]], run_dir: Path) -> str:
    if not details:
        return '<tr><td colspan="10" class="quiet">暂无不一致字段。</td></tr>'
    rows = []
    for detail in details:
        summary_path = detail.get("summaryPath") or ""
        report_link = f'<a href="{escape_html(relative_to(run_dir, Path(summary_path)))}">汇总</a>' if summary_path else ""
        field_meta = []
        if detail.get("lineNo"):
            field_meta.append(f"行 {detail.get('lineNo')}")
        if detail.get("rowName"):
            field_meta.append(str(detail.get("rowName")))
        if detail.get("columnName"):
            field_meta.append(str(detail.get("columnName")))
        form_title = f"{detail.get('formName') or ''} / {detail.get('formId') or ''}"
        if detail.get("declarationStatus"):
            form_title += f" / 申报状态：{detail.get('declarationStatus')}"
        form_html = (
            f'<span title="{escape_html(form_title)}">'
            f'{escape_html(detail.get("formShortName") or detail.get("formName") or detail.get("formId"))}</span>'
        )
        field_title_parts = [
            str(detail.get("displayName") or ""),
            str(detail.get("fieldId") or ""),
            " / ".join(field_meta),
        ]
        field_title = " / ".join(part for part in field_title_parts if part)
        field_label = detail.get("fieldId") or detail.get("displayName") or ""
        field_html = f'<span title="{escape_html(field_title)}">{escape_html(field_label)}</span>'
        tax_title = f"{detail.get('taxTypeName') or ''} / {detail.get('taxType') or ''}"
        if detail.get("declarationStatus"):
            tax_title += f" / 申报状态：{detail.get('declarationStatus')}"
        status_html = render_problem_status(detail)
        rows.append(
            "<tr>"
            f"<td><code>{escape_html(detail.get('taxNo'))}</code></td>"
            f'<td class="nowrap">{escape_html(detail.get("region"))}</td>'
            f'<td class="company-cell" title="{escape_html(detail.get("custName"))}">{escape_html(detail.get("custName"))}</td>'
            f'<td title="{escape_html(tax_title)}">{escape_html(detail.get("taxTypeName") or detail.get("taxType"))}</td>'
            f"<td>{form_html}</td>"
            f'<td class="field-cell">{field_html}</td>'
            f'<td class="value">{render_compare_value(detail.get("apiRawValue"), detail.get("apiNormalized"))}</td>'
            f'<td class="value">{render_compare_value(detail.get("webRawValue"), detail.get("webNormalized"))}</td>'
            f"<td>{status_html}</td>"
            f"<td>{report_link}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_compare_value(raw_value: Any, normalized_value: Any) -> str:
    has_raw = raw_value not in (None, "")
    has_normalized = normalized_value not in (None, "")
    if not has_raw and not has_normalized:
        return '<span class="quiet">空</span>'
    display = raw_value if has_raw else normalized_value
    title_parts = []
    if has_raw:
        title_parts.append(f"原值：{raw_value}")
    if has_normalized and str(normalized_value).strip() != str(raw_value).strip():
        title_parts.append(f"标准：{normalized_value}")
    title = "；".join(title_parts)
    return f'<span title="{escape_html(title)}">{escape_html(display)}</span>'


def render_problem_status(detail: dict[str, Any]) -> str:
    status = str(detail.get("status") or "")
    labels = {
        "mismatch": "不一致",
        "api_missing": "接口缺失",
        "web_missing": "网页缺失",
        "parse_error": "解析失败",
        "mapping_error": "映射错误",
    }
    label = labels.get(status, status or "问题")
    if status == "api_missing" and detail.get("webRawValue") not in (None, ""):
        label = "接口缺失（网页有值）"
        if detail.get("formId") == "vat_general_appendix5":
            label = "接口待补齐"
    css = "fail" if status in {"mismatch", "parse_error", "mapping_error"} else "warn"
    lines = []
    if detail.get("directReason"):
        lines.append(str(detail.get("directReason")))
    if detail.get("diffValue") not in (None, ""):
        lines.append(f"差异：{detail.get('diffValue')}")
    if detail.get("detail"):
        lines.append(str(detail.get("detail")))
    if detail.get("tolerance") not in (None, ""):
        lines.append(f"容差：{detail.get('tolerance')}")
    title = " / ".join(lines)
    return f'<span class="status {css}" title="{escape_html(title)}">{escape_html(label)}</span>'


def tax_item_status_css(status: str) -> str:
    if status == "已申报":
        return "ok"
    if status == "取数失败":
        return "fail"
    if status in {"取数中", "未申报", "未申报/未取数"}:
        return "warn"
    return "idle"


def render_form_matrix_rows(forms: list[dict[str, Any]]) -> str:
    if not forms:
        return '<tr><td colspan="7" class="quiet">暂无表单结果。</td></tr>'
    rows = []
    for form in forms:
        top_fields = "; ".join(f"<code>{escape_html(field)}</code>×{escape_html(count)}" for field, count in form["topFields"])
        rows.append(
            "<tr>"
            f"<td>{escape_html(form.get('formName'))}<br><code>{escape_html(form.get('formId'))}</code></td>"
            f"<td>{escape_html(form.get('taxCount'))}</td>"
            f"<td>{format_rate(form.get('avgRawRate'))}</td>"
            f"<td>{format_rate(form.get('avgEffectiveRate'))}</td>"
            f"<td>{escape_html(form.get('problemTaxCount'))}</td>"
            f"<td>{escape_html(form.get('problemCount'))}</td>"
            f"<td>{top_fields}</td>"
            "</tr>"
        )
    return "".join(rows)


def render_problem_rank_rows(problems: list[dict[str, Any]]) -> str:
    if not problems:
        return '<tr><td colspan="6" class="quiet">暂无问题字段。</td></tr>'
    rows = []
    for problem in problems[:100]:
        statuses = "; ".join(f"{status}:{count}" for status, count in problem["statuses"])
        tax_nos = "; ".join(problem["taxNos"][:12])
        if len(problem["taxNos"]) > 12:
            tax_nos += f"; +{len(problem['taxNos']) - 12}"
        rows.append(
            "<tr>"
            f"<td><code>{escape_html(problem.get('fieldId'))}</code></td>"
            f"<td>{escape_html(problem.get('formName'))}<br><code>{escape_html(problem.get('formId'))}</code></td>"
            f"<td>{escape_html(problem.get('count'))}</td>"
            f"<td>{escape_html(tax_nos)}</td>"
            f"<td>{escape_html(statuses)}</td>"
            f"<td>{escape_html('; '.join(problem.get('diffs') or []))}</td>"
            "</tr>"
        )
    return "".join(rows)


def status_badge(value: Any, manual_required: bool = False) -> str:
    text = str(value or "")
    upper = text.upper()
    if upper == "NO_NEED_COLLECTED":
        return '<span class="status warn" title="NO_NEED_COLLECTED">无需取数</span>'
    if manual_required:
        return '<span class="status fail">需人工</span>'
    if not text:
        return '<span class="status idle">未执行</span>'
    if upper in {"SUCCESS", "COLLECTED", "COLLECTED_PART", "SUCCESSFUL", "DONE", "OK"} or text in {"success", "已申报"}:
        css = "ok"
    elif upper in {"FAILURE", "COLLECTED_FAIL", "FAILED", "ERROR"} or text in {"failed", "取数失败"}:
        css = "fail"
    elif "difference" in text or upper in {"DOING", "WAITING", "TODO", "COLLECTING"} or text in {"未申报", "取数中", "未申报/未取数"}:
        css = "warn"
    else:
        css = "idle"
    label_map = {
        "COLLECTED": "已取数",
        "COLLECTED_PART": "部分取数",
        "SUCCESS": "通过",
        "SUCCESSFUL": "通过",
        "DONE": "完成",
        "OK": "通过",
        "FAILURE": "失败",
        "COLLECTED_FAIL": "取数失败",
        "NO_NEED_COLLECTED": "无需取数",
        "FAILED": "失败",
        "ERROR": "失败",
        "DOING": "处理中",
        "WAITING": "等待中",
        "TODO": "未执行",
        "COLLECTING": "取数中",
        "SKIPPED": "未执行",
    }
    exact_label_map = {
        "success": "通过",
        "failed": "失败",
        "completed_with_differences": "有差异",
        "skipped": "未执行",
    }
    label = exact_label_map.get(text) or label_map.get(upper) or text
    title = "" if label == text else f' title="{escape_html(text)}"'
    return f'<span class="status {css}"{title}>{escape_html(label)}</span>'


def short_form_name(value: str) -> str:
    replacements = {
        "增值税纳税申报表（一般纳税人适用）": "增值税主表",
        "增值税纳税申报表附列资料（一）（本期销售情况明细）": "附表一",
        "增值税纳税申报表附列资料（二）（本期进项税额明细）": "附表二",
        "增值税纳税申报表附列资料（三）（服务、不动产和无形资产扣除项目明细）": "附表三",
        "增值税纳税申报表附列资料（四）（税额抵减情况表）": "附表四",
        "增值税及附加税费申报表附列资料（五）（附加税费情况表）": "附表五",
        "文化事业建设费申报表": "文建费主表",
        "应税服务减除项目清单": "文建费减除清单",
    }
    return replacements.get(value, value or "")


def format_rate(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return str(value)


def escape_html(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def relative_to(base_dir: Path, target: Path) -> str:
    try:
        return target.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError:
        try:
            return target.resolve().as_uri()
        except ValueError:
            return str(target)


if __name__ == "__main__":
    raise SystemExit(main())
