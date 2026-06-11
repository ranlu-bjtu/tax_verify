"""Batch Yidaizhang collection submission followed by serialized verification."""

from __future__ import annotations

import argparse
import copy
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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, ".")

from src.cbj.verification import (
    fetch_backend_fields,
    report_has_errors,
    verify_annual_settlement_cbj,
    verify_personal_cbj,
)
from src.chanjet_admin.task_execution_log import fetch_cbj_mode_from_task_logs
from src.chanjet_admin.task_query import TASK_LIST_URL, ChanjetAdminTaskQuery
from src.coverage.analyzer import write_coverage_status
from src.coverage.registry import (
    build_coverage_targets,
    declaration_statuses_for_collect_statuses,
    normalize_collect_status_keys,
    normalize_tax_type as normalize_coverage_tax_type,
    normalize_tax_type_keys,
)
from src.coverage.models import SupplementCandidate
from src.coverage.supplement import (
    CoverageSupplementPlanner,
    apply_supplement_candidates_to_state,
    select_diverse_supplement_candidates,
)
from src.login.task_login_flow import DEFAULT_MACHINE_ID, GET_CLIENT_JOB_URL, GET_TASK_COOKIE_FALLBACK_URL, TaskLoginFlow
from src.runtime.process_lock import DEFAULT_TAX_BROWSER_LOCK, ProcessLock
from src.ydz.api import YdzApi
from src.ydz.collector import YdzCollector
from src.ydz.models import TERMINAL_COLLECT_STATUSES, YdzAccount, YdzCollectResult
from src.ydz.session import YdzSession, get_env_credentials
from src.ydz.task_resolver import VerifyTaskResolver


LOGGER = logging.getLogger("batch_collect_verify")
PROBLEM_STATUSES = {"mismatch", "api_missing", "web_missing", "parse_error", "mapping_error"}
MAX_SUPPLEMENT_QUERY_WINDOW_DAYS = 39
SUPPLEMENT_LOGIN_PREFLIGHT_POOL_MULTIPLIER = 3
SUPPLEMENT_LOGIN_PREFLIGHT_REFILL_MAX_WAVES = 3
STANDARD_SUPPLEMENT_LOGIN_PREFLIGHT_TAX_TYPES = {
    "VAT_GENERAL",
    "VAT_SMALL",
    "CULTURE_FEE",
    "CBJ_PERSONAL",
    "CBJ_ANNUAL",
}
CIT_A_YDZ_TAX_TYPE_IDS = [2]
CIT_A_YDZ_ACCOUNT_SCAN_PAGE_SIZE = 50
CIT_A_YDZ_ACCOUNT_SCAN_MAX_PAGES = 3
CIT_A_YDZ_ACCOUNT_SCAN_MAX_PERIODS = 1
CIT_A_YDZ_REFRESH_POLL_TIMEOUT_SECONDS = 45
YDZ_EXTERNAL_ACCOUNT_SCAN_SOURCES = {
    "other_enterprise_account_scan",
    "explicit_work_url_account_scan",
    "open_work_tab_account_scan",
}
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
DECLARATION_STATUS_LABELS = {
    "filed": "已申报",
    "submitted": "已申报",
    "success": "已申报",
    "collected": "已申报",
    "unfiled": "未申报",
    "not_filed": "未申报",
    "no_declaration": "未申报",
    "no_need": "未申报",
    "not_collected": "未申报",
    "any": "不区分申报状态",
    "unknown": "未知",
    "": "未知",
}
COVERAGE_SUPPLEMENT_STATUS_LABELS = {
    "not_run": "未执行",
    "not_needed": "无需补齐",
    "running": "查询中",
    "failed": "查询失败",
    "no_candidates": "未找到可补齐任务",
    "applied": "已找到补齐任务",
    "applying": "正在重试补齐任务",
    "verified": "补齐任务已验证",
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
        values.extend(part.strip().lstrip("\ufeff") for part in item.split(",") if part.strip().lstrip("\ufeff"))
    if args.tax_no_file:
        for line in Path(args.tax_no_file).read_text(encoding="utf-8").splitlines():
            clean = line.strip().lstrip("\ufeff")
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


def split_config_values(values: Any) -> list[str]:
    if values is None:
        return []
    raw_items = values if isinstance(values, (list, tuple, set)) else [values]
    result: list[str] = []
    for raw_item in raw_items:
        for part in re.split(r"[,\r\n]+", str(raw_item or "")):
            clean = part.strip()
            if clean:
                result.append(clean)
    return result


def explicit_ydz_work_urls(args: argparse.Namespace) -> list[str]:
    values = split_config_values(getattr(args, "coverage_supplement_ydz_work_url", []))
    values.extend(split_config_values(os.environ.get("YDZ_SUPPLEMENT_WORK_URLS", "")))
    return unique_texts(values)


def redact_ydz_work_url_label(work_url: str) -> str:
    parsed = urlparse(str(work_url or "").strip())
    host = parsed.netloc or "ydz-work-url"
    if "/work.html" in str(parsed.path or ""):
        return f"{host}/.../work.html"
    return host


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
    parser.add_argument(
        "--reuse-collected-task",
        action="store_true",
        help="Allow resolving an existing backend task when Yidaizhang already shows collected. By default, new batch runs submit a fresh collection task.",
    )
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
        "--coverage-supplement-only",
        action="store_true",
        help="Only run backend coverage supplement for an existing run state; skip collection and existing-item verification.",
    )
    parser.add_argument(
        "--coverage-supplement-page-size",
        type=int,
        default=500,
        help="Page size used when searching backend supplement tasks.",
    )
    parser.add_argument(
        "--coverage-supplement-timeout",
        type=int,
        default=600,
        help="Maximum seconds for backend supplement search. 0 disables the limit.",
    )
    parser.add_argument(
        "--coverage-supplement-lookback-days",
        type=int,
        default=0,
        help="Backend supplement search lookback days. 0 keeps the current-month default.",
    )
    parser.add_argument(
        "--coverage-supplement-cit-lookback-days",
        type=int,
        default=100,
        help="Backend supplement lookback days for CIT A representative samples. Queries are sliced into backend-safe windows.",
    )
    parser.add_argument(
        "--coverage-supplement-max-candidates",
        type=int,
        default=3,
        help="Maximum backend supplement candidates to try for each missing coverage target.",
    )
    parser.add_argument(
        "--coverage-supplement-targets",
        default="",
        help=(
            "Comma-separated coverage target keys to supplement, for example "
            "CIT_A:filed,CIT_A:unfiled. This does not change the batch coverage scope."
        ),
    )
    parser.add_argument(
        "--coverage-supplement-refresh-cit-from-ydz",
        action="store_true",
        help=(
            "For CIT A supplement, first try to submit a fresh Yidaizhang collection. "
            "Candidate tax numbers are checked first; if they are absent, a bounded scan of "
            "current-enterprise account sets is used. Default is off."
        ),
    )
    parser.add_argument(
        "--coverage-supplement-scan-ydz-enterprises",
        action="store_true",
        help=(
            "When CIT A fresh refresh finds no current-enterprise source, read-only scan other "
            "selectable Yidaizhang enterprises for CIT A account rows. Default is off."
        ),
    )
    parser.add_argument(
        "--coverage-supplement-ydz-enterprise-scan-limit",
        type=int,
        default=8,
        help="Maximum number of other Yidaizhang enterprises to scan for CIT A source readiness.",
    )
    parser.add_argument(
        "--coverage-supplement-ydz-enterprise-names",
        default="",
        help="Optional comma-separated Yidaizhang enterprise names to scan before auto-detected names.",
    )
    parser.add_argument(
        "--coverage-supplement-ydz-work-url",
        action="append",
        default=[],
        help=(
            "Explicit Yidaizhang cloud work.html URL to scan for CIT A source rows. "
            "Can be repeated; YDZ_SUPPLEMENT_WORK_URLS is also read."
        ),
    )
    parser.add_argument(
        "--coverage-tax-types",
        default="",
        help="Comma-separated coverage tax type keys. Empty means all supported tax types.",
    )
    parser.add_argument(
        "--coverage-collect-statuses",
        default="",
        help="Comma-separated coverage collect status keys: collected,not_collected. Empty means both.",
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
        default="plugin_first",
        help="Tax bureau login strategy passed to main.py. plugin_first uses EtaxPlugin cleanup/new-tab flow before direct fallback.",
    )
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--chrome-path", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user-data-dir", default="./browser_profile/etax_compare_forms")
    parser.add_argument("--plugin-path", default=r"C:\Users\Administrator\Downloads\EtaxPlugin")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--poll-timeout", type=int, default=600)
    parser.add_argument("--browser-lock-timeout", type=int, default=3600)
    parser.add_argument(
        "--verify-timeout",
        type=int,
        default=0,
        help="Maximum seconds for each main.py verification subprocess. 0 uses a bounded default derived from --tax-timeout.",
    )
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
    if args.coverage_supplement_only:
        if args.skip_coverage_supplement:
            LOGGER.info("Coverage supplement only was requested, but coverage supplement is skipped.")
        else:
            exit_code = run_coverage_supplement_phase(args, state, run_dir)
    elif not args.skip_collect:
        exit_code = run_collect_stream(args, tax_nos, state, run_dir)
    else:
        LOGGER.info("Skipping collection phase; using existing state: %s", run_dir / "state.json")
        if args.verify:
            exit_code = run_verify_phase(args, tax_nos, state, run_dir, final=True)
    if not args.coverage_supplement_only and args.verify and not args.skip_coverage_supplement:
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
    selected_coverage_tax_types = parse_coverage_tax_types(getattr(args, "coverage_tax_types", ""))
    if selected_coverage_tax_types:
        state["coverageTaxTypes"] = selected_coverage_tax_types
    else:
        state.setdefault("coverageTaxTypes", [])
    selected_collect_statuses = parse_coverage_collect_statuses(getattr(args, "coverage_collect_statuses", ""))
    if selected_collect_statuses:
        state["coverageCollectStatuses"] = selected_collect_statuses
    else:
        state.setdefault("coverageCollectStatuses", [])
    for tax_no in tax_nos:
        state.setdefault("items", {}).setdefault(
            tax_no,
            {"taxNo": tax_no, "period": args.period, "collect": None, "verify": None},
        )
    return state


def parse_coverage_tax_types(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[,，;\s]+", value) if part.strip()]
    else:
        parts = [str(part).strip() for part in value if str(part).strip()]
    return normalize_tax_type_keys(parts)


def parse_coverage_collect_statuses(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[,，;\s]+", value) if part.strip()]
    else:
        parts = [str(part).strip() for part in value if str(part).strip()]
    return normalize_collect_status_keys(parts)


def parse_coverage_supplement_target_keys(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[,，\s]+", value) if part.strip()]
    else:
        parts = [str(part).strip() for part in value if str(part).strip()]
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = normalize_coverage_supplement_target_key(part)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def normalize_coverage_supplement_target_key(value: Any) -> str:
    text = str(value or "").strip().replace("：", ":")
    if ":" not in text:
        return ""
    tax_type_raw, status_raw = text.split(":", 1)
    tax_types = normalize_tax_type_keys([tax_type_raw])
    status = normalize_coverage_supplement_target_status(status_raw)
    if not tax_types or not status:
        return ""
    return f"{tax_types[0]}:{status}"


def normalize_coverage_supplement_target_status(value: Any) -> str:
    raw = str(value or "").strip()
    upper = raw.upper()
    aliases = {
        "FILED": "filed",
        "COLLECTED": "filed",
        "SUCCESS": "filed",
        "\u5df2\u53d6\u6570": "filed",
        "\u5df2\u7533\u62a5": "filed",
        "UNFILED": "unfiled",
        "NOT_COLLECTED": "unfiled",
        "NOT-COLLECTED": "unfiled",
        "NO_NEED": "unfiled",
        "\u672a\u53d6\u6570": "unfiled",
        "\u672a\u7533\u62a5": "unfiled",
        "ANY": "any",
        "ALL": "any",
    }
    return aliases.get(upper) or aliases.get(raw) or ""


def coverage_targets_for_state(state: dict[str, Any]) -> list[Any]:
    return build_coverage_targets(
        declaration_statuses=declaration_statuses_for_collect_statuses(state.get("coverageCollectStatuses") or []),
        tax_types=parse_coverage_tax_types(state.get("coverageTaxTypes") or []),
    )


def coverage_supplement_target_form_ids(
    item: dict[str, Any],
    active_target_key: str = "",
) -> list[str]:
    if str(item.get("source") or "") != "backend_supplement":
        return []
    keys: list[str] = []
    if active_target_key:
        keys.append(active_target_key)
    if not keys:
        keys.extend(str(value or "") for value in item.get("coverageSupplementTargets") or [])
    if not keys:
        resolved = (item.get("collect") or {}).get("resolvedTask") or {}
        if resolved.get("coverageTarget"):
            keys.append(str(resolved.get("coverageTarget") or ""))

    targets_by_key = {target.key: target for target in build_coverage_targets()}
    form_ids: list[str] = []
    seen: set[str] = set()
    for key in keys:
        target = targets_by_key.get(str(key or ""))
        if not target:
            continue
        for form_id in target.form_ids:
            # CBJ supplement is verified by the dedicated CBJ path, not main.py targets.
            if str(form_id).startswith("cbj_"):
                continue
            if form_id in seen:
                continue
            seen.add(form_id)
            form_ids.append(form_id)
    return form_ids


def verify_targets_for_item(
    requested_targets: str,
    item: dict[str, Any],
    active_coverage_target_key: str = "",
) -> str:
    if str(requested_targets or "").strip().lower() != "auto":
        return requested_targets
    form_ids = coverage_supplement_target_form_ids(item, active_coverage_target_key)
    if not form_ids:
        return requested_targets
    return ",".join(form_ids)


def declaration_status_override_for_coverage_target(active_coverage_target_key: str) -> str:
    key = str(active_coverage_target_key or "").strip()
    if ":" not in key:
        return ""
    status = normalize_coverage_supplement_target_status(key.split(":", 1)[1])
    if status in {"filed", "unfiled"}:
        return status
    return ""


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
    event_status = status or stage_status_for_item(item)
    event_key = {
        "stage": stage,
        "status": event_status,
        "message": message,
        "reason": reason,
    }
    if previous != stage or event_key != item.get("_lastOpsEventKey"):
        append_ops_event(
            run_dir,
            {
                "time": datetime.now().isoformat(timespec="seconds"),
                "runId": state.get("runId"),
                "taxNo": tax_no,
                "stage": stage,
                "stageName": OPS_STAGE_LABELS.get(stage, stage),
                "status": event_status,
                "message": message,
                "reason": reason,
            },
        )
        item["_lastOpsEventKey"] = event_key


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
        stage_reason = str(item.get("stageReason") or "")
        reason = (
            handling.get("manualReason")
            or direct_verify_reason(verify)
            or direct_verify_reason({"reason": stage_reason})
            or stage_reason
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
                "taskId": format_task_ids(collect_task_ids(collect)),
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
    if str(collect.get("status") or "").upper() == "NO_NEED_COLLECTED" or stage == "collect_no_need":
        return "success"
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
    if stage in {"verified"}:
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
    if "TaxLoginNotReadyError" in reason or "Tax bureau login state or digital account authentication is not ready" in reason:
        return normalize_supplement_failure_reason(reason)
    if "PendingTaxLoginJobError" in reason or "已有进税局任务未完成" in reason:
        return normalize_supplement_failure_reason(reason)
    if "ForceTaxLoginRequiredError" in reason or "needForceTax" in reason:
        return normalize_supplement_failure_reason(reason)
    if "getClientJob" in reason:
        return normalize_supplement_failure_reason(reason)
    if "Cannot resolve province from task cookie/client job data" in reason:
        return normalize_supplement_failure_reason(reason)
    if "getTaskCookie failed" in reason:
        return normalize_supplement_failure_reason(reason)
    if "Could not navigate to declaration query page" in reason:
        return normalize_supplement_failure_reason(reason)
    if "RuntimeError:" in reason or "TimeoutError:" in reason:
        return normalize_supplement_failure_reason(reason)
    if "DeclarationQueryAuthError" in reason or "统一登录页" in reason or "数字账户认证" in reason:
        return "税局登录态或数字账户认证已失效。"
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
    if "未能进入申报信息查询页" in reason:
        return "人工重新进入对应税局/数字账户后点击继续验证。"
    if "税局登录失败" in reason or "税局登录超时" in reason or "登录连接状态已失效" in reason:
        return "重新进入税局或重新发起取数任务后再验证。"
    if "统一登录页" in reason or "数字账户认证" in reason:
        return "人工重新进入对应税局/数字账户后点击继续验证。"
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
    if is_ydz_invalid_signature_error(exc):
        return (
            "\u6613\u4ee3\u8d26\u767b\u5f55\u7b7e\u540d\u5df2\u5931\u6548\uff0c"
            "\u9700\u8981\u91cd\u65b0\u767b\u5f55\u6613\u4ee3\u8d26\u540e\u518d\u53d1\u8d77\u53d6\u6570\u3002"
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


def is_ydz_invalid_signature_error(exc: Exception | str) -> bool:
    lower_text = str(exc or "").lower()
    return "invalid signature" in lower_text and (
        "easyacctg" in lower_text or "getbatchlist" in lower_text or "batchsubmittask" in lower_text
    )


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
            chrome_path=args.chrome_path,
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
                force_collect = should_force_collect(args, collect)
                existing_task_ids = collect_task_ids(collect)
                if existing_task_ids and not force_collect:
                    LOGGER.info("Skipping collection for %s; taskId already resolved: %s", tax_no, format_task_ids(existing_task_ids))
                    continue
                LOGGER.info("Submitting Yidaizhang collection for %s/%s", tax_no, args.period)
                result = collector.submit_collect_tax_no(tax_no=tax_no, period=args.period, force=force_collect)
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
                if collect_task_ids(collect) and not should_force_collect(args, collect):
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
            resolve_pending_after_collect_timeout(args, pending, state, run_dir)
            pending = pending_collect_results(results)
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


def resolve_pending_after_collect_timeout(
    args: argparse.Namespace,
    pending: dict[str, YdzCollectResult],
    state: dict[str, Any],
    run_dir: Path,
) -> None:
    if not pending:
        return
    LOGGER.info(
        "Collection polling timed out; checking backend for %s pending task(s) before manual fallback.",
        len(pending),
    )
    try:
        with open_ydz_session(
            args,
            {"kind": "batch-ydz-timeout-resolve", "runId": state["runId"], "period": args.period},
        ) as (
            _session,
            resolver,
            _collector,
        ):
            for tax_no, result in pending.items():
                if has_result_task_id(result):
                    continue
                before = result_task_ids(result)
                resolve_task_id_for_result(resolver, tax_no, result, state, run_dir)
                resolved_ids = result_task_ids(result)
                if resolved_ids and resolved_ids != before:
                    result.manual_required = False
                    result.terminal = True
                    state["items"][tax_no]["collect"] = result.to_dict()
                    set_item_stage(
                        state,
                        run_dir,
                        tax_no,
                        "task_resolved",
                        status="running",
                        message=f"超时前后台兜底解析到 taskId：{format_task_ids(resolved_ids)}",
                    )
    except Exception as exc:
        LOGGER.warning("Backend timeout fallback could not run: %s", exc)
    write_state(state, run_dir)


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


def collect_task_ids(collect: dict[str, Any] | None) -> list[str]:
    collect = collect or {}
    status_by_task_id: dict[str, str] = {}
    resolved_tasks = list(collect.get("resolvedTasks") or [])
    if collect.get("resolvedTask"):
        resolved_tasks.append(collect.get("resolvedTask") or {})
    for task in resolved_tasks:
        task_id = str((task or {}).get("taskId") or "").strip()
        status = str((task or {}).get("status") or "").upper()
        if task_id and status:
            status_by_task_id[task_id] = status
    values: list[Any] = []
    values.extend(collect.get("verifyTaskIds") or [])
    for key in ("verifyTaskId", "taskId"):
        value = collect.get(key)
        if value:
            values.insert(0, value)
    resolved = collect.get("resolvedTask") or {}
    if resolved.get("taskId"):
        values.append(resolved.get("taskId"))
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        known_status = status_by_task_id.get(text)
        if known_status and known_status not in {"SUCCESS", "SUCCEEDED"}:
            continue
        seen.add(text)
        result.append(text)
    return result


def result_task_ids(result: YdzCollectResult) -> list[str]:
    return result.task_ids()


def has_result_task_id(result: YdzCollectResult) -> bool:
    return bool(result_task_ids(result))


def format_task_ids(task_ids: list[str]) -> str:
    return "、".join(task_ids)


def should_force_collect(args: argparse.Namespace, collect: dict[str, Any] | None = None) -> bool:
    collect = collect or {}
    if bool(getattr(args, "force", False)):
        return True
    if bool(getattr(args, "reuse_collected_task", False)):
        return False
    return not bool(collect_task_ids(collect))


def verification_subprocess_timeout(args: argparse.Namespace) -> int:
    explicit = int(getattr(args, "verify_timeout", 0) or 0)
    if explicit > 0:
        return explicit
    if bool(getattr(args, "skip_browser", False)):
        return 120
    tax_timeout = int(getattr(args, "tax_timeout", 600) or 600)
    return max(300, min(900, tax_timeout + 180))


def submit_collect_batch(
    args: argparse.Namespace,
    tax_nos: list[str],
    state: dict[str, Any],
    run_dir: Path,
) -> dict[str, YdzCollectResult]:
    submitted_results: dict[str, YdzCollectResult] = {}
    try:
        with open_ydz_session(args, {"kind": "batch-ydz-submit", "runId": state["runId"], "period": args.period}) as (
            session,
            _resolver,
            collector,
        ):
            retried_invalid_signature = False
            for tax_no in tax_nos:
                item = state["items"][tax_no]
                collect = item.get("collect") or {}
                force_collect = should_force_collect(args, collect)
                existing_task_ids = collect_task_ids(collect)
                if existing_task_ids and not force_collect:
                    LOGGER.info("Skipping collection for %s; taskId already resolved: %s", tax_no, format_task_ids(existing_task_ids))
                    continue
                LOGGER.info("Submitting Yidaizhang collection for %s/%s", tax_no, args.period)
                try:
                    try:
                        result = collector.submit_collect_tax_no(tax_no=tax_no, period=args.period, force=force_collect)
                    except Exception as exc:
                        if not is_ydz_invalid_signature_error(exc) or retried_invalid_signature:
                            raise
                        LOGGER.warning(
                            "Yidaizhang login signature is invalid; refreshing login state and retrying once."
                        )
                        username, password = get_env_credentials()
                        page = session.refresh_login_state(
                            username=username,
                            password=password,
                            enterprise=args.enterprise,
                        )
                        collector.api = YdzApi(page)
                        retried_invalid_signature = True
                        result = collector.submit_collect_tax_no(tax_no=tax_no, period=args.period, force=force_collect)
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
            if collect_task_ids(collect) and not should_force_collect(args, collect):
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
                chrome_path=self.args.chrome_path,
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
                if has_result_task_id(result):
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
                if is_result_ready_for_task_resolution(result):
                    before = result_task_ids(result)
                    resolve_task_id_for_result(resolver, tax_no, result, state, run_dir)
                    did_resolve = did_resolve or bool(result_task_ids(result) and result_task_ids(result) != before)
                elif str(result.status or "").upper() == "NO_NEED_COLLECTED":
                    result.terminal = True
                    state["items"][tax_no]["collect"] = result.to_dict()
                    set_item_stage(state, run_dir, tax_no, "collect_no_need", status="success", message="本期无需取数。")
                elif result.terminal:
                    set_item_stage(state, run_dir, tax_no, "collect_terminal", status="running", message=f"取数终态：{result.status}")
                elif result.submitted and not result.manual_required:
                    set_item_stage(state, run_dir, tax_no, "collect_poll_retry", status="running", message=f"当前取数状态：{result.status}")
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
        if not has_result_task_id(result) and result.submitted and not result.terminal and not result.manual_required
    }


def has_collect_poll_work(results: dict[str, YdzCollectResult]) -> bool:
    for result in results.values():
        if has_result_task_id(result):
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
    for item_key in verification_item_keys(tax_nos, state):
        item = state["items"].get(item_key) or {}
        task_ids = item_verification_task_ids(item)
        for task_id in task_ids:
            if task_id in verified_task_ids:
                continue
            if rerun_verified or not task_verify_status(item, task_id):
                return True
    return False


def verification_item_keys(tax_nos: list[str], state: dict[str, Any]) -> list[str]:
    items = state.get("items") or {}
    result: list[str] = []
    seen: set[str] = set()

    def add(key: str) -> None:
        if key in items and key not in seen:
            seen.add(key)
            result.append(key)

    for tax_no in tax_nos:
        add(tax_no)
        parent = items.get(tax_no) or {}
        for key in parent.get("multiTaskItemKeys") or []:
            add(str(key))
        prefix = f"{tax_no}__task__"
        for key, item in items.items():
            if key in seen:
                continue
            if item.get("parentTaxNo") == tax_no or key.startswith(prefix):
                add(key)
    return result


def task_verify_status(item: dict[str, Any], task_id: str) -> str:
    task_verify = task_verify_entry(item, task_id)
    if task_verify:
        return str(task_verify.get("status") or "")
    verify = item.get("verify") or {}
    task_ids = collect_task_ids(item.get("collect") or {})
    if len(task_ids) <= 1:
        return str(verify.get("status") or "")
    return ""


def item_verification_task_ids(item: dict[str, Any]) -> list[str]:
    collect = item.get("collect") or {}
    task_ids = collect_task_ids(collect)
    if item.get("multiTaskItemKeys") and collect.get("verifyTaskId"):
        return [str(collect.get("verifyTaskId"))]
    return task_ids


def task_verify_entry(item: dict[str, Any], task_id: str) -> dict[str, Any]:
    verify_tasks = item.get("verifyTasks") or {}
    if isinstance(verify_tasks, dict):
        entry = verify_tasks.get(str(task_id)) or {}
        return entry if isinstance(entry, dict) else {}
    if isinstance(verify_tasks, list):
        for entry in verify_tasks:
            if isinstance(entry, dict) and str(entry.get("taskId") or "") == str(task_id):
                return entry
    return {}


def set_task_verify_entry(item: dict[str, Any], task_id: str, verify: dict[str, Any]) -> None:
    verify_tasks = item.setdefault("verifyTasks", {})
    if not isinstance(verify_tasks, dict):
        verify_tasks = {}
        item["verifyTasks"] = verify_tasks
    verify_tasks[str(task_id)] = {**verify, "taskId": str(task_id)}


def aggregate_verify_status(task_results: list[dict[str, Any]]) -> dict[str, Any]:
    if not task_results:
        return {}
    return_code = max(int(result.get("returnCode") or 0) for result in task_results)
    statuses = [str(result.get("status") or "") for result in task_results]
    if any(status == "failed" for status in statuses):
        status = "failed"
    elif any(status == "completed_with_differences" for status in statuses):
        status = "completed_with_differences"
    elif any(status == "skipped" for status in statuses):
        status = "skipped"
    elif all(status == "success" for status in statuses):
        status = "success"
    else:
        status = statuses[-1] or "unknown"
    reasons = unique_texts([str(result.get("reason") or "") for result in task_results if result.get("reason")])
    report_paths: list[str] = []
    for result in task_results:
        report_paths.extend(str(path) for path in result.get("reportPaths") or [] if path)
    latest = task_results[-1]
    return {
        "status": status,
        "returnCode": return_code,
        "reason": "；".join(reasons[:3]),
        "reportDir": latest.get("reportDir") or "",
        "summaryPath": latest.get("summaryPath") or "",
        "reportPaths": unique_texts(report_paths),
        "stdoutLog": latest.get("stdoutLog") or "",
        "stderrLog": latest.get("stderrLog") or "",
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }


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
        if not has_result_task_id(result) and result.submitted and not result.terminal and not result.manual_required
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

    for tax_no, result in list(pending.items()):
        resolve_task_id_for_result(resolver, tax_no, result, state, run_dir)
        if has_result_task_id(result):
            result.manual_required = False
            result.terminal = True
            state["items"][tax_no]["collect"] = result.to_dict()
            pending.pop(tax_no, None)
    for tax_no, result in pending.items():
        result.manual_required = True
        result.errors.append(f"Timed out waiting for collection terminal status; last status={result.status}.")
        state["items"][tax_no]["collect"] = result.to_dict()
        set_item_stage(state, run_dir, tax_no, "collect_timeout", status="manual", reason="取数任务长时间未完成，当前仍为取数中。")
    if pending:
        write_state(state, run_dir)


def is_result_ready_for_task_resolution(result: YdzCollectResult) -> bool:
    if has_result_task_id(result):
        return False
    if str(result.status or "").upper() == "NO_NEED_COLLECTED":
        return False
    if result.manual_required and not result.submitted:
        return False
    return bool(result.terminal or result.status in TERMINAL_COLLECT_STATUSES)


def resolved_task_payload(task: Any) -> dict[str, Any]:
    return {
        "taskId": task.task_id,
        "taskTypeId": task.task_type_id,
        "taskTypeName": task.task_type_name,
        "status": task.status,
        "period": task.period,
        "createdStamp": task.created_stamp,
    }


def apply_resolved_tasks_to_result(resolver: VerifyTaskResolver, result: YdzCollectResult) -> None:
    result.verify_task_ids = [task.task_id for task in resolver.last_tasks]
    result.verify_task_id = result.verify_task_ids[0] if result.verify_task_ids else None
    result.resolved_tasks = [resolved_task_payload(task) for task in resolver.last_tasks]
    result.resolved_task = result.resolved_tasks[0] if result.resolved_tasks else None


def sync_multi_task_items(state: dict[str, Any], parent_key: str, result: YdzCollectResult) -> None:
    task_ids = result_task_ids(result)
    items = state.setdefault("items", {})
    parent_item = items.setdefault(
        parent_key,
        {"taxNo": result.tax_no, "period": result.period, "collect": None, "verify": None},
    )
    old_keys = [str(key) for key in parent_item.get("multiTaskItemKeys") or []]
    new_keys: list[str] = []
    if len(task_ids) <= 1:
        for key in old_keys:
            if (items.get(key) or {}).get("source") == "ydz_multi_task":
                items.pop(key, None)
        parent_item["multiTaskItemKeys"] = []
        return

    resolved_by_id = {
        str(task.get("taskId") or ""): task
        for task in result.resolved_tasks
        if str(task.get("taskId") or "")
    }
    base_collect = result.to_dict()
    for task_id in task_ids[1:]:
        key = multi_task_item_key(parent_key, task_id)
        new_keys.append(key)
        collect = copy.deepcopy(base_collect)
        resolved_task = resolved_by_id.get(task_id) or {"taskId": task_id}
        collect["verifyTaskId"] = task_id
        collect["verifyTaskIds"] = [task_id]
        collect["resolvedTask"] = resolved_task
        collect["resolvedTasks"] = [resolved_task]
        item = items.setdefault(
            key,
            {
                "taxNo": result.tax_no,
                "period": result.period,
                "collect": None,
                "verify": None,
            },
        )
        item["taxNo"] = result.tax_no
        item["period"] = result.period
        item["collect"] = collect
        item["source"] = "ydz_multi_task"
        item["parentTaxNo"] = parent_key
        item["parentTaskIds"] = task_ids
        item.setdefault("verify", None)

    for key in old_keys:
        if key not in new_keys and (items.get(key) or {}).get("source") == "ydz_multi_task":
            items.pop(key, None)
    parent_item["multiTaskItemKeys"] = new_keys


def multi_task_item_key(parent_key: str, task_id: str) -> str:
    safe_task_id = "".join(ch if ch.isalnum() else "_" for ch in str(task_id)).strip("_") or "task"
    return f"{parent_key}__task__{safe_task_id}"


def resolve_task_id_for_result(
    resolver: VerifyTaskResolver,
    tax_no: str,
    result: YdzCollectResult,
    state: dict[str, Any],
    run_dir: Path,
) -> None:
    if has_result_task_id(result):
        return
    try:
        resolver.resolve_all(result.tax_no, result.period, submitted_at=result.submitted_at)
        apply_resolved_tasks_to_result(resolver, result)
    except Exception as exc:
        LOGGER.warning("Could not resolve collect taskId for %s/%s: %s", result.tax_no, result.period, exc)
        result.warnings.append(f"Could not resolve collect taskId: {exc}")
    state["items"][tax_no]["collect"] = result.to_dict()
    sync_multi_task_items(state, tax_no, result)
    resolved_ids = result_task_ids(result)
    set_item_stage(
        state,
        run_dir,
        tax_no,
        "task_resolved" if resolved_ids else "task_unresolved",
        status="running" if resolved_ids else "manual",
        message=f"已解析 taskId：{format_task_ids(resolved_ids)}" if resolved_ids else "",
        reason="" if resolved_ids else "后台未解析到取数 taskId。",
    )
    write_state(state, run_dir)


def resolve_task_ids(
    resolver: VerifyTaskResolver,
    results: dict[str, YdzCollectResult],
    state: dict[str, Any],
    run_dir: Path,
) -> None:
    for tax_no, result in results.items():
        if has_result_task_id(result):
            continue
        try:
            resolver.resolve_all(result.tax_no, result.period, submitted_at=result.submitted_at)
            apply_resolved_tasks_to_result(resolver, result)
        except Exception as exc:
            LOGGER.warning("Could not resolve collect taskId for %s/%s: %s", result.tax_no, result.period, exc)
            result.warnings.append(f"Could not resolve collect taskId: {exc}")
        state["items"][tax_no]["collect"] = result.to_dict()
        sync_multi_task_items(state, tax_no, result)
        resolved_ids = result_task_ids(result)
        set_item_stage(
            state,
            run_dir,
            tax_no,
            "task_resolved" if resolved_ids else "task_unresolved",
            status="running" if resolved_ids else "manual",
            message=f"已解析 taskId：{format_task_ids(resolved_ids)}" if resolved_ids else "",
            reason="" if resolved_ids else "后台未解析到取数 taskId。",
        )
        write_state(state, run_dir)


def run_verify_phase(
    args: argparse.Namespace,
    tax_nos: list[str],
    state: dict[str, Any],
    run_dir: Path,
    final: bool = False,
    active_coverage_target_key: str = "",
) -> int:
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    exit_code = 0

    for item_key in verification_item_keys(tax_nos, state):
        item = state["items"][item_key]
        collect = item.get("collect") or {}
        task_ids = item_verification_task_ids(item)
        display_tax_no = str(item.get("taxNo") or item_key)
        if not task_ids:
            if not final:
                continue
            no_need_collect = str(collect.get("status") or "").upper() == "NO_NEED_COLLECTED"
            reason = no_task_skip_reason(item)
            item["verify"] = {
                "status": "skipped",
                "reason": reason,
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            if no_need_collect:
                set_item_stage(state, run_dir, item_key, "collect_no_need", status="success", message="本期无需取数。")
            else:
                set_item_stage(state, run_dir, item_key, "task_unresolved", status="manual", reason=reason)
            write_state(state, run_dir)
            if not no_need_collect:
                exit_code = max(exit_code, 2)
            continue

        task_results: list[dict[str, Any]] = []
        for task_id in task_ids:
            task_verify = task_verify_entry(item, task_id)
            aggregate_verify = item.get("verify") or {}
            if str(task_id) in verified_task_ids_this_run(args):
                LOGGER.info("Skipping verification for %s taskId=%s; already verified in this batch run", display_tax_no, task_id)
                duplicate_reason = "同一批次已验证相同 taskId，已跳过重复执行。"
                if not task_verify and not aggregate_verify.get("status"):
                    verify_record = {
                        "status": "skipped",
                        "returnCode": 0,
                        "reason": duplicate_reason,
                        "reportDir": str(Path("output") / "reports" / task_id),
                        "summaryPath": "",
                        "reportPaths": [],
                        "updatedAt": datetime.now().isoformat(timespec="seconds"),
                    }
                    set_task_verify_entry(item, task_id, verify_record)
                    item["verify"] = aggregate_verify_status(list((item.get("verifyTasks") or {}).values()))
                    set_item_stage(state, run_dir, item_key, "verified", status="skipped", reason=duplicate_reason)
                    write_state(state, run_dir)
                continue
            if task_verify.get("status") and not args.rerun_verified:
                LOGGER.info("Skipping verification for %s taskId=%s; already recorded status=%s", display_tax_no, task_id, task_verify["status"])
                task_results.append(task_verify)
                continue
            if aggregate_verify.get("status") and len(task_ids) == 1 and not args.rerun_verified:
                LOGGER.info("Skipping verification for %s; already recorded status=%s", display_tax_no, aggregate_verify["status"])
                task_results.append(aggregate_verify)
                continue

            if bool(collect.get("manualRequired")):
                reason = collect_failure_reason(collect) or "Collection requires manual handling; verification was skipped."
                verify_record = {
                    "status": "skipped",
                    "returnCode": 2,
                    "reason": reason,
                    "reportDir": str(Path("output") / "reports" / task_id),
                    "summaryPath": "",
                    "reportPaths": [],
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
                set_task_verify_entry(item, task_id, verify_record)
                item["verify"] = aggregate_verify_status(list((item.get("verifyTasks") or {}).values()))
                set_item_stage(state, run_dir, item_key, "skipped", status="manual", reason=reason)
                write_state(state, run_dir)
                exit_code = max(exit_code, 2)
                task_results.append(verify_record)
                continue

            LOGGER.info("Running verification for %s taskId=%s", display_tax_no, task_id)
            set_item_stage(state, run_dir, item_key, "verifying", status="running", message=f"开始验证 taskId={task_id}")
            write_state(state, run_dir)
            stdout_path = logs_dir / f"{item_key}_{task_id}.out.log"
            stderr_path = logs_dir / f"{item_key}_{task_id}.err.log"
            cbj_kind = ""
            if item_requests_cbj_verification(item):
                cbj_kind = detect_cbj_task(task_id) or "cbj"
            report_dir = Path("output") / "reports" / task_id
            reused_result = reuse_existing_verify_result(args, task_id, cbj_kind)
            if reused_result:
                verify_record = {
                    **reused_result,
                    "reportDir": str(report_dir),
                    "reportPaths": reused_result.get("reportPaths") or [],
                    "stdoutLog": str(stdout_path),
                    "stderrLog": str(stderr_path),
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
                set_task_verify_entry(item, task_id, verify_record)
                task_results.append(verify_record)
                item["verify"] = aggregate_verify_status(list((item.get("verifyTasks") or {}).values()))
                set_item_stage(
                    state,
                    run_dir,
                    item_key,
                    "verified",
                    status="success" if reused_result["returnCode"] == 0 else "warning",
                    message="Reused existing verification report.",
                )
                write_state(state, run_dir)
                exit_code = max(exit_code, reused_result["returnCode"])
                mark_task_id_verified_this_run(args, str(task_id))
                continue
            if cbj_kind:
                cbj_mode = resolve_cbj_mode(args.cbj_mode, item, task_id=task_id)
                LOGGER.info("Detected CBJ task for %s taskId=%s; mode=%s resolvedMode=%s", display_tax_no, task_id, args.cbj_mode, cbj_mode)
                verify_result = run_cbj_verify(args, task_id, stdout_path, stderr_path, cbj_mode)
                verify_record = {
                    "status": verify_result["status"],
                    "returnCode": verify_result["returnCode"],
                    "mode": verify_result["mode"],
                    "reason": verify_result.get("reason", ""),
                    "reportDir": str(Path("output") / "reports" / task_id),
                    "summaryPath": verify_result.get("summaryPath", ""),
                    "reportPath": verify_result.get("reportPath", ""),
                    "reportPaths": [verify_result.get("reportPath", "")] if verify_result.get("reportPath") else [],
                    "stdoutLog": str(stdout_path),
                    "stderrLog": str(stderr_path),
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
                set_task_verify_entry(item, task_id, verify_record)
                task_results.append(verify_record)
                item["verify"] = aggregate_verify_status(list((item.get("verifyTasks") or {}).values()))
                set_item_stage(
                    state,
                    run_dir,
                    item_key,
                    "verified",
                    status="success" if verify_result["returnCode"] == 0 else "warning",
                    message="残保金验证完成。",
                )
                write_state(state, run_dir)
                exit_code = max(exit_code, verify_result["returnCode"])
                mark_task_id_verified_this_run(args, str(task_id))
                continue

            verify_targets = verify_targets_for_item(args.targets, item, active_coverage_target_key)
            if verify_targets != args.targets:
                LOGGER.info(
                    "Restricting backend supplement verification for %s taskId=%s target=%s to forms=%s",
                    display_tax_no,
                    task_id,
                    active_coverage_target_key or ",".join(item.get("coverageSupplementTargets") or []),
                    verify_targets,
                )

            cmd = [
                sys.executable,
                "main.py",
                "--task-id",
                task_id,
                "--targets",
                verify_targets,
                "--cdp-port",
                str(args.cdp_port),
                "--chrome-path",
                args.chrome_path,
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
            declaration_status_override = declaration_status_override_for_coverage_target(active_coverage_target_key)
            if declaration_status_override:
                cmd.extend(["--declaration-status-override", declaration_status_override])

            verify_start_ts = time.time()
            verify_timeout = verification_subprocess_timeout(args)
            timeout_reason = ""
            with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
                try:
                    proc = subprocess.run(
                        cmd,
                        stdout=stdout,
                        stderr=stderr,
                        timeout=verify_timeout if verify_timeout > 0 else None,
                    )
                except subprocess.TimeoutExpired:
                    timeout_reason = (
                        f"Verification subprocess timed out after {verify_timeout}s; "
                        f"taskId={task_id}, forms={verify_targets}."
                    )
                    LOGGER.warning("%s", timeout_reason)
                    stderr.write(f"\nTimeoutError: {timeout_reason}\n")

                    class TimedOutProcess:
                        returncode = 124

                    proc = TimedOutProcess()

            report_since_ts = max(0, verify_start_ts - 2)
            current_reports = load_compare_reports(task_id, since_ts=report_since_ts)
            current_report_paths = [
                str(report.get("_sourcePath"))
                for report in current_reports
                if report.get("_sourcePath")
            ]
            summary_path = latest_summary_path(report_dir, since_ts=report_since_ts)
            if summary_path:
                status = "success" if proc.returncode == 0 else "completed_with_differences"
                return_code = proc.returncode
                stage_status = "success" if proc.returncode == 0 else "warning"
                reason = "" if proc.returncode == 0 else compare_report_reason(task_id, reports=current_reports) or tail_error_reason(stderr_path)
            elif proc.returncode == 0:
                status = "skipped"
                return_code = 2
                stage_status = "manual"
                reason = no_targets_verify_reason(stdout_path, stderr_path)
            else:
                reason = timeout_reason or tail_error_reason(stderr_path) or tail_error_reason(stdout_path)
                if is_no_targets_verify_reason(reason):
                    status = "skipped"
                    stage_status = "manual"
                else:
                    status = "failed"
                    stage_status = "failed"
                return_code = proc.returncode
            verify_record = {
                "status": status,
                "returnCode": return_code,
                "reason": reason,
                "reportDir": str(report_dir),
                "summaryPath": str(summary_path) if summary_path else "",
                "reportPaths": current_report_paths,
                "stdoutLog": str(stdout_path),
                "stderrLog": str(stderr_path),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            set_task_verify_entry(item, task_id, verify_record)
            task_results.append(verify_record)
            item["verify"] = aggregate_verify_status(list((item.get("verifyTasks") or {}).values()))
            set_item_stage(
                state,
                run_dir,
                item_key,
                "verified",
                status=stage_status,
                message="验证完成。",
                reason=reason,
            )
            write_state(state, run_dir)
            exit_code = max(exit_code, return_code)
            mark_task_id_verified_this_run(args, str(task_id))

        if task_results:
            item["verify"] = aggregate_verify_status(task_results)
            if final and str(item.get("stage") or "") not in {"verified", "collect_no_need"}:
                set_item_stage(
                    state,
                    run_dir,
                    item_key,
                    "verified",
                    status=stage_status_for_item(item),
                    reason=str((item.get("verify") or {}).get("reason") or ""),
                )
            write_state(state, run_dir)

    return exit_code


def verify_supplement_target_candidates(
    *,
    args: argparse.Namespace,
    state: dict[str, Any],
    run_dir: Path,
    coverage_targets: list[Any],
    target: Any,
    target_candidates: list[Any],
    attempts: list[dict[str, Any]],
    applied_keys: list[str],
    covered_keys: list[str],
    verify_exit: int,
) -> int:
    target_key = str(getattr(target, "key", "") or "")
    if not target_key or target_key in {str(key) for key in covered_keys}:
        return verify_exit
    if not target_candidates:
        return verify_exit

    for index, candidate in enumerate(target_candidates, start=1):
        current_applied_keys = apply_supplement_candidates_to_state(state, [candidate], enterprise=args.enterprise)
        if not current_applied_keys:
            attempts.append(
                build_supplement_attempt_record(
                    candidate,
                    target,
                    index,
                    len(target_candidates),
                    item_key="",
                    status="failed",
                    step="write supplement task",
                    reason="Backend supplement candidate could not be written into batch state.",
                )
            )
            state["coverageSupplement"]["attempts"] = attempts
            write_state(state, run_dir)
            continue

        item_key = current_applied_keys[0]
        append_unique(applied_keys, item_key)
        item = state["items"].get(item_key) or {}
        task_id = ((item.get("collect") or {}).get("verifyTaskId")) or ""
        attempt = build_supplement_attempt_record(
            candidate,
            target,
            index,
            len(target_candidates),
            item_key=item_key,
            status="verifying",
            step="verify task",
            reason="",
        )
        attempts.append(attempt)
        state["coverageSupplement"]["appliedItemKeys"] = applied_keys
        state["coverageSupplement"]["attempts"] = attempts
        set_item_stage(
            state,
            run_dir,
            item_key,
            "task_resolved",
            status="running",
            message=(
                f"coverage supplement candidate {index}/{len(target_candidates)} taskId={task_id}"
                if task_id
                else "coverage supplement candidate is waiting for verification task."
            ),
        )
        write_state(state, run_dir)

        verify_exit = max(
            verify_exit,
            run_verify_phase(
                args,
                [item_key],
                state,
                run_dir,
                final=True,
                active_coverage_target_key=target_key,
            ),
        )
        coverage_after = write_coverage_status(run_dir, targets=coverage_targets)
        item_after = state.get("items", {}).get(item_key) or {}
        matrix_covered = coverage_target_is_covered(coverage_after, target_key)
        covered = matrix_covered and supplement_item_has_clean_verification(item_after, task_id)
        update_supplement_attempt_record(
            attempt,
            item_after,
            covered,
            task_id=task_id,
            matrix_covered=matrix_covered,
        )
        state["coverageSupplement"]["attempts"] = attempts
        if covered:
            append_unique(covered_keys, target_key)
            state["coverageSupplement"]["coveredKeys"] = covered_keys
            write_state(state, run_dir)
            break
        write_state(state, run_dir)

    return verify_exit


def run_coverage_supplement_phase(args: argparse.Namespace, state: dict[str, Any], run_dir: Path) -> int:
    previous_supplement = state.get("coverageSupplement") if isinstance(state.get("coverageSupplement"), dict) else {}
    excluded_task_ids_by_target = merge_excluded_task_id_maps(
        supplement_excluded_task_ids_from_attempts((previous_supplement or {}).get("attempts") or []),
        supplement_excluded_task_ids_from_state(state),
    )
    excluded_candidate_count = sum(len(task_ids) for task_ids in excluded_task_ids_by_target.values())
    coverage_targets = coverage_targets_for_state(state)
    coverage = write_coverage_status(run_dir, targets=coverage_targets)
    missing_rows = coverage.get("missingTargets") or []
    if not missing_rows:
        state["coverageSupplement"] = {
            "status": "not_needed",
            "message": "当前批次已覆盖全部目标。",
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 0

    targets_by_key = {target.key: target for target in coverage_targets}
    missing_keys = {str(row.get("key") or "") for row in missing_rows}
    missing_targets = [target for key, target in targets_by_key.items() if key in missing_keys]
    raw_requested_targets = str(getattr(args, "coverage_supplement_targets", "") or "").strip()
    requested_target_keys = parse_coverage_supplement_target_keys(raw_requested_targets)
    if raw_requested_targets and not requested_target_keys:
        state["coverageSupplement"] = {
            "status": "failed",
            "message": "No valid --coverage-supplement-targets were provided.",
            "missingKeys": sorted(missing_keys),
            "requestedTargetKeys": [],
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 2
    if requested_target_keys:
        requested_key_set = set(requested_target_keys)
        missing_targets = [target for target in missing_targets if target.key in requested_key_set]
        if not missing_targets:
            state["coverageSupplement"] = {
                "status": "not_needed",
                "message": "Requested supplement targets are already covered or outside the current coverage scope.",
                "missingKeys": sorted(missing_keys),
                "requestedTargetKeys": requested_target_keys,
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
            write_state(state, run_dir)
            return 0
    if not missing_targets:
        state["coverageSupplement"] = {
            "status": "failed",
            "message": "覆盖缺口无法映射到当前支持税种目标。",
            "missingKeys": sorted(missing_keys),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 2

    end_time = datetime.now()
    lookback_days = max(0, int(getattr(args, "coverage_supplement_lookback_days", 0) or 0))
    cit_lookback_days = max(0, int(getattr(args, "coverage_supplement_cit_lookback_days", 100) or 0))
    configured_max_candidates = max(1, int(getattr(args, "coverage_supplement_max_candidates", 3) or 3))
    max_candidates = effective_supplement_max_candidates(configured_max_candidates, missing_targets)
    login_preflight_enabled = should_preflight_standard_supplement_candidates(missing_targets)
    candidate_pool_limit = (
        max_candidates * SUPPLEMENT_LOGIN_PREFLIGHT_POOL_MULTIPLIER
        if login_preflight_enabled
        else max_candidates
    )
    search_windows = supplement_time_windows(end_time, lookback_days)
    start_time = min((window[0] for window in search_windows), default=end_time)
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
        "lookbackDays": lookback_days,
        "citLookbackDays": cit_lookback_days,
        "maxCandidatesPerTarget": max_candidates,
        "candidatePoolLimitPerTarget": candidate_pool_limit,
        "loginPreflightEnabled": login_preflight_enabled,
        "excludedCandidateCount": excluded_candidate_count,
        "excludedCandidateTargets": sorted(excluded_task_ids_by_target),
        "requestedTargetKeys": requested_target_keys,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    write_state(state, run_dir)

    diagnostics: list[dict[str, Any]] = []
    candidates: list[Any] = []
    raw_backend_candidate_count = 0
    login_preflight_records: list[dict[str, Any]] = []
    login_preflight_refill_count = 0
    def supplement_progress(event: dict[str, Any]) -> None:
        state.setdefault("coverageSupplement", {})["progress"] = {
            **event,
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        event_name = event.get("event")
        if event_name == "query_start":
            query_label = f"{event.get('queryField') or 'taxTypeId'}={event.get('queryValue') or event.get('taxTypeId') or ''}"
            LOGGER.info(
                "Coverage supplement query %s/%s: %s taxpayerType=%s targets=%s",
                event.get("groupIndex"),
                event.get("groupCount"),
                query_label,
                event.get("taxPayerType") or "",
                ", ".join(event.get("targetKeys") or []),
            )
        elif event_name == "query_done":
            query_label = f"{event.get('queryField') or 'taxTypeId'}={event.get('queryValue') or event.get('taxTypeId') or ''}"
            LOGGER.info(
                "Coverage supplement query %s/%s done: %s queried=%s elapsed=%ss",
                event.get("groupIndex"),
                event.get("groupCount"),
                query_label,
                event.get("queriedCount"),
                event.get("elapsedSeconds"),
            )
        elif event_name == "target_done":
            diagnostic = event.get("diagnostic") or {}
            LOGGER.info(
                "Coverage supplement target %s: matched=%s reason=%s statusCounts=%s",
                diagnostic.get("targetKey"),
                diagnostic.get("matchedTaskId") or "",
                diagnostic.get("reason") or "",
                diagnostic.get("statusCounts") or {},
            )
        elif event_name == "timeout":
            query_label = f"{event.get('queryField') or 'taxTypeId'}={event.get('queryValue') or event.get('taxTypeId') or ''}"
            LOGGER.warning(
                "Coverage supplement search timed out at query %s/%s %s",
                event.get("groupIndex"),
                event.get("groupCount"),
                query_label,
            )
        write_state(state, run_dir)

    try:
        with ProcessLock(
            DEFAULT_TAX_BROWSER_LOCK,
            timeout=args.browser_lock_timeout,
            owner={"kind": "coverage-supplement", "runId": state["runId"], "period": args.period},
        ):
            session = YdzSession(
                cdp_port=args.cdp_port,
                chrome_path=args.chrome_path,
                user_data_dir=args.user_data_dir,
                plugin_path=args.plugin_path,
                launch_if_needed=True,
            )
            try:
                context = session.connect()
                admin_query = ChanjetAdminTaskQuery(context)
                planner = CoverageSupplementPlanner(admin_query)
                candidates, diagnostics = find_supplement_candidates_for_targets(
                    planner,
                    missing_targets,
                    end_time=end_time,
                    base_period=str(args.period or state.get("period") or ""),
                    lookback_days=lookback_days,
                    cit_lookback_days=cit_lookback_days,
                    page_size=int(getattr(args, "coverage_supplement_page_size", 500) or 500),
                    max_candidates_per_target=candidate_pool_limit,
                    excluded_task_ids_by_target=excluded_task_ids_by_target,
                    timeout_seconds=int(getattr(args, "coverage_supplement_timeout", 600) or 0),
                    progress=supplement_progress,
                )
                raw_backend_candidate_count = len(candidates)
                if login_preflight_enabled and candidates:
                    candidates, login_preflight_records = preflight_supplement_candidates_login_ready(
                        candidates,
                        admin_query,
                    )
                    preflight_exclusions = supplement_excluded_task_ids_from_preflight(login_preflight_records)
                    if preflight_exclusions:
                        excluded_task_ids_by_target = merge_excluded_task_id_maps(
                            excluded_task_ids_by_target,
                            preflight_exclusions,
                        )
                    last_preflight_records = login_preflight_records
                    while (
                        login_preflight_refill_count < SUPPLEMENT_LOGIN_PREFLIGHT_REFILL_MAX_WAVES
                        and supplement_preflight_refill_needed(
                            missing_targets,
                            candidates,
                            max_candidates=max_candidates,
                            preflight_records=last_preflight_records,
                        )
                    ):
                        login_preflight_refill_count += 1
                        refill_candidates, refill_diagnostics = find_supplement_candidates_for_targets(
                            planner,
                            missing_targets,
                            end_time=end_time,
                            base_period=str(args.period or state.get("period") or ""),
                            lookback_days=lookback_days,
                            cit_lookback_days=cit_lookback_days,
                            page_size=int(getattr(args, "coverage_supplement_page_size", 500) or 500),
                            max_candidates_per_target=candidate_pool_limit,
                            excluded_task_ids_by_target=merge_excluded_task_id_maps(
                                excluded_task_ids_by_target,
                                supplement_task_ids_by_target_from_candidates(candidates),
                            ),
                            timeout_seconds=int(getattr(args, "coverage_supplement_timeout", 600) or 0),
                            progress=supplement_progress,
                        )
                        raw_backend_candidate_count += len(refill_candidates)
                        diagnostics = merge_supplement_diagnostics([*diagnostics, *refill_diagnostics])
                        if not refill_candidates:
                            break
                        refill_candidates, refill_records = preflight_supplement_candidates_login_ready(
                            refill_candidates,
                            admin_query,
                        )
                        login_preflight_records.extend(refill_records)
                        last_preflight_records = refill_records
                        refill_exclusions = supplement_excluded_task_ids_from_preflight(refill_records)
                        if refill_exclusions:
                            excluded_task_ids_by_target = merge_excluded_task_id_maps(
                                excluded_task_ids_by_target,
                                refill_exclusions,
                            )
                        previous_candidate_count = len(candidates)
                        candidates = dedupe_supplement_candidates([*candidates, *refill_candidates])
                        if len(candidates) == previous_candidate_count and not refill_exclusions:
                            break
            finally:
                session.close()
    except Exception as exc:
        message = f"后台补齐查询失败：{compact_message(exc, limit=260)}"
        LOGGER.warning(message)
        state["coverageSupplement"] = {
            "status": "failed",
            "message": message,
            "missingKeys": [target.key for target in missing_targets],
            "requestedTargetKeys": requested_target_keys,
            "diagnostics": diagnostics,
            "loginPreflight": login_preflight_records,
            "preflightRefillCount": login_preflight_refill_count,
            "excludedCandidateCount": sum(len(task_ids) for task_ids in excluded_task_ids_by_target.values()),
            "excludedCandidateTargets": sorted(excluded_task_ids_by_target),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 2

    can_try_ydz_cit_refresh = bool(getattr(args, "coverage_supplement_refresh_cit_from_ydz", False)) and any(
        str(getattr(target, "tax_type", "") or "") == "CIT_A" for target in missing_targets
    )
    if not candidates and not can_try_ydz_cit_refresh:
        message = "后台未找到符合缺口税种和申报状态的成功取数任务。"
        LOGGER.info(message)
        state["coverageSupplement"] = {
            "status": "no_candidates",
            "message": message,
            "missingKeys": [target.key for target in missing_targets],
            "requestedTargetKeys": requested_target_keys,
            "diagnostics": diagnostics,
            "candidateCount": 0,
            "backendCandidateCount": raw_backend_candidate_count,
            "preflightReadyCandidateCount": len(candidates),
            "preflightRefillCount": login_preflight_refill_count,
            "loginPreflight": login_preflight_records,
            "excludedCandidateCount": sum(len(task_ids) for task_ids in excluded_task_ids_by_target.values()),
            "excludedCandidateTargets": sorted(excluded_task_ids_by_target),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 0

    grouped_candidates = group_supplement_candidates_by_target(candidates, max_candidates=max_candidates)
    if can_try_ydz_cit_refresh:
        grouped_candidates = ensure_cit_refresh_template_candidates(
            grouped_candidates,
            missing_targets=missing_targets,
            period=str(args.period or state.get("period") or ""),
        )
    ydz_refresh_records: list[dict[str, Any]] = []
    if bool(getattr(args, "coverage_supplement_refresh_cit_from_ydz", False)):
        state["coverageSupplement"].update(
            {
                "status": "refreshing_ydz_collect",
                "message": "正在为企业所得税 A 类补齐候选尝试发起易代账新取数。",
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
        )
        write_state(state, run_dir)
        grouped_candidates, ydz_refresh_records = refresh_cit_supplement_candidates_from_ydz(
            args=args,
            grouped_candidates=grouped_candidates,
            max_candidates=max_candidates,
        )
        grouped_candidates = filter_supplement_candidates_with_task(grouped_candidates)
    effective_candidate_count = sum(len(values) for values in grouped_candidates.values())
    fresh_ydz_candidate_count = count_fresh_supplement_candidates(grouped_candidates)
    if effective_candidate_count <= 0:
        message = "No verifiable supplement taskId was produced by backend search or current-enterprise YDZ refresh."
        LOGGER.info(message)
        source_readiness = build_supplement_source_readiness(
            missing_targets=missing_targets,
            diagnostics=diagnostics,
            candidates=candidates,
            ydz_refresh_records=ydz_refresh_records,
        )
        state["coverageSupplement"] = {
            "status": "no_candidates",
            "message": message,
            "missingKeys": [target.key for target in missing_targets],
            "requestedTargetKeys": requested_target_keys,
            "diagnostics": diagnostics,
            "loginPreflight": login_preflight_records,
            "sourceReadiness": source_readiness,
            "candidateCount": 0,
            "backendCandidateCount": raw_backend_candidate_count,
            "preflightReadyCandidateCount": len(candidates),
            "preflightRefillCount": login_preflight_refill_count,
            "freshYdzCandidateCount": fresh_ydz_candidate_count,
            "freshYdzRefresh": ydz_refresh_records,
            "excludedCandidateCount": sum(len(task_ids) for task_ids in excluded_task_ids_by_target.values()),
            "excludedCandidateTargets": sorted(excluded_task_ids_by_target),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 0
    applied_keys: list[str] = []
    covered_keys: list[str] = []
    attempts: list[dict[str, Any]] = []
    state["coverageSupplement"] = {
        "status": "applying",
        "message": f"已从后台找到 {len(candidates)} 个候选任务，开始按覆盖缺口逐个重试。",
        "missingKeys": [target.key for target in missing_targets],
        "requestedTargetKeys": requested_target_keys,
        "diagnostics": diagnostics,
        "loginPreflight": login_preflight_records,
        "sourceReadiness": build_supplement_source_readiness(
            missing_targets=missing_targets,
            diagnostics=diagnostics,
            candidates=candidates,
            ydz_refresh_records=ydz_refresh_records,
        ),
        "candidateCount": effective_candidate_count,
        "backendCandidateCount": raw_backend_candidate_count,
        "preflightReadyCandidateCount": len(candidates),
        "preflightRefillCount": login_preflight_refill_count,
        "freshYdzCandidateCount": fresh_ydz_candidate_count,
        "freshYdzRefresh": ydz_refresh_records,
        "maxCandidatesPerTarget": max_candidates,
        "candidatePoolLimitPerTarget": candidate_pool_limit,
        "loginPreflightEnabled": login_preflight_enabled,
        "excludedCandidateCount": sum(len(task_ids) for task_ids in excluded_task_ids_by_target.values()),
        "excludedCandidateTargets": sorted(excluded_task_ids_by_target),
        "startTime": start_time.isoformat(timespec="seconds"),
        "endTime": end_time.isoformat(timespec="seconds"),
        "lookbackDays": lookback_days,
        "citLookbackDays": cit_lookback_days,
        "appliedItemKeys": applied_keys,
        "coveredKeys": covered_keys,
        "attempts": attempts,
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    write_state(state, run_dir)

    verify_exit = 0
    for target in missing_targets:
        verify_exit = verify_supplement_target_candidates(
            args=args,
            state=state,
            run_dir=run_dir,
            coverage_targets=coverage_targets,
            target=target,
            target_candidates=grouped_candidates.get(target.key) or [],
            attempts=attempts,
            applied_keys=applied_keys,
            covered_keys=covered_keys,
            verify_exit=verify_exit,
        )

    coverage_after = write_coverage_status(run_dir, targets=coverage_targets)
    remaining_missing = supplement_remaining_missing_keys(missing_targets, covered_keys)
    verify_exit = supplement_final_verify_exit_code(
        verify_exit=verify_exit,
        remaining_missing=remaining_missing,
        missing_targets=missing_targets,
        covered_keys=covered_keys,
        attempts=attempts,
    )
    state["coverageSupplement"].update(
        {
            "status": "verified",
            "message": f"后台补齐已尝试 {len(attempts)} 个候选任务，覆盖 {len(covered_keys)} 个缺口，仍未覆盖 {len(remaining_missing)} 个缺口。",
            "verifyExitCode": verify_exit,
            "appliedItemKeys": applied_keys,
            "coveredKeys": covered_keys,
            "remainingMissingKeys": remaining_missing,
            "loginPreflight": login_preflight_records,
            "sourceReadiness": build_supplement_source_readiness(
                missing_targets=missing_targets,
                diagnostics=diagnostics,
                candidates=candidates,
                ydz_refresh_records=ydz_refresh_records,
            ),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
    )
    write_state(state, run_dir)
    write_coverage_status(run_dir, targets=coverage_targets)
    return verify_exit


def find_supplement_candidates_for_targets(
    planner: CoverageSupplementPlanner,
    missing_targets: list[Any],
    end_time: datetime,
    base_period: str,
    lookback_days: int,
    cit_lookback_days: int,
    page_size: int,
    max_candidates_per_target: int,
    timeout_seconds: int,
    excluded_task_ids_by_target: dict[str, set[str]] | None = None,
    progress: Any = None,
) -> tuple[list[Any], list[dict[str, Any]]]:
    all_candidates: list[Any] = []
    all_diagnostics: list[dict[str, Any]] = []
    seen_candidate_keys: set[tuple[str, str]] = set()
    candidate_counts: dict[str, int] = {}
    candidate_task_ids_by_target: dict[str, set[str]] = {}
    candidate_tax_nos_by_target: dict[str, set[str]] = {}
    deadline = time.monotonic() + timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
    max_candidates = max(1, int(max_candidates_per_target or 1))

    for targets, period, window_start, window_end, search_scope in supplement_search_batches(
        missing_targets,
        base_period=base_period,
        end_time=end_time,
        lookback_days=lookback_days,
        cit_lookback_days=cit_lookback_days,
    ):
        active_targets = [
            target
            for target in targets
            if candidate_counts.get(str(getattr(target, "key", "") or ""), 0) < max_candidates
        ]
        if not active_targets:
            continue
        if deadline and time.monotonic() >= deadline:
            break
        remaining_timeout = 0
        if deadline:
            remaining_timeout = max(1, int(deadline - time.monotonic()))

        def progress_with_scope(event: dict[str, Any]) -> None:
            event = dict(event)
            event["searchScope"] = search_scope
            event["searchPeriod"] = period
            event["searchStartTime"] = window_start.isoformat(timespec="seconds")
            event["searchEndTime"] = window_end.isoformat(timespec="seconds")
            if progress:
                progress(event)

        batch_candidates = planner.find_candidates(
            active_targets,
            start_time=window_start,
            end_time=window_end,
            period=period or None,
            page_size=page_size,
            max_candidates_per_target=max_candidates,
            excluded_task_ids_by_target=excluded_task_ids_by_target,
            timeout_seconds=remaining_timeout,
            progress=progress_with_scope,
        )
        for diagnostic in planner.last_diagnostics:
            item = dict(diagnostic)
            item["searchScope"] = search_scope
            item["searchPeriod"] = period
            item["searchStartTime"] = window_start.isoformat(timespec="seconds")
            item["searchEndTime"] = window_end.isoformat(timespec="seconds")
            all_diagnostics.append(item)
        batch_candidates_by_target: dict[str, list[Any]] = {}
        for candidate in batch_candidates:
            target_key = str(getattr(candidate, "target_key", "") or "")
            task_id = str(getattr(candidate, "task_id", "") or "")
            if not target_key or not task_id:
                continue
            key = (target_key, task_id)
            if key in seen_candidate_keys:
                continue
            if candidate_counts.get(target_key, 0) >= max_candidates:
                continue
            batch_candidates_by_target.setdefault(target_key, []).append(candidate)
        for target_key, target_candidates in batch_candidates_by_target.items():
            if candidate_counts.get(target_key, 0) >= max_candidates:
                continue
            selected_candidates = select_diverse_supplement_candidates(
                target_candidates,
                max_candidates - candidate_counts.get(target_key, 0),
                existing_tax_nos=candidate_tax_nos_by_target.setdefault(target_key, set()),
                existing_task_ids=candidate_task_ids_by_target.setdefault(target_key, set()),
            )
            for candidate in selected_candidates:
                task_id = str(getattr(candidate, "task_id", "") or "")
                key = (target_key, task_id)
                if key in seen_candidate_keys:
                    continue
                if candidate_counts.get(target_key, 0) >= max_candidates:
                    continue
                tax_no = str(getattr(candidate, "tax_no", "") or "").strip()
                seen_candidate_keys.add(key)
                candidate_task_ids_by_target.setdefault(target_key, set()).add(task_id)
                if tax_no:
                    candidate_tax_nos_by_target.setdefault(target_key, set()).add(tax_no)
                candidate_counts[target_key] = candidate_counts.get(target_key, 0) + 1
                all_candidates.append(candidate)
    return all_candidates, merge_supplement_diagnostics(all_diagnostics)


def should_preflight_standard_supplement_candidates(missing_targets: list[Any]) -> bool:
    return any(
        str(getattr(target, "tax_type", "") or "") in STANDARD_SUPPLEMENT_LOGIN_PREFLIGHT_TAX_TYPES
        for target in missing_targets
    )


def supplement_candidate_needs_login_preflight(candidate: Any) -> bool:
    if not str(getattr(candidate, "task_id", "") or ""):
        return False
    if str(getattr(candidate, "reason", "") or "") == "fresh_ydz_collect":
        return False
    return str(getattr(candidate, "tax_type", "") or "") in STANDARD_SUPPLEMENT_LOGIN_PREFLIGHT_TAX_TYPES


def preflight_supplement_candidate_login_ready(candidate: Any, page: Any) -> dict[str, Any]:
    record = {
        "targetKey": str(getattr(candidate, "target_key", "") or ""),
        "taxType": str(getattr(candidate, "tax_type", "") or ""),
        "taskId": str(getattr(candidate, "task_id", "") or ""),
        "taxNo": str(getattr(candidate, "tax_no", "") or ""),
        "status": "ready",
        "stage": "",
        "reason": "",
    }
    if not supplement_candidate_needs_login_preflight(candidate):
        record["status"] = "skipped"
        record["reason"] = "preflight_not_required"
        return record
    if page is None:
        record["status"] = "unknown"
        record["reason"] = "public_manage_page_unavailable"
        return record

    flow = TaskLoginFlow(_ContextPagesBrowserAdapter(getattr(page, "context", None)), timeout=1, poll_timeout=1)
    task_id = record["taskId"]
    client_job = fetch_client_job_once_for_preflight(page, task_id)
    record["stage"] = "getClientJob"
    if not isinstance(client_job, dict):
        record["status"] = "not_ready"
        record["failureCategory"] = "tax_login_expired"
        record["reason"] = "getClientJob returned a non-object response"
        return record
    if client_job.get("_preflightError"):
        record["status"] = "unknown"
        record["reason"] = str(client_job.get("_preflightError") or "")
        return record
    if client_job.get("flag") == 0 or client_job.get("success") is False:
        message = str(client_job.get("msg") or client_job.get("message") or "")
        record["status"] = "not_ready"
        record["reason"] = f"getClientJob failed: {message}"
        if flow._is_pending_client_job_message(message) or flow._client_job_needs_force_tax(client_job):
            record["failureCategory"] = "tax_login_blocked"
        else:
            record["failureCategory"] = "tax_login_expired"
        return record
    if flow._client_job_needs_force_tax(client_job):
        record["status"] = "not_ready"
        record["failureCategory"] = "tax_login_blocked"
        record["reason"] = "getClientJob returned needForceTax=true"
        return record
    if not flow._client_job_has_login_metadata(client_job):
        record["status"] = "not_ready"
        record["failureCategory"] = "tax_login_expired"
        record["reason"] = f"getClientJob returned incomplete tax-login metadata: {flow._client_job_response_summary(client_job)}"
        return record

    data = client_job.get("data") if isinstance(client_job.get("data"), dict) else {}
    inner_task_id = flow._client_job_inner_task_id(data)
    machine_id = preflight_machine_id(page)
    task_cookie = fetch_task_cookie_once_for_preflight(page, inner_task_id, machine_id)
    record["stage"] = "getTaskCookie"
    if not isinstance(task_cookie, dict):
        record["status"] = "not_ready"
        record["failureCategory"] = "tax_login_expired"
        record["reason"] = "getTaskCookie returned a non-object response"
        return record
    if task_cookie.get("_preflightError"):
        record["status"] = "unknown"
        record["reason"] = str(task_cookie.get("_preflightError") or "")
        return record
    if task_cookie.get("flag") == 1 and task_cookie.get("data"):
        record["status"] = "ready"
        record["reason"] = "login_metadata_ready"
        return record
    if task_cookie.get("flag") == 0:
        message = str(task_cookie.get("msg") or task_cookie.get("message") or "")
        record["status"] = "not_ready"
        record["failureCategory"] = classify_supplement_failure_category(f"getTaskCookie failed: {message}")
        record["reason"] = f"getTaskCookie failed: {message}"
        return record
    record["status"] = "unknown"
    record["reason"] = f"getTaskCookie did not return ready data: flag={task_cookie.get('flag')}"
    return record


def preflight_supplement_candidates_login_ready(
    candidates: list[Any],
    admin_query: Any,
) -> tuple[list[Any], list[dict[str, Any]]]:
    if not candidates:
        return [], []
    if not any(supplement_candidate_needs_login_preflight(candidate) for candidate in candidates):
        return candidates, []
    page = None
    if hasattr(admin_query, "_ensure_page"):
        try:
            page = admin_query._ensure_page()
        except Exception as exc:
            page = None
            unavailable_reason = f"login preflight page unavailable: {compact_message(exc, limit=180)}"
        else:
            unavailable_reason = ""
    else:
        unavailable_reason = "login preflight page unavailable: admin query has no browser page"

    filtered: list[Any] = []
    records: list[dict[str, Any]] = []
    for candidate in candidates:
        if not supplement_candidate_needs_login_preflight(candidate):
            filtered.append(candidate)
            continue
        if page is None:
            record = {
                "targetKey": str(getattr(candidate, "target_key", "") or ""),
                "taxType": str(getattr(candidate, "tax_type", "") or ""),
                "taskId": str(getattr(candidate, "task_id", "") or ""),
                "taxNo": str(getattr(candidate, "tax_no", "") or ""),
                "status": "unknown",
                "stage": "preflight",
                "reason": unavailable_reason,
            }
        else:
            record = preflight_supplement_candidate_login_ready(candidate, page)
        records.append(record)
        if record.get("status") != "not_ready":
            filtered.append(candidate)
    return filtered, records


def dedupe_supplement_candidates(candidates: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen: set[tuple[str, str, str, str]] = set()
    for candidate in candidates or []:
        key = (
            str(getattr(candidate, "target_key", "") or ""),
            str(getattr(candidate, "task_id", "") or ""),
            str(getattr(candidate, "tax_no", "") or ""),
            str(getattr(candidate, "reason", "") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def supplement_task_ids_by_target_from_candidates(candidates: list[Any]) -> dict[str, set[str]]:
    task_ids_by_target: dict[str, set[str]] = {}
    for candidate in candidates or []:
        target_key = str(getattr(candidate, "target_key", "") or "")
        task_id = str(getattr(candidate, "task_id", "") or "")
        if target_key and task_id:
            task_ids_by_target.setdefault(target_key, set()).add(task_id)
    return task_ids_by_target


def supplement_excluded_task_ids_from_preflight(records: list[dict[str, Any]]) -> dict[str, set[str]]:
    excluded: dict[str, set[str]] = {}
    for record in records or []:
        if not isinstance(record, dict):
            continue
        if str(record.get("status") or "") != "not_ready":
            continue
        target_key = str(record.get("targetKey") or "")
        task_id = str(record.get("taskId") or "")
        if not target_key or not task_id:
            continue
        category = str(record.get("failureCategory") or "")
        if not category:
            category = classify_supplement_failure_category(str(record.get("reason") or ""))
        if category not in STABLE_SUPPLEMENT_EXCLUDE_CATEGORIES:
            continue
        excluded.setdefault(target_key, set()).add(task_id)
    return excluded


def supplement_preflight_refill_needed(
    missing_targets: list[Any],
    candidates: list[Any],
    max_candidates: int,
    preflight_records: list[dict[str, Any]],
) -> bool:
    not_ready_targets = {
        str(record.get("targetKey") or "")
        for record in preflight_records or []
        if isinstance(record, dict) and str(record.get("status") or "") == "not_ready"
    }
    if not_ready_targets:
        grouped = group_supplement_candidates_by_target(candidates, max_candidates=max_candidates)
        for target in missing_targets or []:
            target_key = str(getattr(target, "key", "") or "")
            if target_key in not_ready_targets and len(grouped.get(target_key) or []) < max(1, int(max_candidates or 1)):
                return True
    return False


class _ContextPagesBrowserAdapter:
    def __init__(self, context: Any) -> None:
        self.context = context

    def get_all_pages(self) -> list[Any]:
        if self.context is None:
            return []
        return list(getattr(self.context, "pages", []) or [])


def fetch_client_job_once_for_preflight(page: Any, task_id: str) -> dict[str, Any]:
    try:
        return page.evaluate(
            """async ({url, taskId}) => {
                try {
                    const requestUrl = `${url}?taskId=${taskId}&orgLoginType=NATIONAL&etaxPluginVersion=2.1.0.109`;
                    const auth = sessionStorage.getItem('Authorization') || localStorage.getItem('Authorization') || '';
                    const accessToken =
                        sessionStorage.getItem('access_token') ||
                        localStorage.getItem('access_token') ||
                        sessionStorage.getItem('token') ||
                        localStorage.getItem('token') ||
                        '';
                    const headers = { "Content-Type": "application/json" };
                    if (auth) headers["authorization"] = auth.startsWith('Bearer ') ? auth : "Bearer " + auth;
                    if (accessToken) headers["token"] = accessToken;
                    const resp = await fetch(requestUrl, { method: "GET", headers, credentials: "include" });
                    const text = await resp.text();
                    try {
                        return JSON.parse(text);
                    } catch (err) {
                        return { flag: 0, _preflightNonJson: true, msg: text.slice(0, 240) };
                    }
                } catch (err) {
                    return { _preflightError: String(err && err.message || err) };
                }
            }""",
            {"url": GET_CLIENT_JOB_URL, "taskId": task_id},
        )
    except Exception as exc:
        return {"_preflightError": str(exc)}


def fetch_task_cookie_once_for_preflight(page: Any, inner_task_id: str, machine_id: str) -> dict[str, Any]:
    try:
        return page.evaluate(
            """async ({taskId, machineId, fallbackUrl}) => {
                try {
                    const apiRoot = window.etaxPlugin_getApiRoot ? window.etaxPlugin_getApiRoot() : fallbackUrl.replace('/api/client/getTaskCookie', '');
                    const resp = await fetch(`${apiRoot}/api/client/getTaskCookie`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ taskId, machineId })
                    });
                    const text = await resp.text();
                    try {
                        return JSON.parse(text);
                    } catch (err) {
                        return { flag: 0, _preflightNonJson: true, msg: text.slice(0, 240) };
                    }
                } catch (err) {
                    return { _preflightError: String(err && err.message || err) };
                }
            }""",
            {
                "taskId": inner_task_id,
                "machineId": machine_id,
                "fallbackUrl": GET_TASK_COOKIE_FALLBACK_URL,
            },
        )
    except Exception as exc:
        return {"_preflightError": str(exc)}


def preflight_machine_id(page: Any) -> str:
    try:
        machine_id = str(page.evaluate("window.robotId || ''") or "").strip()
    except Exception:
        machine_id = ""
    return machine_id or DEFAULT_MACHINE_ID


def supplement_search_batches(
    missing_targets: list[Any],
    base_period: str,
    end_time: datetime,
    lookback_days: int,
    cit_lookback_days: int,
) -> list[tuple[list[Any], str, datetime, datetime, str]]:
    base_period = str(base_period or "")
    batches: list[tuple[list[Any], str, datetime, datetime, str]] = []
    non_cit_targets = [target for target in missing_targets if str(getattr(target, "tax_type", "") or "") != "CIT_A"]
    cit_targets = [target for target in missing_targets if str(getattr(target, "tax_type", "") or "") == "CIT_A"]
    for window_start, window_end in supplement_time_windows(end_time, lookback_days):
        if non_cit_targets:
            batches.append((non_cit_targets, base_period, window_start, window_end, "default"))
    if cit_targets:
        cit_windows = supplement_time_windows(end_time, max(lookback_days, cit_lookback_days))
        for period in supplement_cit_candidate_periods(base_period):
            for window_start, window_end in cit_windows:
                batches.append((cit_targets, period, window_start, window_end, "cit_period_scan"))
    return batches


def supplement_time_windows(end_time: datetime, lookback_days: int) -> list[tuple[datetime, datetime]]:
    if lookback_days <= 0:
        return [(end_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0), end_time)]
    start_time = end_time - timedelta(days=lookback_days)
    windows: list[tuple[datetime, datetime]] = []
    cursor_end = end_time
    max_window = timedelta(days=MAX_SUPPLEMENT_QUERY_WINDOW_DAYS)
    while cursor_end > start_time:
        cursor_start = max(start_time, cursor_end - max_window)
        windows.append((cursor_start, cursor_end))
        cursor_end = cursor_start - timedelta(seconds=1)
    return windows


def supplement_cit_candidate_periods(base_period: str) -> list[str]:
    period = normalize_period_yyyymm(base_period)
    if not period:
        return []
    year = int(period[:4])
    month = int(period[4:6])
    periods = [add_months_to_period(period, offset) for offset in range(0, -12, -1)]
    quarter = latest_quarter_end_period(year, month)
    periods.extend(
        [
            quarter,
            add_months_to_period(quarter, -3),
            add_months_to_period(quarter, -6),
            add_months_to_period(quarter, -9),
            f"{year - 1}12",
        ]
    )
    return unique_texts([item for item in periods if item])


def normalize_period_yyyymm(value: Any) -> str:
    text = re.sub(r"\D", "", str(value or ""))
    if len(text) < 6:
        return ""
    text = text[:6]
    month = int(text[4:6])
    if month < 1 or month > 12:
        return ""
    return text


def latest_quarter_end_period(year: int, month: int) -> str:
    quarter_month = month if month % 3 == 0 else ((month - 1) // 3) * 3
    if quarter_month <= 0:
        year -= 1
        quarter_month = 12
    return f"{year}{quarter_month:02d}"


def add_months_to_period(period: str, months: int) -> str:
    normalized = normalize_period_yyyymm(period)
    if not normalized:
        return ""
    year = int(normalized[:4])
    month = int(normalized[4:6])
    absolute = year * 12 + (month - 1) + int(months)
    new_year = absolute // 12
    new_month = absolute % 12 + 1
    return f"{new_year}{new_month:02d}"


def merge_supplement_diagnostics(diagnostics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for diagnostic in diagnostics:
        target_key = str(diagnostic.get("targetKey") or "")
        if not target_key:
            continue
        if target_key not in merged:
            item = dict(diagnostic)
            item["queriedCount"] = int(diagnostic.get("queriedCount") or 0)
            item["statusCounts"] = dict(diagnostic.get("statusCounts") or {})
            item["statusTaskIds"] = copy_status_task_ids(diagnostic.get("statusTaskIds") or {})
            item["taskTaxTypeCounts"] = dict(diagnostic.get("taskTaxTypeCounts") or {})
            item["cbjModeSourceCounts"] = dict(diagnostic.get("cbjModeSourceCounts") or {})
            item["matchedTaskIds"] = list(diagnostic.get("matchedTaskIds") or [])
            item["excludedTaskCount"] = int(diagnostic.get("excludedTaskCount") or 0)
            item["excludedTaskIds"] = list(diagnostic.get("excludedTaskIds") or [])
            item["candidateCount"] = len(item["matchedTaskIds"])
            item["searchPeriods"] = unique_texts([diagnostic.get("searchPeriod") or ""])
            item["searchWindows"] = unique_texts(
                [
                    "-".join(
                        part
                        for part in (
                            str(diagnostic.get("searchStartTime") or ""),
                            str(diagnostic.get("searchEndTime") or ""),
                        )
                        if part
                    )
                ]
            )
            merged[target_key] = item
            order.append(target_key)
            continue
        item = merged[target_key]
        item["queriedCount"] = int(item.get("queriedCount") or 0) + int(diagnostic.get("queriedCount") or 0)
        merge_count_dict(item.setdefault("statusCounts", {}), diagnostic.get("statusCounts") or {})
        merge_status_task_ids(item.setdefault("statusTaskIds", {}), diagnostic.get("statusTaskIds") or {})
        merge_count_dict(item.setdefault("taskTaxTypeCounts", {}), diagnostic.get("taskTaxTypeCounts") or {})
        merge_count_dict(item.setdefault("cbjModeSourceCounts", {}), diagnostic.get("cbjModeSourceCounts") or {})
        for task_id in diagnostic.get("matchedTaskIds") or []:
            append_unique(item.setdefault("matchedTaskIds", []), str(task_id))
        item["excludedTaskCount"] = int(item.get("excludedTaskCount") or 0) + int(
            diagnostic.get("excludedTaskCount") or 0
        )
        for task_id in diagnostic.get("excludedTaskIds") or []:
            append_unique(item.setdefault("excludedTaskIds", []), str(task_id))
        append_unique(item.setdefault("searchPeriods", []), str(diagnostic.get("searchPeriod") or ""))
        window = "-".join(
            part
            for part in (
                str(diagnostic.get("searchStartTime") or ""),
                str(diagnostic.get("searchEndTime") or ""),
            )
            if part
        )
        append_unique(item.setdefault("searchWindows", []), window)
        if item.get("matchedTaskIds"):
            item["matchedTaskId"] = item.get("matchedTaskId") or item["matchedTaskIds"][0]
            item["candidateCount"] = len(item["matchedTaskIds"])
            item["reason"] = "matched_backend_result_json"
        elif diagnostic_priority(str(diagnostic.get("reason") or "")) > diagnostic_priority(str(item.get("reason") or "")):
            item["reason"] = diagnostic.get("reason") or item.get("reason") or ""
    for item in merged.values():
        if item.get("matchedTaskIds"):
            item["matchedTaskId"] = item.get("matchedTaskId") or item["matchedTaskIds"][0]
            item["candidateCount"] = len(item["matchedTaskIds"])
            item["reason"] = "matched_backend_result_json"
    return [merged[key] for key in order]


def merge_count_dict(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            count = 0
        target[key] = int(target.get(key) or 0) + count


def copy_status_task_ids(source: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    merge_status_task_ids(result, source)
    return result


def merge_status_task_ids(target: dict[str, list[str]], source: dict[str, Any], limit: int = 20) -> None:
    for key, values in source.items():
        bucket = target.setdefault(str(key), [])
        for task_id in values or []:
            if len(bucket) >= limit:
                break
            append_unique(bucket, task_id)


def diagnostic_priority(reason: str) -> int:
    return {
        "matched_backend_result_json": 100,
        "declaration_status_not_matched": 80,
        "target_tax_type_not_matched": 70,
        "declaration_status_unknown": 60,
        "no_success_collect_tasks": 50,
        "supplement_search_timeout": 40,
        "excluded_known_failed_candidates": 30,
    }.get(str(reason or ""), 0)


def supplement_candidate_status_rank(candidate: Any) -> int:
    target_status = str(getattr(candidate, "declaration_status", "") or "")
    parse_status = str(getattr(candidate, "parse_status", "") or "")
    if not target_status or target_status == "any":
        return 0
    if parse_status == target_status:
        return 0
    if parse_status == "unknown":
        return 1
    if not parse_status:
        return 2
    return 3


def supplement_target_tax_type_from_key(target_key: Any) -> str:
    return str(target_key or "").split(":", 1)[0].strip().upper()


def effective_supplement_max_candidates(configured: int, missing_targets: list[Any]) -> int:
    return max(1, int(configured or 1))


def supplement_candidate_source_rank(candidate: Any) -> int:
    reason = str(getattr(candidate, "reason", "") or "")
    if reason == "fresh_ydz_collect":
        return 0
    return 1


def supplement_candidate_sort_key(candidate: Any) -> tuple[Any, ...]:
    return (
        str(getattr(candidate, "target_key", "")),
        supplement_candidate_source_rank(candidate),
        supplement_candidate_status_rank(candidate),
        -(int(getattr(candidate, "created_stamp", 0) or 0)),
        str(getattr(candidate, "task_id", "")),
    )


def group_supplement_candidates_by_target(candidates: list[Any], max_candidates: int = 1) -> dict[str, list[Any]]:
    max_candidates = max(1, int(max_candidates or 1))
    grouped: dict[str, list[Any]] = {}
    for candidate in sorted(candidates, key=supplement_candidate_sort_key):
        key = str(getattr(candidate, "target_key", "") or "")
        if not key:
            continue
        values = grouped.setdefault(key, [])
        if len(values) < max_candidates:
            values.append(candidate)
    return grouped


def count_fresh_supplement_candidates(grouped_candidates: dict[str, list[Any]]) -> int:
    return sum(
        1
        for candidates in grouped_candidates.values()
        for candidate in candidates
        if str(getattr(candidate, "reason", "") or "") == "fresh_ydz_collect"
    )


def ensure_cit_refresh_template_candidates(
    grouped_candidates: dict[str, list[Any]],
    missing_targets: list[Any],
    period: str,
) -> dict[str, list[Any]]:
    refreshed = {key: list(values) for key, values in grouped_candidates.items()}
    for target in missing_targets:
        if str(getattr(target, "tax_type", "") or "") != "CIT_A":
            continue
        key = str(getattr(target, "key", "") or "")
        if not key or refreshed.get(key):
            continue
        refreshed[key] = [supplement_template_candidate_for_target(target, period)]
    return refreshed


def supplement_template_candidate_for_target(target: Any, period: str) -> SupplementCandidate:
    backend_tax_ids = tuple(getattr(target, "backend_tax_ids", ()) or ())
    backend_tax_type_ids = tuple(getattr(target, "backend_tax_type_ids", ()) or ())
    query_field = "taxId" if backend_tax_ids else "taxTypeId"
    query_id = backend_tax_ids[0] if backend_tax_ids else (backend_tax_type_ids[0] if backend_tax_type_ids else "")
    return SupplementCandidate(
        target_key=str(getattr(target, "key", "") or ""),
        tax_type=str(getattr(target, "tax_type", "") or ""),
        tax_type_name=str(getattr(target, "tax_type_name", "") or ""),
        declaration_status=str(getattr(target, "declaration_status", "") or ""),
        declaration_status_name=str(getattr(target, "declaration_status_name", "") or ""),
        task_id="",
        tax_no="",
        period=str(period or ""),
        task_status="",
        backend_tax_type_id=str(query_id) if query_field == "taxTypeId" else "",
        backend_tax_id=str(query_id) if query_field == "taxId" else "",
        backend_query_field=query_field,
        created_stamp=0,
        parse_status="unknown",
        reason="current_enterprise_scan_template",
    )


def filter_supplement_candidates_with_task(grouped_candidates: dict[str, list[Any]]) -> dict[str, list[Any]]:
    filtered: dict[str, list[Any]] = {}
    for target_key, candidates in grouped_candidates.items():
        with_task = [candidate for candidate in candidates if str(getattr(candidate, "task_id", "") or "")]
        if with_task:
            filtered[target_key] = with_task
    return filtered


def build_supplement_source_readiness(
    missing_targets: list[Any],
    diagnostics: list[dict[str, Any]],
    candidates: list[Any],
    ydz_refresh_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    diagnostics_by_key = {str(item.get("targetKey") or ""): item for item in diagnostics or []}
    candidates_by_key: dict[str, list[Any]] = {}
    for candidate in candidates or []:
        candidates_by_key.setdefault(str(getattr(candidate, "target_key", "") or ""), []).append(candidate)
    refresh_by_key: dict[str, list[dict[str, Any]]] = {}
    for record in ydz_refresh_records or []:
        keys = [key.strip() for key in str(record.get("targetKey") or "").split(",") if key.strip()]
        for key in keys:
            refresh_by_key.setdefault(key, []).append(record)

    readiness: list[dict[str, Any]] = []
    for target in missing_targets or []:
        if isinstance(target, dict):
            target_key = str(target.get("key") or "")
        else:
            target_key = str(getattr(target, "key", "") or "")
        if not target_key:
            continue
        target_candidates = candidates_by_key.get(target_key) or []
        target_records = refresh_by_key.get(target_key) or []
        diagnostic = diagnostics_by_key.get(target_key) or {}
        diagnostic_task_ids = [
            str(task_id)
            for task_id in (diagnostic.get("matchedTaskIds") or [])
            if str(task_id or "")
        ]
        backend_candidate_count = len(target_candidates) or len(diagnostic_task_ids)
        ydz_status, ydz_reason = classify_ydz_source_readiness(target_records)
        status = classify_supplement_source_readiness(
            backend_candidate_count=backend_candidate_count,
            backend_reason=str(diagnostic.get("reason") or ""),
            ydz_status=ydz_status,
        )
        account_count = max_int_field(target_records, "accountCount")
        cit_signal_count = max_int_field(target_records, "citSignalCount")
        enterprise_suggestions = ydz_enterprise_scan_suggestions(target_records)
        enterprise_scan_count = len(
            [
                record
                for record in target_records
                if str(record.get("source") or "") in YDZ_EXTERNAL_ACCOUNT_SCAN_SOURCES
            ]
        )
        enterprise_scan_error = first_ydz_enterprise_scan_error(target_records)
        row = {
            "targetKey": target_key,
            "status": status,
            "message": supplement_source_readiness_message(
                status=status,
                backend_candidate_count=backend_candidate_count,
                account_count=account_count,
                cit_signal_count=cit_signal_count,
                enterprise_suggestions=enterprise_suggestions,
                enterprise_scan_count=enterprise_scan_count,
                enterprise_scan_error=enterprise_scan_error,
            ),
            "nextAction": supplement_source_readiness_next_action(status),
            "backendCandidateCount": backend_candidate_count,
            "backendReason": str(diagnostic.get("reason") or ""),
            "backendMatchedTaskIds": diagnostic_task_ids,
            "ydzStatus": ydz_status,
            "ydzReason": ydz_reason,
            "ydzAccountCount": account_count,
            "ydzCitSignalCount": cit_signal_count,
            "ydzEnterpriseScanCount": enterprise_scan_count,
            "ydzEnterpriseSuggestions": enterprise_suggestions,
            "ydzEnterpriseScanError": enterprise_scan_error,
        }
        readiness.append(row)
    return readiness


def classify_ydz_source_readiness(records: list[dict[str, Any]]) -> tuple[str, str]:
    reasons = {str(record.get("reason") or "") for record in records or []}
    has_task = any(record.get("taskIds") for record in records or [])
    if has_task or any(str(record.get("status") or "") == "resolved" for record in records or []):
        return "fresh_task_resolved", "fresh_ydz_collect_task_resolved"
    no_need_record = next(
        (
            record
            for record in records or []
            if str(record.get("collectStatus") or "").upper() == "NO_NEED_COLLECTED"
        ),
        None,
    )
    if no_need_record is not None:
        return "ydz_no_need_collect", str(no_need_record.get("reason") or "NO_NEED_COLLECTED")
    external_account_records = [
        record for record in records or [] if str(record.get("source") or "") in YDZ_EXTERNAL_ACCOUNT_SCAN_SOURCES
    ]
    if any(max_int_field([record], "citSignalCount") > 0 for record in external_account_records):
        return "other_enterprise_has_cit_signal", "other_enterprise_account_scan_found_cit_signal"
    if any(is_ydz_enterprise_scan_login_required(record) for record in records or []):
        return "other_enterprise_scan_login_required", "other_enterprise_scan_login_required"
    failed_external_source_reason = next(
        (
            str(record.get("reason") or "")
            for record in external_account_records
            if str(record.get("status") or "") == "failed" and str(record.get("reason") or "")
        ),
        "",
    )
    if failed_external_source_reason:
        return "other_enterprise_scan_unavailable", failed_external_source_reason
    login_reason = next((reason for reason in reasons if is_ydz_login_required_reason(reason)), "")
    if login_reason:
        return "ydz_login_required", login_reason
    if "current_enterprise_scan_no_cit_account_signal" in reasons:
        return "current_enterprise_no_cit_signal", "current_enterprise_scan_no_cit_account_signal"
    if external_account_records:
        return "other_enterprise_no_cit_signal", "other_enterprise_account_scan_no_cit_signal"
    if "no_ydz_account_in_current_enterprise" in reasons:
        return "candidate_not_in_current_enterprise", "no_ydz_account_in_current_enterprise"
    if "current_enterprise_scan_no_fresh_task_id" in reasons:
        return "current_enterprise_no_fresh_task", "current_enterprise_scan_no_fresh_task_id"
    if records:
        return "checked_no_fresh_task", next((reason for reason in reasons if reason), "checked_no_fresh_task")
    return "not_checked", ""


def classify_supplement_source_readiness(
    backend_candidate_count: int,
    backend_reason: str,
    ydz_status: str,
) -> str:
    if ydz_status == "fresh_task_resolved":
        return "fresh_task_ready"
    if ydz_status == "other_enterprise_has_cit_signal":
        return "other_enterprise_has_cit_signal"
    if ydz_status == "other_enterprise_scan_login_required":
        return "other_enterprise_scan_login_required"
    if ydz_status == "other_enterprise_scan_unavailable":
        return "other_enterprise_scan_unavailable"
    if ydz_status == "ydz_login_required":
        return "ydz_login_required"
    if ydz_status == "ydz_no_need_collect":
        return "ydz_no_need_collect"
    if ydz_status == "current_enterprise_no_cit_signal":
        return "current_enterprise_no_cit_signal"
    if ydz_status == "other_enterprise_no_cit_signal":
        return "other_enterprise_no_cit_signal"
    if ydz_status == "candidate_not_in_current_enterprise" and backend_candidate_count > 0:
        return "backend_candidates_not_refreshable"
    if backend_candidate_count > 0:
        return "backend_candidates_only"
    if backend_reason:
        return "backend_no_usable_candidate"
    return "no_source_checked"


def supplement_source_readiness_message(
    status: str,
    backend_candidate_count: int,
    account_count: int,
    cit_signal_count: int,
    enterprise_suggestions: list[dict[str, Any]] | None = None,
    enterprise_scan_count: int = 0,
    enterprise_scan_error: str = "",
) -> str:
    if status == "fresh_task_ready":
        return "\u5df2\u751f\u6210\u65b0\u7684\u6613\u4ee3\u8d26\u53d6\u6570 taskId\uff0c\u53ef\u7ee7\u7eed\u9a8c\u8bc1\u8be5\u8986\u76d6\u7f3a\u53e3\u3002"
    if status == "other_enterprise_has_cit_signal":
        suggestion = (enterprise_suggestions or [{}])[0]
        enterprise = str(suggestion.get("enterprise") or "")
        signal_count = int(suggestion.get("citSignalCount") or 0)
        samples = ", ".join(str(item) for item in (suggestion.get("sampleTaxNos") or [])[:3] if str(item or ""))
        sample_text = f"\uff0c\u6837\u4f8b\u7a0e\u53f7\uff1a{samples}" if samples else ""
        return (
            f"\u5df2\u5728\u5176\u4ed6\u6613\u4ee3\u8d26\u4f01\u4e1a\u6216\u6307\u5b9a work.html \u6765\u6e90\u300c{enterprise}\u300d"
            f"\u627e\u5230 {signal_count} \u4e2a\u4f01\u4e1a\u6240\u5f97\u7a0e A \u7c7b\u8d26\u5957{sample_text}\u3002"
        )
    if status == "current_enterprise_no_cit_signal":
        return (
            "\u5f53\u524d\u6613\u4ee3\u8d26\u4f01\u4e1a\u5df2\u626b\u63cf"
            f" {account_count} \u4e2a\u8d26\u5957\uff0c\u4f46\u4f01\u4e1a\u6240\u5f97\u7a0e A \u7c7b\u4fe1\u53f7\u6570\u4e3a {cit_signal_count}\uff0c"
            "\u4e0d\u9002\u5408\u968f\u673a\u53d1\u8d77\u65b0\u53d6\u6570\u3002"
        )
    if status == "other_enterprise_scan_login_required":
        detail = f"\u8be6\u60c5\uff1a{enterprise_scan_error}" if enterprise_scan_error else ""
        return (
            "\u5f53\u524d\u4f01\u4e1a\u65e0\u4f01\u4e1a\u6240\u5f97\u7a0e A \u7c7b\u8d26\u5957\u4fe1\u53f7\uff0c"
            "\u4f46\u626b\u63cf\u5176\u4ed6\u6613\u4ee3\u8d26\u4f01\u4e1a\u65f6\u7f3a\u5c11\u53ef\u7528\u767b\u5f55\u6001\u6216\u51ed\u636e\u3002"
            f"{detail}"
        )
    if status == "other_enterprise_scan_unavailable":
        detail = f"\u8be6\u60c5\uff1a{enterprise_scan_error}" if enterprise_scan_error else ""
        return (
            "\u5f53\u524d\u6613\u4ee3\u8d26\u4f01\u4e1a\u65e0\u4f01\u4e1a\u6240\u5f97\u7a0e A \u7c7b\u8d26\u5957\u4fe1\u53f7\uff0c"
            "\u5176\u4ed6\u4f01\u4e1a\u7684\u6613\u4ee3\u8d26\u5e94\u7528\u6682\u672a\u80fd\u81ea\u52a8\u6253\u5f00\u6216\u65e0\u53ef\u7528\u5165\u53e3\u3002"
            f"{detail}"
        )
    if status == "ydz_login_required":
        return (
            "\u6613\u4ee3\u8d26\u4f1a\u8bdd\u6216\u63a5\u53e3 token \u4e0d\u53ef\u7528\uff0c"
            "\u65e0\u6cd5\u5c06\u5f53\u524d\u4f01\u4e1a\u5237\u65b0\u6210\u65b0\u53d6\u6570 taskId\u3002"
        )
    if status == "ydz_no_need_collect":
        return (
            "\u6613\u4ee3\u8d26\u5df2\u6210\u529f\u53d1\u8d77\u65b0\u53d6\u6570\uff0c"
            "\u4f46\u8fd4\u56de\u672c\u671f\u65e0\u9700\u7533\u62a5\u6216\u65e0\u9700\u53d6\u6570\uff0c"
            "\u672a\u751f\u6210\u53ef\u7528\u7684\u9a8c\u8bc1 taskId\u3002"
        )
    if status == "other_enterprise_no_cit_signal":
        return (
            f"\u5df2\u626b\u63cf {enterprise_scan_count} \u4e2a\u5176\u4ed6\u6613\u4ee3\u8d26\u4f01\u4e1a\u6216\u6307\u5b9a work.html \u6765\u6e90\uff0c"
            "\u6682\u672a\u627e\u5230\u4f01\u4e1a\u6240\u5f97\u7a0e A \u7c7b\u8d26\u5957\u4fe1\u53f7\u3002"
        )
    if status == "backend_candidates_not_refreshable":
        return (
            f"\u540e\u53f0\u6709 {backend_candidate_count} \u4e2a\u5386\u53f2\u5019\u9009\uff0c"
            "\u4f46\u5019\u9009\u7a0e\u53f7\u4e0d\u5728\u5f53\u524d\u6613\u4ee3\u8d26\u4f01\u4e1a\uff0c\u65e0\u6cd5\u5728\u5f53\u524d\u4f01\u4e1a\u5237\u65b0\u6210\u65b0 taskId\u3002"
        )
    if status == "backend_candidates_only":
        return (
            f"\u540e\u53f0\u6709 {backend_candidate_count} \u4e2a\u5386\u53f2\u5019\u9009\uff0c"
            "\u4f46\u672a\u83b7\u5f97\u53ef\u7528\u7684\u6613\u4ee3\u8d26\u65b0\u53d6\u6570\u6765\u6e90\u3002"
        )
    if status == "backend_no_usable_candidate":
        return "\u540e\u53f0\u67e5\u5230\u5386\u53f2\u4efb\u52a1\uff0c\u4f46\u6ca1\u6709\u7b26\u5408\u8be5\u7f3a\u53e3\u7684\u53ef\u7528\u5019\u9009\u3002"
    return "\u672a\u786e\u8ba4\u5230\u53ef\u7528\u6837\u672c\u6765\u6e90\u3002"


def supplement_source_readiness_next_action(status: str) -> str:
    actions = {
        "fresh_task_ready": "\u7ee7\u7eed\u4f7f\u7528\u65b0 taskId \u8dd1\u6807\u51c6\u9a8c\u8bc1\u3002",
        "other_enterprise_has_cit_signal": "\u5207\u6362\u5230\u63d0\u793a\u7684\u6613\u4ee3\u8d26\u4f01\u4e1a\uff0c\u6216\u4f7f\u7528\u6307\u5b9a work.html URL \u91cd\u8bd5 CIT A \u8865\u9f50\u5237\u65b0\u3002",
        "other_enterprise_scan_login_required": "\u901a\u8fc7\u5de5\u4f5c\u53f0\u4e34\u65f6\u586b\u5165\u6613\u4ee3\u8d26\u8d26\u53f7\u5bc6\u7801\uff0c\u6216\u5728\u7ec8\u7aef\u8bbe\u7f6e YDZ_USERNAME/YDZ_PASSWORD \u540e\u91cd\u8bd5\u4f01\u4e1a\u626b\u63cf\u3002",
        "other_enterprise_scan_unavailable": "\u624b\u5de5\u786e\u8ba4\u76ee\u6807\u4f01\u4e1a\u7684\u6613\u4ee3\u8d26\u5e94\u7528\u662f\u5426\u5df2\u5f00\u901a\uff1b\u82e5\u5df2\u5f00\u901a\uff0c\u63d0\u4f9b\u5176 work.html URL\uff0c\u6216\u5728\u5171\u4eab\u6d4f\u89c8\u5668\u624b\u5de5\u6253\u5f00\u8be5 work.html \u6807\u7b7e\u9875\u540e\u91cd\u8bd5\u3002",
        "ydz_login_required": "\u901a\u8fc7\u5de5\u4f5c\u53f0\u4e34\u65f6\u586b\u5165\u6613\u4ee3\u8d26\u8d26\u53f7\u5bc6\u7801\uff0c\u6216\u624b\u5de5\u91cd\u65b0\u767b\u5f55\u6613\u4ee3\u8d26\u540e\u91cd\u8bd5\u8865\u9f50\u5237\u65b0\u3002",
        "ydz_no_need_collect": "\u66f4\u6362\u5019\u9009\u7a0e\u53f7\u6216\u6240\u5c5e\u671f\uff0c\u4f18\u5148\u9009\u62e9\u4f1a\u751f\u6210\u4f01\u4e1a\u6240\u5f97\u7a0e A \u7c7b\u53d6\u6570 taskId \u7684\u6837\u672c\u3002",
        "current_enterprise_no_cit_signal": "\u5207\u6362\u5230\u6709\u4f01\u4e1a\u6240\u5f97\u7a0e A \u7c7b\u8d26\u5957\u7684\u6613\u4ee3\u8d26\u4f01\u4e1a\uff0c\u6216\u5148\u521b\u5efa/\u5bfc\u5165\u8be5\u7c7b\u8d26\u5957\u518d\u53d6\u6570\u3002",
        "other_enterprise_no_cit_signal": "\u5148\u521b\u5efa/\u5bfc\u5165\u4e00\u4e2a\u4f01\u4e1a\u6240\u5f97\u7a0e A \u7c7b\u8d26\u5957\uff0c\u6216\u6269\u5927\u53ef\u9009\u4f01\u4e1a\u540e\u91cd\u65b0\u626b\u63cf\u3002",
        "backend_candidates_not_refreshable": "\u5207\u6362\u5230\u5305\u542b\u5019\u9009\u7a0e\u53f7\u7684\u6613\u4ee3\u8d26\u4f01\u4e1a\uff0c\u6216\u5148\u5efa\u8d26\u5957\u540e\u91cd\u65b0\u53d6\u6570\u3002",
        "backend_candidates_only": "\u4f18\u5148\u5237\u65b0\u6210\u5f53\u524d\u6613\u4ee3\u8d26\u4f01\u4e1a\u7684\u65b0\u53d6\u6570 taskId\uff0c\u5386\u53f2 taskId \u53ef\u80fd\u7a0e\u5c40\u767b\u5f55\u6001\u5df2\u8fc7\u671f\u3002",
        "backend_no_usable_candidate": "\u6269\u5927\u5019\u9009\u6765\u6e90\u6216\u5148\u5236\u9020\u4e00\u4e2a\u53ef\u7528\u6837\u672c\uff0c\u518d\u8fd0\u884c\u8865\u9f50\u3002",
    }
    return actions.get(status, "\u9700\u8981\u4eba\u5de5\u786e\u8ba4\u6837\u672c\u6765\u6e90\u3002")


def ydz_enterprise_scan_suggestions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for record in records or []:
        if str(record.get("source") or "") not in YDZ_EXTERNAL_ACCOUNT_SCAN_SOURCES:
            continue
        cit_signal_count = max_int_field([record], "citSignalCount")
        if cit_signal_count <= 0:
            continue
        suggestions.append(
            {
                "enterprise": str(record.get("enterprise") or ""),
                "accountCount": max_int_field([record], "accountCount"),
                "citSignalCount": cit_signal_count,
                "sampleTaxNos": [
                    str(item)
                    for item in (record.get("sampleTaxNos") or [])
                    if str(item or "")
                ][:5],
            }
        )
    return suggestions


def first_ydz_enterprise_scan_error(records: list[dict[str, Any]]) -> str:
    for record in records or []:
        if str(record.get("source") or "") != "other_enterprise_selector_scan":
            continue
        reason = str(record.get("reason") or "").strip()
        if reason:
            return reason
    for record in records or []:
        if str(record.get("source") or "") not in YDZ_EXTERNAL_ACCOUNT_SCAN_SOURCES:
            continue
        if str(record.get("status") or "") != "failed":
            continue
        reason = str(record.get("reason") or "").strip()
        if reason:
            return reason
    return ""


def is_ydz_enterprise_scan_login_required(record: dict[str, Any]) -> bool:
    source = str(record.get("source") or "")
    reason = str(record.get("reason") or "")
    if source not in {"other_enterprise_selector_scan", *YDZ_EXTERNAL_ACCOUNT_SCAN_SOURCES}:
        return False
    return is_ydz_login_required_reason(reason)


def is_ydz_login_required_reason(reason: str) -> bool:
    return (
        "YDZ_USERNAME" in reason
        or "YDZ_PASSWORD" in reason
        or "\u767b\u5f55\u6001\u7f3a\u5931" in reason
        or "\u51ed\u636e" in reason
        or "\u9a8c\u8bc1\u7801" in reason
        or "\u624b\u5de5\u786e\u8ba4" in reason
        or "\u672a\u8fdb\u5165\u4f01\u4e1a\u9009\u62e9" in reason
        or "Could not locate Yidaizhang login inputs" in reason
        or "Yidaizhang login token is missing" in reason
        or "API token is missing" in reason
        or "http=701" in reason
        or "token \u4e0d\u80fd\u4e3a\u7a7a" in reason
    )


def max_int_field(records: list[dict[str, Any]], field: str) -> int:
    result = 0
    for record in records or []:
        try:
            result = max(result, int(record.get(field) or 0))
        except (TypeError, ValueError):
            continue
    return result


def refresh_cit_supplement_candidates_from_ydz(
    args: argparse.Namespace,
    grouped_candidates: dict[str, list[Any]],
    max_candidates: int,
) -> tuple[dict[str, list[Any]], list[dict[str, Any]]]:
    cit_targets = {
        target_key: candidates
        for target_key, candidates in grouped_candidates.items()
        if str(target_key).startswith("CIT_A:") and candidates
    }
    if not cit_targets:
        return grouped_candidates, []

    records: list[dict[str, Any]] = []
    refreshed: dict[str, list[Any]] = {key: list(values) for key, values in grouped_candidates.items()}
    try:
        with open_ydz_session(
            args,
            {"kind": "coverage-supplement-cit-refresh", "targets": sorted(cit_targets)},
        ) as (session, resolver, collector):
            enterprise_scan_cache: list[dict[str, Any]] | None = None
            cit_collector = YdzCollector(
                api=collector.api,
                enterprise=collector.enterprise,
                query_area_code=collector.query_area_code,
                tax_type_ids=CIT_A_YDZ_TAX_TYPE_IDS,
                poll_interval=collector.poll_interval,
                poll_timeout=collector.poll_timeout,
            )
            for target_key, candidates in cit_targets.items():
                fresh_candidates: list[Any] = []
                for candidate in candidates:
                    if not str(getattr(candidate, "tax_no", "") or ""):
                        continue
                    if fresh_candidates:
                        break
                    record, new_candidates = refresh_one_supplement_candidate_from_ydz(
                        args=args,
                        collector=cit_collector,
                        resolver=resolver,
                        candidate=candidate,
                    )
                    records.append(record)
                    fresh_candidates.extend(new_candidates)
                if not fresh_candidates:
                    scan_records, scan_candidates = refresh_current_enterprise_cit_candidates_from_ydz(
                        args=args,
                        collector=cit_collector,
                        resolver=resolver,
                        template=candidates[0],
                        original_candidates=candidates,
                        max_candidates=max_candidates,
                    )
                    records.extend(scan_records)
                    fresh_candidates.extend(scan_candidates)
                if not fresh_candidates and explicit_ydz_work_urls(args):
                    scan_records, scan_candidates = refresh_explicit_ydz_work_url_cit_candidates_from_ydz(
                        args=args,
                        session=session,
                        resolver=resolver,
                        template=candidates[0],
                        original_candidates=candidates,
                        current_enterprise=collector.enterprise,
                        max_candidates=max_candidates,
                    )
                    records.extend(scan_records)
                    fresh_candidates.extend(scan_candidates)
                if (
                    not fresh_candidates
                    and bool(getattr(args, "coverage_supplement_scan_ydz_enterprises", False))
                ):
                    current_work_url = ""
                    try:
                        current_work_url = str(getattr(collector.api.page, "url", "") or "")
                    except Exception:
                        current_work_url = ""
                    open_tab_records, open_tab_candidates = refresh_open_ydz_work_tab_cit_candidates_from_ydz(
                        args=args,
                        session=session,
                        resolver=resolver,
                        template=candidates[0],
                        current_enterprise=collector.enterprise,
                        max_candidates=max_candidates,
                        exclude_urls={current_work_url} if current_work_url else set(),
                    )
                    records.extend(open_tab_records)
                    fresh_candidates.extend(open_tab_candidates)
                if (
                    not fresh_candidates
                    and bool(getattr(args, "coverage_supplement_scan_ydz_enterprises", False))
                ):
                    if enterprise_scan_cache is None:
                        enterprise_scan_cache = scan_other_ydz_enterprises_for_cit_accounts(
                            args=args,
                            session=session,
                            target_key=target_key,
                            current_enterprise=collector.enterprise,
                        )
                        enterprise_records = enterprise_scan_cache
                    else:
                        enterprise_records = retarget_ydz_enterprise_scan_records(
                            enterprise_scan_cache,
                            target_key=target_key,
                        )
                    records.extend(enterprise_records)
                if fresh_candidates:
                    refreshed[target_key] = merge_fresh_supplement_candidates(
                        fresh_candidates=fresh_candidates,
                        original_candidates=refreshed.get(target_key) or [],
                        max_candidates=max_candidates,
                    )
    except Exception as exc:
        records.append(
            {
                "targetKey": ",".join(sorted(cit_targets)),
                "status": "failed",
                "reason": friendly_collect_exception(exc),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
        )
    return refreshed, records


def refresh_current_enterprise_cit_candidates_from_ydz(
    args: argparse.Namespace,
    collector: YdzCollector,
    resolver: VerifyTaskResolver,
    template: Any,
    original_candidates: list[Any],
    max_candidates: int,
) -> tuple[list[dict[str, Any]], list[SupplementCandidate]]:
    target_key = str(getattr(template, "target_key", "") or "")
    periods = ydz_cit_refresh_periods(args, template, original_candidates)
    records: list[dict[str, Any]] = []
    fresh_candidates: list[SupplementCandidate] = []
    tried_accounts: set[tuple[str, str]] = set()
    original_tax_nos = {
        str(getattr(candidate, "tax_no", "") or "")
        for candidate in original_candidates
        if str(getattr(candidate, "tax_no", "") or "")
    }
    attempt_limit = max(1, int(max_candidates or 1))
    attempts = 0
    for period in periods:
        if attempts >= attempt_limit or fresh_candidates:
            break
        try:
            accounts = collector.list_accounts(
                period=period,
                page_size=CIT_A_YDZ_ACCOUNT_SCAN_PAGE_SIZE,
                max_pages=CIT_A_YDZ_ACCOUNT_SCAN_MAX_PAGES,
            )
        except Exception as exc:
            records.append(
                {
                    "targetKey": target_key,
                    "period": period,
                    "status": "failed",
                    "reason": friendly_collect_exception(exc),
                    "source": "current_enterprise_account_scan",
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
            )
            continue

        sorted_accounts = [
            account for account in sort_current_enterprise_cit_accounts(accounts) if account_has_cit_signal(account)
        ]
        cit_signal_count = len(sorted_accounts)
        records.append(
            {
                "targetKey": target_key,
                "period": period,
                "status": "account_scan",
                "reason": "current_enterprise_account_scan",
                "source": "current_enterprise_account_scan",
                "accountCount": len(accounts),
                "citSignalCount": cit_signal_count,
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
        )
        if not sorted_accounts:
            records.append(
                {
                    "targetKey": target_key,
                    "period": period,
                    "status": "skipped",
                    "reason": "current_enterprise_scan_no_cit_account_signal",
                    "source": "current_enterprise_account_scan",
                    "accountCount": len(accounts),
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
            )
            continue
        for account in sorted_accounts:
            if attempts >= attempt_limit or fresh_candidates:
                break
            if account.tax_no in original_tax_nos:
                continue
            key = (account.tax_no, period)
            if key in tried_accounts:
                continue
            tried_accounts.add(key)
            attempts += 1
            record, new_candidates = refresh_one_current_enterprise_cit_account_from_ydz(
                args=args,
                collector=collector,
                resolver=resolver,
                template=template,
                account=account,
                period=period,
            )
            records.append(record)
            fresh_candidates.extend(new_candidates)
    if not fresh_candidates:
        records.append(
            {
                "targetKey": target_key,
                "status": "skipped",
                "reason": "current_enterprise_scan_no_fresh_task_id",
                "source": "current_enterprise_account_scan",
                "periods": periods,
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
        )
    return records, fresh_candidates


def scan_other_ydz_enterprises_for_cit_accounts(
    args: argparse.Namespace,
    session: YdzSession,
    target_key: str,
    current_enterprise: str,
) -> list[dict[str, Any]]:
    username, password = get_env_credentials()
    period = normalize_period_yyyymm(str(getattr(args, "period", "") or "")) or str(getattr(args, "period", "") or "")
    limit = max(1, int(getattr(args, "coverage_supplement_ydz_enterprise_scan_limit", 8) or 8))
    explicit_names = [
        name.strip()
        for name in str(getattr(args, "coverage_supplement_ydz_enterprise_names", "") or "").split(",")
        if name.strip()
    ]
    records: list[dict[str, Any]] = []
    try:
        detected_names = session.list_enterprises(username=username, password=password, limit=limit + len(explicit_names) + 1)
    except Exception as exc:
        detected_names = []
        records.append(
            {
                "targetKey": target_key,
                "period": period,
                "status": "failed",
                "reason": friendly_collect_exception(exc),
                "source": "other_enterprise_selector_scan",
                "currentEnterprise": current_enterprise,
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
        )

    enterprises = [
        name
        for name in unique_texts(explicit_names + detected_names)
        if name and not same_ydz_enterprise_name(name, current_enterprise)
    ][:limit]
    if not enterprises:
        records.append(
            {
                "targetKey": target_key,
                "period": period,
                "status": "skipped",
                "reason": "other_enterprise_scan_no_selectable_enterprises",
                "source": "other_enterprise_account_scan",
                "currentEnterprise": current_enterprise,
                "enterpriseScanCount": 0,
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return records

    for enterprise in enterprises:
        try:
            page = session.switch_enterprise(username=username, password=password, enterprise=enterprise)
            api = YdzApi(page)
            collector = YdzCollector(
                api=api,
                enterprise=enterprise,
                tax_type_ids=CIT_A_YDZ_TAX_TYPE_IDS,
                poll_interval=int(getattr(args, "poll_interval", 15) or 15),
                poll_timeout=int(getattr(args, "poll_timeout", 600) or 600),
            )
            accounts = collector.list_accounts(
                period=period,
                page_size=CIT_A_YDZ_ACCOUNT_SCAN_PAGE_SIZE,
                max_pages=CIT_A_YDZ_ACCOUNT_SCAN_MAX_PAGES,
            )
            cit_accounts = [
                account for account in sort_current_enterprise_cit_accounts(accounts) if account_has_cit_signal(account)
            ]
            records.append(
                {
                    "targetKey": target_key,
                    "period": period,
                    "status": "account_scan",
                    "reason": "other_enterprise_account_scan",
                    "source": "other_enterprise_account_scan",
                    "currentEnterprise": current_enterprise,
                    "enterprise": enterprise,
                    "accountCount": len(accounts),
                    "citSignalCount": len(cit_accounts),
                    "sampleTaxNos": [account.tax_no for account in cit_accounts[:5]],
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
            )
            if cit_accounts:
                break
        except Exception as exc:
            records.append(
                {
                    "targetKey": target_key,
                    "period": period,
                    "status": "failed",
                    "reason": friendly_collect_exception(exc),
                    "source": "other_enterprise_account_scan",
                    "currentEnterprise": current_enterprise,
                    "enterprise": enterprise,
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
            )
    return records


def refresh_explicit_ydz_work_url_cit_candidates_from_ydz(
    args: argparse.Namespace,
    session: YdzSession,
    resolver: VerifyTaskResolver,
    template: Any,
    original_candidates: list[Any],
    current_enterprise: str,
    max_candidates: int,
) -> tuple[list[dict[str, Any]], list[SupplementCandidate]]:
    target_key = str(getattr(template, "target_key", "") or "")
    period = normalize_period_yyyymm(str(getattr(args, "period", "") or "")) or str(getattr(args, "period", "") or "")
    urls = explicit_ydz_work_urls(args)
    records: list[dict[str, Any]] = []
    fresh_candidates: list[SupplementCandidate] = []
    if not urls:
        return records, fresh_candidates

    attempted_accounts: set[tuple[str, str]] = set()
    attempt_limit = max(1, int(max_candidates or 1))
    attempts = 0

    for work_url in urls:
        if attempts >= attempt_limit or fresh_candidates:
            break
        label = redact_ydz_work_url_label(work_url)
        try:
            page = session.open_work_url(work_url)
            collector = YdzCollector(
                api=YdzApi(page),
                enterprise=label,
                tax_type_ids=CIT_A_YDZ_TAX_TYPE_IDS,
                poll_interval=int(getattr(args, "poll_interval", 15) or 15),
                poll_timeout=int(getattr(args, "poll_timeout", 600) or 600),
            )
            accounts = collector.list_accounts(
                period=period,
                page_size=CIT_A_YDZ_ACCOUNT_SCAN_PAGE_SIZE,
                max_pages=CIT_A_YDZ_ACCOUNT_SCAN_MAX_PAGES,
            )
            cit_accounts = [
                account for account in sort_current_enterprise_cit_accounts(accounts) if account_has_cit_signal(account)
            ]
            records.append(
                {
                    "targetKey": target_key,
                    "period": period,
                    "status": "account_scan",
                    "reason": "explicit_work_url_account_scan",
                    "source": "explicit_work_url_account_scan",
                    "currentEnterprise": current_enterprise,
                    "enterprise": label,
                    "accountCount": len(accounts),
                    "citSignalCount": len(cit_accounts),
                    "sampleTaxNos": [account.tax_no for account in cit_accounts[:5]],
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
            )
            for account in cit_accounts:
                if attempts >= attempt_limit or fresh_candidates:
                    break
                account_key = (account.tax_no, period)
                if account_key in attempted_accounts:
                    continue
                attempted_accounts.add(account_key)
                attempts += 1
                record, new_candidates = refresh_one_current_enterprise_cit_account_from_ydz(
                    args=args,
                    collector=collector,
                    resolver=resolver,
                    template=template,
                    account=account,
                    period=period,
                )
                record.update(
                    {
                        "source": "explicit_work_url_account_scan",
                        "currentEnterprise": current_enterprise,
                        "enterprise": label,
                    }
                )
                records.append(record)
                fresh_candidates.extend(new_candidates)
        except Exception as exc:
            records.append(
                {
                    "targetKey": target_key,
                    "period": period,
                    "status": "failed",
                    "reason": friendly_collect_exception(exc),
                    "source": "explicit_work_url_account_scan",
                    "currentEnterprise": current_enterprise,
                    "enterprise": label,
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
            )

    if not fresh_candidates:
        records.append(
            {
                "targetKey": target_key,
                "period": period,
                "status": "skipped",
                "reason": "explicit_work_url_scan_no_fresh_task_id",
                "source": "explicit_work_url_account_scan",
                "currentEnterprise": current_enterprise,
                "urlCount": len(urls),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
        )
    return records, fresh_candidates


def refresh_open_ydz_work_tab_cit_candidates_from_ydz(
    args: argparse.Namespace,
    session: YdzSession,
    resolver: VerifyTaskResolver,
    template: Any,
    current_enterprise: str,
    max_candidates: int,
    exclude_urls: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[SupplementCandidate]]:
    target_key = str(getattr(template, "target_key", "") or "")
    period = normalize_period_yyyymm(str(getattr(args, "period", "") or "")) or str(getattr(args, "period", "") or "")
    records: list[dict[str, Any]] = []
    fresh_candidates: list[SupplementCandidate] = []
    pages = session.ready_open_work_pages(exclude_urls=exclude_urls or set())
    if not pages:
        records.append(
            {
                "targetKey": target_key,
                "period": period,
                "status": "skipped",
                "reason": "open_work_tab_scan_no_ready_pages",
                "source": "open_work_tab_scan",
                "currentEnterprise": current_enterprise,
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return records, fresh_candidates

    attempted_accounts: set[tuple[str, str]] = set()
    attempt_limit = max(1, int(max_candidates or 1))
    attempts = 0
    for page in pages:
        if attempts >= attempt_limit or fresh_candidates:
            break
        try:
            label = redact_ydz_work_url_label(str(getattr(page, "url", "") or ""))
        except Exception:
            label = "open-ydz-work-tab"
        try:
            collector = YdzCollector(
                api=YdzApi(page),
                enterprise=label,
                tax_type_ids=CIT_A_YDZ_TAX_TYPE_IDS,
                poll_interval=int(getattr(args, "poll_interval", 15) or 15),
                poll_timeout=int(getattr(args, "poll_timeout", 600) or 600),
            )
            accounts = collector.list_accounts(
                period=period,
                page_size=CIT_A_YDZ_ACCOUNT_SCAN_PAGE_SIZE,
                max_pages=CIT_A_YDZ_ACCOUNT_SCAN_MAX_PAGES,
            )
            cit_accounts = [
                account for account in sort_current_enterprise_cit_accounts(accounts) if account_has_cit_signal(account)
            ]
            records.append(
                {
                    "targetKey": target_key,
                    "period": period,
                    "status": "account_scan",
                    "reason": "open_work_tab_account_scan",
                    "source": "open_work_tab_account_scan",
                    "currentEnterprise": current_enterprise,
                    "enterprise": label,
                    "accountCount": len(accounts),
                    "citSignalCount": len(cit_accounts),
                    "sampleTaxNos": [account.tax_no for account in cit_accounts[:5]],
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
            )
            for account in cit_accounts:
                if attempts >= attempt_limit or fresh_candidates:
                    break
                account_key = (account.tax_no, period)
                if account_key in attempted_accounts:
                    continue
                attempted_accounts.add(account_key)
                attempts += 1
                record, new_candidates = refresh_one_current_enterprise_cit_account_from_ydz(
                    args=args,
                    collector=collector,
                    resolver=resolver,
                    template=template,
                    account=account,
                    period=period,
                )
                record.update(
                    {
                        "source": "open_work_tab_account_scan",
                        "currentEnterprise": current_enterprise,
                        "enterprise": label,
                    }
                )
                records.append(record)
                fresh_candidates.extend(new_candidates)
        except Exception as exc:
            records.append(
                {
                    "targetKey": target_key,
                    "period": period,
                    "status": "failed",
                    "reason": friendly_collect_exception(exc),
                    "source": "open_work_tab_account_scan",
                    "currentEnterprise": current_enterprise,
                    "enterprise": label,
                    "updatedAt": datetime.now().isoformat(timespec="seconds"),
                }
            )

    if not fresh_candidates:
        records.append(
            {
                "targetKey": target_key,
                "period": period,
                "status": "skipped",
                "reason": "open_work_tab_scan_no_fresh_task_id",
                "source": "open_work_tab_account_scan",
                "currentEnterprise": current_enterprise,
                "tabCount": len(pages),
                "updatedAt": datetime.now().isoformat(timespec="seconds"),
            }
        )
    return records, fresh_candidates


def same_ydz_enterprise_name(name: str, current_enterprise: str) -> bool:
    left = "".join(str(name or "").split())
    right = "".join(str(current_enterprise or "").split())
    if not left or not right:
        return False
    return left == right or left.startswith(right) or right.startswith(left)


def retarget_ydz_enterprise_scan_records(records: list[dict[str, Any]], target_key: str) -> list[dict[str, Any]]:
    retargeted: list[dict[str, Any]] = []
    for record in records or []:
        copied = dict(record)
        copied["targetKey"] = target_key
        retargeted.append(copied)
    return retargeted


def ydz_cit_refresh_periods(args: argparse.Namespace, template: Any, original_candidates: list[Any]) -> list[str]:
    values: list[str] = []
    values.append(str(getattr(args, "period", "") or ""))
    for candidate in original_candidates:
        values.append(str(getattr(candidate, "period", "") or ""))
    values.append(str(getattr(template, "period", "") or ""))
    periods = [normalize_period_yyyymm(value) for value in values]
    return unique_texts([period for period in periods if period])[:CIT_A_YDZ_ACCOUNT_SCAN_MAX_PERIODS]


def sort_current_enterprise_cit_accounts(accounts: list[YdzAccount]) -> list[YdzAccount]:
    return sorted(
        accounts,
        key=lambda account: (
            0 if account_has_cit_signal(account) else 1,
            0 if str(account.auth_status or "") in {"", "AUTHORIZED"} else 1,
            str(account.tax_no or ""),
        ),
    )


def account_has_cit_signal(account: YdzAccount) -> bool:
    for detail in (account.raw or {}).get("taxItemDetailList") or []:
        try:
            tax_type_id = int(detail.get("taxTypeId"))
        except (TypeError, ValueError):
            tax_type_id = None
        text = " ".join(
            str(detail.get(key) or "")
            for key in ("taxTypeName", "taxName", "name", "message", "initStatusEnum")
        )
        if tax_type_id == 2 or "\u4f01\u4e1a\u6240\u5f97\u7a0e" in text:
            return True
    return False


def refresh_one_current_enterprise_cit_account_from_ydz(
    args: argparse.Namespace,
    collector: YdzCollector,
    resolver: VerifyTaskResolver,
    template: Any,
    account: YdzAccount,
    period: str,
) -> tuple[dict[str, Any], list[SupplementCandidate]]:
    target_key = str(getattr(template, "target_key", "") or "")
    record = {
        "targetKey": target_key,
        "sourceTaskId": str(getattr(template, "task_id", "") or ""),
        "taxNo": account.tax_no,
        "period": period,
        "status": "checking",
        "reason": "current_enterprise_account_scan",
        "source": "current_enterprise_account_scan",
        "taskIds": [],
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        result = collector.submit_collect_tax_no(tax_no=account.tax_no, period=period, force=True)
        poll_fresh_supplement_collect_result(collector, result, args)
        if is_result_ready_for_task_resolution(result) or result.submitted:
            resolver.resolve_all(result.tax_no, result.period, submitted_at=result.submitted_at)
            apply_resolved_tasks_to_result(resolver, result)
    except Exception as exc:
        record.update({"status": "failed", "reason": friendly_collect_exception(exc)})
        return record, []

    record.update(
        {
            "collectStatus": result.status,
            "manualRequired": result.manual_required,
            "warnings": list(result.warnings or [])[:3],
            "errors": list(result.errors or [])[:3],
            "taxItems": list(result.tax_items or [])[:5],
        }
    )
    task_ids = result_task_ids(result)
    record["taskIds"] = task_ids
    if not task_ids:
        if str(result.status or "").upper() == "NO_NEED_COLLECTED":
            reason = no_need_collect_reason(result.to_dict())
        else:
            reason = collect_failure_reason(result.to_dict()) or "fresh_ydz_collect_no_task_id"
        record.update({"status": "failed", "reason": reason})
        return record, []

    created_by_task_id = {
        str(task.task_id): task.created_stamp
        for task in getattr(resolver, "last_tasks", []) or []
        if getattr(task, "task_id", None)
    }
    fresh_candidates = [
        clone_supplement_candidate_with_account_task(
            template,
            account=account,
            task_id=task_id,
            period=period,
            created_stamp=created_by_task_id.get(str(task_id)),
        )
        for task_id in task_ids
    ]
    record.update({"status": "resolved", "reason": "fresh_ydz_collect_task_resolved"})
    return record, fresh_candidates


def refresh_one_supplement_candidate_from_ydz(
    args: argparse.Namespace,
    collector: YdzCollector,
    resolver: VerifyTaskResolver,
    candidate: Any,
) -> tuple[dict[str, Any], list[SupplementCandidate]]:
    target_key = str(getattr(candidate, "target_key", "") or "")
    tax_no = str(getattr(candidate, "tax_no", "") or "")
    if target_key.startswith("CIT_A:"):
        period = normalize_period_yyyymm(str(getattr(args, "period", "") or "")) or str(
            getattr(args, "period", "") or ""
        )
    else:
        period = str(getattr(candidate, "period", "") or getattr(args, "period", "") or "")
    record = {
        "targetKey": target_key,
        "sourceTaskId": str(getattr(candidate, "task_id", "") or ""),
        "taxNo": tax_no,
        "period": period,
        "status": "checking",
        "reason": "",
        "taskIds": [],
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }
    if not tax_no or not period:
        record.update({"status": "skipped", "reason": "candidate_missing_tax_no_or_period"})
        return record, []

    account = collector.find_account(tax_no, period)
    if account is None:
        record.update({"status": "skipped", "reason": "no_ydz_account_in_current_enterprise"})
        return record, []

    try:
        result = collector.submit_collect_tax_no(tax_no=tax_no, period=period, force=True)
        poll_fresh_supplement_collect_result(collector, result, args)
        if is_result_ready_for_task_resolution(result) or result.submitted:
            resolver.resolve_all(result.tax_no, result.period, submitted_at=result.submitted_at)
            apply_resolved_tasks_to_result(resolver, result)
    except Exception as exc:
        record.update({"status": "failed", "reason": friendly_collect_exception(exc)})
        return record, []

    record.update(
        {
            "collectStatus": result.status,
            "manualRequired": result.manual_required,
            "warnings": list(result.warnings or [])[:3],
            "errors": list(result.errors or [])[:3],
            "taxItems": list(result.tax_items or [])[:5],
        }
    )
    task_ids = result_task_ids(result)
    record["taskIds"] = task_ids
    if not task_ids:
        if str(result.status or "").upper() == "NO_NEED_COLLECTED":
            reason = no_need_collect_reason(result.to_dict())
        else:
            reason = collect_failure_reason(result.to_dict()) or "fresh_ydz_collect_no_task_id"
        record.update({"status": "failed", "reason": reason})
        return record, []

    created_by_task_id = {
        str(task.task_id): task.created_stamp
        for task in getattr(resolver, "last_tasks", []) or []
        if getattr(task, "task_id", None)
    }
    fresh_candidates = [
        clone_supplement_candidate_with_task(
            candidate,
            task_id=task_id,
            period=result.period,
            created_stamp=created_by_task_id.get(str(task_id)),
        )
        for task_id in task_ids
    ]
    record.update({"status": "resolved", "reason": "fresh_ydz_collect_task_resolved"})
    return record, fresh_candidates


def poll_fresh_supplement_collect_result(
    collector: YdzCollector,
    result: YdzCollectResult,
    args: argparse.Namespace,
) -> None:
    if not result.submitted or result.terminal or result.manual_required:
        return
    timeout = min(
        max(1, int(getattr(args, "poll_timeout", 600) or 600)),
        CIT_A_YDZ_REFRESH_POLL_TIMEOUT_SECONDS,
    )
    interval = max(1, int(getattr(args, "poll_interval", 15) or 15))
    deadline = time.time() + timeout
    while time.time() < deadline:
        collector.refresh_collect_status(result)
        if result.terminal or result.manual_required or result.status in TERMINAL_COLLECT_STATUSES:
            return
        time.sleep(interval)
    result.manual_required = True
    result.errors.append(f"Timed out waiting for fresh supplement collection; last status={result.status}.")


def clone_supplement_candidate_with_task(
    candidate: Any,
    task_id: str,
    period: str,
    created_stamp: int | None,
) -> SupplementCandidate:
    return SupplementCandidate(
        target_key=str(getattr(candidate, "target_key", "") or ""),
        tax_type=str(getattr(candidate, "tax_type", "") or ""),
        tax_type_name=str(getattr(candidate, "tax_type_name", "") or ""),
        declaration_status=str(getattr(candidate, "declaration_status", "") or ""),
        declaration_status_name=str(getattr(candidate, "declaration_status_name", "") or ""),
        task_id=str(task_id),
        tax_no=str(getattr(candidate, "tax_no", "") or ""),
        period=period or str(getattr(candidate, "period", "") or ""),
        task_status="SUCCESS",
        backend_tax_type_id=str(getattr(candidate, "backend_tax_type_id", "") or ""),
        backend_tax_id=str(getattr(candidate, "backend_tax_id", "") or ""),
        backend_query_field=str(getattr(candidate, "backend_query_field", "") or ""),
        created_stamp=created_stamp if created_stamp is not None else int(time.time() * 1000),
        parse_status=str(getattr(candidate, "parse_status", "") or ""),
        reason="fresh_ydz_collect",
    )


def clone_supplement_candidate_with_account_task(
    candidate: Any,
    account: YdzAccount,
    task_id: str,
    period: str,
    created_stamp: int | None,
) -> SupplementCandidate:
    return SupplementCandidate(
        target_key=str(getattr(candidate, "target_key", "") or ""),
        tax_type=str(getattr(candidate, "tax_type", "") or ""),
        tax_type_name=str(getattr(candidate, "tax_type_name", "") or ""),
        declaration_status=str(getattr(candidate, "declaration_status", "") or ""),
        declaration_status_name=str(getattr(candidate, "declaration_status_name", "") or ""),
        task_id=str(task_id),
        tax_no=str(account.tax_no or ""),
        period=period or str(getattr(candidate, "period", "") or ""),
        task_status="SUCCESS",
        backend_tax_type_id=str(getattr(candidate, "backend_tax_type_id", "") or ""),
        backend_tax_id=str(getattr(candidate, "backend_tax_id", "") or ""),
        backend_query_field=str(getattr(candidate, "backend_query_field", "") or ""),
        created_stamp=created_stamp if created_stamp is not None else int(time.time() * 1000),
        parse_status="unknown",
        reason="fresh_ydz_collect",
    )


def merge_fresh_supplement_candidates(
    fresh_candidates: list[Any],
    original_candidates: list[Any],
    max_candidates: int,
) -> list[Any]:
    merged: list[Any] = []
    seen_task_ids: set[str] = set()
    for candidate in [*fresh_candidates, *original_candidates]:
        task_id = str(getattr(candidate, "task_id", "") or "")
        if not task_id or task_id in seen_task_ids:
            continue
        seen_task_ids.add(task_id)
        merged.append(candidate)
    return sorted(merged, key=supplement_candidate_sort_key)[: max(1, int(max_candidates or 1))]


def coverage_target_is_covered(coverage_payload: dict[str, Any], target_key: str) -> bool:
    for target in coverage_payload.get("targets") or []:
        if str(target.get("key") or "") == str(target_key) and bool(target.get("covered")):
            return True
    return False


def supplement_verify_record_for_item(item: dict[str, Any], task_id: str = "") -> dict[str, Any]:
    if task_id:
        task_verify = task_verify_entry(item, task_id)
        if task_verify:
            return task_verify
    verify = item.get("verify") or {}
    return verify if isinstance(verify, dict) else {}


def supplement_verify_record_is_clean(verify: dict[str, Any]) -> bool:
    if not isinstance(verify, dict):
        return False
    if str(verify.get("status") or "") != "success":
        return False
    try:
        return_code = int(verify.get("returnCode") or 0)
    except (TypeError, ValueError):
        return False
    return return_code == 0


def supplement_item_has_clean_verification(item: dict[str, Any], task_id: str = "") -> bool:
    return supplement_verify_record_is_clean(supplement_verify_record_for_item(item, task_id))


def supplement_remaining_missing_keys(missing_targets: list[Any], covered_keys: list[str]) -> list[str]:
    covered = {str(key) for key in covered_keys}
    return [
        str(getattr(target, "key", "") or "")
        for target in missing_targets
        if str(getattr(target, "key", "") or "") not in covered
    ]


def build_supplement_attempt_record(
    candidate: Any,
    target: Any,
    attempt_no: int,
    total_candidates: int,
    item_key: str,
    status: str,
    step: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "targetKey": str(getattr(target, "key", "") or getattr(candidate, "target_key", "") or ""),
        "taxType": str(getattr(candidate, "tax_type", "") or getattr(target, "tax_type", "") or ""),
        "taxTypeName": str(getattr(candidate, "tax_type_name", "") or getattr(target, "tax_type_name", "") or ""),
        "declarationStatus": str(
            getattr(candidate, "declaration_status", "") or getattr(target, "declaration_status", "") or ""
        ),
        "declarationStatusName": str(
            getattr(candidate, "declaration_status_name", "")
            or getattr(target, "declaration_status_name", "")
            or ""
        ),
        "taskId": str(getattr(candidate, "task_id", "") or ""),
        "taxNo": str(getattr(candidate, "tax_no", "") or ""),
        "period": str(getattr(candidate, "period", "") or ""),
        "backendTaxTypeId": str(getattr(candidate, "backend_tax_type_id", "") or ""),
        "backendTaxId": str(getattr(candidate, "backend_tax_id", "") or ""),
        "backendQueryField": str(getattr(candidate, "backend_query_field", "") or ""),
        "parseStatus": str(getattr(candidate, "parse_status", "") or ""),
        "candidateReason": str(getattr(candidate, "reason", "") or ""),
        "itemKey": item_key,
        "attemptNo": attempt_no,
        "totalCandidates": total_candidates,
        "status": status,
        "step": step,
        "reason": normalize_supplement_failure_reason(reason),
        "updatedAt": datetime.now().isoformat(timespec="seconds"),
    }


def update_supplement_attempt_record(
    attempt: dict[str, Any],
    item: dict[str, Any],
    covered: bool,
    task_id: str = "",
    matrix_covered: bool = False,
) -> None:
    verify = supplement_verify_record_for_item(item, task_id)
    reason = verify.get("reason") or item.get("stageReason") or ""
    verify_status = str(verify.get("status") or "")
    if covered:
        attempt.update(
            {
                "status": "covered",
                "step": "覆盖成功",
                "reason": "该候选任务已生成有效报告并覆盖目标税种/申报状态。",
            }
        )
    else:
        if matrix_covered and not supplement_verify_record_is_clean(verify) and not reason:
            reason = (
                "Coverage matrix has an existing report for this target, "
                "but the current supplement candidate did not verify successfully."
            )
        failure_category = classify_supplement_failure_category(reason)
        failure_step = classify_supplement_failure_step(reason, verify_status)
        failure_reason = normalize_supplement_failure_reason(reason or "验证后没有命中目标税种/申报状态。")
        attempt.update(
            {
                "status": "failed",
                "step": failure_step,
                "failureCategory": failure_category,
                "reason": failure_reason,
            }
        )
    attempt.update(
        {
            "verifyStatus": verify_status,
            "returnCode": verify.get("returnCode"),
            "summaryPath": verify.get("summaryPath") or "",
            "reportPaths": verify.get("reportPaths") or [],
            "stdoutLog": verify.get("stdoutLog") or "",
            "stderrLog": verify.get("stderrLog") or "",
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
    )


def is_tax_login_switch_limit_reason(reason: str) -> bool:
    lower = str(reason or "").lower()
    return (
        "same-province" in lower
        or "same province" in lower
        or "switch limit" in lower
        or ("wait" in lower and "1 hour" in lower)
    )


def classify_supplement_failure_step(reason: str, verify_status: str = "") -> str:
    text = str(reason or "")
    lower = text.lower()
    if "undeclaredtaxalreadydeclarederror" in lower or "already declared" in lower:
        return "税局现场状态冲突"
    if "undeclaredtaxtargetunavailableerror" in lower or "undeclared tax target is unavailable" in lower:
        return "查找未申报入口"
    if (
        "taxloginnotreadyerror" in lower
        or "tax bureau login state or digital account authentication is not ready" in lower
        or "getclientjob returned incomplete tax-login metadata" in lower
        or "getclientjob returned a non-object response" in lower
        or "getclientjob failed" in lower
        or "getclientjob failed after retries" in lower
        or "cannot resolve inner taskid from getclientjob response" in lower
        or "cannot resolve province from getclientjob response" in lower
        or "cannot resolve province from task cookie/client job data" in lower
        or "gettaskcookie" in lower
        or "declarationqueryautherror" in lower
        or "tax bureau login timeout" in lower
        or "login timeout" in lower
        or "\u7a0e\u5c40\u767b\u5f55\u6001" in text
        or "\u6570\u5b57\u8d26\u6237\u8ba4\u8bc1" in text
        or "\u540c\u7701\u5207\u6362" in text
        or "\u9891\u7e41\u5207\u6362" in text
        or "\u7b49\u5f851\u5c0f\u65f6\u540e\u518d\u91cd\u8bd5" in text
        or is_tax_login_switch_limit_reason(text)
    ):
        return "税局登录"
    if "could not navigate to declaration query page" in lower or "/loading" in lower:
        return "进入申报查询页"
    if "declaration row was not found" in lower or "query returned no row" in lower:
        return "查找申报记录"
    if "target form" in lower or "confirm" in lower or "切换" in text:
        return "切换/确认申报表"
    if is_no_targets_verify_reason(text):
        return "选择验证表单"
    if verify_status == "completed_with_differences":
        return "字段比对"
    if verify_status == "skipped":
        return "验证跳过"
    return "验证任务"


def classify_supplement_failure_category(reason: str) -> str:
    text = str(reason or "")
    lower = text.lower()
    if "undeclaredtaxalreadydeclarederror" in lower or "already declared" in lower:
        return "source_state_conflict"
    if "declaration row was not found" in lower or "query returned no row" in lower or "未查询到目标申报记录" in text:
        return "source_state_conflict"
    if "undeclaredtaxtargetunavailableerror" in lower or "undeclared tax target is unavailable" in lower:
        return "target_entry_unavailable"
    if (
        "pendingtaxloginjoberror" in lower
        or "needforcetax" in lower
        or "force-enter" in lower
        or "\u540c\u7701\u5207\u6362" in text
        or "\u9891\u7e41\u5207\u6362" in text
        or "\u7b49\u5f851\u5c0f\u65f6\u540e\u518d\u91cd\u8bd5" in text
        or ("\u7cfb\u7edf\u9650\u5236" in text and "1\u5c0f\u65f6" in text)
        or is_tax_login_switch_limit_reason(text)
    ):
        return "tax_login_blocked"
    if (
        "getclientjob returned incomplete tax-login metadata" in lower
        or "getclientjob returned a non-object response" in lower
        or "getclientjob failed" in lower
        or "getclientjob failed after retries" in lower
        or "cannot resolve inner taskid from getclientjob response" in lower
        or "cannot resolve province from getclientjob response" in lower
        or "cannot resolve province from task cookie/client job data" in lower
    ):
        return "tax_login_expired"
    if (
        "declarationqueryautherror" in lower
        or "taxloginnotreadyerror" in lower
        or "tax bureau login state or digital account authentication is not ready" in lower
        or "getclientjob returned incomplete tax-login metadata" in lower
        or "getclientjob returned a non-object response" in lower
        or "getclientjob failed" in lower
        or "getclientjob failed after retries" in lower
        or "cannot resolve inner taskid from getclientjob response" in lower
        or "cannot resolve province from getclientjob response" in lower
        or "cannot resolve province from task cookie/client job data" in lower
        or "tpass." in lower
        or "/loading" in lower
        or "gettaskcookie" in lower
        or "\u7a0e\u5c40\u767b\u5f55\u6001" in text
        or "\u6570\u5b57\u8d26\u6237\u8ba4\u8bc1" in text
        or "登录连接状态已失效" in text
        or "重新发起任务" in text
    ):
        return "tax_login_expired"
    if "timeout" in lower:
        return "timeout"
    return "verification_failed"


def supplement_final_verify_exit_code(
    verify_exit: int,
    remaining_missing: list[str],
    missing_targets: list[Any],
    covered_keys: list[str],
    attempts: list[dict[str, Any]],
) -> int:
    if not remaining_missing:
        return 0
    return verify_exit


STABLE_SUPPLEMENT_EXCLUDE_CATEGORIES = {
    "tax_login_expired",
    "tax_login_blocked",
    "source_state_conflict",
    "target_entry_unavailable",
}


def supplement_excluded_task_ids_from_attempts(attempts: list[dict[str, Any]]) -> dict[str, set[str]]:
    excluded: dict[str, set[str]] = {}
    for attempt in attempts or []:
        if not isinstance(attempt, dict):
            continue
        if str(attempt.get("status") or "") != "failed":
            continue
        target_key = str(attempt.get("targetKey") or "")
        task_id = str(attempt.get("taskId") or "")
        if not target_key or not task_id:
            continue
        category = str(attempt.get("failureCategory") or "")
        if not category:
            category = classify_supplement_failure_category(str(attempt.get("reason") or ""))
        if category not in STABLE_SUPPLEMENT_EXCLUDE_CATEGORIES:
            continue
        excluded.setdefault(target_key, set()).add(task_id)
    return excluded


def supplement_excluded_task_ids_from_state(state: dict[str, Any]) -> dict[str, set[str]]:
    excluded: dict[str, set[str]] = {}
    supplement = state.get("coverageSupplement") if isinstance(state, dict) else {}
    if isinstance(supplement, dict):
        excluded = merge_excluded_task_id_maps(
            excluded,
            supplement_excluded_task_ids_from_preflight(supplement.get("loginPreflight") or []),
        )

    items = state.get("items") if isinstance(state, dict) else {}
    if not isinstance(items, dict):
        return excluded
    for item in items.values():
        if not isinstance(item, dict):
            continue
        if str(item.get("source") or "") != "backend_supplement":
            continue
        target_keys: list[str] = [
            str(value or "")
            for value in (item.get("coverageSupplementTargets") or [])
            if str(value or "")
        ]
        resolved = (item.get("collect") or {}).get("resolvedTask") or {}
        resolved_target = str(resolved.get("coverageTarget") or "")
        if resolved_target and resolved_target not in target_keys:
            target_keys.append(resolved_target)
        if not target_keys:
            continue

        verify_records: list[tuple[str, dict[str, Any]]] = []
        verify_tasks = item.get("verifyTasks") or {}
        if isinstance(verify_tasks, dict):
            for task_id, verify in verify_tasks.items():
                if isinstance(verify, dict):
                    verify_records.append((str(task_id or ""), verify))
        collect_task_id = str(((item.get("collect") or {}).get("verifyTaskId")) or "")
        aggregate_verify = item.get("verify") or {}
        if collect_task_id and isinstance(aggregate_verify, dict) and collect_task_id not in verify_tasks:
            verify_records.append((collect_task_id, aggregate_verify))

        for task_id, verify in verify_records:
            if not task_id:
                continue
            if str(verify.get("status") or "") != "failed":
                continue
            category = classify_supplement_failure_category(str(verify.get("reason") or item.get("stageReason") or ""))
            if category not in STABLE_SUPPLEMENT_EXCLUDE_CATEGORIES:
                continue
            for target_key in target_keys:
                excluded.setdefault(target_key, set()).add(task_id)
    return excluded


def merge_excluded_task_id_maps(*maps: dict[str, set[str]]) -> dict[str, set[str]]:
    merged: dict[str, set[str]] = {}
    for mapping in maps:
        for target_key, task_ids in (mapping or {}).items():
            if not target_key:
                continue
            merged.setdefault(str(target_key), set()).update(str(task_id) for task_id in task_ids if str(task_id))
    return merged


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
        chrome_path=args.chrome_path,
        user_data_dir=args.user_data_dir,
        plugin_path=args.plugin_path,
        chanjet_timeout=300,
        tax_timeout=args.tax_timeout,
        tax_login_strategy=args.tax_login_strategy,
        config_root="config",
        query_year=args.query_year,
    )


def resolve_cbj_mode(configured_mode: str, item: dict[str, Any], task_id: str = "") -> str:
    if configured_mode != "auto":
        return configured_mode
    collect = item.get("collect") or {}
    log_mode = resolve_cbj_mode_from_task_logs(task_id or item_cbj_task_id(item))
    if log_mode:
        return log_mode
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


def resolve_cbj_mode_from_task_logs(task_id: str) -> str:
    if not task_id:
        return ""
    try:
        mode = fetch_cbj_mode_from_task_logs(str(task_id)) or ""
    except Exception as exc:
        LOGGER.info("Could not resolve CBJ mode from task logs for taskId=%s: %s", task_id, exc)
        return ""
    if mode:
        LOGGER.info("Resolved CBJ mode from task logs for taskId=%s: %s", task_id, mode)
    return mode


def item_cbj_task_id(item: dict[str, Any]) -> str:
    collect = item.get("collect") or {}
    for key in ("verifyTaskId", "taskId"):
        value = collect.get(key)
        if value:
            return str(value)
    resolved = collect.get("resolvedTask") or {}
    for key in ("taskId", "id"):
        value = resolved.get(key)
        if value:
            return str(value)
    return ""


def item_requests_cbj_verification(item: dict[str, Any]) -> bool:
    for target in item.get("coverageSupplementTargets") or []:
        if str(target).startswith("CBJ_") or str(target).startswith("CBJ:"):
            return True
    collect = item.get("collect") or {}
    resolved = collect.get("resolvedTask") or {}
    if str(resolved.get("backendTaxTypeId") or "") in {"26", "31"} or str(resolved.get("backendTaxId") or "") == "39":
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


def latest_summary_path(report_dir: Path, since_ts: float | None = None) -> Path | None:
    if not report_dir.exists():
        return None
    summaries = [
        path
        for path in report_dir.glob("compare_summary_*.html")
        if since_ts is None or path.stat().st_mtime >= since_ts
    ]
    summaries = sorted(summaries, key=lambda path: path.stat().st_mtime, reverse=True)
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
        if report.get("quality_issues"):
            return True
    return False


def quality_issue_label(issue: Any) -> str:
    text = str(issue or "").strip()
    labels = {
        "declaration_status_unknown": "申报状态未知",
        "low_web_extraction_coverage": "网页解析覆盖率低",
    }
    if text.startswith("both_missing_ratio="):
        return "接口和网页同时为空比例过高"
    if text.startswith("mismatch="):
        return f"不一致{text.split('=', 1)[1]}"
    if text.startswith("api_missing="):
        return f"接口缺失{text.split('=', 1)[1]}"
    if text.startswith("web_missing="):
        return f"网页缺失{text.split('=', 1)[1]}"
    if text.startswith("parse_error="):
        return f"解析失败{text.split('=', 1)[1]}"
    if text.startswith("mapping_error="):
        return f"映射异常{text.split('=', 1)[1]}"
    return labels.get(text, text)


def compare_report_reason(
    task_id: str,
    max_forms: int = 4,
    reports: list[dict[str, Any]] | None = None,
    since_ts: float | None = None,
) -> str:
    issue_labels = [
        ("mismatch_count", "\u4e0d\u4e00\u81f4"),
        ("api_missing_count", "\u63a5\u53e3\u7f3a\u5931"),
        ("web_missing_count", "\u7f51\u9875\u7f3a\u5931"),
        ("parse_error_count", "\u89e3\u6790\u5931\u8d25"),
        ("mapping_error_count", "\u6620\u5c04\u5f02\u5e38"),
    ]
    parts: list[str] = []
    for report in reports if reports is not None else load_compare_reports(task_id, since_ts=since_ts):
        summary = report.get("summary") or {}
        issues = []
        for key, label in issue_labels:
            try:
                count = int(summary.get(key, 0) or 0)
            except (TypeError, ValueError):
                count = 0
            if count > 0:
                issues.append(f"{label}{count}")
        for issue in report.get("quality_issues") or []:
            label = quality_issue_label(issue)
            if label and label not in issues:
                issues.append(label)
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
        if text.startswith(
            (
                "RuntimeError:",
                "TimeoutError:",
                "ValueError:",
                "KeyError:",
                "FileNotFoundError:",
                "DeclarationQueryAuthError:",
                "scripts.compare_tax_forms.DeclarationQueryAuthError:",
                "scripts.compare_tax_forms.UndeclaredTaxTargetUnavailableError:",
                "scripts.compare_tax_forms.UndeclaredTaxAlreadyDeclaredError:",
                "playwright._impl._errors.Error:",
            )
        ):
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
    elif not collect_task_ids(collect) and verify_status == "skipped":
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
    actionable_low_coverage_forms = actionable_low_web_coverage_forms(verify)
    stderr_log = verify.get("stderrLog")
    if stderr_log:
        for line in read_log_lines(Path(str(stderr_log)), max_lines=300):
            if "low web extraction coverage" in line:
                match = re.search(r"([A-Za-z0-9_]+) low web extraction coverage: ([^\r\n]+)", line)
                if match:
                    form_id = match.group(1)
                    if form_id not in actionable_low_coverage_forms:
                        continue
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
            elif "declaration_status_unknown" in line:
                continue
    return unique_texts([risk for risk in risks if risk])


def actionable_low_web_coverage_forms(verify: dict[str, Any]) -> set[str]:
    forms: set[str] = set()
    for report in load_reports_from_verify(verify):
        form_id = str(report.get("batch_id") or report.get("target_id") or report.get("form_id") or "")
        summary = report.get("summary") or {}
        try:
            web_missing_count = int(summary.get("web_missing_count", 0) or 0)
        except (TypeError, ValueError):
            web_missing_count = 0
        quality_issues = {str(issue) for issue in report.get("quality_issues") or []}
        if web_missing_count > 0 or "low_web_extraction_coverage" in quality_issues:
            forms.add(form_id)
    return forms


def load_reports_from_verify(verify: dict[str, Any]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for report_path in verify.get("reportPaths") or []:
        path = Path(str(report_path))
        try:
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    return reports


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


def normalize_supplement_failure_reason(value: Any, limit: int = 260) -> str:
    text = compact_message(repair_mojibake_text(value), limit=900)
    if not text:
        return "验证后没有命中目标税种/申报状态。"
    lower = text.lower()
    if "pendingtaxloginjoberror" in lower or "已有进税局任务未完成" in text or "之前执行过 进税局" in text:
        task_id = extract_pending_tax_login_task_id(text)
        suffix = f"占用任务：{task_id}。" if task_id else ""
        return compact_message(
            f"已有进税局任务未完成，新的税局登录被后台拒绝。{suffix}请等待占用任务结束，或在后台处理后重试。",
            limit,
        )
    if (
        "getclientjob returned incomplete tax-login metadata" in lower
        or "getclientjob returned a non-object response" in lower
        or "getclientjob failed" in lower
        or "getclientjob failed after retries" in lower
        or "cannot resolve inner taskid from getclientjob response" in lower
        or "cannot resolve province from getclientjob response" in lower
        or "cannot resolve province from task cookie/client job data" in lower
    ):
        return compact_message(
            "Tax bureau login failed: getClientJob did not return complete tax-login metadata. "
            "The backend candidate's enter-tax-bureau login state is not ready; try the next candidate or recreate the collection task.",
            limit,
        )
    if "gettaskcookie failed" in lower:
        detail = clean_failure_detail(text.split(":", 1)[1] if ":" in text else "")
        if is_tax_login_switch_limit_reason(detail):
            return "税局登录被后台限制：同省税局切换过于频繁或仍有登录任务占用，请等待限制解除后重试。"
        if "登录连接状态已失效" in detail or "重新发起任务" in detail:
            return "税局登录失败：登录连接状态已失效，请重新发起取数任务后再验证。"
        if is_unreadable_failure_detail(detail):
            return "税局登录失败：获取进税局 cookie 失败，原始返回内容不可读。通常是登录连接状态失效、进税局任务过期或需要重新发起任务。"
        suffix = f" 原始提示：{detail}" if detail else ""
        return compact_message(f"税局登录失败：获取进税局 cookie 失败。通常是登录连接状态失效、进税局任务过期或需要重新发起任务。{suffix}", limit)
    if (
        "declarationqueryautherror" in lower
        or "taxloginnotreadyerror" in lower
        or "tax bureau login state or digital account authentication is not ready" in lower
        or ("tpass." in lower and "#/login" in lower)
        or "declaration query did not become usable" in lower
        or "stayed on loading page" in lower
        or "\u7a0e\u5c40\u767b\u5f55\u6001" in text
        or "\u6570\u5b57\u8d26\u6237\u8ba4\u8bc1" in text
        or "统一登录页" in text
        or "数字账户认证" in text
    ):
        return "税局登录态或数字账户认证已失效，请人工重新进入对应税局/数字账户后重试。"
    if "needforcetax" in lower or "force-enter confirmation" in lower:
        return "税局已有进行中的任务，需要人工确认是否强制进入税局后再验证。"
    if "tax bureau login timeout" in lower or "login timeout" in lower:
        return "税局登录超时：未在限定时间内进入已登录税局页面，请重新进入税局后重试。"
    if "could not navigate to declaration query page" in lower:
        target = extract_failure_target(text)
        url = extract_failure_url(text)
        target_text = form_id_display_name(target) if target else "目标申报表"
        url_text = f"当前URL：{shorten_url(url)}" if url else ""
        return compact_message(
            f"未能进入申报信息查询页：打开{target_text}前，税局页面停留在非申报查询页。请重新进入对应税局/数字账户后重试。{url_text}",
            limit,
        )
    if "/loading" in lower and ("declaration query" in lower or "申报" in text):
        return "未能进入申报信息查询页：税局页面停留在 loading 状态，请重新进入对应税局/数字账户后重试。"
    if "declaration row was not found" in lower or "query returned no row" in lower:
        return "未查询到目标申报记录：请核对申报表种类、所属期、申报日期条件，或确认该税种本期是否已申报。"
    if "undeclaredtaxtargetunavailableerror" in lower or "undeclared tax target is unavailable" in lower:
        target = extract_failure_target(text)
        target_text = form_id_display_name(target) if target else "目标税种"
        return compact_message(
            f"税局当前未找到{target_text}的未申报入口；如果页面只显示 B 类、核定征收或热门服务入口，应按源任务状态不匹配处理，不进入字段比对。",
            limit,
        )
    if "no_resultjson" in lower or "no resultjson" in lower:
        return "后台任务没有生成可验证结果 JSON：任务可能尚未成功完成或结果未保存，不能进入字段验证。"
    if is_no_targets_verify_reason(text):
        return "该 taskId 没有自动匹配到项目当前支持的税种/表单，未进入字段验证。"
    if "target form" in lower and ("not found" in lower or "confirm" in lower):
        return "未能切换或确认目标申报表：税局页面可能停留在其它表单或菜单结构已变化。"
    text = re.sub(r"^(RuntimeError|TimeoutError|ValueError|Exception):\s*", "", text, flags=re.IGNORECASE)
    text = clean_failure_detail(text)
    return compact_message(text or "验证任务失败，未解析到更明确原因。", limit)


def extract_pending_tax_login_task_id(text: str) -> str:
    match = re.search(r"进税局\((\d{12,})\)", str(text or ""))
    if match:
        return match.group(1)
    match = re.search(r"占用任务[:：]\s*(\d{12,})", str(text or ""))
    if match:
        return match.group(1)
    return ""


def repair_mojibake_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    candidates = [text]
    for encoding in ("gbk", "cp936", "latin1", "cp1252"):
        try:
            candidates.append(text.encode(encoding).decode("utf-8"))
        except Exception:
            pass
    return min(candidates, key=lambda item: (mojibake_score(item), -cjk_count(item), len(item)))


def mojibake_score(text: str) -> int:
    score = text.count("\ufffd") * 6 + text.count("□") * 4
    for token in ("锛", "銆", "鍚", "鐧", "绋", "鏁", "浠", "璐", "浜", "涓", "鈥", "€", "鑱", "楠"):
        score += text.count(token) * 2
    return score


def cjk_count(text: str) -> int:
    return sum(1 for char in text if "\u4e00" <= char <= "\u9fff")


def clean_failure_detail(value: Any) -> str:
    text = compact_message(repair_mojibake_text(value), limit=360)
    text = re.sub(r"^(RuntimeError|TimeoutError|ValueError|Exception):\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^getTaskCookie failed[:：]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[（(]?\s*响应id[:：][^）)\s]+[）)]?", "", text, flags=re.IGNORECASE)
    return text.strip("；;，,。 ")


def is_unreadable_failure_detail(text: str) -> bool:
    if not text:
        return False
    if "\ufffd" in text or "□" in text:
        return True
    return mojibake_score(text) >= 6 and cjk_count(text) < 6


def extract_failure_target(text: str) -> str:
    match = re.search(r"target=([A-Za-z0-9_]+)", text)
    return match.group(1) if match else ""


def extract_failure_url(text: str) -> str:
    match = re.search(r"url=([^;\s]+)", text)
    return match.group(1) if match else ""


def shorten_url(url: str, limit: int = 110) -> str:
    text = str(url or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


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
        write_coverage_status(run_dir, targets=coverage_targets_for_state(state))
    except Exception as exc:
        LOGGER.warning("Could not write coverage status for %s: %s", run_dir, exc)

    form_columns = dashboard["form_columns"]
    verified_matrix_items = [item for item in dashboard["items"] if item.get("formResults")]
    tax_rows = render_tax_matrix_rows(verified_matrix_items, form_columns, run_dir)
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
    .coverage-table th:nth-child(3) {{ width: 90px; }}
    .coverage-table th:nth-child(4) {{ width: 150px; }}
    .coverage-table th:nth-child(5) {{ width: 150px; }}
    .coverage-table th:nth-child(6) {{ width: 220px; }}
    .attempt-table th:nth-child(1) {{ width: 170px; }}
    .attempt-table th:nth-child(2) {{ width: 80px; }}
    .attempt-table th:nth-child(3) {{ width: 150px; }}
    .attempt-table th:nth-child(4) {{ width: 150px; }}
    .attempt-table th:nth-child(5) {{ width: 70px; }}
    .attempt-table th:nth-child(6) {{ width: 80px; }}
    .attempt-table th:nth-child(7) {{ width: 120px; }}
    .attempt-table {{ table-layout: fixed; min-width: 1100px; }}
    .attempt-table td.reason-cell {{ white-space: normal; min-width: 320px; max-width: 620px; word-break: break-word; overflow-wrap: anywhere; }}
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
        item_task_ids = item_verification_task_ids(item)
        task_id = format_task_ids(item_task_ids)
        report_entries: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for current_task_id in item_task_ids:
            task_verify = task_verify_entry(item, current_task_id)
            if not task_verify and len(item_task_ids) == 1:
                task_verify = verify
            if not verify_record_should_load_reports(task_verify):
                continue
            paths = task_verify.get("reportPaths") if task_verify else None
            for report in load_compare_reports(current_task_id, paths=paths or None):
                report_entries.append((current_task_id, task_verify, report))
        form_results = {}
        total_passed = 0
        total_denominator = 0
        raw_rates = []
        problem_count = 0

        for report_task_id, report_verify, report in report_entries:
            form_id = str(report.get("batch_id") or "")
            form_name = str(report.get("form_name") or form_id)
            tax_type = normalize_coverage_tax_type(report.get("tax_type"), form_id=form_id)
            tax_type_name = tax_type_display_name(tax_type)
            declaration_status = declaration_status_for_report(report, tax_type=tax_type)
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
                        task_id=report_task_id,
                        area_code=area_code,
                        region=region,
                        summary_path=report_verify.get("summaryPath") or verify.get("summaryPath") or "",
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


def verify_record_should_load_reports(verify: dict[str, Any]) -> bool:
    if not isinstance(verify, dict):
        return False
    return str(verify.get("status") or "") in {"success", "completed_with_differences"}


def supplement_target_keys_for_item(item: dict[str, Any]) -> set[str]:
    keys: set[str] = {
        str(value or "")
        for value in (item.get("coverageSupplementTargets") or [])
        if str(value or "")
    }
    resolved = (item.get("collect") or {}).get("resolvedTask") or {}
    resolved_target = str(resolved.get("coverageTarget") or "")
    if resolved_target:
        keys.add(resolved_target)
    return keys


def load_compare_reports(
    task_id: str,
    since_ts: float | None = None,
    paths: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not task_id:
        return []
    if paths:
        report_paths = [Path(path) for path in paths if str(path or "").strip()]
    else:
        report_dir = Path("output") / "reports" / task_id
        if not report_dir.exists():
            return []
        report_paths = sorted(report_dir.glob("*_compare_*.json"))
    reports = []
    for path in report_paths:
        if not path.exists():
            continue
        if since_ts is not None and path.stat().st_mtime < since_ts:
            continue
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(report, dict):
                report["_sourcePath"] = str(path)
            reports.append(report)
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


def declaration_status_display_name(status: Any) -> str:
    text = str(status or "").strip()
    return DECLARATION_STATUS_LABELS.get(text, text or "未知")


def coverage_supplement_status_display_name(status: Any) -> str:
    text = str(status or "").strip()
    return COVERAGE_SUPPLEMENT_STATUS_LABELS.get(text, text or "未执行")


def format_declaration_status_counts(status_counts: dict[str, Any]) -> str:
    if not status_counts:
        return "无"
    order = {"unknown": 0, "unfiled": 1, "filed": 2}
    def count_value(key: str) -> int:
        try:
            return int(status_counts.get(key) or 0)
        except (TypeError, ValueError):
            return 0
    keys = sorted(
        status_counts,
        key=lambda key: (-count_value(key), order.get(str(key), 99), str(key)),
    )
    parts = []
    for key in keys:
        label = declaration_status_display_name(key)
        parts.append(f"{label}：{status_counts.get(key)} 个")
    return "；".join(parts)


def format_task_tax_type_counts(counts: dict[str, Any]) -> str:
    if not counts:
        return "无"

    def count_value(key: str) -> int:
        try:
            return int(counts.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    keys = sorted(counts, key=lambda key: (-count_value(key), str(key)))
    parts = []
    for key in keys:
        if str(key) == "CBJ_UNKNOWN":
            parts.append(f"残保金类型未知：{counts.get(key)} 个")
            continue
        label = "未知" if str(key) == "unknown" else tax_type_display_name(key)
        parts.append(f"{label}：{counts.get(key)} 个")
    return "；".join(parts)


def format_cbj_mode_source_counts(counts: dict[str, Any]) -> str:
    if not counts:
        return ""

    labels = {
        "execution_log_annual": "执行日志识别为汇算清缴",
        "execution_log_personal": "执行日志识别为个税",
        "task_list_fields": "任务列表字段识别为个税",
        "api_result_fields": "接口字段识别为个税",
        "api_result_missing": "接口字段缺失",
        "api_error": "接口读取失败",
        "backend_tax_type_31": "后台税种ID识别为汇算清缴",
        "backend_tax_id_unknown": "残保金类型未知",
        "unknown": "未知",
    }

    def count_value(key: str) -> int:
        try:
            return int(counts.get(key) or 0)
        except (TypeError, ValueError):
            return 0

    parts = []
    for key in sorted(counts, key=lambda value: (-count_value(value), str(value))):
        parts.append(f"{labels.get(str(key), str(key))}：{counts.get(key)} 个")
    return "；".join(parts)


def declaration_status_for_report(report: dict[str, Any], tax_type: Any = "") -> str:
    tax_type_text = str(tax_type or "")
    if tax_type_text == "CBJ_PERSONAL":
        return "已取数"
    if tax_type_text == "CBJ_ANNUAL":
        return "已验证"
    status = report.get("declaration_status") or report.get("declarationStatus")
    if status:
        normalized = declaration_status_display_name(status)
        return "未申报" if normalized == "未知" else normalized
    current_period_flag = report.get("current_period_flag")
    if current_period_flag is False:
        return "未申报"
    if current_period_flag is True:
        return "已申报"
    return "未申报"


def summarize_verified_tax_statuses(form_results: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    statuses: dict[str, dict[str, str]] = {}
    for form in form_results.values():
        tax_type = str(form.get("taxType") or form.get("formId") or "")
        if not tax_type:
            continue
        raw_status = str(form.get("declarationStatus") or "")
        if tax_type in {"CBJ_PERSONAL", "CBJ_ANNUAL"}:
            display_status = "已取数" if tax_type == "CBJ_PERSONAL" else "已验证"
            statuses[tax_type] = {
                "taxType": tax_type,
                "taxTypeName": short_tax_type_name(form.get("taxTypeName") or tax_type_display_name(tax_type)),
                "declarationStatus": display_status,
                "rawStatuses": raw_status,
            }
            continue
        status = normalize_declaration_status(raw_status)
        item = statuses.setdefault(
            tax_type,
            {
                "taxType": tax_type,
                "taxTypeName": short_tax_type_name(form.get("taxTypeName") or tax_type_display_name(tax_type)),
                "declarationStatus": "",
                "rawStatuses": "",
                "_statusValues": [],
            },
        )
        item.setdefault("_statusValues", []).append(status)
        raw_statuses = [part for part in item.get("rawStatuses", "").split(" / ") if part]
        if raw_status and raw_status not in raw_statuses:
            raw_statuses.append(raw_status)
        item["rawStatuses"] = " / ".join(raw_statuses)

    rows = []
    for item in statuses.values():
        values = [str(value or "") for value in item.pop("_statusValues", [])]
        unique_values = set(values)
        if "未知" in unique_values or not unique_values:
            item["declarationStatus"] = "未知"
        elif "未申报" in unique_values and "已申报" in unique_values:
            item["declarationStatus"] = "未知"
        elif "未申报" in unique_values:
            item["declarationStatus"] = "未申报"
        elif "已申报" in unique_values:
            item["declarationStatus"] = "已申报"
        else:
            item["declarationStatus"] = values[-1] if values else "未知"
        rows.append(item)
    return rows


def normalize_declaration_status(status: Any) -> str:
    text = str(status or "").strip()
    if "不区分" in text:
        return "不区分申报状态"
    if text in {"未知", ""}:
        return "未申报"
    if text in {"未申报", "未申报/未取数"}:
        return "未申报"
    if text in {"已申报", "申报成功"}:
        return "已申报"
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
    targets = payload.get("targets") or []
    missing = payload.get("missingTargets") or []
    supplement = payload.get("supplement") or {}
    diagnostics = {str(item.get("targetKey") or ""): item for item in supplement.get("diagnostics") or []}
    if not targets and missing:
        missing_keys = {str(target.get("key") or "") for target in missing}
        targets = [{**target, "covered": str(target.get("key") or "") not in missing_keys, "examples": []} for target in missing]

    rows = []
    for target in targets:
        key = str(target.get("key") or "")
        diag = diagnostics.get(key) or {}
        covered = bool(target.get("covered"))
        examples = target.get("examples") or []
        example = examples[0] if examples else {}
        reason = "" if covered else coverage_gap_reason(target, supplement, diag)
        tax_type_name = target.get("taxTypeName") or tax_type_display_name(target.get("taxType"))
        declaration_status_name = (
            target.get("declarationStatusName")
            or declaration_status_display_name(target.get("declarationStatus"))
        )
        task_id = str(example.get("taskId") or "")
        report_path = str(example.get("sourcePath") or "")
        task_html = (
            f'<a href="{escape_html(relative_to(run_dir, Path(report_path)))}"><code>{escape_html(task_id)}</code></a>'
            if task_id and report_path
            else (f"<code>{escape_html(task_id)}</code>" if task_id else "")
        )
        rows.append(
            "<tr>"
            f"<td>{escape_html(tax_type_name)}</td>"
            f"<td>{escape_html(declaration_status_name)}</td>"
            f"<td>{coverage_status_badge(covered)}</td>"
            f"<td>{escape_html(example.get('taxNo') or '')}</td>"
            f"<td>{task_html}</td>"
            f"<td>{escape_html(reason)}</td>"
            "</tr>"
        )
    supplement_status = coverage_supplement_status_display_name(supplement.get("status"))
    attempts_html = render_supplement_attempts_table(run_dir, supplement.get("attempts") or [])
    covered_targets = summary.get("coveredTargets", 0)
    total_targets = summary.get("totalTargets", len(targets))
    missing_count = summary.get("missingTargets", len(missing))
    summary_text = (
        f"已覆盖 {covered_targets}/{total_targets} 个税种/申报状态，"
        f"未覆盖 {missing_count} 个。后台补齐状态：{supplement_status}。"
    )
    return (
        '<div class="coverage-panel">'
        "<h2>税种覆盖说明</h2>"
        f'<div class="coverage-summary">{escape_html(summary_text)}</div>'
        '<div class="scroll"><table class="coverage-table">'
        "<thead><tr><th>税种</th><th>申报状态</th><th>覆盖情况</th><th>代表税号</th><th>taskId</th><th>未覆盖原因</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
        f"{attempts_html}"
        "</div>"
    )


def coverage_status_badge(covered: bool) -> str:
    if covered:
        return '<span class="status ok">已覆盖</span>'
    return '<span class="status fail">未覆盖</span>'


def render_supplement_attempts_table(run_dir: Path, attempts: list[dict[str, Any]]) -> str:
    if not attempts:
        return ""
    rows = []
    for attempt in attempts:
        summary_path = str(attempt.get("summaryPath") or "")
        task_id = str(attempt.get("taskId") or "")
        task_html = (
            f'<a href="{escape_html(relative_to(run_dir, Path(summary_path)))}"><code>{escape_html(task_id)}</code></a>'
            if task_id and summary_path
            else (f"<code>{escape_html(task_id)}</code>" if task_id else "")
        )
        status = str(attempt.get("status") or "")
        css = "ok" if status == "covered" else ("warn" if status == "verifying" else "fail")
        status_label = {
            "covered": "已覆盖",
            "verifying": "验证中",
            "failed": "失败",
        }.get(status, status or "未知")
        rows.append(
            "<tr>"
            f"<td>{escape_html(attempt.get('taxTypeName') or tax_type_display_name(attempt.get('taxType')))}</td>"
            f"<td>{escape_html(attempt.get('declarationStatusName') or declaration_status_display_name(attempt.get('declarationStatus')))}</td>"
            f"<td>{escape_html(attempt.get('taxNo') or '')}</td>"
            f"<td>{task_html}</td>"
            f"<td>{escape_html(attempt.get('attemptNo') or '')}/{escape_html(attempt.get('totalCandidates') or '')}</td>"
            f'<td><span class="status {css}">{escape_html(status_label)}</span></td>'
            f"<td>{escape_html(attempt.get('step') or '')}</td>"
            f"<td class=\"reason-cell\">{escape_html(normalize_supplement_failure_reason(attempt.get('reason') or ''))}</td>"
            "</tr>"
        )
    return (
        "<h2>后台补齐尝试记录</h2>"
        '<div class="scroll"><table class="attempt-table">'
        "<thead><tr><th>税种</th><th>申报状态</th><th>候选税号</th><th>taskId</th><th>序号</th><th>结果</th><th>失败/完成步骤</th><th>直接原因</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div>"
    )


def supplement_source_readiness_for_target(supplement: dict[str, Any], target_key: str) -> dict[str, Any]:
    for item in supplement.get("sourceReadiness") or []:
        if isinstance(item, dict) and str(item.get("targetKey") or "") == str(target_key or ""):
            return item
    return {}


def format_source_readiness_gap_text(readiness: dict[str, Any]) -> str:
    if not readiness:
        return ""
    message = str(readiness.get("message") or "").strip()
    next_action = str(readiness.get("nextAction") or "").strip()
    if message and next_action:
        return f"{message}\u4e0b\u4e00\u6b65\uff1a{next_action}"
    return message or next_action


def coverage_gap_reason(target: dict[str, Any], supplement: dict[str, Any], diagnostic: dict[str, Any]) -> str:
    target_key = str(target.get("key") or diagnostic.get("targetKey") or "")
    readiness = supplement_source_readiness_for_target(supplement, target_key)
    readiness_text = format_source_readiness_gap_text(readiness)
    attempts = [
        item
        for item in supplement.get("attempts") or []
        if str(item.get("targetKey") or "") == target_key
    ]
    if attempts and not any(str(item.get("status") or "") == "covered" for item in attempts):
        last_attempt = attempts[-1]
        attempt_reason = normalize_supplement_failure_reason(last_attempt.get("reason") or "未命中目标覆盖状态")
        punctuation = "" if attempt_reason.endswith(("。", "！", "？", ".", "!", "?")) else "。"
        text = (
            f"后台已找到并尝试 {len(attempts)} 个候选任务，"
            f"最后失败步骤：{last_attempt.get('step') or '验证任务'}；"
            f"原因：{attempt_reason}{punctuation}"
        )
        if readiness_text:
            text += f"来源预检：{readiness_text}"
        return text
    if readiness_text and str(readiness.get("status") or "") not in {"fresh_task_ready"}:
        return readiness_text
    reason = str(diagnostic.get("reason") or "")
    queried = diagnostic.get("queriedCount")
    status_counts = diagnostic.get("statusCounts") or {}
    task_type_counts = diagnostic.get("taskTaxTypeCounts") or {}
    if reason == "no_success_collect_tasks":
        return f"后台当月没有查到该税种的成功取数任务（查询数量 {queried or 0}）。"
    if reason == "declaration_status_not_matched":
        return f"后台有成功任务，但申报状态不符合目标；解析分布：{format_declaration_status_counts(status_counts)}。"
    if reason == "declaration_status_unknown":
        return f"后台有成功任务，但未能从任务结果或执行日志解析申报状态（查询数量 {queried or 0}）。"
    if reason == "required_backend_fields_missing":
        fields = diagnostic.get("requiredFields") or []
        field_text = "、".join(str(field) for field in fields if field) or "目标税种必需字段"
        missing_count = diagnostic.get("requiredFieldMissingCount") or 0
        return (
            f"后台有成功任务，但任务结果缺少{field_text}，"
            f"不能作为该税种的补齐任务（不符合数量 {missing_count}）。"
        )
    if reason == "target_tax_type_not_matched":
        cbj_source_counts = diagnostic.get("cbjModeSourceCounts") or {}
        cbj_source_text = format_cbj_mode_source_counts(cbj_source_counts)
        if cbj_source_text:
            return (
                "后台有成功任务，但任务实际类型不是目标税种/纳税人类型；"
                f"任务类型分布：{format_task_tax_type_counts(task_type_counts)}；"
                f"残保金识别来源分布：{cbj_source_text}。"
            )
        return (
            "后台有成功任务，但任务实际类型不是目标税种/纳税人类型；"
            f"任务类型分布：{format_task_tax_type_counts(task_type_counts)}。"
        )
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
        if not item.get("formResults"):
            continue
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
    if not rows:
        colspan = 10 + len(form_columns)
        return f'<tr><td colspan="{colspan}" class="quiet">暂无完成完整验证流程的表单结果。</td></tr>'
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
    label = "通过" if problem_count == 0 else f"{problem_count}项"
    title = f"通过率：{format_rate(rate)}；问题数：{problem_count}"
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
    if status in {"已申报", "未申报", "已取数", "已验证", "不区分申报状态"}:
        return "ok"
    if status == "取数失败":
        return "fail"
    if status in {"取数中", "未申报/未取数", "未知"}:
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
    if upper in {"SUCCESS", "COLLECTED", "COLLECTED_PART", "SUCCESSFUL", "DONE", "OK"} or text in {"success", "已申报", "未申报"}:
        css = "ok"
    elif upper in {"FAILURE", "COLLECTED_FAIL", "FAILED", "ERROR"} or text in {"failed", "取数失败"}:
        css = "fail"
    elif "difference" in text or upper in {"DOING", "WAITING", "TODO", "COLLECTING"} or text in {"取数中", "未申报/未取数"}:
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
