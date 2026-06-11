from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ydz_create_customers import (  # noqa: E402
    ensure_backend_login,
    load_env_file,
    wait_for_backend_session,
)
from src.chanjet_admin.privacy_phone import ChanjetPrivacyPhoneBridge, ChanjetPrivacyPhoneSync  # noqa: E402
from src.chanjet_admin.task_query import PUBLIC_MANAGE_URL  # noqa: E402

LOGGER = logging.getLogger(__name__)
DEFAULT_CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
DEFAULT_PROFILE_DIR = str(ROOT / "browser_profile" / "public_manage_privacy_phone")
CHROME_AUTOMATION_STEALTH_ARGS = ["--disable-blink-features=AutomationControlled"]
SUCCESS_STATUSES = {"OK", "DRY_RUN", "EXISTS", "PULLED", "DRY_RUN_EXISTS", "DRY_RUN_MISSING", "SKIPPED"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync public-manage privacy phone binding data by reusing a logged-in browser session."
    )
    parser.add_argument("--private-phone", action="append", default=[], help="Privacy phone number. Can be repeated.")
    parser.add_argument("--private-phone-file", help="Text file containing privacy phone numbers.")
    parser.add_argument("--env-file", help="Optional env file with TAX_BACKEND_USERNAME/TAX_BACKEND_PASSWORD.")
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--chrome-path", default=DEFAULT_CHROME_PATH)
    parser.add_argument("--user-data-dir", default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--session-timeout", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true", help="Query summary/detail but do not call the copy API.")
    parser.add_argument(
        "--online-only",
        action="store_true",
        help="Only run the online copy flow; by default the script verifies/pulls data into integration.",
    )
    parser.add_argument("--no-launch-chrome", action="store_true")
    parser.add_argument("--skip-auto-login", action="store_true", help="Only use the current browser login state.")
    parser.add_argument("--output-json", help="Optional sanitized JSON result path.")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args(argv)


def read_private_phones(args: argparse.Namespace) -> list[str]:
    values = list(args.private_phone or [])
    if args.private_phone_file:
        text = Path(args.private_phone_file).read_text(encoding="utf-8")
        values.extend(text.replace(",", "\n").replace("，", "\n").split())
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        phone = str(value or "").strip()
        if not phone or phone in seen:
            continue
        seen.add(phone)
        result.append(phone)
    if not result:
        raise SystemExit("No privacy phone numbers were provided.")
    return result


def is_cdp_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2):
            return True
    except Exception:
        return False


def launch_chrome_if_needed(args: argparse.Namespace) -> None:
    if is_cdp_alive(args.cdp_port):
        return
    if args.no_launch_chrome:
        raise SystemExit(f"Chrome CDP is not available on port {args.cdp_port}.")
    Path(args.user_data_dir).mkdir(parents=True, exist_ok=True)
    command = [
        args.chrome_path,
        f"--remote-debugging-port={args.cdp_port}",
        f"--user-data-dir={args.user_data_dir}",
        "--no-first-run",
        "--disable-popup-blocking",
        *CHROME_AUTOMATION_STEALTH_ARGS,
        os.environ.get("TAX_BACKEND_URL") or PUBLIC_MANAGE_URL,
    ]
    LOGGER.info("Launching Chrome CDP on port %s.", args.cdp_port)
    subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    deadline = time.time() + 20
    while time.time() < deadline:
        if is_cdp_alive(args.cdp_port):
            return
        time.sleep(0.5)
    raise SystemExit(f"Chrome CDP did not become available on port {args.cdp_port}.")


def write_output_json(path_value: str | None, payload: Any) -> None:
    if not path_value:
        return
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, str(args.log_level).upper(), logging.INFO))
    load_env_file(args.env_file)
    private_phones = read_private_phones(args)
    launch_chrome_if_needed(args)

    reports: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp_port}")
        if not browser.contexts:
            raise SystemExit("No browser context is available.")
        context = browser.contexts[0]
        if args.skip_auto_login:
            backend_ready = wait_for_backend_session(context, timeout=args.session_timeout)
        else:
            backend_ready = ensure_backend_login(context, timeout=args.session_timeout)
        if not backend_ready:
            raise SystemExit(
                "Public-manage login session is not ready. Login in Chrome or provide "
                "TAX_BACKEND_USERNAME/TAX_BACKEND_PASSWORD through environment variables."
            )

        syncer = ChanjetPrivacyPhoneSync(context) if args.online_only else ChanjetPrivacyPhoneBridge(context)
        if args.online_only:
            print("status\tprivatePhone\tsummaryCount\tdetailCount\tcopySuccess\terrors")
        else:
            print(
                "status\tprivatePhone\tinteSummaryCount\tonlineSummaryCount\t"
                "onlineDetailCount\tcopySuccess\tpullSuccess\terrors"
            )
        for private_phone in private_phones:
            try:
                if args.online_only:
                    result = syncer.sync_private_phone(private_phone, dry_run=args.dry_run)
                else:
                    result = syncer.ensure_integration_private_phone(private_phone, dry_run=args.dry_run)
            except Exception as exc:
                report = {
                    "privatePhone": private_phone,
                    "status": "FAILED",
                    "summaryCount": 0,
                    "detailCount": 0,
                    "inteSummaryCount": 0,
                    "onlineSummaryCount": 0,
                    "onlineDetailCount": 0,
                    "copySuccess": False,
                    "pullSuccess": False,
                    "errors": [str(exc)],
                }
            else:
                report = result.to_report()
            reports.append(report)
            errors = "; ".join(str(item) for item in report.get("errors") or [])
            if args.online_only:
                print(
                    "\t".join(
                        [
                            str(report.get("status") or ""),
                            str(report.get("privatePhone") or ""),
                            str(report.get("summaryCount") or 0),
                            str(report.get("detailCount") or 0),
                            str(bool(report.get("copySuccess"))),
                            errors,
                        ]
                    )
                )
            else:
                print(
                    "\t".join(
                        [
                            str(report.get("status") or ""),
                            str(report.get("privatePhone") or ""),
                            str(report.get("inteSummaryCount") or 0),
                            str(report.get("onlineSummaryCount") or 0),
                            str(report.get("onlineDetailCount") or 0),
                            str(bool(report.get("copySuccess"))),
                            str(bool(report.get("pullSuccess"))),
                            errors,
                        ]
                    )
                )

    write_output_json(args.output_json, reports)
    return 0 if all(str(row.get("status")) in SUCCESS_STATUSES for row in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
