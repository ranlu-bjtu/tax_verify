"""Full login flow:
1. getClientJob (from browser) -> get inner taskId
2. Poll getTaskCookie with inner taskId + machineId -> flag=1
3. Build login URL -> open in browser
4. Wait for tax bureau redirect

Run: python scripts/jiangxi_login.py
"""
import sys, json, time, urllib.parse
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

TASK_ID = "2063137059184345777"
MACHINE_ID = "2D2D1044AF004A6A8CCAEBBDB5E03EDA"
CDP_PORT = 9222

pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{CDP_PORT}')
ctx = browser.contexts[0]

chanjet_page = None
for page in ctx.pages:
    if 'chanjet.com' in page.url:
        chanjet_page = page
        break

if not chanjet_page:
    print('ERROR: No Chanjet page!')
    pw.stop()
    sys.exit(1)

print(f'Chanjet page: {chanjet_page.url}')

# Close leftover chinatax tabs
for c in browser.contexts:
    for p in list(c.pages):
        if 'chinatax.gov.cn' in p.url and 'chanjet.com' not in p.url:
            try: p.close()
            except: pass

# Set robotId
chanjet_page.evaluate(f'window.robotId = "{MACHINE_ID}"')

# Step 1: getClientJob -> inner taskId (with auth headers from Chanjet session)
print('Step 1: getClientJob (with auth)...')
client_job = chanjet_page.evaluate("""async (taskId) => {
    const url = `https://data-task-management.chanjet.com/pub-tax-management/api/remote/getClientJob?taskId=${taskId}&orgLoginType=NATIONAL&etaxPluginVersion=2.1.0.109`;

    // Get auth tokens from Chanjet session
    const auth = sessionStorage.getItem('Authorization') || '';
    const accessToken = sessionStorage.getItem('access_token') || '';
    const userId = sessionStorage.getItem('userId') || '';

    const headers = { "Content-Type": "application/json" };
    if (auth) headers["authorization"] = "Bearer " + auth;
    if (accessToken) headers["token"] = accessToken;

    const resp = await fetch(url, { method: "GET", headers });
    return await resp.json();
}""", TASK_ID)

cj_data = client_job.get('data') or {}
declareJob = cj_data.get('declareJob') or {}
tydl = cj_data.get('tydl') or {}
cookies_inner = tydl.get('cookies') or {}
taskInfo = cookies_inner.get('taskInfo') or {}
inner_task_id = taskInfo.get('taskId', '')
province = declareJob.get('province', '')

print(f'  Inner taskId: {inner_task_id}')
print(f'  Province: {province}')
print(f'  TaxNo: {declareJob.get("taxNo", "")}')

if not inner_task_id:
    print('getClientJob failed - no inner taskId!')
    pw.stop()
    sys.exit(1)

# Step 2: Poll getTaskCookie with inner taskId
print('\nStep 2: Polling getTaskCookie with inner taskId...')
cookie_result = None
poll_start = time.time()

while time.time() - poll_start < 60:
    poll = chanjet_page.evaluate("""async (params) => {
        const apiRoot = window.etaxPlugin_getApiRoot();
        const url = apiRoot + "/api/client/getTaskCookie";
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ taskId: params.taskId, machineId: params.machineId })
        });
        return await response.json();
    }""", {'taskId': inner_task_id, 'machineId': MACHINE_ID})

    flag = poll.get('flag')
    elapsed = int(time.time() - poll_start)
    msg = poll.get('msg', poll.get('message', ''))
    print(f'  [{elapsed}s] flag={flag}, msg={msg[:50]}')

    if flag == 1:
        cookie_result = poll
        break
    elif flag == 0:
        print(f'  FAILED: {msg}')
        pw.stop()
        sys.exit(1)
    else:
        time.sleep(3)

if cookie_result is None:
    print('Polling timeout')
    pw.stop()
    sys.exit(1)

# Step 3: Build login URL (merge getClientJob + getTaskCookie data)
print('\nStep 3: Building login URL...')
gtc_data = cookie_result.get('data') or {}
gtc_declareJob = gtc_data.get('declareJob') or {}
gtc_tydl = gtc_data.get('tydl') or {}
province_val = gtc_declareJob.get('province', province) or province
proCid = gtc_tydl.get('proCid') or tydl.get('proCid') or {}
gtc_cookies = gtc_tydl.get('cookies') or {}

loginCookies = {
    'province': province_val, 'origin': 'prod',
    'ciaToken': gtc_data.get('ciaToken', ''),
    'client_id': proCid.get('client_id', ''),
    'idcard': gtc_tydl.get('idcard') or tydl.get('idcard', ''),
    'taxNo': gtc_tydl.get('taxNo') or tydl.get('taxNo', ''),
    'batchNo': gtc_tydl.get('batchNo') or tydl.get('batchNo'),
    'orgId': gtc_declareJob.get('clientUseorgId') or declareJob.get('clientUseorgId', ''),
    'loginVersion': (gtc_declareJob.get('loginInfo') or declareJob.get('loginInfo') or {}).get('loginVersion', ''),
    'proxyTaxNo': (gtc_declareJob.get('loginInfo') or declareJob.get('loginInfo') or {}).get('cSiteLoginName', ''),
    'tgtUrl': gtc_data.get('tgtUrl', ''),
    'forceRedirectEtaxProvinces': gtc_data.get('forceRedirectEtaxProvinces') or cj_data.get('forceRedirectEtaxProvinces', ''),
}

for sub in [gtc_cookies.get('tpass_localstorage'), gtc_cookies.get('etax_cookie'), gtc_cookies.get('taskInfo')]:
    if sub: loginCookies.update(sub)
if gtc_data.get('floatSeconds'): loginCookies['floatSeconds'] = gtc_data['floatSeconds']
if gtc_data.get('warnSeconds'): loginCookies['warnSeconds'] = gtc_data['warnSeconds']

loginCookies_encoded = urllib.parse.quote(json.dumps(loginCookies, ensure_ascii=False))
newTabUrl = f'https://tpass.{province_val}.chinatax.gov.cn:8443/#/login?redirect_uri={proCid.get("redirect_url", "")}&client_id={proCid.get("client_id", "")}&cookie={loginCookies_encoded}'
print(f'  Province: {province_val}, URL: {len(newTabUrl)} chars')

# Step 4: Open tpass URL
print('\nStep 4: Opening tpass login URL...')
new_page = ctx.new_page()
try:
    new_page.goto(newTabUrl, wait_until='domcontentloaded', timeout=30000)
except Exception as e:
    print(f'  Nav: {str(e)[:80]}')

# Step 5: Monitor redirects
print('\nStep 5: Monitoring redirects...')
start_time = time.time()
while time.time() - start_time < 45:
    try:
        url = new_page.url
        title = new_page.title()
        elapsed = int(time.time() - start_time)
        print(f'  [{elapsed}s] {url[:100]} | {title[:40]}')
        if 'chinatax.gov.cn' in url and 'chanjet.com' not in url:
            if 'tpass' not in url and '/loginb/' not in url and 'login' not in url.lower():
                print(f'\nSUCCESS! Tax bureau: {url}')
                new_page.screenshot(path='./output/screenshots/tax_bureau_main.png', full_page=True)
                pw.stop()
                sys.exit(0)
    except:
        pass

    for c in browser.contexts:
        for p in c.pages:
            if p == chanjet_page: continue
            try:
                pu = p.url
                if 'chinatax.gov.cn' in pu and 'chanjet.com' not in pu and 'tpass' not in pu and '/loginb/' not in pu and 'login' not in pu.lower():
                    print(f'\nSUCCESS! Found: {pu}')
                    p.screenshot(path='./output/screenshots/tax_bureau_main.png', full_page=True)
                    pw.stop()
                    sys.exit(0)
            except: pass
    time.sleep(3)

print('\nAll pages:')
for c in browser.contexts:
    for p in c.pages:
        try: print(f'  {p.url[:100]} | {p.title()[:40]}')
        except:
            try: print(f'  {p.url[:100]}')
            except: pass
pw.stop()