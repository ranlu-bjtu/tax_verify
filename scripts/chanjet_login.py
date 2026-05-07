"""Login to Chanjet backend and use EtaxPlugin to enter tax bureau.

1. Launch Chrome with EtaxPlugin
2. Login to Chanjet (account/password)
3. Navigate to task management page
4. Find task and trigger "一键进税局"
5. Wait for plugin to auto-login to tax bureau
"""

import sys
import time
sys.path.insert(0, ".")

from src.login.browser_manager import BrowserManager

bm = BrowserManager()
bm.launch({"headless": False, "cdp_port": 9222, "user_data_dir": "./browser_profile/etax_session6"})
page = bm.get_page()

# Wait for plugin to initialize on about:blank
time.sleep(2)

# Step 1: Login to Chanjet
print("\n=== Step 1: Navigate to Chanjet login ===")
page.goto("https://login.chanjet.com/", wait_until="domcontentloaded", timeout=30000)
time.sleep(3)
print(f"URL: {page.url}")
print(f"Title: {page.title()}")

# Check if plugin scripts are loaded on this page
try:
    has_insert = page.evaluate("typeof window.etaxPlugin_insertScriptIntoHeadElement === 'function'")
    print(f"Plugin scripts injected: {has_insert}")
except:
    print("Plugin scripts: could not evaluate")

# Find and fill login form
print("\n=== Step 2: Fill login form ===")
time.sleep(2)

# Try to find input fields
try:
    inputs = page.query_selector_all("input")
    print(f"Found {len(inputs)} input fields:")
    for i, inp in enumerate(inputs):
        itype = inp.get_attribute("type") or ""
        ph = inp.get_attribute("placeholder") or ""
        name = inp.get_attribute("name") or ""
        autocomplete = inp.get_attribute("autocomplete") or ""
        print(f"  [{i}] type='{itype}' placeholder='{ph[:30]}' name='{name}' autocomplete='{autocomplete}'")

    if len(inputs) >= 2:
        # Fill username (first text input)
        username_input = None
        password_input = None
        for inp in inputs:
            itype = inp.get_attribute("type") or ""
            name = inp.get_attribute("name") or ""
            autocomplete = inp.get_attribute("autocomplete") or ""
            if itype == "password":
                password_input = inp
            elif itype in ("", "text", "tel") and not username_input:
                # Skip hidden/search inputs
                if name.lower() not in ("_csrf", "csrf") and "search" not in name.lower():
                    username_input = inp

        if username_input:
            username_input.fill("13963316973")
            print("Filled username: 13963316973")
        if password_input:
            password_input.fill("201314@Lr")
            print("Filled password")

        time.sleep(1)

        # Click login button
        login_btn = page.query_selector("button:has-text('登录')")
        if login_btn:
            login_btn.click()
            print("Clicked login button")
        else:
            # Press Enter on password field
            if password_input:
                password_input.press("Enter")
                print("Pressed Enter")

        time.sleep(5)
        print(f"\nAfter login attempt - URL: {page.url}")
        print(f"After login attempt - Title: {page.title()}")

        page.screenshot(path="./output/screenshots/after_login.png", full_page=True)
except Exception as e:
    print(f"Login form error: {e}")
    import traceback
    traceback.print_exc()

# Step 2b: If redirected to another login page, try again
if "login.chanjet.com" in page.url or "登录" in page.title():
    print("\n=== Step 2b: Still on login page, trying again ===")
    time.sleep(2)
    try:
        inputs = page.query_selector_all("input")
        for i, inp in enumerate(inputs):
            itype = inp.get_attribute("type") or ""
            if itype == "password":
                inp.fill("201314@Lr")
                print("Filled password field")
            elif itype in ("", "text", "tel") and "search" not in (inp.get_attribute("placeholder") or "").lower():
                inp.fill("13963316973")
                print("Filled username field")

        time.sleep(1)
        # Find and click login button
        btns = page.query_selector_all("button")
        for btn in btns:
            text = btn.inner_text().strip()
            if text == "登录":
                btn.click()
                print("Clicked 登录 button")
                break
        time.sleep(5)
        print(f"After retry - URL: {page.url}")
        page.screenshot(path="./output/screenshots/after_login_retry.png", full_page=True)
    except Exception as e:
        print(f"Retry error: {e}")

# Step 3: Navigate to task management
print("\n=== Step 3: Navigate to task management ===")
task_url = "https://public-manage.chanjet.com/taxserver#/taskManage/taxTaskList"
page.goto(task_url, wait_until="domcontentloaded", timeout=30000)
time.sleep(5)
print(f"URL: {page.url}")
print(f"Title: {page.title()}")
page.screenshot(path="./output/screenshots/task_page.png", full_page=True)

# Step 4: Check plugin state
print("\n=== Step 4: Plugin state ===")
try:
    checks = page.evaluate("""() => {
        return {
            robotId: typeof window.robotId !== 'undefined' ? window.robotId : 'NOT DEFINED',
            hasGetApiRoot: typeof window.etaxPlugin_getApiRoot === 'function',
            hasGetTaskCookie: typeof window.etaxPlugin_apiClientGetTaskCookie === 'function',
            hasStartPolling: typeof window.startPollingTask === 'function',
            hasInsertScript: typeof window.etaxPlugin_insertScriptIntoHeadElement === 'function',
        };
    }""")
    for k, v in checks.items():
        print(f"  {k}: {v}")
except Exception as e:
    print(f"  Evaluate error: {e}")

# Step 5: Look for task rows
print("\n=== Step 5: Find task list ===")
try:
    # Try to find all visible text content
    body_text = page.evaluate("document.body?.innerText?.substring(0, 2000)")
    if body_text:
        print(f"Page text (first 2000 chars):\n{body_text[:500]}")

    # Look for table rows
    rows = page.query_selector_all("tr")
    print(f"\nTotal <tr> elements: {len(rows)}")

    # Look for div elements with class containing "row" or "item"
    rows_div = page.query_selector_all("div[class*='row'], div[class*='item'], div[class*='table'], div[class*='list']")
    print(f"Divs with row/item/table/list class: {len(rows_div)}")
    for i, div in enumerate(rows_div[:10]):
        text = div.inner_text().strip()[:80]
        cls = div.get_attribute("class") or ""
        if text:
            print(f"  [{i}] class='{cls[:40]}' text='{text}'")
except Exception as e:
    print(f"  Error: {e}")

# Save full page screenshot
page.screenshot(path="./output/screenshots/final_state.png", full_page=True)
print(f"\nFinal screenshot: ./output/screenshots/final_state.png")

print("\n=== Browser is open. Please check what's on screen ===")
print("If you see the task list, look for taskId 2063633789326335821")
print("Press Enter to exit...")
input()
bm.close()
