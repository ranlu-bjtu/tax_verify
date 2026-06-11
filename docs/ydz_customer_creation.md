# Yidaizhang Customer Creation Automation

This workflow creates or updates Yidaizhang customers from the public-manage backend task list.
It is intended for the operational flow used for creating account sets before tax collection.

## What It Does

For each tax number, the automation:

1. Reads the latest successful backend collection task from public-manage.
2. Extracts enterprise name, login method, proxy tax number, privacy number, and password from `loginJson`.
3. Resolves the Yidaizhang tax area code through `queryTaxGeoByTaxNo`, with a local fallback map.
4. For integration (`--env inte`), checks whether the privacy number already exists in the integration backend.
5. If the integration backend has no privacy-number data, copies it in the online backend and pulls it into integration.
6. Checks whether the customer already exists in Yidaizhang using `custWorkbench/queryPageList`.
7. Creates the customer only when it does not already exist.
8. Saves dynamic tax login info through `taxInfo/saveCustTaxAndBusiInfo`.
9. Verifies both customer defaults and dynamic tax info through query APIs.

The flow is idempotent: re-running the same tax number updates and verifies login info instead of creating duplicates.

## Preconditions

Start or reuse a Chrome session with CDP enabled on port `9222`.
The script can launch Chrome automatically. If the browser session is not ready, it attempts automatic login from configured secrets before falling back to manual login.

Both pages must become logged in:

- Yidaizhang target environment and enterprise.
- Public-manage backend task list.

No account passwords, tax login passwords, cookies, tokens, or Authorization headers are stored in the repo.

## Login Configuration

The selected environment controls which Yidaizhang credentials are used:

- 集测: `YDZ_INTE_URL`, `YDZ_INTE_WORK_URL`, `YDZ_INTE_USERNAME`, `YDZ_INTE_PASSWORD`, `YDZ_INTE_ENTERPRISE`
- 线上: `YDZ_PROD_URL`, `YDZ_PROD_WORK_URL`, `YDZ_PROD_USERNAME`, `YDZ_PROD_PASSWORD`, `YDZ_PROD_ENTERPRISE`
- 报税后台: `TAX_BACKEND_URL`, `TAX_BACKEND_USERNAME`, `TAX_BACKEND_PASSWORD`

Secrets can come from process environment variables, an uncommitted local env file passed with `--env-file`, or the operator console's temporary login fields. The console passes temporary values only to the child process environment; they are not written to the command line, job record, or result JSON.

Use `--skip-auto-login` only when debugging an existing browser login state.

If public-manage shows `403` or `无权访问`, the current browser token belongs to an account without access to the task list. Treat that as not logged in for this workflow; log in with a backend account that has task-list permission or provide `TAX_BACKEND_USERNAME` and `TAX_BACKEND_PASSWORD`.

## Yidaizhang Token Auth Mode

The default mode is `auto`: it tries direct password auth first, and falls back to browser login when no usable Yidaizhang API token context is produced.

```powershell
python scripts\ydz_create_customers.py --env inte --tax-no-file tax_nos.txt
```

For runs where a valid Yidaizhang `work.html` URL and API tokens are already available, the script can call Yidaizhang customer APIs without reading tokens from the page:

```powershell
python scripts\ydz_create_customers.py --env inte --tax-no-file tax_nos.txt --ydz-auth-mode token
```

Token mode reads these variables from the process environment or `--env-file`:

```text
YDZ_INTE_IFRAME_TOKEN
YDZ_INTE_CIA_TOKEN
YDZ_INTE_WORK_URL
YDZ_INTE_ORG_ID      optional, defaults to the configured integration org
YDZ_INTE_USER_ID     optional, defaults to the configured integration user

YDZ_PROD_IFRAME_TOKEN
YDZ_PROD_CIA_TOKEN
YDZ_PROD_WORK_URL
YDZ_PROD_ORG_ID      optional, defaults to the configured production org
YDZ_PROD_USER_ID     optional, defaults to the configured production user
```

Generic fallbacks `YDZ_IFRAME_TOKEN`, `YDZ_CIA_TOKEN`, `YDZ_WORK_URL`, `YDZ_ORG_ID`, and `YDZ_USER_ID` are also supported for portable one-off usage.

Manual-source runs can combine token mode with `--manual-source-env` and `--skip-privacy-phone-sync`; that path does not need to open Chrome because it does not query public-manage. Backend-source runs still need a public-manage browser session unless backend tokens are supplied by a future backend-token adapter.

Token mode is not a password-login bypass. It only reuses an already issued Yidaizhang API token. If the token is expired or the org id does not match the target environment, the run fails before creating or updating a customer.

## Yidaizhang Password Auth Mode

`--ydz-auth-mode password` tries to log in through the normal Chanjet account-password endpoints, then continues only if a usable Yidaizhang API token context is available:

```powershell
python scripts\ydz_create_customers.py --env inte --tax-no-file tax_nos.txt --ydz-auth-mode password
```

The mode reads the same `YDZ_INTE_USERNAME` / `YDZ_INTE_PASSWORD` or `YDZ_PROD_USERNAME` / `YDZ_PROD_PASSWORD` variables as browser auto-login. It does not write passwords, tokens, cookies, or Authorization values to output files.

This is a guarded best-effort path, not a slider or CAPTCHA bypass. When `--ydz-auth-mode password` is explicitly selected, Chanjet slider, SMS, phone binding, password-change, or SSO-without-business-token blockers stop before customer mutation. In default `auto` mode, those password-auth blockers are logged and the flow continues with browser login.

## Integration Privacy Number Preparation

Integration account-set creation prepares privacy-number data before writing the customer:

1. Query integration backend:

```text
POST https://data-task-management-chanapp.inte.chanjet.com/pub-tax-management/api/privatePhone/summary
```

with payload:

```json
{"privatePhone":"<privacy number>"}
```

2. If the integration summary has records, continue.
3. If it is empty, run the online backend copy flow:

```text
POST https://data-task-management.chanapp.chanjet.com/pub-tax-management/api/privatePhone/summary
POST https://data-task-management.chanapp.chanjet.com/pub-tax-management/api/privatePhone/ref/getDetail
GET  https://data-task-management.chanapp.chanjet.com/pub-tax-management/api/privatePhone/copyDataByPrivatePhone?privatePhone=<privacy number>
```

4. Pull the copied data into integration:

```text
GET https://data-task-management-chanapp.inte.chanjet.com/pub-tax-management/api/privatePhone/pullPrivateDataByPrivatePhone?privatePhone=<privacy number>
```

The integration privacy-number API must not receive the `token` header; sending `token` causes `用户身份证认证失败，请重新进行认证。`. The workflow keeps `authorization` and removes `token` only for the integration privacy-number endpoints.

## Operator Console Entry

Open the local workbench:

```powershell
python scripts\ops_console.py --open
```

Use the `创建账套` section for this workflow. The console writes each run under:

```text
output/accountset_runs/<runId>/
```

Each run contains the input tax-number file, `logs/ops_console.log`, and a sanitized `accountset_summary.json`. The result JSON uses the same public status fields as the command-line script and does not store tax login passwords, cookies, tokens, or raw backend `loginJson`.

## Integration Environment

```powershell
python scripts\ydz_create_customers.py --env inte --tax-no-file tax_nos.txt
```

Defaults:

- Opening period: `202501`
- Taxpayer type: `SMALL_TAXPAYER`
- Industry: `11079`
- Accountant: `user7793`
- Org id: `90001204213`

## Production Environment

```powershell
python scripts\ydz_create_customers.py --env prod --tax-no-file tax_nos.txt
```

Defaults:

- Opening period: `202501`
- Taxpayer type: `SMALL_TAXPAYER`
- Industry: `11079`
- Accountant: `user-yAfUZb`
- Org id: `90011827608`

## Useful Options

Dry run without writing:

```powershell
python scripts\ydz_create_customers.py --env inte --tax-no-file tax_nos.txt --dry-run
```

Single tax number:

```powershell
python scripts\ydz_create_customers.py --env inte --tax-no 91110116MAEETH8W2C
```

Save a sanitized result report:

```powershell
python scripts\ydz_create_customers.py --env inte --tax-no-file tax_nos.txt --output-json output\ydz_customer_create_summary.json
```

Override defaults:

```powershell
python scripts\ydz_create_customers.py --env inte --tax-no-file tax_nos.txt --opening-period 202501 --industry-id 11079 --taxpayer-type SMALL_TAXPAYER
```

## Result Status

- `OK`: created or updated, and both verification queries matched.
- `PARTIAL`: request finished, but customer defaults or tax-info verification did not match.
- `FAILED`: backend source data, Yidaizhang API call, or verification failed.
- `DRY_RUN`: source data and existing customer state were checked without writing.

## Safety Rules

- Do not pass or save passwords in command arguments.
- Use browser login state or host-managed secrets for login.
- Do not commit files under `output/`, `browser_profile/`, or `runtime/`.
- Do not write raw backend `loginJson` to logs or reports.
