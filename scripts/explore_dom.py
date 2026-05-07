"""Browser DOM exploration script for Jiangxi tax bureau.

Launches Chrome with EtaxPlugin, auto-logs in, navigates to the
declaration query page, and dumps DOM structure for field mapping.

Usage:
    python scripts/explore_dom.py
"""

import json
import logging
import sys
import time

# Add project root to path
sys.path.insert(0, ".")

from src.login.browser_manager import BrowserManager
from src.login.login_detector import LoginDetector, EtaxAutoLoginHandler
from src.navigation.navigation_engine import NavigationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Jiangxi province config
PROVINCE = "jiangxi"
TASK_ID = "2063633789326335821"
LOGIN_TIMEOUT = 180

# Navigation steps for Jiangxi (same pattern as Shandong)
NAV_STEPS = [
    {"action": "click", "selector": "a:has-text('我要查询'), button:has-text('我要查询'), *:has-text('我要查询')", "wait_until": "domcontentloaded", "timeout": 10000, "description": "点击'我要查询'菜单"},
    {"action": "click", "selector": "a:has-text('一户式查询'), *:has-text('一户式查询')", "wait_until": "domcontentloaded", "timeout": 10000, "description": "点击'一户式查询'子菜单"},
    {"action": "click", "selector": "a:has-text('申报信息查询'), *:has-text('申报信息查询')", "wait_until": "domcontentloaded", "timeout": 10000, "description": "点击'申报信息查询'"},
    {"action": "wait", "selector": "table, .result-list, .data-list", "timeout": 15000, "description": "等待查询结果列表页面加载"},
]

RESULT_LIST_CONFIG = {
    "row_selector": "table tbody tr, .result-list > *, .data-list > *",
    "click_selector": "a, button, .view-btn, .detail-btn",
    "wait_after_click": 5000,
}


def dump_page_structure(page, label=""):
    """Dump page URL, title, and key DOM elements."""
    logger.info(f"\n{'='*60}")
    logger.info(f"PAGE: {label}")
    logger.info(f"URL: {page.url}")
    logger.info(f"Title: {page.title()}")
    logger.info(f"{'='*60}")

    # Get all tables
    tables = page.query_selector_all("table")
    logger.info(f"Tables found: {len(tables)}")
    for i, table in enumerate(tables):
        rows = table.query_selector_all("tr")
        logger.info(f"  Table {i}: {len(rows)} rows")
        for j, row in enumerate(rows[:5]):
            cells = row.query_selector_all("td, th")
            cell_texts = [c.inner_text().strip()[:50] for c in cells if c.inner_text().strip()]
            if cell_texts:
                logger.info(f"    Row {j}: {cell_texts}")

    # Get all visible links/buttons with text
    links = page.query_selector_all("a, button")
    logger.info(f"\nLinks/Buttons: {len(links)}")
    for link in links[:30]:
        text = link.inner_text().strip()[:40]
        href = link.get_attribute("href") or ""
        cls = link.get_attribute("class") or ""
        if text:
            logger.info(f"  [{link.tag_name}] '{text}' href={href[:50]} class={cls[:50]}")

    # Check for forms
    forms = page.query_selector_all("form")
    if forms:
        logger.info(f"\nForms: {len(forms)}")
        for i, form in enumerate(forms[:5]):
            inputs = form.query_selector_all("input, select, textarea")
            logger.info(f"  Form {i}: {len(inputs)} inputs")

    # Check for common CSS classes that might indicate data fields
    for selector in [".data-cell", ".field-value", ".form-control", "[data-field]", "[data-id]", "[id*='bqs']", "[id*='bnlj']", "[class*='cell']", "input[readonly]", "input:not([type='hidden'])"]:
        els = page.query_selector_all(selector)
        if els:
            logger.info(f"\nSelector '{selector}': {len(els)} elements")
            for el in els[:10]:
                text = el.inner_text().strip()[:80]
                val = el.get_attribute("value") or ""
                eid = el.get_attribute("id") or ""
                cls = el.get_attribute("class") or ""
                logger.info(f"  [{el.tag_name}] id='{eid}' class='{cls[:40]}' text='{text}' value='{val[:40]}'")


def dump_detail_page_dom(page):
    """Dump detailed DOM of the declaration detail page.

    Focus on finding input fields, spans with data, table cells
    that contain the tax form values.
    """
    logger.info("\n" + "=" * 80)
    logger.info("DETAIL PAGE DOM ANALYSIS")
    logger.info(f"URL: {page.url}")
    logger.info("=" * 80)

    # Full page text (first 5000 chars)
    body = page.query_selector("body")
    if body:
        text = body.inner_text()[:3000]
        logger.info(f"\nPage text (first 3000 chars):\n{text}")

    # Check for the main tax form table
    # Look for patterns like "应征增值税不含税销售额" or field IDs
    logger.info("\n--- Searching for tax form fields ---")

    # Strategy 1: Look for input fields with values
    all_inputs = page.query_selector_all("input[type='text'], input[type='number'], input:not([type])")
    logger.info(f"\nText/number inputs: {len(all_inputs)}")
    for inp in all_inputs[:40]:
        val = inp.get_attribute("value") or inp.inner_text() or ""
        eid = inp.get_attribute("id") or ""
        name = inp.get_attribute("name") or ""
        readonly = inp.get_attribute("readonly") or ""
        cls = inp.get_attribute("class") or ""
        if val.strip() or eid:
            logger.info(f"  input id='{eid}' name='{name}' value='{val[:60]}' readonly={bool(readonly)} class='{cls[:40]}'")

    # Strategy 2: Look for span/td/div with data-cell-id or similar attributes
    for attr in ["data-cell-id", "data-field-id", "data-field", "data-id", "data-name"]:
        els = page.query_selector_all(f"[{attr}]")
        if els:
            logger.info(f"\nElements with [{attr}]: {len(els)}")
            for el in els[:20]:
                val = el.inner_text().strip()[:60]
                attr_val = el.get_attribute(attr) or ""
                eid = el.get_attribute("id") or ""
                logger.info(f"  [{el.tag_name}] {attr}='{attr_val}' id='{eid}' text='{val}'")

    # Strategy 3: Find all table cells with non-empty text
    logger.info("\n--- Table cells with values ---")
    tds = page.query_selector_all("td, th")
    for td in tds:
        text = td.inner_text().strip()
        if text and len(text) < 200:
            eid = td.get_attribute("id") or ""
            cls = td.get_attribute("class") or ""
            rowspan = td.get_attribute("rowspan") or ""
            colspan = td.get_attribute("colspan") or ""
            # Check for parent tr
            try:
                tr = td.evaluate("el => el.closest('tr')?.rowIndex ?? -1")
            except:
                tr = -1
            logger.info(f"  td[row={tr}] id='{eid}' class='{cls[:30]}' rowspan={rowspan} colspan={colspan} text='{text[:80]}'")

    # Strategy 4: Look for specific known field IDs in the DOM
    known_fields = [
        "yzzzsbhsxse_hwjlw_bqs", "yzzzsbhsxse_fwjbdc_bqs",
        "bqmse_hwjlw_bqs", "bqynse_hwjlw_bqs",
        "ynsehj_hwjlw_bqs", "bqybtse_hwjlw_bqs",
    ]
    logger.info("\n--- Searching for known field IDs in DOM ---")
    for fid in known_fields:
        # Search as element id
        el = page.query_selector(f"#{fid}")
        if el:
            logger.info(f"  FOUND #{fid}: text='{el.inner_text().strip()[:60]}'")
        # Search as text content
        try:
            found = page.evaluate(f"""
                () => {{
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    let node;
                    while (node = walker.nextNode()) {{
                        if (node.textContent.includes('{fid}')) {{
                            const el = node.parentElement;
                            return {{ tag: el.tagName, text: el.textContent.substring(0, 100) }};
                        }}
                    }}
                    return null;
                }}
            """)
            if found:
                logger.info(f"  TEXT MATCH '{fid}': <{found['tag']}> {found['text'][:80]}")
        except:
            pass

    # Strategy 5: Screenshot the page for visual inspection
    try:
        page.screenshot(path="./output/screenshots/detail_page.png", full_page=True)
        logger.info("\nScreenshot saved to ./output/screenshots/detail_page.png")
    except Exception as e:
        logger.warning(f"Screenshot failed: {e}")


def main():
    bm = BrowserManager()
    try:
        bm.launch({"headless": False, "cdp_port": 9222})
        page = bm.get_page()

        # Auto-login
        logger.info(f"Starting auto-login for province: {PROVINCE}")
        detector = LoginDetector(province=PROVINCE)
        handler = EtaxAutoLoginHandler(
            province=PROVINCE,
            task_id=TASK_ID,
            login_detector=detector,
            timeout=LOGIN_TIMEOUT,
        )
        handler.auto_login(page)
        logger.info("Login successful!")

        # Dump main page structure
        dump_page_structure(page, "Main page after login")

        # Navigate to query page
        logger.info("\nNavigating to declaration query page...")
        nav = NavigationEngine(page)

        from src.models.tax_type import WebConfig, NavigationStep
        web_cfg = WebConfig(
            navigation_steps=[NavigationStep(**s) for s in NAV_STEPS],
            result_list=RESULT_LIST_CONFIG,
        )

        success = nav.navigate_to_form(web_cfg)
        if not success:
            logger.error("Navigation failed!")
            return

        # Dump result list page structure
        dump_page_structure(page, "Declaration query result list")

        # Count results
        count = nav.get_result_count(RESULT_LIST_CONFIG)
        logger.info(f"\nResult count: {count}")

        if count > 0:
            # Click the first result
            logger.info("\nClicking first result item...")
            if nav.click_result_item(0, RESULT_LIST_CONFIG):
                dump_detail_page_dom(page)

                # Wait for user to inspect
                logger.info("\n\n=== Browser is open for inspection ===")
                logger.info("Press Enter to continue and exit...")
                input()
            else:
                logger.error("Failed to click result item")
        else:
            logger.warning("No results found, dumping current page DOM")
            dump_detail_page_dom(page)
            logger.info("\n\n=== Browser is open for inspection ===")
            logger.info("Press Enter to continue and exit...")
            input()

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        bm.close()


if __name__ == "__main__":
    main()
