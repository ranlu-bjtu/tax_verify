"""Verify residual employment security fund collection result by taskId."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

sys.path.insert(0, ".")

from src.cbj.verification import report_has_errors, verify_annual_settlement_cbj, verify_personal_cbj


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify CBJ collection result by taskId.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--mode", choices=["personal", "annual_settlement"], required=True)
    parser.add_argument("--query-year", type=int, default=date.today().year)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--browser-mode", choices=["auto", "connect", "launch"], default="auto", dest="mode_for_browser")
    parser.add_argument("--config-root", default="config")
    parser.add_argument("--chrome-path", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user-data-dir", default="./browser_profile/etax_compare_forms")
    parser.add_argument("--plugin-path", default=r"C:\Users\Administrator\Downloads\EtaxPlugin")
    parser.add_argument("--chanjet-timeout", type=int, default=300)
    parser.add_argument("--tax-timeout", type=int, default=240)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.mode == "personal":
        report_path = verify_personal_cbj(args.task_id)
    else:
        browser_args = argparse.Namespace(
            cdp_port=args.cdp_port,
            mode=args.mode_for_browser,
            chrome_path=args.chrome_path,
            user_data_dir=args.user_data_dir,
            plugin_path=args.plugin_path,
            chanjet_timeout=args.chanjet_timeout,
            tax_timeout=args.tax_timeout,
            config_root=args.config_root,
            query_year=args.query_year,
        )
        report_path = verify_annual_settlement_cbj(args.task_id, browser_args)
    print(report_path)
    return 1 if report_has_errors(report_path) else 0


if __name__ == "__main__":
    raise SystemExit(main())
