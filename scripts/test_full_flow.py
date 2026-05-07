"""Test the full tax verification flow:
1. Launch Chrome with EtaxPlugin + CDP
2. Wait for user to login to Chanjet
3. Trigger EtaxPlugin auto-login to tax bureau
4. Navigate to declaration query -> click VAT form
5. Dump DOM structure for field mapping
6. Extract data and compare with API

Run: python scripts/test_full_flow.py
"""

import json
import logging
import sys
import time

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

from src.login.browser_manager import BrowserManager
from src.login.auto_tax_login import AutoTaxLogin, CHANJET_TASK_URL
from src.navigation.navigation_engine import NavigationEngine
from src.api.api_client import APIClient
from src.parser.web_dom_parser import WebDOMParser
from src.login.login_detector import LoginDetector

TASK_ID = "2063633789326335821"
PROVINCE = "jiangxi"
CDP_PORT = 9222


def get_api_data():
    """Fetch API data for comparison."""
    logger.info(f"Fetching API data for task: {TASK_ID}")
    client = APIClient()
    response = client.fetch_by_task_id(TASK_ID)
    # Extract zzszb_qc from the nested structure
    if isinstance(response, dict):
        # response has flattened structure, get zzszb_qc fields
        qc_data = {}
        for key, val in response.items():
            if key.startswith("zzszb_qc") or key.startswith("sz_zzs"):
                qc_data[key] = val
        # Direct zzszb_qc access
        if "data" in response and isinstance(response["data"], dict):
            for key in response["data"]:
                if key.startswith("zzszb_qc"):
                    qc_data[key] = response["data"][key]
        logger.info(f"API data extracted: {len(qc_data)} fields")
        return qc_data, response
    return {}, response


def dump_dom(page, label=""):
    """Dump page DOM structure for analysis."""
    logger.info(f"\n{'='*60}")
    logger.info(f"DOM DUMP: {label}")
    logger.info(f"URL: {page.url}")
    logger.info(f"Title: {page.title()}")
    logger.info(f"{'='*60}")

    # Tables
    tables = page.query_selector_all("table")
    logger.info(f"Tables: {len(tables)}")
    for i, table in enumerate(tables):
        rows = table.query_selector_all("tr")
        logger.info(f"  Table {i}: {len(rows)} rows")
        for j, row in enumerate(rows[:40]):
            cells = row.query_selector_all("td, th")
            for k, cell in enumerate(cells):
                text = cell.inner_text().strip()
                eid = cell.get_attribute("id") or ""
                cls = cell.get_attribute("class") or ""
                if text or eid:
                    logger.info(f"    [{i},{j},{k}] id='{eid}' class='{cls[:30]}' text='{text[:100]}'")

    # Input fields with values
    inputs = page.query_selector_all("input[type='text'], input[type='number'], input:not([type])")
    logger.info(f"\nInput fields: {len(inputs)}")
    for inp in inputs[:40]:
        val = (inp.get_attribute("value") or "").strip()
        eid = (inp.get_attribute("id") or "").strip()
        name = (inp.get_attribute("name") or "").strip()
        readonly = bool(inp.get_attribute("readonly"))
        if val or eid:
            logger.info(f"  input id='{eid}' name='{name}' value='{val[:60]}' readonly={readonly}")

    # Data attributes
    for attr in ["data-cell-id", "data-field-id", "data-field", "data-id"]:
        els = page.query_selector_all(f"[{attr}]")
        if els:
            logger.info(f"\n[{attr}]: {len(els)} elements")
            for el in els[:20]:
                logger.info(f"  <{el.tag_name}> {attr}='{el.get_attribute(attr)}' text='{el.inner_text().strip()[:60]}'")

    # Known field IDs
    logger.info("\nKnown field IDs search:")
    known_fields = [
        "yzzzsbhsxse_hwjlw_bqs", "yzzzsbhsxse_fwjbdc_bqs",
        "bqmse_hwjlw_bqs", "bqynse_hwjlw_bqs",
        "ynsehj_hwjlw_bqs", "bqybtse_hwjlw_bqs",
        "msxse_hwjlw_bqs", "xwqymsxse_hwjlw_bqs",
        "wdqzdxse_hwjlw_bqs", "wdqzdmse_hwjlw_bqs",
        "bqynsejze_hwjlw_bqs", "hdxse_hwjlw_bqs",
        "skqjkjdptfpbhsxse_hwjlw_bqs",
        "swjgdkdzzszyfpbhsxse_hwjlw_bqs",
        "ckmsxse_hwjlw_bqs", "skqjkjdptfpxse1_hwjlw_bqs",
        "xsczbdcbhsxse_hwjlw_bqs",
    ]
    for fid in known_fields:
        try:
            el = page.query_selector(f"#{fid}")
            if el:
                logger.info(f"  FOUND #{fid}: '{el.inner_text().strip()[:60]}'")
        except:
            pass

    # Screenshot
    page.screenshot(path="./output/screenshots/dom_dump.png", full_page=True)
    logger.info("Screenshot saved: ./output/screenshots/dom_dump.png")


def main():
    # Step 0: Get API data first
    api_qc_data, api_response = get_api_data()
    logger.info(f"API province: {api_response.get('province', 'unknown')}")

    # Step 1: Launch Chrome with extension + CDP
    logger.info("\n=== Step 1: Launch Chrome with EtaxPlugin ===")
    bm = BrowserManager()
    bm.launch_with_extension({
        "user_data_dir": "./browser_profile/etax_flow_test",
        "cdp_port": CDP_PORT,
    })
    page = bm.get_page()

    # Step 2: Navigate to Chanjet and wait for user login
    logger.info("\n=== Step 2: Navigate to Chanjet ===")
    page.goto(CHANJET_TASK_URL, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    auto_login = AutoTaxLogin(bm, province=PROVINCE)
    logger.info("Waiting for Chanjet login (user must login manually)...")

    # Poll for Chanjet login completion
    chanjet_logged_in = auto_login.wait_for_chanjet_login(page, timeout=300)
    if not chanjet_logged_in:
        logger.error("Chanjet login timeout!")
        bm.close()
        return

    # Step 3: Trigger EtaxPlugin auto-login
    logger.info("\n=== Step 3: Trigger EtaxPlugin auto-login ===")
    chanjet_page = bm.find_page_by_url("chanjet.com") or page
    tax_page = auto_login.trigger_plugin_and_wait(chanjet_page, TASK_ID, timeout=120)

    if not tax_page:
        logger.error("Tax bureau login failed!")
        bm.close()
        return

    logger.info(f"Tax bureau logged in! URL: {tax_page.url}")

    # Step 4: Navigate to declaration query
    logger.info("\n=== Step 4: Navigate to declaration query ===")
    from src.models.tax_type import WebConfig, NavigationStep

    web_cfg = WebConfig(
        navigation_steps=[
            NavigationStep(action="click", selector="a:has-text('我要查询'), button:has-text('我要查询'), *:has-text('我要查询')", wait_until="domcontentloaded", timeout=10000, description="点击'我要查询'菜单"),
            NavigationStep(action="click", selector="a:has-text('一户式查询'), *:has-text('一户式查询')", wait_until="domcontentloaded", timeout=10000, description="点击'一户式查询'子菜单"),
            NavigationStep(action="click", selector="a:has-text('申报信息查询'), *:has-text('申报信息查询')", wait_until="domcontentloaded", timeout=10000, description="点击'申报信息查询'"),
            NavigationStep(action="wait", selector="table, .result-list, .data-list", timeout=15000, description="等待查询结果列表页面加载"),
        ],
        result_list={
            "enabled": True,
            "row_selector": "table tbody tr, .result-list > *, .data-list > *",
            "click_selector": "a, button, .view-btn, .detail-btn",
            "wait_after_click": 5000,
        },
    )

    nav = NavigationEngine(tax_page)
    nav_success = nav.navigate_to_form(web_cfg)
    if not nav_success:
        logger.warning("Navigation failed, dumping current page anyway")
        dump_dom(tax_page, "After failed navigation")

    # Step 5: Dump result list page
    logger.info("\n=== Step 5: Result list page ===")
    dump_dom(tax_page, "Result list page")

    # Count results
    result_list_cfg = web_cfg.result_list
    count = nav.get_result_count(result_list_cfg)
    logger.info(f"Result count: {count}")

    if count > 0:
        # Click first result (增值税小规模申报表)
        logger.info("\n=== Step 6: Click first result ===")
        if nav.click_result_item(0, result_list_cfg):
            time.sleep(3)
            dump_dom(tax_page, "VAT declaration detail page")

            # Try to extract data
            parser = WebDOMParser(tax_page)
            web_data = parser.extract_by_mappings([])  # No mappings yet, use table extraction
            if web_cfg.table_selector:
                table_data = parser.extract_table(web_cfg)
                web_data.update(table_data)

            logger.info(f"\nExtracted web data: {len(web_data)} fields")
            for key, val in web_data.items():
                logger.info(f"  {key}: {val}")

            # Compare with API data
            logger.info("\n=== Comparison ===")
            for key in api_qc_data:
                api_val = api_qc_data[key]
                web_val = web_data.get(key, "NOT FOUND")
                match = "MATCH" if str(api_val) == str(web_val) else f"DIFF (api={api_val}, web={web_val})"
                logger.info(f"  {key}: {match}")

    bm.close()
    logger.info("\nDone!")


if __name__ == "__main__":
    main()