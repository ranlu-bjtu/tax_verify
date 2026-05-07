"""Compatibility wrapper for the VAT small-scale main-table comparison.

The maintained implementation lives in ``scripts.compare_tax_forms``.  This
file is kept so old commands still work, but it no longer owns a separate
browser/login/extraction flow.
"""

from __future__ import annotations

import argparse
import logging
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.compare_tax_forms import run_compare, setup_logging

LOGGER = logging.getLogger("compare_vat_small_main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare VAT small-scale main table by taskId.",
    )
    parser.add_argument("--task-id", required=True, help="Outer Chanjet taskId.")
    parser.add_argument("--config-root", default="config")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--mode", choices=["auto", "connect", "launch"], default="auto")
    parser.add_argument("--user-data-dir", default="./browser_profile/etax_compare_main")
    parser.add_argument("--plugin-path", default=r"C:\Users\Administrator\Downloads\EtaxPlugin")
    parser.add_argument("--chanjet-timeout", type=int, default=300)
    parser.add_argument("--tax-timeout", type=int, default=180)
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--log-level", default="INFO")

    # Deprecated options accepted for command compatibility.  The canonical
    # target definition now owns these details.
    parser.add_argument("--id-workbook", default="", help=argparse.SUPPRESS)
    parser.add_argument("--sheet", default="", help=argparse.SUPPRESS)
    parser.add_argument("--tax-code", default="", help=argparse.SUPPRESS)
    parser.add_argument("--tax-type", default="", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(args.log_level)
    LOGGER.warning(
        "scripts/compare_vat_small_main.py is deprecated; use "
        "python main.py --task-id <id> --targets vat_small_main"
    )
    return run_compare(
        Namespace(
            task_id=args.task_id,
            targets="vat_small_main",
            config_root=args.config_root,
            cdp_port=args.cdp_port,
            mode=args.mode,
            user_data_dir=args.user_data_dir,
            plugin_path=args.plugin_path,
            chanjet_timeout=args.chanjet_timeout,
            tax_timeout=args.tax_timeout,
            skip_api=False,
            skip_browser=args.skip_browser,
            skip_pdf=args.skip_pdf,
            log_level=args.log_level,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
