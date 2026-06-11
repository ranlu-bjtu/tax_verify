---
name: ydz-create-accountset
description: Create or update Yidaizhang customer account sets in integration or production environments by tax number. Use when an agent needs to create 易代账 customers/account books, fetch tax-login data from public-manage backend tasks, save tax bureau login information, verify saved fields, run a dry-run, or diagnose Yidaizhang/public-manage login readiness.
---

# Yidaizhang Account Set Creation

Use this skill to create or update Yidaizhang customers and account sets from tax numbers. Prefer the bundled CLI because the workflow is fragile and must always save the dynamic tax-login table after creating the customer.

## Independence Contract

This skill is a standalone reusable package. It must work after copying the entire `ydz-create-accountset/` folder to another agent host.

- Use the bundled `scripts/ydz_accountset_cli.py`; do not call project-local account-set scripts outside this skill folder.
- Do not import or require this repository's `src/`, `scripts/`, `output/`, `runtime/`, `browser_profile/`, or project memory files.
- Keep all required business mappings, defaults, API calls, login flow, and verification logic inside this skill folder.
- Credentials must come from browser state, host-managed secrets, environment variables, or `--env-file`; never from files committed with the skill.

## Quick Start

Read `references/workflow.md` before running a live create. For field mapping details, read `references/api-field-mapping.md`.

Run commands from this skill folder:

```powershell
python .\scripts\ydz_accountset_cli.py login --env inte
python .\scripts\ydz_accountset_cli.py doctor --env inte --open
python .\scripts\ydz_accountset_cli.py create --env inte --tax-no 91532801MAG08KFE4F
python .\scripts\ydz_accountset_cli.py create --env prod --tax-no-file .\tax_nos.txt
```

Use `--dry-run` before live batches:

```powershell
python .\scripts\ydz_accountset_cli.py create --env inte --tax-no-file .\tax_nos.txt --dry-run
```

If the host already has a valid Yidaizhang `work.html` URL plus API tokens, `create` can use `--ydz-auth-mode token`. If the host also has valid public-manage header tokens, add `--backend-auth-mode token` so backend-source creation can run without opening the public-manage page. See `references/config-and-secrets.md`.

By default, `create` uses `--ydz-auth-mode auto`: it tries the normal Chanjet account-password login endpoints first, then falls back to browser login when no usable Yidaizhang API token context is produced. For integration, password auth first calls the normal captcha API with default code `666666` to obtain `verifyToken`. Explicit `create --ydz-auth-mode password` is strict and stops on slider/CAPTCHA, SMS, phone binding, password-change, or SSO-without-business-token blockers.

If public-manage password API login is blocked by SSO risk controls, default `--backend-auth-mode auto` logs the blocker and falls back to the existing browser session path. Explicit `--backend-auth-mode password` is strict and stops before customer mutation.

If the user provides all customer tax-login fields directly, `create --manual-source-env` reads `YDZ_MANUAL_*` variables and bypasses public-manage source lookup. In manual mode, pass `--skip-privacy-phone-sync` or rely on the manual-mode default skip; only the Yidaizhang API session/token context is required.

Supported backend-source login methods for account-set creation are:

- `YSHDL`: tax bureau privacy-number login.
- `DLYW-YSHDL`: tax bureau privacy-number proxy login.
- `SDSRDX`: tax bureau manual captcha-code login.
- `DLYW-SDSRDX`: tax bureau manual captcha-code proxy login.

For `YSHDL` and `DLYW-YSHDL`, `cTaxPreparerName` is the privacy number. For `SDSRDX` and `DLYW-SDSRDX`, `cTaxPreparerName` is the phone number/login account. `DLYW-*` methods require `cSiteLoginName` / proxy company tax number. Integration privacy-phone copy/pull runs only for the privacy-number methods, not for manual captcha-code methods.

## Required Sessions

Playwright is optional. API-only paths such as `--ydz-auth-mode token --backend-auth-mode token`, or a successful password-auth token context, do not need Playwright. Install the Python `playwright` package only when the run must open/reuse Chrome for browser login, manual verification, or CDP session checks.

The CLI prefers Chrome CDP at `http://127.0.0.1:9222`. If that port is already owned by a normal Chrome that Playwright cannot control, `login`, `doctor --open`, and `create` automatically retry managed Chrome on `9333`, `9444`, `9555`, then `9666` with a port-suffixed browser profile. The user's existing Chrome is not closed or relaunched.

Before a live create, ensure both sessions are ready:

- Target Yidaizhang environment and target enterprise.
- Public-manage tax backend task list, or valid backend token variables for `--backend-auth-mode token`.

Use `login` to open Chrome and use configured secrets to log in. `doctor --open` and `create` also try automatic login unless `--skip-auto-login` is passed. For public-manage, auto mode tries configured backend tokens, then guarded account-password API login, then browser fallback. If a page shows CAPTCHA, SMS, MFA, or an enterprise chooser that automation cannot complete, complete it in the browser and rerun the command.

When a production account is already authenticated but no `cloud.chanjet.com/.../work.html` page is active, the CLI recovers through the Chanjet workbench app list for the configured org id and clicks the primary `易代账` app entry. This avoids asking the user to manually find the production work URL, but it still does not bypass real verification challenges.

## Defaults

Integration (`--env inte`):

- Opening period: `202501`
- Taxpayer type: `SMALL_TAXPAYER`
- Industry: `11079`
- Accountant: resolved from the Yidaizhang login phone through `getChildEmpListByUserId`; fallback `user7793`

Production (`--env prod`):

- Opening period: `202501`
- Taxpayer type: `SMALL_TAXPAYER`
- Industry: `11079`
- Accountant: resolved from the Yidaizhang login phone through `getChildEmpListByUserId`; fallback `user-yAfUZb`

Customer name, enterprise name, and account book name must stay the same.

## Credential Handling

Never embed plaintext passwords, cookies, tokens, Authorization headers, or raw backend `loginJson` in this skill. The CLI reads browser login state and may read optional environment variables described in `references/config-and-secrets.md`.

If another agent asks for credentials, first run:

```powershell
python .\scripts\ydz_accountset_cli.py login --env inte
python .\scripts\ydz_accountset_cli.py doctor --env inte --open
```

Ask the user only for the specific missing login or manual verification step.

## Result Rules

The CLI only reports `OK` when both checks pass:

- Customer/account-set fields match expected defaults.
- Dynamic tax-login fields match the backend source.

`PARTIAL` means the request completed but one verification layer failed. `FAILED` means source extraction, API call, or verification could not complete. Do not treat customer creation alone as success.
