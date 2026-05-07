"""Jiangxi tax bureau auto-login via EtaxPlugin:
1. Connect to Chrome via CDP
2. Get auth tokens from Chanjet page sessionStorage
3. Call getClientJob from browser -> get inner taskId
4. Call getTaskCookie from Python (requests) -> get login data
5. Build tpass URL (exactly as EtaxPlugin's userLogin does)
6. Dispatch clearTaxCookiesAndOpenNewTab event -> background handles cookie clear + tab open
7. Wait for tax bureau redirect

Run: python scripts/jiangxi_login_v2.py
"""

import sys, json, time, urllib.parse, requests

sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

TASK_ID = "2063633789326335821"
MACHINE_ID = "2D2D1044AF004A6A8CCAEBBDB5E03EDA"
CDP_PORT = 9222

GET_TASK_COOKIE_URL = "https://data-task-scheduler-ex.chanapp.chanjet.com/api/client/getTaskCookie"


def build_login_url(gtc_data, cj_data=None):
    """Build tpass login URL exactly as EtaxPlugin's userLogin() does.

    loginCookies is a flat object with spread sub-objects:
    ...tpass_localstorage (new_key16, cookie_type, token)
    ...etax_cookie (empty for jiangxi)
    ...taskInfo (waitAsyncNotify, needForceTax, taskId, etc.)
    """
    tydl = gtc_data.get('tydl') or {}
    declareJob = gtc_data.get('declareJob') or {}
    cookies = tydl.get('cookies') or {}
    proCid = tydl.get('proCid') or {}
    loginInfo = declareJob.get('loginInfo') or {}

    tpass_localstorage = cookies.get('tpass_localstorage') or {}
    etax_cookie = cookies.get('etax_cookie') or {}
    taskInfo = cookies.get('taskInfo') or {}

    province = declareJob.get('province', '') or (cj_data or {}).get('declareJob', {}).get('province', '')
    client_id = proCid.get('client_id', '')
    redirect_url = proCid.get('redirect_url', '')
    forceRedirectEtaxProvinces = gtc_data.get('forceRedirectEtaxProvinces', '')

    loginCookies = {
        'province': province,
        'origin': 'prod',
        'ciaToken': gtc_data.get('ciaToken', ''),
        'client_id': client_id,
        'idcard': tydl.get('idcard', ''),
        'taxNo': tydl.get('taxNo', ''),
        'batchNo': tydl.get('batchNo'),
        'orgId': declareJob.get('clientUseorgId', ''),
        'loginVersion': loginInfo.get('loginVersion', ''),
        'proxyTaxNo': loginInfo.get('cSiteLoginName', ''),
        'tgtUrl': gtc_data.get('tgtUrl', ''),
        'forceRedirectEtaxProvinces': forceRedirectEtaxProvinces,
        **tpass_localstorage,
        **etax_cookie,
        **taskInfo,
    }

    # Add countdown params
    if gtc_data.get('floatSeconds'):
        loginCookies['floatSeconds'] = gtc_data['floatSeconds']
    if gtc_data.get('warnSeconds'):
        loginCookies['warnSeconds'] = gtc_data['warnSeconds']

    loginCookies_encoded = urllib.parse.quote(
        json.dumps(loginCookies, ensure_ascii=False)
    )

    # Jiangxi uses port 8443 (not in hasPortArea list)
    url = (
        f'https://tpass.{province}.chinatax.gov.cn:8443/#/login'
        f'?redirect_uri={redirect_url}'
        f'&client_id={client_id}'
        f'&cookie={loginCookies_encoded}'
    )
    return url, province, loginCookies


def build_tax_domains(province):
    """Build the taxDomains list for cookie clearing, as userLogin does."""
    port = ':8443'  # jiangxi uses 8443
    return [
        'https://www.chinatax.gov.cn/',
        'https://chinatax.gov.cn/',
        f'https://{province}.chinatax.gov.cn/',
        f'https://tpass.{province}.chinatax.gov.cn/',
        f'https://tpass.{province}.chinatax.gov.cn{port}/',
        f'https://dppt.{province}.chinatax.gov.cn{port}/',
        f'https://etax.{province}.chinatax.gov.cn/',
        f'https://etax.{province}.chinatax.gov.cn/dwsbf-app-ww-web',
        f'https://www.etax.{province}.chinatax.gov.cn/',
        f'https://etax.{province}.chinatax.gov.cn{port}/',
        f'https://etax-xwcj.{province}.chinatax.gov.cn/',
        f'https://znhd.{province}.chinatax.gov.cn/',
        f'https://znhd.{province}.chinatax.gov.cn{port}/',
    ]


def main():
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
    ctx = browser.contexts[0]

    # Find Chanjet page
    chanjet_page = None
    for page in ctx.pages:
        if 'chanjet.com' in page.url:
            chanjet_page = page
            break

    if not chanjet_page:
        print('ERROR: No Chanjet page found!')
        pw.stop()
        sys.exit(1)

    print(f'Chanjet page: {chanjet_page.url}')

    # Close leftover chinatax tabs (not the Chanjet page)
    closed = 0
    for c in browser.contexts:
        for p in list(c.pages):
            if 'chinatax.gov.cn' in p.url and 'chanjet.com' not in p.url:
                try:
                    p.close()
                    closed += 1
                except:
                    pass
    if closed:
        print(f'Closed {closed} leftover chinatax tabs')

    # Set robotId on Chanjet page
    chanjet_page.evaluate(f'window.robotId = "{MACHINE_ID}"')

    # ========================================================================
    # Step 1: getClientJob from browser (DNS doesn't resolve for Python)
    # ========================================================================
    print('\n=== Step 1: getClientJob (browser fetch with auth) ===')
    client_job = chanjet_page.evaluate("""async (taskId) => {
        const url = `https://data-task-management.chanjet.com/pub-tax-management/api/remote/getClientJob?taskId=${taskId}&orgLoginType=NATIONAL&etaxPluginVersion=2.1.0.109`;

        const auth = sessionStorage.getItem('Authorization') || '';
        const accessToken = sessionStorage.getItem('access_token') || '';

        const headers = { "Content-Type": "application/json" };
        if (auth) headers["authorization"] = "Bearer " + auth;
        if (accessToken) headers["token"] = accessToken;

        const resp = await fetch(url, { method: "GET", headers });
        return await resp.json();
    }""", TASK_ID)

    cj_data = client_job.get('data') or {}
    cj_declareJob = cj_data.get('declareJob') or {}
    cj_tydl = cj_data.get('tydl') or {}
    cj_cookies = cj_tydl.get('cookies') or {}
    cj_taskInfo = cj_cookies.get('taskInfo') or {}

    inner_task_id = cj_taskInfo.get('taskId', '')
    province = cj_declareJob.get('province', '')

    print(f'  Inner taskId: {inner_task_id}')
    print(f'  Province: {province}')
    print(f'  TaxNo: {cj_tydl.get("taxNo", "")}')

    if not inner_task_id:
        print('ERROR: getClientJob failed - no inner taskId!')
        pw.stop()
        sys.exit(1)

    # ========================================================================
    # Step 2: getTaskCookie from Python (DNS resolves for this domain)
    # ========================================================================
    print('\n=== Step 2: getTaskCookie (Python requests) ===')
    poll_start = time.time()
    gtc_result = None

    while time.time() - poll_start < 60:
        try:
            resp = requests.post(
                GET_TASK_COOKIE_URL,
                json={"taskId": inner_task_id, "machineId": MACHINE_ID},
                headers={
                    'Content-Type': 'application/json',
                    'Origin': 'https://public-manage.chanjet.com',
                },
                timeout=10,
            )
            result = resp.json()
        except Exception as e:
            print(f'  Request error: {e}')
            time.sleep(3)
            continue

        flag = result.get('flag')
        elapsed = int(time.time() - poll_start)
        msg = result.get('msg', result.get('message', ''))
        print(f'  [{elapsed}s] flag={flag}, msg={msg[:50]}')

        if flag == 1:
            gtc_result = result
            break
        elif flag == 0:
            print(f'  FAILED: {msg}')
            pw.stop()
            sys.exit(1)
        else:
            time.sleep(3)

    if gtc_result is None:
        print('Polling timeout')
        pw.stop()
        sys.exit(1)

    gtc_data = gtc_result.get('data') or {}

    # Save for debugging
    with open('./output/task_cookie_jiangxi_v2.json', 'w', encoding='utf-8') as f:
        json.dump(gtc_result, f, ensure_ascii=False, indent=2)
    print(f'  Saved to ./output/task_cookie_jiangxi_v2.json')

    # ========================================================================
    # Step 3: Build tpass login URL (exactly as EtaxPlugin's userLogin)
    # ========================================================================
    print('\n=== Step 3: Build tpass login URL ===')
    newTabUrl, province, loginCookies = build_login_url(gtc_data, cj_data)
    taxDomains = build_tax_domains(province)

    currentTaskId = (gtc_data.get('tydl', {}).get('cookies', {}).get('taskInfo', {}).get('taskId', '')
                     or inner_task_id)

    print(f'  Province: {province}')
    print(f'  URL length: {len(newTabUrl)} chars')
    print(f'  loginCookies keys: {list(loginCookies.keys())}')

    # ========================================================================
    # Step 4: Dispatch clearTaxCookiesAndOpenNewTab event
    # This triggers the background script to:
    #   1. Clear all tax domain cookies (chrome.cookies.removeAll)
    #   2. Close all chinatax tabs
    #   3. Open new tab with tpass URL (after 2000ms delay)
    #   4. Reload new tab (after 50ms)
    # ========================================================================
    print('\n=== Step 4: Dispatch clearTaxCookiesAndOpenNewTab ===')

    # First set apiRoot in background (important for heartbeat)
    chanjet_page.evaluate("""() => {
        const currentApiRoot = window.etaxPlugin_getApiRoot ? window.etaxPlugin_getApiRoot() : 'https://data-task-scheduler-ex.chanapp.chanjet.com';
        window.dispatchEvent(new CustomEvent('setApiRoot', { detail: { apiRoot: currentApiRoot } }));
    }""")

    # Dispatch clearTaxCookiesAndOpenNewTab directly
    result = chanjet_page.evaluate("""(params) => {
        try {
            window.dispatchEvent(new CustomEvent('clearTaxCookiesAndOpenNewTab', {
                detail: {
                    province: params.province,
                    taxDomains: params.taxDomains,
                    newTabUrl: params.newTabUrl,
                    ms: 2000,
                    taskId: params.taskId
                }
            }));
            return 'dispatched';
        } catch (e) {
            return 'ERROR: ' + e.message;
        }
    }""", {
        "province": province,
        "taxDomains": taxDomains,
        "newTabUrl": newTabUrl,
        "taskId": currentTaskId,
    })

    print(f'  Event result: {result}')

    # ========================================================================
    # Step 5: Wait for tax bureau redirect
    # ========================================================================
    print('\n=== Step 5: Waiting for tax bureau redirect ===')
    print('  (background script will: clear cookies, close chinatax tabs, open tpass tab after 2s)')

    start_time = time.time()
    max_wait = 120

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)
        all_pages_info = []

        for c in browser.contexts:
            for p in c.pages:
                try:
                    url = p.url
                    title = p.title()
                    all_pages_info.append((url, title))
                except:
                    all_pages_info.append(('(error)', ''))

        # Print page status every 5 seconds
        if elapsed % 5 == 0 and elapsed > 0:
            print(f'  [{elapsed}s] Pages: {len(all_pages_info)}')
            for url, title in all_pages_info:
                short_url = url[:80]
                short_title = title[:30]
                if 'chinatax' in url or 'tpass' in url or 'etax' in url:
                    print(f'    {short_url} | {short_title}')

        # Check for successful tax bureau redirect
        for url, title in all_pages_info:
            if 'chinatax.gov.cn' in url and 'chanjet.com' not in url:
                # Exclude tpass login page and loginb page
                if 'tpass' not in url and '/loginb/' not in url and 'login' not in url.lower():
                    print(f'\n  SUCCESS! Tax bureau: {url}')
                    # Find the page object and screenshot
                    for c in browser.contexts:
                        for p in c.pages:
                            try:
                                if p.url == url:
                                    p.screenshot(path='./output/screenshots/tax_bureau_main.png', full_page=True)
                                    print(f'  Screenshot saved: ./output/screenshots/tax_bureau_main.png')
                                    pw.stop()
                                    return url
                            except:
                                pass

        time.sleep(3)

    # Timeout - print all pages for debugging
    print('\n  TIMEOUT - All pages:')
    for c in browser.contexts:
        for p in c.pages:
            try:
                print(f'    {p.url[:100]} | {p.title()[:40]}')
            except:
                try:
                    print(f'    {p.url[:100]}')
                except:
                    pass

    pw.stop()
    return None


if __name__ == '__main__':
    result = main()
    if result:
        print(f'\nTax bureau URL: {result}')
    else:
        print('\nFailed to reach tax bureau main page')