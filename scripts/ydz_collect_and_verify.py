"""Collect Yidaizhang tax data by tax number, then optionally run verification."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, ".")

from src.runtime.process_lock import DEFAULT_TAX_BROWSER_LOCK, ProcessLock
from src.ydz.pipeline import YdzPipeline


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
    return list(dict.fromkeys(values))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Yidaizhang collect-and-verify pipeline.")
    parser.add_argument("--tax-no", action="append", help="Tax number. Can be repeated or comma-separated.")
    parser.add_argument("--tax-no-file", help="UTF-8 file containing one tax number per line.")
    parser.add_argument("--period", default=previous_month_period(), help="Tax period in YYYYMM. Default: previous month.")
    parser.add_argument("--enterprise", default="\u84dd\u5929\u4e4b\u7231", help="Yidaizhang enterprise name.")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--user-data-dir", default="./browser_profile/etax_compare_forms")
    parser.add_argument("--plugin-path", default=r"C:\Users\Administrator\Downloads\EtaxPlugin")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--poll-timeout", type=int, default=600)
    parser.add_argument("--force", action="store_true", help="Submit collection even if the account is already collected.")
    parser.add_argument("--verify", action="store_true", help="Run existing verification when a verification taskId is resolved.")
    parser.add_argument("--targets", default="auto", help="Targets passed to main.py when --verify is enabled.")
    parser.add_argument("--skip-browser", action="store_true", help="Passed to main.py verification when --verify is enabled.")
    parser.add_argument("--tax-timeout", type=int, default=600, help="Tax bureau login and task-cookie timeout passed to main.py.")
    parser.add_argument("--browser-lock-timeout", type=int, default=3600, help="Seconds to wait for the shared browser lock.")
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

    pipeline = YdzPipeline(
        enterprise=args.enterprise,
        cdp_port=args.cdp_port,
        user_data_dir=args.user_data_dir,
        plugin_path=args.plugin_path,
        poll_interval=args.poll_interval,
        poll_timeout=args.poll_timeout,
    )
    with ProcessLock(
        DEFAULT_TAX_BROWSER_LOCK,
        timeout=args.browser_lock_timeout,
        owner={"kind": "ydz-collect", "period": args.period, "taxNos": tax_nos},
    ):
        results = pipeline.run_collect(tax_nos=tax_nos, period=args.period, force=args.force)

    exit_code = 0
    for result in results:
        status = result.status or "UNKNOWN"
        print(f"{result.tax_no}: {status}, submitted={result.submitted}, manualRequired={result.manual_required}")
        if result.verify_task_id:
            print(f"  resolved collect taskId: {result.verify_task_id}")
        for warning in result.warnings:
            print(f"  warning: {warning}")
        for error in result.errors:
            print(f"  error: {error}")

        if args.verify:
            if result.verify_task_id:
                cmd = [
                    sys.executable,
                    "main.py",
                    "--task-id",
                    result.verify_task_id,
                    "--targets",
                    args.targets,
                    "--log-level",
                    args.log_level,
                    "--tax-timeout",
                    str(args.tax_timeout),
                ]
                if args.skip_browser:
                    cmd.append("--skip-browser")
                cmd.extend(["--browser-lock-timeout", str(args.browser_lock_timeout)])
                proc = subprocess.run(cmd)
                exit_code = max(exit_code, proc.returncode)
            else:
                print(f"  verification skipped: no verification taskId resolved for {result.tax_no}")
                exit_code = max(exit_code, 2)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
