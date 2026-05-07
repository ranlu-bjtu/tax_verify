"""Simple browser launcher - just opens Chrome with EtaxPlugin and waits.

Use this to manually navigate to the tax bureau and inspect the DOM.
"""

import sys
sys.path.insert(0, ".")

from src.login.browser_manager import BrowserManager

bm = BrowserManager()
bm.launch({"headless": False, "cdp_port": 9222, "user_data_dir": "./browser_profile/etax_session2"})
page = bm.get_page()

# Navigate to Jiangxi tax bureau login page
page.goto("https://etax.jiangxi.chinatax.gov.cn:8443/loginb/", wait_until="domcontentloaded", timeout=30000)

print("\n" + "="*60)
print("Chrome is open. Please:")
print("1. Use EtaxPlugin or manually login to Jiangxi tax bureau")
print("2. Navigate to: 我要查询 -> 一户式查询 -> 申报信息查询")
print("3. Click on the VAT declaration result to view detail page")
print("4. Then press Enter here to dump the DOM structure")
print("="*60)

input("\nPress Enter when you're on the detail page...")

# Dump DOM
print("\n\n=== DUMPING PAGE DOM ===")
print(f"URL: {page.url}")
print(f"Title: {page.title()}")

# Tables
tables = page.query_selector_all("table")
print(f"\nTables: {len(tables)}")
for i, table in enumerate(tables):
    rows = table.query_selector_all("tr")
    print(f"\n  Table {i}: {len(rows)} rows")
    for j, row in enumerate(rows):
        cells = row.query_selector_all("td, th")
        for k, cell in enumerate(cells):
            text = cell.inner_text().strip()
            eid = cell.get_attribute("id") or ""
            cls = cell.get_attribute("class") or ""
            if text or eid:
                print(f"    [{i},{j},{k}] id='{eid}' class='{cls}' text='{text[:80]}'")

# Input fields
inputs = page.query_selector_all("input, textarea")
print(f"\n\nInput fields: {len(inputs)}")
for inp in inputs:
    val = (inp.get_attribute("value") or "").strip()
    eid = (inp.get_attribute("id") or "").strip()
    name = (inp.get_attribute("name") or "").strip()
    itype = inp.get_attribute("type") or ""
    if val or eid:
        print(f"  input[{itype}] id='{eid}' name='{name}' value='{val[:60]}'")

# Elements with data attributes
for attr in ["data-cell-id", "data-field-id", "data-field", "data-id"]:
    els = page.query_selector_all(f"[{attr}]")
    if els:
        print(f"\nElements with [{attr}]: {len(els)}")
        for el in els[:20]:
            print(f"  [{el.tag_name}] {attr}='{el.get_attribute(attr)}' text='{el.inner_text().strip()[:60]}'")

# Screenshot
page.screenshot(path="./output/screenshots/detail_page.png", full_page=True)
print(f"\nScreenshot saved: ./output/screenshots/detail_page.png")

input("\nPress Enter to exit...")
bm.close()
