# Troubleshooting

## Playwright install prompt

Playwright is not required for API-only creation paths. If the CLI prints an install prompt, the current run has reached a browser/CDP path. Install only the Python package:

```powershell
python -m pip install playwright
```

Do not run `playwright install chromium` unless the host has no local Chrome. This skill normally launches or connects to local Chrome through CDP.

## `doctor` says Chrome CDP is unavailable

Run with `--open`, or start Chrome with remote debugging on port `9222`. With `--open`, the CLI prefers `9222` and can launch a managed fallback browser on `9333`, `9444`, `9555`, or `9666` if the preferred port is unavailable or incompatible.

```powershell
python .\scripts\ydz_accountset_cli.py doctor --env inte --open
```

## Yidaizhang token missing

Run automatic login first:

```powershell
python .\scripts\ydz_accountset_cli.py login --env inte --env-file C:\secure\ydz.env
```

Then rerun `doctor --open`. If automatic login cannot complete because of CAPTCHA, SMS, MFA, or an enterprise chooser, finish the visible browser step manually and rerun.

When the CLI launches Chrome itself, it passes `--enable-automation` for Playwright compatibility and `--disable-blink-features=AutomationControlled` to reduce automation markers. This may reduce slider frequency, but it is not a guaranteed bypass.

If Playwright reports that the current Chrome lacks `--enable-automation`, do not restart the user's normal Chrome first. Rerun `login`, `doctor --open`, or `create`; the CLI should switch to a fallback CDP port and isolated browser profile automatically.

If Yidaizhang shows a slider during password login, the CLI logs `MANUAL_VERIFICATION_REQUIRED` and keeps waiting for a valid workbench session. Complete the slider in the opened Chrome window; when `/ydzee/.../work.html` becomes usable, the same run continues automatically. If the wait times out, rerun with the logged-in browser session or run `login --env <env>` first.

If the org ID does not match the expected environment, select the correct enterprise or pass explicit overrides:

```powershell
--org-id <orgId> --user-id <userId> --accountant-id <employeeId>
```

For integration, the account may briefly show a real-name-auth reminder after enterprise selection. The CLI opens the configured `work.html` URL directly after login to reuse the token. If this still fails, pass the exact known workbench URL with `--ydz-work-url`.

## Public-manage token missing

Run automatic login first:

```powershell
python .\scripts\ydz_accountset_cli.py login --env inte --env-file C:\secure\ydz.env
```

If the backend still stops at the login page, complete CAPTCHA/SMS/MFA manually and rerun `doctor`.

If the backend page shows `403` or `无权访问`, the browser has a token for an account without permission. This is not a ready backend session. Configure `TAX_BACKEND_USERNAME` and `TAX_BACKEND_PASSWORD` for an account with task-list access, or clear the visible backend session and log in manually with the correct account.

## No backend task found

The tax number may have no recent successful collection task with login information. Increase lookback:

```powershell
--lookback-days 30,180,730,1460
```

If still missing, verify the task list manually with status `SUCCESS` and task categories `2,3` (国税/取票).

## `PARTIAL`

`PARTIAL` means the create/save requests completed but verification failed.

Common causes:

- The dynamic tax-info save endpoint was skipped or rejected.
- The login method was saved on old customer fields but not `taxInfoDTO`.
- The wrong proxy tax number was used for `DLYW-YSHDL`.
- The employee lookup could not match the Yidaizhang login phone, so the run fell back to the packaged default accountant.

Re-run with `--dry-run` and inspect the field named in the error.

## Sensitive Output

The CLI result intentionally shows only `hasPassword=true/false`; it does not print the password value. Do not modify the tool to write raw `loginJson`, tokens, cookies, or Authorization headers.
