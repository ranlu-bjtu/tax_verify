# Workflow

## Commands

Diagnose sessions:

```powershell
python .\scripts\ydz_accountset_cli.py doctor --env inte --open
```

Login using configured secrets:

```powershell
python .\scripts\ydz_accountset_cli.py login --env inte
```

Create one customer/account set:

```powershell
python .\scripts\ydz_accountset_cli.py create --env inte --tax-no 91532801MAG08KFE4F
```

Create a batch:

```powershell
python .\scripts\ydz_accountset_cli.py create --env prod --tax-no-file .\tax_nos.txt
```

Dry run:

```powershell
python .\scripts\ydz_accountset_cli.py create --env inte --tax-no-file .\tax_nos.txt --dry-run
```

## End-To-End Flow

1. Determine the target environment: `inte` or `prod`.
2. Resolve authentication.
   - Yidaizhang defaults to `--ydz-auth-mode auto`: password API attempt, then browser fallback.
   - Public-manage defaults to `--backend-auth-mode auto`: configured backend header tokens, then password API attempt, then browser fallback.
   - Prefer Chrome CDP on port `9222` only for the sides that still need browser login.
   - If `9222` is occupied by an incompatible user Chrome, retry managed Chrome on `9333`, `9444`, `9555`, then `9666` with a port-suffixed browser profile.
   - When the CLI launches Chrome itself, it includes `--enable-automation` and `--disable-blink-features=AutomationControlled`.
3. Run `login --env <env>` or let `doctor/create` auto-login from configured secrets.
4. Ensure Yidaizhang is logged in and the correct enterprise is selected.
5. Ensure public-manage backend is ready through token provider or browser login.
6. Query public-manage successful backend tasks by tax number with task categories `2,3`, without `taskTypeId`, and with `loginType=YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX`.
7. Extract source fields:
   - Enterprise name.
   - Region.
   - Login method.
   - Proxy company tax number.
   - Privacy number.
   - Personal user password.
8. Resolve Yidaizhang area code through `queryTaxGeoByTaxNo`; fall back to province/tax-number mapping.
9. For integration (`--env inte`) and only when login method is `YSHDL` or `DLYW-YSHDL`, query the integration privacy-number summary using `{"privatePhone":"<value>"}`.
10. If integration has no privacy-number data for a privacy-number method, copy it in the online backend and call the integration pull API before customer creation. Skip this step for `SDSRDX` and `DLYW-SDSRDX` because `cTaxPreparerName` is a phone/login account, not a privacy number.
11. Check whether the customer already exists in Yidaizhang.
12. Resolve the assigned accountant from Yidaizhang employee data:
   - Call `trans/easyacctg/employee/getChildEmpListByUserId`.
   - Ignore `EASYACCTG_ADMIN` rows.
   - Match the Yidaizhang login account phone to employee `mobile`.
   - Use matched `userId` as `accountantEmployeeId`; fall back to current `userId`, then the packaged environment default.
13. Create the customer/account set only if missing.
14. Save dynamic tax-login information with `taxInfo/saveCustTaxAndBusiInfo`.
15. Verify customer defaults and dynamic tax-login fields through query APIs.
16. Return a sanitized status table or sanitized JSON.

Integration privacy-number endpoints under `data-task-management-chanapp.inte.chanjet.com` use the public-manage `authorization` header but must not include the `token` header. The online copy endpoints keep the normal public-manage headers.

## Login Behavior

`login`, `doctor --open`, and `create` read credentials from environment variables or `--env-file`. They never store passwords in the skill or output JSON.

Playwright is a lazy optional dependency. Token/password API paths run without importing it when they can complete without browser fallback. The CLI prompts to install the Python `playwright` package only when a browser/CDP path is actually needed, such as `login`, `doctor --open`, Yidaizhang/browser fallback, public-manage/browser fallback, or manual verification in Chrome.

For public-manage backend-source lookup, the CLI can use backend API tokens without opening the public-manage page:

```powershell
python .\scripts\ydz_accountset_cli.py create --env inte --tax-no 91532801MAG08KFE4F --backend-auth-mode token
```

Required backend token variables:

```text
TAX_BACKEND_AUTHORIZATION
TAX_BACKEND_TOKEN or TAX_BACKEND_ACCESS_TOKEN
```

Default backend auth mode is `auto`: try configured backend tokens first, then run the normal Chanjet SSO account-password API chain (`authorizeByJsonp -> /token`), then fall back to browser login. Explicit `--backend-auth-mode password` is strict. If SSO returns slider/CAPTCHA/SMS/risk-control blockers such as `访问拒绝`, strict mode stops before mutation and auto mode uses browser fallback.

For Yidaizhang integration, the login flow may stop at a real-name-auth reminder after enterprise selection. The CLI handles this by opening the configured `work.html` URL directly after authentication; if that still does not reach `/ydzee/.../work.html`, complete the visible prompt manually and rerun.

For production, an authenticated public landing page can exist without an active `cloud.chanjet.com/.../work.html` page. The CLI now opens `workbench.chanjet.com/v2/myapp/list?orgId=<env org id>` and clicks the primary `易代账` app's `进入应用` control before falling back to direct `work.html` navigation. This is a browser-session recovery step; it still requires a valid Chanjet login state or a completed visible verification challenge.

The CLI launch flag can reduce automation detection, but slider/CAPTCHA/MFA prompts can still appear and remain manual verification steps. Integration password auth can handle the simple test captcha through `loginV2/accountVerify` with default code `666666`; this is separate from slider or SMS challenges.

If Yidaizhang shows a slider during password login, the CLI logs `MANUAL_VERIFICATION_REQUIRED` and keeps waiting for a valid workbench session. Complete the slider in the opened Chrome window; when `/ydzee/.../work.html` becomes usable, the same run continues automatically. If the wait times out, rerun with the logged-in browser session or run `login --env <env>` first.

Pass `--skip-auto-login` only when you intentionally want to check an existing browser session without using configured credentials.

## Chrome CDP Behavior

The default requested CDP port is `9222`. The CLI leaves an existing browser on that port untouched. If Playwright rejects it because it was not started with automation-compatible flags, the CLI switches to the fallback ports and a separate profile directory such as `browser_profile_9333`.

Use `--cdp-port <port>` only when the host has a known managed Chrome port. Use `--no-launch-chrome` only for strict diagnostics; it disables the managed fallback launch.

## Token Auth Mode

The default mode is `auto`: `create` tries direct password auth first, then falls back to browser login if it cannot build a usable Yidaizhang API token context. If a host agent already has a valid Yidaizhang `work.html` URL plus API tokens, `create` can call Yidaizhang APIs without reading the Yidaizhang page:

```powershell
python .\scripts\ydz_accountset_cli.py create --env inte --tax-no 91532801MAG08KFE4F --ydz-auth-mode token
```

Required variables:

```text
YDZ_INTE_IFRAME_TOKEN
YDZ_INTE_CIA_TOKEN
YDZ_INTE_WORK_URL

YDZ_PROD_IFRAME_TOKEN
YDZ_PROD_CIA_TOKEN
YDZ_PROD_WORK_URL
```

Optional variables override the packaged defaults:

```text
YDZ_INTE_ORG_ID
YDZ_INTE_USER_ID
YDZ_INTE_USER_MOBILE
YDZ_INTE_USER_NAME
YDZ_PROD_ORG_ID
YDZ_PROD_USER_ID
YDZ_PROD_USER_MOBILE
YDZ_PROD_USER_NAME
```

Generic fallback names are also supported: `YDZ_IFRAME_TOKEN`, `YDZ_CIA_TOKEN`, `YDZ_WORK_URL`, `YDZ_ORG_ID`, `YDZ_USER_ID`, `YDZ_USER_MOBILE`, and `YDZ_USER_NAME`.

Yidaizhang token mode only replaces the Yidaizhang workbench-page token read. For a fully page-light backend-source run, combine it with `--backend-auth-mode token` and valid backend token variables. Integration privacy-phone copy/pull uses the same backend provider; integration endpoints still omit the `token` header.

## Password Auth Mode

The CLI also supports a guarded direct-login attempt:

```powershell
python .\scripts\ydz_accountset_cli.py create --env inte --tax-no 91532801MAG08KFE4F --ydz-auth-mode password
```

This mode uses the configured Yidaizhang username and password, opens the normal Chanjet login endpoints, and proceeds only if it can build the same `work.html` / `iframeToken` / `ciaToken` context required by token mode. For integration, it calls `loginV2/accountVerify` with the configured captcha code first, then passes the returned `verifyToken` to `loginV2/accountLogin`. It never writes the password or returned tokens to result files.

If Chanjet asks for slider/CAPTCHA, SMS, phone binding, or password change, explicit `--ydz-auth-mode password` returns a blocker status before any customer mutation. In default `auto` mode, the blocker is logged and the CLI falls back to browser login.

## Manual Source Mode

When the user already provides the enterprise/customer and tax-login fields, the CLI can bypass public-manage lookup:

```powershell
python .\scripts\ydz_accountset_cli.py create --env inte --manual-source-env --skip-privacy-phone-sync --tax-no 91110116MAEETH8W2C
```

Manual source reads `YDZ_MANUAL_*` variables listed in `references/config-and-secrets.md`. `YDZ_MANUAL_TAX_NO` can replace `--tax-no`; both are deduplicated when supplied. Customer name and enterprise name remain the same value from `YDZ_MANUAL_CUSTOMER_NAME`. For `SDSRDX` and `DLYW-SDSRDX`, put the phone/login account in `YDZ_MANUAL_PRIVACY_NO`; for `DLYW-*`, also provide `YDZ_MANUAL_PROXY_TAX_NO`.

This mode does not query public-manage and does not run privacy-phone copy/pull. It still calls Yidaizhang APIs to check/create the customer, save dynamic tax-login fields, and verify the saved result. Area code can be supplied directly with `YDZ_MANUAL_AREA_CODE`; if omitted, the CLI queries Yidaizhang tax geo and falls back to the area name/tax-number prefix.

## Idempotency

Re-running the same tax number must not create duplicates. If the customer exists, update/save the tax-login information and verify again.

## Live Run Safety

- Always run `--dry-run` for new batches.
- Use `--output-json` only for sanitized reports.
- Do not paste raw backend `loginJson` into chat or documents.
- If the CLI returns `PARTIAL`, inspect which verification layer failed before retrying.
