"""Launch Chrome with EtaxPlugin + CDP, let user do everything manually, then dump DOM."""

import sys, time, subprocess
sys.path.insert(0, ".")

plugin_path = r"C:\Users\Administrator\Downloads\EtaxPlugin"
user_data_dir = r"C:\Users\Administrator\tax_verify\browser_profile\etax_cdp"
cdp_port = 9222

chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
cmd = [
    chrome_path,
    "--load-extension=" + plugin_path,
    "--user-data-dir=" + user_data_dir,
    "--remote-debugging-port=" + str(cdp_port),
    "--no-first-run",
    "--no-default-browser-check",
    "https://login.chanjet.com/"
]
print("Starting Chrome with EtaxPlugin and CDP...")
print(f"CDP port: {cdp_port}")
proc = subprocess.Popen(cmd)
time.sleep(3)
print("Chrome launched successfully!")

print("\n" + "="*70)
print("Please do the following in Chrome:")
print("  1. Login to Chanjet (13963316973 / 201314@Lr)")
print("  2. Go to: https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList")
print("  3. Find taskId 2063633789326335821 and click '一键进税局'")
print("  4. Wait for plugin to auto-login to tax bureau")
print("  5. Navigate to: 申报信息查询 -> 点击增值税申报表 -> 进入详情页")
print("  6. Then press Enter here to dump the DOM")
print("="*70)

input("\nPress Enter when you're on the tax form detail page...")

# Reconnect via CDP and dump DOM
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
ctx = browser.contexts[0]
page = ctx.pages[-1] if ctx.pages else ctx.new_page()

print("\n" + "="*70)
print("DOM DUMP START")
print(f"URL: {page.url}")
print(f"Title: {page.title()}")
print("="*70)

# Tables
tables = page.query_selector_all("table")
print(f"\nTables: {len(tables)}")
for i, table in enumerate(tables):
    rows = table.query_selector_all("tr")
    print(f"\n  === Table {i} ({len(rows)} rows) ===")
    for j, row in enumerate(rows):
        cells = row.query_selector_all("td, th")
        row_data = []
        for k, cell in enumerate(cells):
            text = cell.inner_text().strip()
            eid = cell.get_attribute("id") or ""
            cls = cell.get_attribute("class") or ""
            if text or eid:
                row_data.append(f"  [{k}] id='{eid}' class='{cls[:30]}' text='{text[:100]}'")
        if row_data:
            print(f"    Row {j}:")
            for rd in row_data:
                print(rd)

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

# Data attributes
print("\n\nData attributes:")
for attr in ["data-cell-id", "data-field-id", "data-field", "data-id"]:
    els = page.query_selector_all(f"[{attr}]")
    if els:
        print(f"\n  [{attr}]: {len(els)} elements")
        for el in els[:20]:
            tag = el.tag_name
            aval = el.get_attribute(attr) or ""
            text = el.inner_text().strip()[:60]
            print(f"    <{tag}> {attr}='{aval}' text='{text}'")

# Known field IDs
print("\n\nKnown field IDs in DOM:")
known = ["yzzzsbhsxse_hwjlw_bqs", "bqmse_hwjlw_bqs", "bqynse_hwjlw_bqs",
         "ynsehj_hwjlw_bqs", "bqybtse_hwjlw_bqs", "msxse_hwjlw_bqs",
         "xwqymsxse_hwjlw_bqs", "bqynsejze_hwjlw_bqs"]
for fid in known:
    try:
        el = page.query_selector(f"#{fid}")
        if el:
            print(f"  FOUND #{fid}: text='{el.inner_text().strip()[:60]}'")
    except:
        pass

page.screenshot(path="./output/screenshots/tax_detail_final.png", full_page=True)
print(f"\n\nScreenshot: ./output/screenshots/tax_detail_final.png")

browser.close()
pw.stop()
proc.terminate()
print("\nDone!")
