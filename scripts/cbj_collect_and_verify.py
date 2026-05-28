"""Collect and verify residual employment security fund data from Yidaizhang."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, ".")

from src.cbj.verification import report_has_errors, verify_annual_settlement_cbj, verify_personal_cbj
from src.runtime.process_lock import DEFAULT_TAX_BROWSER_LOCK, ProcessLock
from src.ydz.api import YdzApi
from src.ydz.collector import YdzCollector
from src.ydz.models import CBJ_COLLECT_TAX_TYPE_IDS, YdzCollectResult
from src.ydz.session import YdzSession, get_env_credentials
from src.ydz.task_resolver import VerifyTaskResolver


LOGGER = logging.getLogger("cbj_collect_and_verify")


def previous_month_period(today: date | None = None) -> str:
    today = today or date.today()
    year = today.year
    month = today.month - 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year}{month:02d}"


def parse_tax_type_ids(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CBJ collection verification pipeline.")
    parser.add_argument("--personal-tax-no", required=True, help="Tax number for personal-income CBJ collection check.")
    parser.add_argument("--annual-tax-no", required=True, help="Tax number for annual-settlement CBJ collection check.")
    parser.add_argument("--period", default=previous_month_period(), help="Yidaizhang collection period in YYYYMM.")
    parser.add_argument("--enterprise", default="\u84dd\u5929\u4e4b\u7231", help="Yidaizhang enterprise name.")
    parser.add_argument("--tax-type-ids", default=",".join(str(x) for x in CBJ_COLLECT_TAX_TYPE_IDS))
    parser.add_argument("--query-year", type=int, default=date.today().year)
    parser.add_argument("--run-id", default="", help="Run id. Defaults to current timestamp.")
    parser.add_argument("--output-dir", default="output/cbj_runs")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--mode", choices=["auto", "connect", "launch"], default="auto")
    parser.add_argument("--config-root", default="config")
    parser.add_argument("--user-data-dir", default="./browser_profile/etax_compare_forms")
    parser.add_argument("--plugin-path", default=r"C:\Users\Administrator\Downloads\EtaxPlugin")
    parser.add_argument("--chanjet-timeout", type=int, default=300)
    parser.add_argument("--tax-timeout", type=int, default=240)
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--poll-timeout", type=int, default=900)
    parser.add_argument("--browser-lock-timeout", type=int, default=3600)
    parser.add_argument("--force", action="store_true", help="Submit collection even if Yidaizhang already shows collected.")
    parser.add_argument("--skip-annual-browser", action="store_true", help="Only fetch backend fields for annual settlement.")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(args.output_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    state: dict[str, Any] = {
        "runId": run_id,
        "period": args.period,
        "enterprise": args.enterprise,
        "taxTypeIds": parse_tax_type_ids(args.tax_type_ids),
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "items": {
            args.personal_tax_no: {"mode": "personal", "taxNo": args.personal_tax_no},
            args.annual_tax_no: {"mode": "annual_settlement", "taxNo": args.annual_tax_no},
        },
    }
    exit_code = 0
    with ProcessLock(
        DEFAULT_TAX_BROWSER_LOCK,
        timeout=args.browser_lock_timeout,
        owner={"kind": "cbj-collect-verify", "runId": run_id, "period": args.period},
    ):
        try:
            results = run_collect(args)
            for tax_no, result in results.items():
                state["items"][tax_no]["collect"] = result.to_dict()
            write_state(state, run_dir)
            exit_code = max(exit_code, run_verifications(args, results, state, run_dir))
        finally:
            write_state(state, run_dir)
    print_summary(state)
    return exit_code


def run_collect(args: argparse.Namespace) -> dict[str, YdzCollectResult]:
    username, password = get_env_credentials()
    session = YdzSession(
        cdp_port=args.cdp_port,
        user_data_dir=args.user_data_dir,
        plugin_path=args.plugin_path,
        launch_if_needed=True,
    )
    results: dict[str, YdzCollectResult] = {}
    try:
        context = session.connect()
        page = session.ensure_ready(username=username, password=password, enterprise=args.enterprise)
        api = YdzApi(page)
        resolver = VerifyTaskResolver(context)
        collector = YdzCollector(
            api=api,
            enterprise=args.enterprise,
            tax_type_ids=parse_tax_type_ids(args.tax_type_ids),
            poll_interval=args.poll_interval,
            poll_timeout=args.poll_timeout,
        )
        for tax_no in (args.personal_tax_no, args.annual_tax_no):
            LOGGER.info("Submitting CBJ collection for %s/%s", tax_no, args.period)
            result = collector.submit_collect_tax_no(tax_no=tax_no, period=args.period, force=args.force)
            resolve_task_id(
                resolver,
                result,
                poll_interval=args.poll_interval,
                poll_timeout=args.poll_timeout,
            )
            try:
                collector.refresh_collect_status(result)
            except Exception as exc:
                LOGGER.info("Could not refresh Yidaizhang CBJ status for %s/%s: %s", tax_no, args.period, exc)
            results[tax_no] = result
    finally:
        session.close()
    return results


def resolve_task_id(
    resolver: VerifyTaskResolver,
    result: YdzCollectResult,
    poll_interval: int,
    poll_timeout: int,
) -> None:
    deadline = time.time() + poll_timeout
    last_status = ""
    last_error = ""
    while time.time() < deadline:
        try:
            result.verify_task_id = resolver.resolve(result.tax_no, result.period, submitted_at=result.submitted_at)
            if resolver.last_task:
                copy_resolved_task(resolver, result)
                status = str(resolver.last_task.status or "").upper()
                if status != last_status:
                    LOGGER.info(
                        "CBJ collect task resolved for %s/%s: taskId=%s status=%s",
                        result.tax_no,
                        result.period,
                        result.verify_task_id,
                        status,
                    )
                    last_status = status
                if status == "SUCCESS":
                    return
                if status in {"FAILURE", "FAILED", "FAIL"}:
                    result.manual_required = True
                    result.errors.append(f"Collect task failed in public-manage: status={status}")
                    return
            else:
                LOGGER.info("Waiting for CBJ collect taskId for %s/%s.", result.tax_no, result.period)
        except Exception as exc:
            last_error = str(exc)
            LOGGER.info("Waiting for CBJ collect taskId for %s/%s: %s", result.tax_no, result.period, exc)
        time.sleep(poll_interval)

    if result.verify_task_id:
        try_recent_success_fallback(resolver, result)
        result.warnings.append(
            f"Collect taskId resolved but did not reach SUCCESS before timeout; last status={last_status or 'unknown'}."
        )
        return
    message = f"Could not resolve collect taskId before timeout."
    if last_error:
        message += f" Last error: {last_error}"
    LOGGER.warning("Could not resolve CBJ collect taskId for %s/%s: %s", result.tax_no, result.period, message)
    result.warnings.append(message)
    try_recent_success_fallback(resolver, result)


def copy_resolved_task(resolver: VerifyTaskResolver, result: YdzCollectResult) -> None:
    if not resolver.last_task:
        return
    result.resolved_task = {
        "taskId": resolver.last_task.task_id,
        "taskTypeId": resolver.last_task.task_type_id,
        "taskTypeName": resolver.last_task.task_type_name,
        "status": resolver.last_task.status,
        "period": resolver.last_task.period,
        "createdStamp": resolver.last_task.created_stamp,
    }


def try_recent_success_fallback(resolver: VerifyTaskResolver, result: YdzCollectResult) -> None:
    current_task_id = result.verify_task_id
    try:
        fallback_task_id = resolver.resolve(result.tax_no, result.period, submitted_at=None)
    except Exception as exc:
        result.warnings.append(f"Recent successful task fallback failed: {exc}")
        return
    if not resolver.last_task or str(resolver.last_task.status or "").upper() != "SUCCESS":
        return
    if fallback_task_id and fallback_task_id != current_task_id:
        result.verify_task_id = fallback_task_id
        copy_resolved_task(resolver, result)
        result.warnings.append(
            f"Using recent successful collect taskId={fallback_task_id} because current taskId={current_task_id} did not finish."
        )


def run_verifications(
    args: argparse.Namespace,
    results: dict[str, YdzCollectResult],
    state: dict[str, Any],
    run_dir: Path,
) -> int:
    exit_code = 0
    personal = results.get(args.personal_tax_no)
    annual = results.get(args.annual_tax_no)
    if personal:
        exit_code = max(exit_code, verify_one(args.personal_tax_no, "personal", personal, args, state, run_dir))
    if annual:
        mode = "annual_backend_only" if args.skip_annual_browser else "annual_settlement"
        exit_code = max(exit_code, verify_one(args.annual_tax_no, mode, annual, args, state, run_dir))
    return exit_code


def verify_one(
    tax_no: str,
    mode: str,
    result: YdzCollectResult,
    args: argparse.Namespace,
    state: dict[str, Any],
    run_dir: Path,
) -> int:
    task_id = result.verify_task_id
    if not task_id:
        state["items"][tax_no]["verify"] = {
            "status": "failed",
            "reason": "No collect taskId resolved.",
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 2
    try:
        if mode in {"personal", "annual_backend_only"}:
            report_path = verify_personal_cbj(task_id)
        else:
            report_path = verify_annual_settlement_cbj(task_id, args)
        has_errors = report_has_errors(report_path)
        state["items"][tax_no]["verify"] = {
            "status": "failed" if has_errors else "success",
            "mode": mode,
            "taskId": task_id,
            "reportPath": str(report_path),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 1 if has_errors else 0
    except Exception as exc:
        LOGGER.exception("CBJ verification failed for %s taskId=%s", tax_no, task_id)
        state["items"][tax_no]["verify"] = {
            "status": "failed",
            "mode": mode,
            "taskId": task_id,
            "reason": str(exc),
            "updatedAt": datetime.now().isoformat(timespec="seconds"),
        }
        write_state(state, run_dir)
        return 2


def write_state(state: dict[str, Any], run_dir: Path) -> None:
    state["updatedAt"] = datetime.now().isoformat(timespec="seconds")
    (run_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def print_summary(state: dict[str, Any]) -> None:
    print(f"CBJ runId: {state.get('runId')}")
    for tax_no, item in state.get("items", {}).items():
        collect = item.get("collect") or {}
        verify = item.get("verify") or {}
        print(
            f"{tax_no}: mode={item.get('mode')} collect={collect.get('status')} "
            f"taskId={collect.get('verifyTaskId') or ''} verify={verify.get('status') or ''}"
        )
        if verify.get("reportPath"):
            print(f"  report: {verify['reportPath']}")
        if verify.get("reason"):
            print(f"  reason: {verify['reason']}")


if __name__ == "__main__":
    raise SystemExit(main())
