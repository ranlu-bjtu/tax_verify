# Configuration And Secrets

The skill must not store real passwords. Configure secrets in the host tool, process environment, or a local env file passed with `--env-file`.

## Environment Variables

Integration Yidaizhang:

```text
YDZ_INTE_URL=https://ydz.inte.chanjet.com/
YDZ_INTE_USERNAME=<account>
YDZ_INTE_PASSWORD=<password>
YDZ_INTE_ENTERPRISE=<enterprise name>
```

Production Yidaizhang:

```text
YDZ_PROD_URL=https://ydz.chanjet.com/
YDZ_PROD_USERNAME=<account>
YDZ_PROD_PASSWORD=<password>
YDZ_PROD_ENTERPRISE=<enterprise name>
```

Public-manage backend:

```text
TAX_BACKEND_URL=https://public-manage.chanjet.com/taxserver/#/taskManage/taxTaskList
TAX_BACKEND_USERNAME=<account>
TAX_BACKEND_PASSWORD=<password>
```

Optional public-manage backend token-auth variables:

```text
TAX_BACKEND_AUTHORIZATION=<Authorization header value from public-manage /token>
TAX_BACKEND_TOKEN=<access_token from public-manage /token>
TAX_BACKEND_ACCESS_TOKEN=<alias for TAX_BACKEND_TOKEN>
TAX_BACKEND_USER_ID=<optional backend user id>
```

Use backend token mode with `--backend-auth-mode token`. Default backend auth mode is `auto`: the CLI first tries the token variables above, then tries the normal Chanjet SSO password API chain, then falls back to browser login. Strict password mode is enabled with `--backend-auth-mode password`; it does not bypass slider/CAPTCHA, SMS, MFA, password-change, or SSO risk-control prompts.

Optional Yidaizhang environment overrides:

```text
YDZ_INTE_WORK_URL=<work.html customer-list URL>
YDZ_PROD_WORK_URL=<work.html customer-list URL>
YDZ_INTE_LOGIN_CAPTCHA=666666
```

Integration password auth defaults the captcha code to `666666`. Override it with `YDZ_INTE_LOGIN_CAPTCHA`, `YDZ_INTE_CAPTCHA`, or `YDZ_INTE_VERIFY_CODE` when the host uses a different test code. Generic fallback names `YDZ_LOGIN_CAPTCHA`, `YDZ_CAPTCHA`, and `YDZ_VERIFY_CODE` are also supported. Production does not default a captcha value.

Manual-source account-set variables:

```text
YDZ_MANUAL_TAX_NO=<tax number>
YDZ_MANUAL_CUSTOMER_NAME=<customer and enterprise name>
YDZ_MANUAL_AREA_CODE=<optional tax area code>
YDZ_MANUAL_AREA_NAME=<area name; used as fallback when area code is omitted>
YDZ_MANUAL_LOGIN_METHOD=<YSHDL, DLYW-YSHDL, SDSRDX, DLYW-SDSRDX, or supported display text>
YDZ_MANUAL_PROXY_TAX_NO=<required for DLYW-* proxy login>
YDZ_MANUAL_PRIVACY_NO=<privacy number for YSHDL/DLYW-YSHDL; phone/login account for SDSRDX/DLYW-SDSRDX>
YDZ_MANUAL_PASSWORD=<tax login password>
```

Use manual source with:

```powershell
python .\scripts\ydz_accountset_cli.py create --env inte --manual-source-env --skip-privacy-phone-sync
```

Manual-source mode bypasses public-manage task lookup and integration privacy-phone sync. It still needs a usable Yidaizhang browser session, token mode context, or successful password-auth token context.

Optional token-auth variables:

```text
YDZ_INTE_IFRAME_TOKEN=<iframeToken from a valid Yidaizhang workbench session>
YDZ_INTE_CIA_TOKEN=<ciaToken from a valid Yidaizhang workbench session>
YDZ_INTE_ORG_ID=<org id, optional>
YDZ_INTE_USER_ID=<user id, optional>
YDZ_INTE_USER_MOBILE=<login phone, optional; helps resolve accountantEmployeeId>
YDZ_INTE_USER_NAME=<login user name, optional>

YDZ_PROD_IFRAME_TOKEN=<iframeToken from a valid Yidaizhang workbench session>
YDZ_PROD_CIA_TOKEN=<ciaToken from a valid Yidaizhang workbench session>
YDZ_PROD_ORG_ID=<org id, optional>
YDZ_PROD_USER_ID=<user id, optional>
YDZ_PROD_USER_MOBILE=<login phone, optional; helps resolve accountantEmployeeId>
YDZ_PROD_USER_NAME=<login user name, optional>
```

Token-auth mode is enabled with `--ydz-auth-mode token`. Treat tokens like passwords: configure them in the host secret store or an uncommitted env file, and never write them into the skill files.

Default auth mode is `auto`: the CLI first tries password auth with the configured Yidaizhang credentials, then falls back to browser login if no usable API token context is produced. Strict password-auth mode is enabled with `--ydz-auth-mode password`. It reads the same `YDZ_INTE_USERNAME` / `YDZ_INTE_PASSWORD` or `YDZ_PROD_USERNAME` / `YDZ_PROD_PASSWORD` variables and attempts the normal Chanjet account-password login endpoints. For integration, password auth calls `loginV2/accountVerify` with the configured captcha code before `loginV2/accountLogin`. Optional `YDZ_INTE_VERIFY_TOKEN`, `YDZ_PROD_VERIFY_TOKEN`, or `YDZ_VERIFY_TOKEN` can be supplied only when the host already obtained a valid verification token through an approved flow.

Password-auth mode does not bypass slider/CAPTCHA, SMS, phone binding, or password-change prompts. If those blockers appear, use browser mode and complete the visible challenge, or use token mode with already issued Yidaizhang API tokens.

## Local Env File

The CLI accepts `--env-file <path>`. Keep this file outside the repo when it contains passwords.

Example:

```powershell
python .\scripts\ydz_accountset_cli.py login --env inte --env-file C:\secure\ydz.env
python .\scripts\ydz_accountset_cli.py doctor --env inte --env-file C:\secure\ydz.env --open
```

## Credential Policy

- Environment or host-managed tokens are preferred for API-only authentication when available.
- Browser login state remains the fallback for visible verification challenges.
- Environment or host-managed credentials are used for automatic login when token/browser state is missing.
- Ask the user only for missing credentials or manual login verification.
- Never write `YDZ_*_PASSWORD`, `TAX_BACKEND_PASSWORD`, cookies, tokens, or raw backend `loginJson` to output files.

## Auto Login

The CLI command sequence should be:

```powershell
python .\scripts\ydz_accountset_cli.py login --env inte --env-file C:\secure\ydz.env
python .\scripts\ydz_accountset_cli.py doctor --env inte --env-file C:\secure\ydz.env --open
python .\scripts\ydz_accountset_cli.py create --env inte --env-file C:\secure\ydz.env --tax-no <taxNo> --dry-run
```

`doctor --open` and `create` also try automatic login by default. Use `--skip-auto-login` only for debugging an already logged-in browser session.
