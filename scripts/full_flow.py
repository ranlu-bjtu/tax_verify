"""Full flow: Login Chanjet -> Trigger EtaxPlugin -> Auto-login tax bureau -> Dump DOM.

1. Launch Chrome with EtaxPlugin via persistent context
2. Login to Chanjet backend
3. Navigate to task management page
4. Wait for plugin to trigger auto-login to tax bureau
5. Dump DOM from the tax form detail page
"""

import sys
import time
sys.path.insert(0, ".")

from src.login.browser_manager import BrowserManager

bm = BrowserManager()
bm.launch({"headless": False, "cdp_port": 9222, "user_data_dir": "./browser_profile/etax_final"})
page = bm.get_page()

print("\n" + "="*60)
print("Step 1: Login to Chanjet")
print("="*60)

# Navigate to Chanjet login
page.goto("https://login.chanjet.com/", wait_until="domcontentloaded", timeout=30000)
time.sleep(3)

# Check plugin is loaded
try:
    has_insert = page.evaluate("typeof window.etaxPlugin_insertScriptIntoHeadElement === 'function'")
    print(f"Plugin content scripts loaded: {has_insert}")
except:
    print("Plugin check: could not evaluate")

# Login
print("Filling login credentials...")
try:
    inputs = page.query_selector_all("input")
    print(f"Found {len(inputs)} inputs")
    for i, inp in enumerate(inputs):
        itype = inp.get_attribute("type") or ""
        name = inp.get_attribute("name") or ""
        autocomplete = inp.get_attribute("autocomplete") or ""
        print(f"  [{i}] type='{itype}' name='{name}' autocomplete='{autocomplete}'")

    username_input = None
    password_input = None
    for inp in inputs:
        itype = inp.get_attribute("type") or ""
        name = inp.get_attribute("name") or ""
        if itype == "password":
            password_input = inp
        elif itype in ("", "text", "tel") and not username_input:
            if name.lower() not in ("_csrf", "csrf") and "search" not in name.lower():
                username_input = inp

    if username_input:
        username_input.fill("13963316973")
        print("  Username filled")
    if password_input:
        password_input.fill("201314@Lr")
        print("  Password filled")

    time.sleep(1)
    btn = page.query_selector("button:has-text('登录')")
    if btn:
        btn.click()
        print("  Login button clicked")
    elif password_input:
        password_input.press("Enter")
        print("  Pressed Enter")

    time.sleep(5)
    print(f"After login: {page.url}")
    page.screenshot(path="./output/screenshots/chanjet_login_done.png")
except Exception as e:
    print(f"Login error: {e}")
    import traceback; traceback.print_exc()

print("\n" + "="*60)
print("Step 2: Navigate to task management")
print("="*60)

# Navigate to task management
page.goto("https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList", wait_until="domcontentloaded", timeout=30000)
time.sleep(5)
print(f"Task list URL: {page.url}")
print(f"Title: {page.title()}")

# Check plugin state
try:
    result = page.evaluate("""() => ({
        robotId: typeof window.robotId !== 'undefined' ? window.robotId : 'NOT DEFINED',
        hasGetApiRoot: typeof window.etaxPlugin_getApiRoot === 'function',
        hasGetTaskCookie: typeof window.etaxPlugin_apiClientGetTaskCookie === 'function',
        hasStartPolling: typeof window.startPollingTask === 'function',
    })""")
    print(f"Plugin state: {result}")
except Exception as e:
    print(f"Plugin check error: {e}")

page.screenshot(path="./output/screenshots/task_list.png")

# Look for the task and trigger login
print("\n" + "="*60)
print("Step 3: Find task and trigger '一键进税局'")
print("="*60)
time.sleep(2)

# Try to find elements related to the task
try:
    # Search for elements containing the task ID or tax-related text
    found = page.evaluate("""() => {
        const allEls = document.querySelectorAll('div, span, a, button, td, th');
        const results = [];
        const keywords = ['进税局', '2063633789326335821', '增值税', 'taskManage'];
        for (const el of allEls) {
            const text = el.textContent?.trim() || '';
            for (const kw of keywords) {
                if (text.includes(kw) || text.toLowerCase().includes(kw.toLowerCase())) {
                    results.push({
                        tag: el.tagName,
                        class: (el.className || '').substring(0, 80),
                        id: el.id || '',
                        text: text.substring(0, 100)
                    });
                    break;
                }
            }
            if (results.length >= 30) break;
        }
        return results;
    }""")
    for item in found:
        print(f"  <{item['tag']}> class='{item['class'][:40]}' text='{item['text'][:60]}'")
except Exception as e:
    print(f"Search error: {e}")

# Check page body text
try:
    body_text = page.evaluate("document.body?.innerText?.substring(0, 1000)")
    print(f"\nPage text:\n{body_text}")
except:
    pass

print("\n\n=== Browser open for manual inspection ===")
print("If you see the task list, please find the button for taskId 2063633789326335821")
print("to enter tax bureau, then press Enter to dump DOM...")
input()

# Step 4: Wait for redirect to tax bureau and dump DOM
print("\n" + "="*60)
print("Step 4: Dump DOM from tax bureau detail page")
print("="*60)

time.sleep(3)
print(f"Current URL: {page.url}")
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
                print(f"    [{i},{j},{k}] id='{eid}' class='{cls[:30]}' text='{text[:80]}'")

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
for attr in ["data-cell-id", "data-field-id", "data-field", "data-id"]:
    els = page.query_selector_all(f"[{attr}]")
    if els:
        print(f"\nElements with [{attr}]: {len(els)}")
        for el in els[:20]:
            print(f"  [{el.tag_name}] {attr}='{el.get_attribute(attr)}' text='{el.inner_text().strip()[:60]}'")

page.screenshot(path="./output/screenshots/tax_detail.png", full_page=True)
print(f"\nScreenshot saved: ./output/screenshots/tax_detail.png")

print("\nDone!")
bm.close()
