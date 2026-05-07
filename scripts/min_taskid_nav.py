"""Minimal taskId flow: login to tax bureau and navigate to declaration query.

This script intentionally stops at the smallest browser-level acceptance test:

1. Launch or connect to Chrome with EtaxPlugin and CDP.
2. Open the Chanjet task list and wait until the user is logged in.
3. Resolve province/inner taskId through getClientJob/getTaskCookie.
4. Navigate to the configured declaration information query page.
5. Save screenshots so the current browser state is easy to inspect.

Example:
    python scripts/min_taskid_nav.py --task-id 2063136603916901951
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")

from src.config.config_loader import ConfigLoader
from src.login.auto_tax_login import CHANJET_TASK_URL
from src.login.browser_manager import BrowserManager
from src.login.task_login_flow import TaskLoginFlow
from src.navigation.navigation_engine import NavigationEngine
from src.registry.tax_type_registry import TaxTypeRegistry


LOGGER = logging.getLogger("min_taskid_nav")
SCREENSHOT_DIR = Path("./output/screenshots")
DECLARATION_QUERY_URL_HINTS = ("sbxxcx", "sbxx/sbxxcx", "zhcx/sbxx")
DECLARATION_QUERY_TEXT_HINTS = ("申报信息查询", "申报信息")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Login to tax bureau by taskId and navigate to declaration query page."
    )
    parser.add_argument("--task-id", default="", help="Chanjet taskId.")
    parser.add_argument("--tax-type", default="VAT_SMALL_SCALE", help="Tax type config id.")
    parser.add_argument("--company", default="", help="Company name or taxpayer_id in config.")
    parser.add_argument("--config-root", default="config", help="Config root directory.")
    parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome CDP port.")
    parser.add_argument(
        "--mode",
        choices=["auto", "connect", "launch"],
        default="auto",
        help="Connect to existing Chrome, launch a new one, or try connect then launch.",
    )
    parser.add_argument(
        "--user-data-dir",
        default="./browser_profile/etax_min_taskid",
        help="Chrome profile dir when --mode launch is used.",
    )
    parser.add_argument(
        "--plugin-path",
        default=r"C:\Users\Administrator\Downloads\EtaxPlugin",
        help="EtaxPlugin directory when --mode launch is used.",
    )
    parser.add_argument("--chanjet-timeout", type=int, default=300)
    parser.add_argument("--tax-timeout", type=int, default=180)
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_defaults(args: argparse.Namespace) -> str:
    """Resolve taskId from company config when CLI args are omitted."""
    task_id = args.task_id

    loader = ConfigLoader(config_root=args.config_root)
    for company in loader.load_companies():
        if args.company:
            matched = args.company in {company.get("name"), company.get("taxpayer_id")}
            if not matched:
                continue

        task_id = task_id or company.get("task_id", "")
        break

    if not task_id:
        raise ValueError("taskId is required. Pass --task-id or set company.task_id.")

    return task_id


def connect_browser(args: argparse.Namespace) -> BrowserManager:
    bm = BrowserManager()

    if args.mode in {"auto", "connect"}:
        try:
            LOGGER.info("Connecting to existing Chrome CDP on port %s", args.cdp_port)
            bm.connect_cdp(args.cdp_port)
            return bm
        except Exception as exc:
            if args.mode == "connect":
                raise
            LOGGER.info("CDP connect failed, launching Chrome instead: %s", exc)

    LOGGER.info("Launching Chrome with EtaxPlugin and CDP on port %s", args.cdp_port)
    bm.launch_with_extension(
        {
            "user_data_dir": args.user_data_dir,
            "cdp_port": args.cdp_port,
            "plugin_path": args.plugin_path,
        }
    )
    return bm


def get_web_config(config_root: str, tax_type: str):
    registry = TaxTypeRegistry()
    registry.load_all_from_dir(config_root)
    tax_config = registry.get(tax_type)
    if not tax_config.forms:
        raise ValueError(f"Tax type has no forms: {tax_type}")
    form = tax_config.forms[0]
    if not form.web_config:
        raise ValueError(f"Form has no web_config: {form.form_code}")
    return form.web_config


def save_screenshot(page, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / name
    try:
        page.screenshot(path=str(path), full_page=True, timeout=10000)
        LOGGER.info("Screenshot saved: %s", path)
    except Exception as exc:
        LOGGER.warning("Screenshot skipped (%s): %s", name, exc)


def is_declaration_query_page(page) -> bool:
    """Return True when the current page appears to be the declaration query page."""
    url = (page.url or "").lower()
    if any(hint in url for hint in DECLARATION_QUERY_URL_HINTS):
        return True

    try:
        title = page.title() or ""
        if any(hint in title for hint in DECLARATION_QUERY_TEXT_HINTS):
            return True
    except Exception:
        pass

    try:
        body_text = page.evaluate("document.body ? document.body.innerText.slice(0, 5000) : ''")
        return any(hint in body_text for hint in DECLARATION_QUERY_TEXT_HINTS)
    except Exception:
        return False


def main() -> int:
    args = parse_args()
    setup_logging(args.log_level)

    task_id = load_defaults(args)
    web_config = get_web_config(args.config_root, args.tax_type)

    LOGGER.info("TaskId: %s", task_id)
    LOGGER.info("Tax type: %s", args.tax_type)

    bm = connect_browser(args)
    try:
        page = bm.find_page_by_url("chanjet.com") or bm.get_page()
        LOGGER.info("Opening Chanjet task list: %s", CHANJET_TASK_URL)
        page.goto(CHANJET_TASK_URL, wait_until="domcontentloaded", timeout=30000)
        save_screenshot(page, "min_taskid_chanjet.png")

        LOGGER.info("Waiting for Chanjet login. Finish login in Chrome if prompted.")
        start = time.time()
        while time.time() - start < args.chanjet_timeout:
            chanjet_page = bm.find_page_by_url("chanjet.com")
            if chanjet_page:
                title = chanjet_page.title()
                if title and "登录" not in title and "Login" not in title:
                    break
            time.sleep(3)
        else:
            LOGGER.error("Chanjet login was not detected before timeout.")
            return 2

        chanjet_page = bm.find_page_by_url("chanjet.com") or page
        LOGGER.info("Resolving task metadata and logging into tax bureau.")
        flow = TaskLoginFlow(bm, timeout=args.tax_timeout)
        try:
            tax_page, task_info = flow.login(chanjet_page, task_id)
        except Exception as exc:
            LOGGER.error("Task login failed: %s", exc)
            return 3

        LOGGER.info("Resolved province: %s", task_info.province)
        LOGGER.info("Resolved inner taskId: %s", task_info.inner_task_id)
        LOGGER.info("Tax-bureau page detected: %s", tax_page.url)
        save_screenshot(tax_page, "min_taskid_tax_logged_in.png")

        if is_declaration_query_page(tax_page):
            LOGGER.info("Already on declaration information query page: %s", tax_page.url)
            save_screenshot(tax_page, "min_taskid_declaration_query.png")
            return 0

        LOGGER.info("Navigating to declaration information query page.")
        nav = NavigationEngine(tax_page)
        if not nav.navigate_to_form(web_config):
            if is_declaration_query_page(tax_page):
                LOGGER.info("Navigation ended on declaration information query page: %s", tax_page.url)
                save_screenshot(tax_page, "min_taskid_declaration_query.png")
                return 0
            LOGGER.error("Navigation to declaration query failed. Current URL: %s", tax_page.url)
            save_screenshot(tax_page, "min_taskid_nav_failed.png")
            return 4

        if not is_declaration_query_page(tax_page):
            LOGGER.error("Navigation completed but target page was not detected: %s", tax_page.url)
            save_screenshot(tax_page, "min_taskid_nav_unknown.png")
            return 5

        LOGGER.info("Navigation completed. Current URL: %s", tax_page.url)
        save_screenshot(tax_page, "min_taskid_declaration_query.png")
        return 0
    finally:
        bm.close()


if __name__ == "__main__":
    raise SystemExit(main())
