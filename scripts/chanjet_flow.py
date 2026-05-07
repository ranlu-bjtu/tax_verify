"""Navigate to Chanjet backend and let EtaxPlugin auto-login.

Flow:
1. Launch Chrome with EtaxPlugin
2. Navigate to Chanjet task management page
3. Wait for plugin to initialize (CIoT, robotId, etc.)
4. Check if plugin auto-triggers login, or click the button
5. Wait for redirect to tax bureau and login completion
"""

import sys
import time
sys.path.insert(0, ".")

from src.login.browser_manager import BrowserManager

bm = BrowserManager()
bm.launch({"headless": False, "cdp_port": 9222, "user_data_dir": "./browser_profile/etax_session3"})
page = bm.get_page()

# Navigate to Chanjet backend task list
CHANJET_URL = "https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList"
print(f"\nNavigating to Chanjet backend: {CHANJET_URL}")
page.goto(CHANJET_URL, wait_until="domcontentloaded", timeout=30000)

# Wait for page and plugin to load
print("Waiting for page and plugin scripts to initialize...")
time.sleep(8)

# Check what we have
print(f"\nCurrent URL: {page.url}")
print(f"Title: {page.title()}")

# Check if CIoT/robotId is available
try:
    robot_id = page.evaluate("window.robotId || 'NOT SET'")
    print(f"window.robotId: {robot_id}")
except:
    print("Cannot evaluate window.robotId")

# Check if plugin functions are available
try:
    has_start_polling = page.evaluate("typeof window.startPollingTask === 'function'")
    print(f"window.startPollingTask available: {has_start_polling}")
except:
    has_start_polling = False

try:
    has_get_api_root = page.evaluate("typeof window.etaxPlugin_getApiRoot === 'function'")
    print(f"window.etaxPlugin_getApiRoot available: {has_get_api_root}")
    if has_get_api_root:
        api_root = page.evaluate("window.etaxPlugin_getApiRoot()")
        print(f"  API root: {api_root}")
except:
    pass

# Check if getTaskCookie API function is available
try:
    has_get_task_cookie = page.evaluate("typeof window.etaxPlugin_apiClientGetTaskCookie === 'function'")
    print(f"window.etaxPlugin_apiClientGetTaskCookie available: {has_get_task_cookie}")
except:
    pass

# Check for UI elements on the page - task list buttons etc.
try:
    # Look for buttons or links related to entering tax bureau
    buttons = page.query_selector_all("button, a, [role='button']")
    print(f"\nButtons/links on page: {len(buttons)}")
    for btn in buttons:
        text = btn.inner_text().strip()[:50]
        cls = (btn.get_attribute("class") or "")[:40]
        onclick = (btn.get_attribute("onclick") or "")[:50]
        if text:
            print(f"  [{btn.tag_name}] class='{cls}' text='{text}' onclick={bool(onclick)}")
except Exception as e:
    print(f"Error reading buttons: {e}")

# Check for task rows in the table
try:
    rows = page.query_selector_all("table tr, .el-table__row, .table-row")
    print(f"\nTable rows found: {len(rows)}")
    for i, row in enumerate(rows[:10]):
        text = row.inner_text().strip()[:120]
        if text:
            print(f"  Row {i}: {text}")
except Exception as e:
    print(f"Error reading rows: {e}")

# Dump page HTML structure (simplified)
print("\n\n--- Page structure (key divs) ---")
try:
    body_html = page.evaluate("""
        () => {
            const els = document.querySelectorAll('div[class*="task"], div[class*="table"], div[class*="list"], div[class*="enter"], button[class*="tax"], button[class*="login"]');
            return Array.from(els).slice(0, 30).map(el => `<${el.tagName} class="${el.className}" id="${el.id}">${el.textContent?.substring(0, 100) || ''}</${el.tagName}>`).join('\n');
        }
    """)
    print(body_html[:3000])
except:
    pass

# Take screenshot
page.screenshot(path="./output/screenshots/chanjet_page.png", full_page=True)
print(f"\nScreenshot saved: ./output/screenshots/chanjet_page.png")

print("\n\n=== Browser is open for inspection ===")
print("If you see the Chanjet task list page:")
print("1. Look for a '一键进税局' or '进税局' button")
print("2. Or click on a task row to select it")
print("3. The EtaxPlugin toolbar icon may also trigger login")
print("\nPress Enter to exit...")
input()
bm.close()
