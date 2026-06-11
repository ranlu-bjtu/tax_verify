# CHANGELOG_AI.md

## 2026-06-11: pre-push cleanup and sensitive fixture scrub

Changed:
- Added local artifact ignore rules for `.DS_Store`, temporary Office lock files, and the local `ID终版/` source-data folder.
- Replaced real-looking phone/privacy-number fixtures in tests and project memory with fixed dummy test numbers.
- Rechecked the accumulated workbench, validation, account-set, backend-auth, privacy-phone, and standalone skill changes before pushing.

Validation:
- `python tests\unit\test_ydz_customer_creation.py`
- `python tests\unit\test_ydz_create_customers_script.py`
- `python tests\unit\test_ops_console.py`
- `python tests\unit\test_chanjet_admin_privacy_phone.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q main.py scripts src skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests tests\unit`
- Known plaintext credential/JWT/Bearer scan returned no matches for the current user-provided secrets.

## 2026-06-11: packaged account-set skill

Changed:
- Added `agents/openai.yaml` to the standalone `skills\ydz-create-accountset` package metadata.
- Built a clean reusable skill archive excluding tests, `__pycache__`, and compiled Python files.

Package:
- `dist\ydz-create-accountset-20260611-130644.zip`
- SHA256: `E7B409D7401EA8201D165058D79534D66C209A9982CBE4EDB40895DE16A67A8F`

Validation:
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m py_compile skills\ydz-create-accountset\scripts\ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py`
- Package contents verified to include only `SKILL.md`, `_meta.json`, `agents`, `references`, and `scripts`.
- Package scan found no project-source imports, tests/cache files, or known plaintext credentials.

## 2026-06-11: account-set skill lazy Playwright dependency

Changed:
- Centralized Playwright loading in the standalone account-set skill behind `load_sync_playwright()`.
- API-only creation paths can avoid importing Playwright when token/password auth contexts are sufficient.
- Browser/CDP fallback now shows a focused install hint only when Playwright is missing.
- Updated standalone and installed skill docs to describe Playwright as optional and local Chrome CDP as the normal browser path.

Validation:
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m py_compile skills\ydz-create-accountset\scripts\ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py`

## 2026-06-11: account-set skill documentation cleanup

Changed:
- Updated the standalone account-set skill docs to describe CDP fallback ports and isolated fallback browser profiles.
- Updated troubleshooting guidance for the Playwright `--enable-automation` Chrome compatibility error.
- Synced installed `ydz-create-customer` skill references with the standalone skill, including API field mapping and troubleshooting docs.
- Removed generated `__pycache__` files from skill folders after validation.

Validation:
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m py_compile skills\ydz-create-accountset\scripts\ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py`

## 2026-06-11: account-set Chrome CDP fallback ports

Changed:
- Added a shared CDP connection helper for Yidaizhang account-set creation.
- Managed Chrome now starts with `--enable-automation` plus the existing automation-controlled flag.
- If the requested CDP port is occupied by a Chrome that Playwright rejects for missing automation flags, the flow retries on `9333`, `9444`, `9555`, and `9666`.
- Fallback ports use isolated port-suffixed browser profiles.
- Updated project login/create flows, standalone `skills\ydz-create-accountset`, and installed `C:\Users\Administrator\.codex\skills\ydz-create-customer`.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests tests\unit\test_ydz_create_customers_script.py`
- `python -m py_compile C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py`

Risk:
- If every candidate port is occupied or Chrome cannot launch, the flow still fails before account-set mutation and reports the CDP connection problem.

## 2026-06-11: public-manage backend API auth for account-set creation

Changed:
- Added public-manage backend token provider support.
- `ChanjetAdminTaskQuery` and privacy-phone sync can now run from backend header tokens without a public-manage browser page.
- Added `--backend-auth-mode auto|token|password|browser` to the project account-set script.
- Default backend auto mode tries token variables, then guarded public-manage password API login, then browser fallback.
- Synchronized the standalone `skills\ydz-create-accountset` package and installed `C:\Users\Administrator\.codex\skills\ydz-create-customer`.
- Updated skill docs for backend token variables and the password-login risk-control boundary.

Validation:
- `python tests\unit\test_chanjet_admin_auth.py`
- `python tests\unit\test_chanjet_admin_task_query.py`
- `python tests\unit\test_chanjet_admin_privacy_phone.py`
- `python tests\unit\test_ydz_create_customers_script.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py src\chanjet_admin skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests tests\unit\test_chanjet_admin_auth.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_chanjet_admin_privacy_phone.py tests\unit\test_ydz_create_customers_script.py`
- Live backend password API attempt returned `MANUAL_VERIFICATION_REQUIRED` / `访问拒绝`.
- Live SSO-derived token exchange queried backend tasks for `91110112MA7JR5JN75` without a browser context.

Risk:
- Backend password API login remains subject to SSO risk controls. Auto mode falls back to browser; strict password mode stops before mutation.

## 2026-06-11: live production account-set creation for 91410403MA45FH9B45

Ran:
- Created production Yidaizhang account set for tax number `91410403MA45FH9B45`.
- Source backend task id: `2077729249222326026`.
- Created customer id: `3583772421003683`.
- Customer name from backend: `平顶山市炭壹环保科技有限公司`.
- Area: `河南`.
- Login method: `DLYW-SDSRDX`.
- Assigned accountant resolved from login mobile: `60009603684`.

Result:
- Status `OK`, action `created`.
- Customer fields and dynamic tax-login fields both verified.
- Password auth still returned production `访问拒绝`, then the run succeeded by reusing the browser Yidaizhang/public-manage login state.

Changed during this run:
- Fixed a live backend-login bug where `ensure_backend_login()` referenced a missing `env` variable while filling the public-manage login form.
- Fixed the standalone skill browser-mode result header so `accountantId/accountantSource` columns line up with printed result values.
- Synced the fix into `skills\ydz-create-accountset` and installed `C:\Users\Administrator\.codex\skills\ydz-create-customer`.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m py_compile scripts\ydz_create_customers.py skills\ydz-create-accountset\scripts\ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py`

## 2026-06-11: production YDZ workbench app-entry recovery

Changed:
- Added production browser fallback that opens Chanjet workbench app list for the configured org id and clicks the primary `易代账` `进入应用` entry.
- The fallback now runs before direct `work.html` navigation when no active YDZ cloud page exists.
- Hardened app-entry matching for longer production rows that include purchase period, purchase state, and user-list controls.
- Synced the same behavior to `skills\ydz-create-accountset` and installed `C:\Users\Administrator\.codex\skills\ydz-create-customer`.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py src\ydz skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`
- `python -m py_compile C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py`
- Live non-mutating CDP smoke opened `https://cloud.chanjet.com/ydzee/u7anoc8y5p7p/49le0svcsa/work.html#/home/dataBoard`.

Risk:
- This does not bypass real production access denial, slider, SMS, or phone-binding challenges; it only recovers from an already-authenticated browser/workbench state.

## 2026-06-10: live production YDZ account-set creation smoke test

Ran:
- Created production Yidaizhang account set for tax number `91510108MACTKN8WXQ`.
- Target enterprise: `蓝天之爱的企业` / org id `90011827608`.
- Source backend task id: `2077729326532848172`.
- Created customer id: `3583003354864060`.
- Login method: `SDSRDX`.
- Assigned accountant resolved from login mobile: `60009603684`.

Result:
- Status `OK`, action `created`.
- Customer fields and dynamic tax-login fields both verified.
- No privacy-phone sync was run because `SDSRDX` is a phone/login-account method.

## 2026-06-10: YDZ account-set supports SDSRDX login methods

Changed:
- Added project support for `SDSRDX` and `DLYW-SDSRDX`.
- Backend-source task lookup now sends `loginType=YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX` while keeping `taskCategorys=2,3` and no tax-type restriction.
- Backend candidate selection now ignores rows without supported account-set login methods or required login fields.
- Dynamic tax-info save uses `cTaxPreparerName` as privacy number for `YSHDL/DLYW-YSHDL` and as phone/login account for `SDSRDX/DLYW-SDSRDX`.
- `DLYW-*` methods use `cSiteLoginName` for proxy company tax number.
- Integration privacy-phone sync now runs only for privacy-number methods.
- Workbench manual-accountset entry now shows the two manual captcha-code methods and labels the shared account input as privacy number/phone.
- Synced the same behavior into `skills\ydz-create-accountset` and the installed `C:\Users\Administrator\.codex\skills\ydz-create-customer` skill.

Validation:
- `python tests\unit\test_ydz_customer_creation.py`
- `python tests\unit\test_ops_console.py`
- `python tests\unit\test_chanjet_admin_task_query.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`

Risk:
- No live account set was created in this run; verification is limited to code paths, payload mapping, filtering, and docs.

## 2026-06-10: YDZ account-set accountant resolves from login phone

Changed:
- Account-set creation now queries `trans/easyacctg/employee/getChildEmpListByUserId` before create/update.
- The resolver matches the Yidaizhang login phone to employee row `mobile` and uses row `userId` as `accountantEmployeeId`.
- Admin-only rows are filtered out; fallback order is current Yidaizhang `userId`, then the packaged environment default.
- Result output now includes `accountantId` and `accountantSource`.
- Saved customer verification checks the resolved accountant id.
- Synced the same logic into the standalone `skills\ydz-create-accountset` CLI and docs.

Validation:
- `python tests\unit\test_ydz_customer_creation.py`
- `python tests\unit\test_ydz_create_customers_script.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py src\ydz skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`

Risk:
- The interface name and row shape were verified from real Yidaizhang frontend assets. This run did not fetch a live authenticated employee-list response because no usable Yidaizhang token context was present in the shell.

## 2026-06-10: YDZ integration captcha login can use accountVerify

Changed:
- Added integration captcha support to the Yidaizhang password-auth client.
- Password auth now calls `loginV2/accountVerify` with the captcha code to obtain `verifyToken`, then calls `loginV2/accountLogin`.
- Integration defaults the captcha code to `666666`; production has no default captcha code.
- Browser fallback form filling also passes the configured captcha value when a captcha input is visible.
- Synced the same behavior into the standalone `skills\ydz-create-accountset` CLI.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- Direct function-call verification for `tests\unit\test_ydz_password_auth.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py src\ydz skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`

Risk:
- This uses the normal frontend captcha API and does not solve slider, SMS, phone binding, or password-change challenges.
- If password auth succeeds but does not expose Yidaizhang business tokens, `auto` still falls back to browser mode.

## 2026-06-10: CIT A is optional in workbench coverage

Changed:
- Restored the Enterprise Income Tax A-class coverage checkbox in the workbench.
- The checkbox is unchecked by default, so small-period default runs still exclude `CIT_A`.
- If an operator explicitly checks Enterprise Income Tax A-class, the workbench sends `CIT_A` in `--coverage-tax-types` and the existing CIT A coverage path is used.
- CIT A source controls remain hidden from the workbench page: no work.html URL field, no other-enterprise scan checkbox, and no account-set precheck button.

Validation:
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py`

## 2026-06-10: completed-with-differences reports stay in the tax matrix

Changed:
- Batch summary loading no longer drops completed backend-supplement reports just because another clean sample covers the same target.
- Tasks with `verifyStatus=completed_with_differences` now remain in the tax-number/form matrix and contribute their field differences to problem details.
- Failed or skipped tasks without completed form reports are still excluded from the tax-number/form matrix.

Validation:
- `python tests\unit\test_batch_summary_rendering.py`
- `python -m compileall -q main.py scripts src`

Observed result:
- Tax number `91110111MA01TFJN6C` now appears in the latest run's matrix with its culture-fee form result and differences.

## 2026-06-10: workbench small-period result display cleanup

Changed:
- Batch summary tax-number/form matrix now shows only items that produced completed form report results; collection/login/manual items without form results are kept out of that matrix.
- Unfiled declaration status is now styled as a normal state instead of a warning state.
- CBJ display remains status-independent: personal CBJ shows as collected and annual-settlement CBJ shows as verified, even if source records contain unknown or unfiled-like text.
- Coverage explanation table no longer shows backend tax ID/filter columns.
- Workbench small-period coverage entry no longer defaults to CIT A and no longer shows CIT A work.html source, enterprise scan, or account-set precheck controls.

Validation:
- `python tests\unit\test_batch_summary_rendering.py`
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q main.py scripts src`

Risk:
- CIT A backend/server-side helper functions remain available for future large-period or historical-run use, but the current workbench UI only exposes normal coverage selection by default, not source-discovery controls.

## 2026-06-10: YDZ account-set default auth is password-first auto

Changed:
- Changed account-set auth default from `browser` to `auto` in `scripts\ydz_create_customers.py`.
- `auto` now tries guarded password auth first, then falls back to browser login when no usable Yidaizhang token context is produced.
- Added `auto` as an explicit `--ydz-auth-mode` choice in the project script and standalone skill CLI.
- Updated the workbench Yidaizhang auth selector: blank/default now means `自动（账号密码优先）`, and explicit `browser` remains available.
- Synced the same default behavior into `skills\ydz-create-accountset\scripts\ydz_accountset_cli.py`.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- `python tests\unit\test_ops_console.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m py_compile scripts\ydz_create_customers.py scripts\ops_console.py skills\ydz-create-accountset\scripts\ydz_accountset_cli.py`

Observed result:
- Default create/login preparation prefers password auth without making password-auth blockers fatal.
- Forced `--ydz-auth-mode password` remains strict.

## 2026-06-10: Standalone YDZ account-set skill can use manual source fields

Changed:
- Added `create --manual-source-env` to `skills\ydz-create-accountset\scripts\ydz_accountset_cli.py`.
- Added `ManualSourceResolver` and `manual_source_from_env()` inside the standalone skill.
- Manual mode reads `YDZ_MANUAL_*` customer/tax-login fields, adds `YDZ_MANUAL_TAX_NO` to the input tax-number list, skips public-manage lookup, and skips integration privacy-phone sync.
- Added `--skip-privacy-phone-sync` to the skill CLI.
- Updated `SKILL.md`, `references\config-and-secrets.md`, and `references\workflow.md`.

Validation:
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m py_compile skills\ydz-create-accountset\scripts\ydz_accountset_cli.py`

Observed result:
- The standalone skill now supports creating/updating account sets from user-provided login information.
- It still requires valid Yidaizhang auth through browser, token, or guarded password-auth mode.
- No public-manage backend login is required for manual-source mode.

## 2026-06-10: YDZ account-set creation can try guarded password auth

Changed:
- Added `src\ydz\password_auth.py` for normal Chanjet account-password login attempts, including RSA password encryption, CIA auth-code retrieval, account-login submission, response classification, and token-context extraction.
- Added `--ydz-auth-mode password` to `scripts\ydz_create_customers.py`.
- Added the `password` auth mode to the local workbench account-set forms and command validation.
- Synced equivalent self-contained logic into `skills\ydz-create-accountset\scripts\ydz_accountset_cli.py`.
- Updated project docs and standalone skill references with usage and boundaries.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- `python tests\unit\test_ops_console.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- Direct function-call verification for `tests\unit\test_ydz_password_auth.py` because pytest is not installed locally.
- `python -m compileall -q main.py scripts src skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`

Observed result:
- Password mode proceeds only if it can produce the same Yidaizhang API token context required by token mode.
- Slider/CAPTCHA, SMS, phone binding, password-change, and SSO-without-business-token cases are reported before any customer mutation.
- Browser mode remains the default reliable path.

## 2026-06-10: YDZ account-set API can use token auth context

Changed:
- Added a `YdzAuthContext` path so Yidaizhang customer/account-set API calls can use a supplied `work.html` URL, `iframeToken`, `ciaToken`, org id, and user id instead of reading those values from a browser page.
- Added `--ydz-auth-mode token` to `scripts\ydz_create_customers.py`.
- Manual-source account-set creation can now run in token mode without launching Chrome when all source fields are supplied through `YDZ_MANUAL_*` and privacy-phone sync is skipped.
- Backend-source account-set creation can use token mode for Yidaizhang API calls, but still needs a public-manage browser session for backend source lookup and integration privacy-phone preparation.
- Synced the same token-auth capability into the standalone `skills/ydz-create-accountset/` CLI without importing project modules.
- Added non-sensitive workbench command wiring for `accountsetYdzAuthMode`; tokens still must come from environment variables or an env file and are not placed in job commands.
- Documented token-auth variables and boundaries in project docs and the standalone skill docs.

Validation:
- `python tests\unit\test_ydz_customer_creation.py`
- `python tests\unit\test_ydz_create_customers_script.py`
- `python tests\unit\test_ops_console.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q main.py scripts src skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`

Observed result:
- Browser mode remains available as the fallback path.
- Token mode is an API-context reuse path, not a password-login or CAPTCHA bypass.
- Direct password-to-token login remains a separate discovery item because the current verified customer workflow depends on tokens already issued by Yidaizhang.

## 2026-06-10: Standard supplement uses historical backend candidates with bounded retry

Changed:
- Removed the default fresh-Yidaizhang task generation path for standard supplement targets.
- Standard targets now verify historical public-manage backend candidates directly through the normal `main.py --task-id` path.
- The configured supplement candidate limit is honored directly; the workbench/default remains 3 candidates per missing target.
- If one historical candidate fails at tax-bureau login readiness, the attempt keeps its normal category such as `tax_login_expired` or `tax_login_blocked`, then the supplement loop tries the next backend candidate/tax number.
- If a later historical candidate covers the target, the supplement phase returns success for that target even though earlier candidates failed.
- If all configured historical candidates fail, the target remains failed with the recorded attempt reasons instead of hiding the result behind a fresh-task regeneration state.
- The backend candidate picker now prefers distinct tax numbers for the same missing target before using additional taskIds from an already selected tax number; this applies both inside one backend query and when merging candidates across search windows.
- `getClientJob failed: ...`, incomplete metadata, unresolved inner taskId/province metadata, non-object `getClientJob` responses, and exhausted `getClientJob` retries are now classified as tax-bureau login readiness failures instead of generic verification failures.
- Workbench direct failure text now also normalizes unresolved task-cookie/client-job province metadata instead of showing the raw `ValueError`.
- Standard supplement now performs a lightweight login preflight before full form verification: it checks `getClientJob` metadata and one `getTaskCookie` read, drops definitively not-ready backend candidates, and keeps unknown candidates when the preflight page itself is unavailable.
- To avoid preflight drops consuming the operator's 3 verification attempts, standard supplement searches a bounded raw pool of up to 3x the configured candidate limit, then groups only the login-ready/unknown candidates back down to the configured limit.
- If the first preflight pass drops a target below the final candidate limit, the same run now performs up to 3 bounded backend refill searches with those not-ready taskIds excluded, preflights the refill candidates, and merges the ready/unknown refill candidates before verification.
- Refill searches now also temporarily exclude taskIds already seen in the current run, including ready/unknown preflight candidates, so the refill pool is not spent on duplicate backend rows. Only definitive `not_ready` taskIds are persisted for later runs.
- Preflight `not_ready` records are now persisted as stable supplement exclusions, so a taskId already proven not login-ready is not selected again in the next supplement run.
- Removed the workbench fresh retry count field and the `--coverage-supplement-fresh-retry-waves` command wiring.
- Kept CIT A's explicit source-readiness/fresh-refresh tools unchanged because they are outside the current standard-target robustness scope.
- Fixed Windows process detection in the workbench to use the Windows process API before falling back to `tasklist`, so tests and job monitoring do not depend on `tasklist` permissions.

Validation:
- `python tests\unit\test_coverage_framework.py`
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_task_login_flow.py`
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q main.py scripts src`

Observed result:
- Future standard supplement runs no longer require an existing YDZ account set to produce a fresh task before validation.
- Historical backend candidates are tried up to the configured limit, with different tax numbers preferred and per-candidate failure reasons preserved for the operator.
- Candidates whose `getClientJob` response fails or lacks usable tax-login metadata are now excluded from future supplement candidate reuse like other stable tax-login blockers.
- Definitively expired/not-ready login candidates can now be filtered before full verification, reducing tax-login failures shown as actual verification attempts.
- A single supplement run can now continue past expired early preflight pools and try later backend history without waiting for a second operator-triggered run.
- Refill searches are less likely to be blocked by duplicate ready/unknown rows from the first preflight pass.
- Re-running supplement after a preflight-only filter now skips those filtered taskIds and broadens to other backend candidates instead of revisiting the same stale login source.
- The broader robustness goal remains active: the code path is aligned with the requested fallback model, but live proof across newly selected supported tasks is still needed before completion.

## 2026-06-10: New-task tax-login fast fail and real verification preserved

Changed:
- Kept backend supplement candidates on the normal `main.py --task-id` verification path. The runner does not reuse previous successful reports or historical taskIds as "stable priority" evidence for new tasks.
- Bounded tax-login readiness waits so a new backend task cannot stay indefinitely at `getClientJob`, `getTaskCookie`, `/loading`, `tpass.*#/login`, or tax authorization-code pages.
- Added `TaxLoginNotReadyError` for tax-bureau login/authentication pages that stay unusable, and normalized it as a tax-login readiness blocker instead of a field-comparison failure.
- Classified English same-province switch-limit messages as `tax_login_blocked`, not generic cookie expiry.

Validation:
- `python tests\unit\test_task_login_flow.py`
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q main.py scripts src tests\unit\test_task_login_flow.py tests\unit\test_batch_handling_info.py`
- Confirmed there is no `preverified` / `verified_history` / previous-success reuse path in `scripts`, `src`, or `tests`.

Observed result:
- New candidates still enter real tax-bureau verification.
- If verification reaches the forms and fields differ, the result remains visible as a mismatch/difference.
- If the browser is stuck at tax-login readiness, the attempt now exits with a classified login blocker and the batch can move to the next candidate.

## 2026-06-10: Current batch accepted with CIT A deferred

Changed:
- Refreshed `output\batch_runs\codex_full_20260609_204530` after the user explicitly deferred Enterprise Income Tax A-class coverage for this round.
- The active coverage scope now excludes `CIT_A` and consumption tax, keeping `VAT_GENERAL`, `VAT_SMALL`, `CULTURE_FEE`, `CBJ_PERSONAL`, and `CBJ_ANNUAL`.

Validation:
- Refreshed the batch summary with `scripts\batch_collect_verify.py --coverage-supplement-only --coverage-tax-types VAT_GENERAL,VAT_SMALL,CULTURE_FEE,CBJ_PERSONAL,CBJ_ANNUAL`.
- `coverage_matrix.csv` shows all 8 in-scope targets covered.
- `coverage_missing.csv` has 0 rows.
- `batch_problem_details.csv` has 0 rows.

Observed result:
- The current round is clean for the agreed scope.
- `CIT_A:filed` and `CIT_A:unfiled` remain source-readiness work for a later round, requiring a usable CIT A YDZ work source or account set.

## 2026-06-10: CIT A YDZ no-need source classification

Changed:
- Added a dedicated `ydz_no_need_collect` source-readiness status for CIT A fresh YDZ refresh.
- When Yidaizhang accepts a fresh collect request but returns `NO_NEED_COLLECTED`, the coverage gap now reports that no verifiable taskId was produced because the account is no-need for the period.
- The next action now points operators to change the candidate tax number or period instead of treating the result as a generic missing fresh source.
- The classification now relies on `collectStatus=NO_NEED_COLLECTED` even when the backend reason is empty, and candidate-refresh diagnostics persist `collectStatus`, warnings, errors, and tax-item snippets.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_ydz_collector.py`
- `python -m compileall -q main.py scripts src`

Observed result:
- The authoritative batch remains `8/10`; `CIT_A:filed` and `CIT_A:unfiled` still require usable CIT A source samples.
- This change improves source-blocker diagnosis and avoids spending operator time on account sets that YDZ itself says have no declaration/collection need for the period.

## 2026-06-10: CIT A account-set source precheck entry

Changed:
- Added a workbench action for CIT A account-set source precheck.
- The action extracts only the current missing CIT A representative candidates from an existing batch state and runs the existing account-set script with `--dry-run`.
- Candidate tax numbers are written to the normal run input file; credentials remain child-process environment values and are not exposed in the displayed command.

Validation:
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py`
- Built a dry-run precheck command from `output\batch_runs\codex_full_20260609_204530`.

Observed result:
- The current batch yields two precheck candidates: `91500105MAEQ3URL80` for `CIT_A:filed` and `91310115MA1HAHW684` for `CIT_A:unfiled`.
- The generated command includes `--dry-run`; no customer or account set is created by this precheck step.

## 2026-06-10: CIT A supplement retry with open-tab scan enabled

Changed:
- Tightened open YDZ work-tab exclusion to compare the base `work.html` URL, so current-enterprise tabs with different hash routes are not treated as distinct source candidates.
- Updated source-readiness next action for unavailable enterprise scans to mention either providing a work URL or manually opening a target work tab.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q scripts\batch_collect_verify.py src\ydz\session.py tests\unit\test_batch_handling_info.py`
- Live target-scoped supplement retry on `output\batch_runs\codex_full_20260609_204530`.

Observed result:
- The live retry found `2063992990329483939` for `CIT_A:unfiled`, but verification failed at `getTaskCookie` because the tax login connection had expired before any CIT A form was reached.
- `CIT_A:filed` remains without a clean filed source.
- `batch_problem_details.csv` remains header-only; no parser or field-comparison issue is evidenced.

## 2026-06-10: CIT A open YDZ work-tab source scan

Changed:
- Added `YdzSession.ready_open_work_pages()` to collect already-open YDZ `work.html` tabs that are ready for batch declaration API calls.
- CIT A supplement enterprise scanning now checks ready open work tabs before automatic workbench enterprise switching.
- Open-tab source records are included in source-readiness diagnostics and can feed the existing fresh YDZ collection path.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q scripts\batch_collect_verify.py src\ydz\session.py tests\unit\test_batch_handling_info.py`

Observed result:
- The runner can now reuse a manually opened CIT A-ready YDZ work tab without requiring the operator to copy the full URL.
- The authoritative batch remains at `8/10` until a ready tab, explicit URL, or account set with CIT A signals is available.

## 2026-06-10: workbench CIT A work URL input

Changed:
- Added an optional CIT A YDZ `work.html` URL input to the workbench batch verification form.
- Workbench batch and existing-run retry commands now enable CIT A fresh refresh when that field is supplied.
- The raw URL is passed only through `YDZ_SUPPLEMENT_WORK_URLS` in the child environment; it is not added to the displayed command.

Validation:
- `python tests\unit\test_ops_console.py`
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py`
- `python -m compileall -q scripts\batch_collect_verify.py src\ydz\session.py tests\unit\test_batch_handling_info.py`

Observed result:
- The workbench can now launch the explicit CIT A source path implemented in the batch runner.
- The current batch still needs a real CIT A-ready work URL/account set before the remaining two CIT A coverage targets can be verified.

## 2026-06-10: CIT A explicit YDZ work URL source path

Changed:
- Added `YdzSession.open_work_url()` to open a supplied YDZ cloud `work.html` URL, reach batch declaration, and require API token readiness.
- Supported both production and integration YDZ cloud hosts when recognizing `work.html` pages.
- Added `--coverage-supplement-ydz-work-url` and `YDZ_SUPPLEMENT_WORK_URLS` to CIT A supplement refresh.
- Explicit work URLs are scanned for CIT A account-row signals and can reuse the existing fresh YDZ collection plus backend taskId resolution path.
- Source-readiness diagnostics include explicit work URL scan records and store only redacted labels.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q scripts\batch_collect_verify.py src\ydz\session.py tests\unit\test_batch_handling_info.py`

Observed result:
- The code path is ready for a supplied active CIT A `work.html` source.
- The current authoritative batch still needs a real CIT A-ready source before the remaining `CIT_A:filed` and `CIT_A:unfiled` targets can be completed.

## 2026-06-10: CIT A blocker decision captured

Changed:
- Added the decision record that authenticated Yidaizhang workbench recovery is only login readiness, not CIT A source readiness.
- Clarified that an active Yidaizhang `work.html` entry plus a CIT A account-row signal is required before fresh CIT A collection should be submitted.

Validation:
- Recomputed source readiness in-memory from `output\batch_runs\codex_full_20260609_204530\state.json` using the current classification code.

Observed result:
- Current code classifies both `CIT_A:filed` and `CIT_A:unfiled` as `other_enterprise_scan_unavailable` from the saved scan records.
- Coverage remains source-blocked at `8/10`; no parser or field mismatch evidence exists in `batch_problem_details.csv`.

## 2026-06-10: CIT A YDZ workbench recovery and enterprise-source triage

Changed:
- Hardened `YdzSession.ensure_ready()` and `refresh_login_state()` so authenticated Yidaizhang landing/redirect pages without login inputs try the known workbench URL before falling back to password login.
- Added workbench-based enterprise discovery through `workbench.chanjet.com/v2/home` and its `切换企业` dialog.
- Corrected source-readiness classification for English `Yidaizhang login token is missing` failures and for other-enterprise app-entry failures.
- Other-enterprise scan now treats `蓝天之爱` and `蓝天之爱的企业` as the same current enterprise.

Validation:
- `python tests\unit\test_ydz_collector.py`
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q src\ydz\session.py scripts\batch_collect_verify.py scripts\ops_console.py tests\unit\test_batch_handling_info.py tests\unit\test_ydz_collector.py tests\unit\test_ops_console.py`
- Live target-scoped CIT A supplement retry on `output\batch_runs\codex_full_20260609_204530` with YDZ credentials, fresh refresh, and enterprise scanning.
- Live probe confirmed `list_enterprises()` reads 10 enterprises from the workbench switch dialog.

Observed result:
- Coverage remains `8/10`; missing targets remain `CIT_A:filed` and `CIT_A:unfiled`.
- `batch_problem_details.csv` remains header-only; no mismatch, web-missing, parser, or mapping defect is evidenced.
- The previous YDZ token/login-input blocker is fixed: current-enterprise account scan now reaches YDZ API and scans 144 account rows.
- Current enterprise has `citSignalCount=0`.
- Other selectable enterprises are visible, but the sampled target enterprise workbench pages did not expose an automatic YDZ cloud workbench entry; expired/unavailable YDZ apps must be handled by providing a valid `work.html` URL, switching to an enterprise with an active YDZ app, or creating/importing CIT A account sets.

## 2026-06-10: CIT A YDZ token blocker classification and workbench scan option

Changed:
- Hardened Yidaizhang authenticated-entry handling so existing cloud workbench tabs no longer count as a successful enterprise-selector open.
- Enterprise switching now ignores pre-existing cloud pages while waiting for a newly opened or navigated workbench page.
- Added a workbench checkbox that passes `--coverage-supplement-refresh-cit-from-ydz` and `--coverage-supplement-scan-ydz-enterprises` to the batch runner.
- Classified Yidaizhang `http=701 / token 不能为空` refresh failures as `ydz_login_required` in `coverageSupplement.sourceReadiness`.
- Batch tax-number input parsing now strips UTF-8 BOM from both command arguments and input files.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q scripts\batch_collect_verify.py scripts\ops_console.py src\ydz\session.py tests\unit\test_batch_handling_info.py tests\unit\test_ops_console.py`
- Live target-scoped CIT A supplement retry on `output\batch_runs\codex_full_20260609_204530`.
- `python scripts\coverage_check.py --run-dir output\batch_runs\codex_full_20260609_204530`

Observed result:
- Coverage remains `8/10`; missing targets remain `CIT_A:filed` and `CIT_A:unfiled`.
- `batch_problem_details.csv` is still header-only, so no mismatch, web-missing, parser, or mapping defect is currently evidenced.
- Current source blocker is Yidaizhang fresh-refresh auth: `/trans/easyacctg/query/getBatchList failed: http=701 ... token 不能为空`.
- `coverage_missing.csv` and `batch_summary.html` now tell the operator to refresh/provide Yidaizhang login state before retrying CIT A fresh collection.

## 2026-06-10: CIT A other-enterprise source scan diagnostics

Changed:
- Added Yidaizhang enterprise-list and enterprise-switch helpers for controlled source discovery.
- Added `--coverage-supplement-scan-ydz-enterprises`, `--coverage-supplement-ydz-enterprise-scan-limit`, and `--coverage-supplement-ydz-enterprise-names`.
- CIT A supplement can now read-only scan other selectable Yidaizhang enterprises for account rows whose batch-list data exposes a CIT A signal.
- Source readiness now distinguishes `other_enterprise_has_cit_signal` and `other_enterprise_scan_login_required`.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q main.py scripts src tests\unit\test_batch_handling_info.py`
- Live target-scoped CIT A supplement retry on `output\batch_runs\codex_full_20260609_204530` with other-enterprise scanning enabled.
- `python scripts\coverage_check.py --run-dir output\batch_runs\codex_full_20260609_204530`

Observed result:
- Coverage remains `8/10`; missing targets remain `CIT_A:filed` and `CIT_A:unfiled`.
- Current enterprise still scanned 144 account rows with `citSignalCount=0`.
- Other-enterprise scan could not open the enterprise selector because the current terminal has no `YDZ_USERNAME/YDZ_PASSWORD` and the reusable browser login state was insufficient.
- `coverage_missing.csv` now says the next action is to provide Yidaizhang credentials through the workbench or environment, then rerun the enterprise scan.
- `batch_problem_details.csv` remains empty; no mismatch, web-missing, parser, or mapping defect was produced.

## 2026-06-10: coverage supplement source-readiness diagnostics

Changed:
- Added `coverageSupplement.sourceReadiness` to summarize backend candidate availability, current-enterprise Yidaizhang refreshability, scanned account count, CIT A signal count, and operator next action per missing target.
- `batch_summary.html` now appends source-readiness context to failed supplement attempts and uses it directly when a gap has no verifiable candidate.
- `coverage_missing.csv` now prefers source-readiness text over generic backend diagnostics for missing targets.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_coverage_framework.py`
- `python -m compileall -q main.py scripts src tests\unit\test_batch_handling_info.py tests\unit\test_coverage_framework.py`
- Live targeted retry on `output\batch_runs\codex_full_20260609_204530` with `--coverage-supplement-refresh-cit-from-ydz`.
- `python scripts\coverage_check.py --run-dir output\batch_runs\codex_full_20260609_204530`

Observed result:
- Coverage remains `8/10`; missing targets remain `CIT_A:filed` and `CIT_A:unfiled`.
- The latest retry found backend candidates `2046902314731814672` and `2063992986034126352`, but both failed at expired tax-login state.
- `sourceReadiness` now records that the current Yidaizhang enterprise scanned 144 account rows for `202605` with `ydzCitSignalCount=0` for both CIT A targets.
- `coverage_missing.csv` now tells the operator to switch to an enterprise with CIT-ready account rows or create/import such account sets before retrying.
- `batch_problem_details.csv` remains header-only; no mismatch, web-missing, parser, or mapping defect was produced.

## 2026-06-10: CIT A fresh YDZ scan is current-period and signal-gated

Changed:
- Added paged current-enterprise account discovery through `YdzCollector.list_accounts()`.
- CIT A fresh supplement refresh can now scan the current Yidaizhang enterprise when backend candidate tax numbers are not present there.
- The current-enterprise scan is limited to the batch period and only submits accounts whose Yidaizhang batch row exposes a CIT signal. This avoids wasting time on expired historical periods and arbitrary non-CIT accounts.
- Fresh supplement polling is capped with a short dedicated timeout for representative-task discovery, instead of using the normal 600s collection wait.
- Fresh-refresh diagnostics now record current-enterprise account counts, CIT signal counts, and no-signal reasons under `coverageSupplement.freshYdzRefresh`.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_coverage_framework.py`
- `python -m compileall -q main.py scripts src tests\unit\test_batch_handling_info.py tests\unit\test_coverage_framework.py`
- Live targeted retry on `output\batch_runs\codex_full_20260609_204530` with `--coverage-supplement-refresh-cit-from-ydz`.

Observed result:
- Coverage remains `8/10`; `CIT_A:filed` and `CIT_A:unfiled` are still missing.
- Current enterprise `蓝天之爱` returned 144 account rows for period `202605`, but `citSignalCount=0`, so no fresh YDZ task was submitted.
- Historical backend fallback still failed only for tax-login expiry/source-entry issues. `batch_problem_details.csv` remains header-only, so there is still no parser mismatch or web-missing evidence.

## 2026-06-10: CIT A supplement can try fresh YDZ collection

Changed:
- Added `--coverage-supplement-refresh-cit-from-ydz` to `scripts/batch_collect_verify.py`. It is off by default and only affects CIT A supplement retries when explicitly provided.
- CIT A supplement refresh now checks whether each backend candidate tax number exists in the current Yidaizhang enterprise. If it does, the runner submits a fresh collection, resolves the new taskId, and tries that task before the historical backend task.
- Supplement candidate ordering now prefers fresh YDZ tasks, then exact declaration-status candidates, then unknown-status probes, then newest task time.
- Persisted fresh-refresh diagnostics under `coverageSupplement.freshYdzRefresh`.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_coverage_framework.py`
- `python -m compileall -q main.py scripts src tests\unit\test_batch_handling_info.py tests\unit\test_coverage_framework.py`
- `python scripts\coverage_check.py --run-dir output\batch_runs\codex_full_20260609_204530`
- Live retry with `--coverage-supplement-refresh-cit-from-ydz` on `codex_full_20260609_204530`.

Observed result:
- Coverage remains `8/10`; missing targets remain `CIT_A:filed` and `CIT_A:unfiled`.
- All 10 checked CIT A backend candidate tax numbers were absent from the current Yidaizhang enterprise `蓝天之爱`, so no fresh taskId was created.
- Historical fallback verification produced no mismatch, no web-missing, and no parser evidence. Failures were tax-login expiry or source-state conflict.

## 2026-06-10: expanded CIT A supplement retry to 20 candidates

Changed:
- Reran the existing batch `output\batch_runs\codex_full_20260609_204530` with `--coverage-supplement-only` and target scope `CIT_A:filed,CIT_A:unfiled`.
- Expanded the CIT A search to a 540-day CIT lookback and `--coverage-supplement-max-candidates 10` for each target.
- The retry found additional CIT A unknown/filed-probe candidates and unfiled candidates, then verified only `cit_a_main` for those supplement tasks.

Validation:
- Live supplement command completed and rebuilt `batch_summary.html`.
- Coverage remains `8/10`; the remaining missing targets are still `CIT_A:filed` and `CIT_A:unfiled`.
- `batch_problem_details.csv` still has 0 problem rows, so the current run has no actionable mismatch or web-missing evidence.
- The 20 new supplement attempts failed as external/source issues: most were `tax_login_expired`; two Sichuan filed probes reached the declaration query page but no CIT A/A200000 row existed for the target period and were classified as source-state conflicts.

Risk:
- CIT A coverage is still blocked by source evidence, not by a confirmed parser defect. A usable filed sample must expose a CIT A/A200000 declaration query row for the target period, and a usable unfiled sample must expose a real A-class current-declare entry with valid tax-login state.

## 2026-06-10: added target-scoped supplement-only retry and faster CIT A hot-service triage

Changed:
- `scripts/batch_collect_verify.py` now supports `--coverage-supplement-only`, so an existing batch can run backend coverage supplement without re-verifying every original tax number first.
- Added `--coverage-supplement-targets`, for example `CIT_A:filed,CIT_A:unfiled`, to retry only selected missing coverage target keys without changing `coverageTaxTypes` or the global coverage matrix scope.
- Invalid `--coverage-supplement-targets` no longer falls back to a full supplement run; the run fails early with a structured `requestedTargetKeys` field.
- `scripts/compare_tax_forms.py` now rejects CIT A undeclared hot-service-only pages before entering the target-click loop or the fill-button polling loop. If the tax-bureau home page shows `本期应申报` as empty and only lists resident-enterprise CIT under hot services, the verifier reports the target entry as unavailable immediately.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_detail_form_switching.py`
- `python -m compileall -q main.py scripts src tests\unit\test_detail_form_switching.py tests\unit\test_batch_handling_info.py`
- Ran `--coverage-supplement-only --coverage-supplement-targets CIT_A:filed,CIT_A:unfiled` for `output\batch_runs\codex_full_20260609_204530`. Coverage remained `8/10`; global `coverageTaxTypes` stayed `['VAT_GENERAL', 'VAT_SMALL', 'CIT_A', 'CULTURE_FEE', 'CBJ_PERSONAL', 'CBJ_ANNUAL']`, and problem details stayed empty.
- Live rerun of CIT A unfiled task `2063992496406681785` now fails at the tax-home precheck in about 28s, instead of clicking the hot-service shortcut and waiting for the fill-button loop. The blocker remains external/source-state: no real CIT A current-declare entry exists on the page.

Risk:
- `CIT_A:filed` and `CIT_A:unfiled` remain uncovered. The latest retries found only unfiled candidates with tax-login expiry or hot-service-only/no-entry states; no field mismatch or web-missing evidence was produced.
- The new target-scoped supplement option is intended for controlled retries. Normal workbench/batch runs still use the full coverage scope unless the operator explicitly narrows supplement targets.

## 2026-06-10: cleaned current coverage run and tightened CIT A undeclared triage

Changed:
- `scripts/batch_collect_verify.py` now suppresses superseded backend-supplement difference reports when the same coverage target has a clean successful supplement candidate. This removes stale field-problem rows from `batch_problem_details.csv` without hiding ordinary batch-task mismatches.
- Verification stderr extraction now prefers final business exceptions such as `scripts.compare_tax_forms.DeclarationQueryAuthError` over earlier Playwright navigation-race stack lines.
- Supplement failure normalization now turns CIT A unavailable undeclared entries into a clear source/entry-state reason instead of leaving raw exception text.
- `scripts/compare_tax_forms.py` now treats CIT A undeclared home entries as valid only inside the current declare/todo scope, rejects B-class or deemed-assessment CIT entries, and avoids clicking hot-service-only CIT A shortcuts as if they were a real undeclared form entry.
- VAT small undeclared parsing fixes from this run handle split DOM rows and percent-suffixed surcharge rates; the successful task `2076981259194503123` now covers `VAT_SMALL:unfiled`.

Validation:
- `python tests\unit\test_detail_form_switching.py`
- `python tests\unit\test_batch_summary_rendering.py`
- `python tests\unit\test_vat_small_web_extraction_parsers.py`
- `python tests\unit\test_coverage_framework.py`
- `python -m compileall -q main.py scripts src tests\unit\test_batch_summary_rendering.py tests\unit\test_detail_form_switching.py tests\unit\test_vat_small_web_extraction_parsers.py`
- Rebuilt `output\batch_runs\codex_full_20260609_204530`: coverage is `8/10`, and `batch_problem_details.csv` contains only the header row.
- Live rerun for `2076981259194503123` completed VAT small undeclared main, appendix1, and appendix2 with no mismatches or web-missing fields.
- CIT A supplement retry scanned a 365-day CIT lookback for period `202605`; `CIT_A:filed` had no usable filed candidate, while eight `CIT_A:unfiled` candidates failed only for tax-login expiry or source/entry-state mismatch.

Risk:
- `CIT_A:filed` and `CIT_A:unfiled` remain uncovered in `codex_full_20260609_204530`; current evidence points to missing usable backend/tax-bureau source candidates, not field parser defects.
- The temporary targeted CIT supplement command rewrote the batch coverage selection to CIT only; the state was restored to the full selected coverage scope before rebuilding coverage.

## 2026-06-09: hardened coverage supplement success gating and broadened backend source search

Changed:
- Coverage analysis now counts only successful verification records (`status=success`, `returnCode=0`) as covered. Failed or timed-out tasks no longer satisfy coverage just because a partial report exists under `output/reports/<taskId>`.
- Backend supplement attempts now require both a covered matrix target and a clean current-candidate verification before marking an attempt as `covered`.
- Batch problem details now ignore partial reports from failed/skipped verification records; failed candidates remain visible in the supplement attempt list instead of producing stale field mismatch rows.
- Added `--coverage-supplement-lookback-days` so supplement search can include previous-month task creation windows without changing the default current-month behavior.
- Coverage supplement no longer filters backend task-list rows by `loginType=YSHDL,DLYW-YSHDL`; this previously hid valid CIT A and CBJ personal collect tasks.
- CIT A undeclared home-page matching now recognizes Jiangsu-style hot-service labels such as `居民企业（查账征收）企业所...`, and target status detection no longer inherits a previous VAT row's `已申报` status.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_batch_summary_rendering.py`
- `python tests\unit\test_coverage_framework.py`
- `python tests\unit\test_detail_form_switching.py`
- `python -m compileall -q main.py scripts src`
- Rebuilt coverage for `output\batch_runs\codex_full_20260609_172724`: failed partial reports no longer mark `VAT_GENERAL:unfiled` as covered.
- Reran backend supplement for `codex_full_20260609_172724`: `VAT_GENERAL:unfiled` was covered by task `2077729274992279442`; `CBJ_PERSONAL:any` was covered by task `2077729713080388191`.
- Current `batch_problem_details.csv` has 0 rows after excluding failed-candidate partial reports.

Risk:
- `VAT_SMALL:unfiled` and `CULTURE_FEE:unfiled` still need usable representative tasks; current candidates are blocked by live tax-bureau already-declared or missing-entry states.
- `CIT_A:unfiled` now finds backend candidates, but the tested Jiangsu tax page keeps returning to the portal without an editable CIT form entry.
- `CIT_A:filed` was not found in the broadened successful collect-task search; all returned CIT A candidates were parsed as unfiled.

## 2026-06-09: fixed VAT general appendix1 API fallback and Yunnan undeclared navigation classification

Changed:
- `scripts/compare_tax_forms.py` now applies a narrow API fallback for VAT general appendix1 `hjxse_6`: when the appendix API value is empty/zero, the verifier uses the VAT general main current-period immediate-refund sales value (`asysljsxse_jzjtxm_bys`, then `yshwxse_jzjtxm_bys`) before comparing.
- VAT general undeclared main-form retained-tax cumulative fields now subtract the current-period value for `sqldse_ybxm_bnlj` and `qmldse_ybxm_bnlj`, matching the backend cumulative-minus-current-period convention observed in Shanghai undeclared evidence.
- Tax-home undeclared entry clicks now tolerate repeated `Execution context was destroyed` navigation interruptions and continue classification from the current page instead of surfacing the raw Playwright exception.
- Yunnan `/mhzx/api/mh/tpass/code` authorization-code error pages are classified as tax-bureau auth/session failures, not as missing tax-form fields.
- Backend coverage supplement now honors `--coverage-supplement-max-candidates` instead of hard-capping each missing target at one candidate.

Validation:
- `python tests\unit\test_vat_main_web_value_rules.py`
- `python tests\unit\test_detail_form_switching.py`
- `python tests\unit\test_coverage_framework.py`
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q main.py scripts src`
- Live rerun: `python main.py --task-id 2077729644358679384 --targets vat_general_appendix1 --log-level INFO` completed with `total=134 match=134 mismatch=0 web_missing=0`.
- Batch rerun for `9111011457522550X2` in `codex_full_20260609_172724` completed successfully and updated the batch summary.
- Evidence replay for Shanghai undeclared task `2077729330827119155` reused the captured web values from `vat_general_main_compare_2077729330827119155_20260609_183407.json`; after the retained-tax rule, `compare_target()` reports `total=158 match=158 mismatch=0`.
- Multi-candidate supplement rerun for `codex_full_20260609_172724` tried 9 candidates with `maxCandidatesPerTarget=3`.
- Live rerun for Yunnan culture-fee unfiled task `2077729644358674126` no longer fails with raw navigation-context errors; the current blocker is an external state issue where the tax-bureau home page does not list the culture-fee undeclared entry.

Risk:
- The VAT appendix1 fallback is intentionally limited to `hjxse_6`; other appendix fields still require explicit evidence before aliasing to main-form fields.
- The Shanghai undeclared retained-tax fix was verified by replaying previously captured tax-page evidence because the live tax-bureau page now reports the same period as already declared.
- Yunnan culture-fee unfiled coverage still needs another representative task or manual tax-bureau state correction because the current tax-bureau home page has no target undeclared entry.

## 2026-06-09: bounded verification recovery and kept all selected tax forms visible

Changed:
- `scripts/compare_tax_forms.py` now keeps every form registered for a selected tax type in the verification output, even when one form has zero comparable API fields. Such reports are marked with `not_comparable=true` and `not_comparable_reason=api_no_comparable_fields` instead of disappearing from coverage output.
- Auto target selection now keeps all registered forms for selected VAT, culture fee, and consumption tax groups once that tax type is detected.
- Added a 60-second budget around expensive web extraction recovery loops, with clearer logs for recovery attempts and remaining missing fields.
- Added tax-home status detection for undeclared navigation. If the target row is already declared, the flow quickly falls back to declared-query mode when backend status is unknown, or reports a status conflict when backend status says unfiled.
- `scripts/batch_collect_verify.py` now has `--verify-timeout` and applies a bounded default per `main.py` subprocess. Final verification also marks no-taskId items as `task_unresolved/manual` instead of leaving them `running`.
- `src/login/task_login_flow.py` now fast-fails repeated pending tax-login locks when the same occupying taskId is returned three times, and the pending detector recognizes both normal Chinese and common mojibake messages.

Validation:
- `python tests\unit\test_web_extraction_recovery.py`
- `python tests\unit\test_detail_form_switching.py`
- `python tests\unit\test_consumption_tax_support.py`
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_task_login_flow.py`
- `python -m compileall -q main.py scripts src`
- `python main.py --task-id 2077729270697418910 --targets consumption_tax_main,consumption_tax_surcharge --skip-browser --log-level INFO`
- Live browser rerun: `python main.py --task-id 2077729644359026066 --targets culture_fee_main,culture_fee_deduction --log-level INFO` kept the zero-API culture fee deduction target and then failed with the expected already-declared/status-conflict reason from the tax-bureau home page.
- Live browser rerun: `python main.py --task-id 2077729270697418910 --targets consumption_tax_main,consumption_tax_surcharge --log-level INFO` completed both consumption-tax forms with 29/29 matches for each form.

Risk:
- The 60-second recovery budget may leave hard-to-render fields as `web_missing` instead of waiting indefinitely. This is intentional for batch stability, but some province-specific pages may still need dedicated parsers.
- Backend supplement task-list query parallelization was intentionally not implemented in this pass because the current query object shares browser-derived login/token state. It should be split into independent request clients before parallel execution.
- Real tax-bureau verification still depends on current external login state and task locks; the successful live rerun covers the current Shaanxi consumption-tax path, not every province-specific page.

## 2026-06-09: fixed VAT small appendix2 refund amount web parsing

Changed:
- Fixed small VAT appendix2 text parsing for the `bqybtse_*` refund amount column by mapping it to the ninth numeric value in each surcharge row.
- Added a regression parser case covering city construction tax, education surcharge, and local education surcharge refund amounts.

Validation:
- `python tests\unit\test_vat_small_web_extraction_parsers.py`
- `python -m compileall -q scripts\compare_tax_forms.py tests\unit\test_vat_small_web_extraction_parsers.py`
- `python -m compileall -q main.py scripts src`
- Live rerun: `python main.py --task-id 2077729738850235767 --targets vat_small_appendix2 --log-level INFO`
- Latest live report for task `2077729738850235767`: `vat_small_appendix2 complete: total=32 match=32 mismatch=0 api_missing=0 web_missing=0 match_rate=100.0%`.

## 2026-06-09: limited backend supplement verification to the active coverage target

Changed:
- Backend coverage supplement verification now narrows `main.py --targets` from `auto` to the active coverage target's form IDs when a supplement candidate is being tried.
- This prevents multi-tax backend tasks from verifying unrelated forms before the missing coverage target, such as a `CULTURE_FEE` supplement task running VAT general forms first.
- CBJ supplement tasks remain on the dedicated CBJ verification path and are not converted into `main.py` form targets.
- Final verification now also closes out items that reuse an existing skipped/failed/success result, avoiding stale `running` display when the batch process has already exited.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q scripts\batch_collect_verify.py tests\unit\test_batch_handling_info.py`
- Live monitoring of run `ops_20260609_152646` identified the prior waste/failure pattern: `CULTURE_FEE:filed` spent most time verifying VAT forms first, and `CULTURE_FEE:unfiled` failed on `vat_general_main` before reaching culture fee.

## 2026-06-09: fixed non-VAT coverage supplement backend tax filters

Changed:
- Audited public-manage task-list filters for CIT A, culture fee, consumption tax, and CBJ after the VAT `taxTypeId` issue.
- Changed CIT A, culture fee, and consumption tax coverage targets to use backend `taxId=2`, `taxId=3`, and `taxId=26` respectively instead of `taxTypeId`.
- Kept CBJ on `taxId=39`, which was already the reliable backend filter.
- Added regression coverage so non-VAT supplement planning sends `tax_id` and leaves `tax_type_id` empty.

Validation:
- `python tests\unit\test_coverage_framework.py`
- `python tests\unit\test_chanjet_admin_task_query.py`
- `python -m compileall -q src\coverage\registry.py src\coverage\supplement.py src\chanjet_admin\task_query.py tests\unit\test_coverage_framework.py tests\unit\test_chanjet_admin_task_query.py`
- Live backend checks confirmed `taxId=2/3/26/39` return CIT A, culture fee, consumption tax, and CBJ rows, while `taxTypeId` filters return mixed rows.

## 2026-06-09: fixed VAT small coverage supplement backend query

Changed:
- Changed VAT coverage supplement targets to query backend task list with `taxId=1` instead of `taxTypeId=1`.
- `find_collect_tasks_by_filters()` now sends backend `taskTypeId=3` for collect-task searches, while plain `query_tasks()` remains unchanged for account-set source lookup.
- Updated coverage tests so VAT normal/small targets use `taxId=1` plus taxpayer type.

Validation:
- `python tests\unit\test_chanjet_admin_task_query.py`
- `python tests\unit\test_coverage_framework.py`
- `python -m compileall -q src\chanjet_admin\task_query.py src\coverage\registry.py src\coverage\supplement.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_coverage_framework.py`
- Live backend supplement check for `VAT_SMALL:filed` returned task `2077729738850235767` with `parseStatus=filed`.

## 2026-06-09: fixed Tianjin unfiled VAT status-conflict handling

Changed:
- Hardened tax-home recovery for undeclared entries so Tianjin-style cards can click the target title first and then the actual action button.
- When backend task logs explicitly mark a target as unfiled but the tax bureau undeclared page reports the period is already declared, the verifier now stops with a clear status-conflict error instead of falling back to declared-query verification.

Validation:
- `python tests\unit\test_detail_form_switching.py`
- `python tests\unit\test_consumption_tax_support.py`
- `python -m compileall -q scripts\compare_tax_forms.py tests\unit\test_detail_form_switching.py tests\unit\test_consumption_tax_support.py`
- Live rerun of task `2077729648653721147` reached Tianjin VAT general undeclared page and failed with the expected conflict message: tax bureau says the period was already declared while backend current-period marker is `false`.

## 2026-06-09: repackaged standalone YDZ account-set skill

Changed:
- Rebuilt `skills/ydz-create-accountset.zip` from the standalone skill folder.
- Excluded Python runtime caches from the package so the archive only contains the skill instructions, references, CLI, tests, and metadata.

Validation:
- `$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\ydz-create-accountset`
- `python -m unittest skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- Sensitive-value scan found no embedded live passwords or Bearer tokens.

## 2026-06-09: added coverage supplement collect-status filter

Changed:
- Added `已取数` and `未取数` checkboxes under the workbench coverage range.
- Workbench batch commands now pass `--coverage-collect-statuses`.
- Batch state persists `coverageCollectStatuses`, and coverage status/supplement targets are generated from selected tax types plus selected collect statuses.
- Existing batches without saved collect-status filters still default to both statuses.

Validation:
- `python -m compileall -q scripts\ops_console.py scripts\batch_collect_verify.py src\coverage tests\unit\test_ops_console.py tests\unit\test_coverage_framework.py`
- `python tests\unit\test_ops_console.py`
- `python tests\unit\test_coverage_framework.py`
- Workbench page returned HTTP 200 and contains the new `coverageCollectStatuses` controls.

## 2026-06-09: optimized workbench layout display

Changed:
- Replaced the long stacked left-side operation forms with entry tabs for `取数验证`, `创建账套`, `手工创建`, `隐私号同步`, and `环境检查`.
- The selected operation tab is remembered in browser local storage.
- On desktop, the right-side status/result area is independently scrollable so current task logs and progress remain easy to inspect while switching operation forms.
- On narrow screens, forms collapse to one column and action buttons have stable responsive widths.

Validation:
- `python -m compileall -q scripts\ops_console.py`
- Visual checks captured with local Chrome at desktop, manual-tab, and narrow mobile widths.

## 2026-06-09: updated test-writing policy

Changed:
- Added a project rule to avoid writing large amounts of unit tests just for coverage.
- Future tests should be the minimum necessary for core business logic, boundary conditions, external payload assembly, high-risk cross-module behavior, and historical regressions.
- Simple CRUD, style-only changes, copy changes, and low-risk field pass-through should not get tests merely to improve coverage numbers.

Validation:
- Not run; documentation/rule-only update.

## 2026-06-09: added manual-source account-set creation entry to the workbench

Changed:
- Added a `手工创建账套` workbench form for cases where the operator already has customer name, region, login method, privacy number, proxy tax number, and personal password.
- The manual entry wraps `scripts/ydz_create_customers.py` with `--manual-source-env --skip-privacy-phone-sync`; customer login fields are passed only through child-process environment variables.
- Manual-source runs open/login only Yidaizhang and deliberately skip public-manage backend page operations, backend task lookup, and integration privacy-number synchronization/preparation.
- Added a reusable `ManualCustomerSourceResolver` and shared login-method/source validation for backend and manual sources.

Validation:
- `python -m compileall -q main.py scripts src tests\unit\test_ydz_customer_creation.py tests\unit\test_ydz_create_customers_script.py tests\unit\test_ops_console.py`
- `python tests\unit\test_ydz_customer_creation.py`
- `python tests\unit\test_ydz_create_customers_script.py`
- `python tests\unit\test_ops_console.py`

## 2026-06-09: account-set slider handoff is now visible and recoverable in the workbench

Changed:
- Yidaizhang account-set creation now logs whether it is reusing an existing Chrome CDP/browser session or launching a new browser with `--disable-blink-features=AutomationControlled`.
- When password login triggers the Yidaizhang slider, the script emits the stable marker `MANUAL_VERIFICATION_REQUIRED` and keeps waiting for a valid workbench session.
- The workbench parses that marker while the process is still running and immediately shows `需人工验证 / 等待易代账滑块` instead of looking like a generic long-running task.
- After the operator completes the slider in Chrome, the same script continues to wait for the workbench session and proceeds with backend login/source lookup and account-set creation.
- Workbench PID checks now use `tasklist` on Windows instead of `os.kill(pid, 0)`, avoiding signal-based process checks while refreshing job status.
- Synced the same marker and login-source logging into `skills/ydz-create-accountset` and the installed local `ydz-create-customer` skill copy.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- Selected account-set workbench status tests executed successfully; full `test_ops_console.py` is still blocked in this environment by an unrelated `openpyxl/numpy` import interruption in the export-review test.
- `python -m unittest discover -s skills\ydz-create-accountset\tests`
- `python -m compileall -q main.py scripts src skills\ydz-create-accountset\scripts\ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py`
- Skill validation passed for both the repository skill and the installed local skill.

## 2026-06-09: fixed account-set full-flow login handoff and backend source lookup

Changed:
- Account-set creation now handles the post-login Yidaizhang `passport.../vm/redirectVM` handoff page by clicking the visible entry when possible and then opening `work.html` directly if the handoff page does not navigate on its own.
- Public-manage backend source lookup now splits long lookback periods into windows of at most 39 days, matching the backend limit and avoiding `查询时间范围不能超过40天`.
- Tax-number file parsing now reads UTF-8 BOM files with `utf-8-sig` and strips any leading BOM from tax numbers.
- Synced these fixes to the standalone `skills/ydz-create-accountset` CLI and the installed local `ydz-create-customer` skill copy.

Validation:
- Unit/compile checks passed for account-set script, backend source resolver, workbench, public-manage task query, privacy-phone bridge, and the standalone skill tests.
- Live integration run `output/accountset_runs/accountset_inte_20260609_fullflow_fix/` for `91330YYJ3200684` reached backend source lookup and failed cleanly because no successful backend task with login info was found.
- Live integration run `output/accountset_runs/accountset_inte_20260609_fullflow_known_source/` for `91110112MA7JR5JN75` completed with `status=OK`, `action=existing`, backend task `2077729292172107486`, privacy-phone status `PULLED`, and verification passed.

## 2026-06-08: added Chrome AutomationControlled launch mitigation

Changed:
- Added `--disable-blink-features=AutomationControlled` to Chrome startup paths for Yidaizhang customer/account-set creation, Yidaizhang sessions, privacy-phone sync, the shared browser manager, and the Windows CDP startup script.
- Synced the same mitigation to `skills/ydz-create-accountset` and the installed local `ydz-create-customer` skill copy.
- Added regression checks that the project account-set script and portable skill include the launch flag.

Note:
- This may reduce slider frequency but does not guarantee bypassing Yidaizhang slider verification; manual slider handoff remains in place.

## 2026-06-08: fixed Yidaizhang login handoff for account-set creation

Changed:
- `scripts/ydz_create_customers.py` now detects the Yidaizhang slider challenge and treats it as a manual verification handoff instead of repeatedly submitting the same login form.
- The Yidaizhang login wait now preserves the login page, clicks the public-site `进入易代账` entry when available, and opens the workbench from a separate tab.
- After backend login finishes, account-set creation re-checks Yidaizhang readiness so a manually completed slider can be picked up before failing.
- Account-set creation no longer calls `browser.close()` on the shared Chrome CDP browser, preserving manual login state for subsequent workbench runs.
- Synced the same login handoff behavior to the standalone `skills/ydz-create-accountset` CLI and the installed local `ydz-create-customer` skill copy.

Root cause:
- The integration login page required slider verification, which the script cannot automatically complete.
- A later successful manual login could still be missed because the script did not re-check Yidaizhang after backend login and could close the shared browser at the end of a run.

Validation:
```powershell
python -m compileall -q scripts\ydz_create_customers.py tests\unit\test_ydz_create_customers_script.py
python tests\unit\test_ydz_create_customers_script.py
python tests\unit\test_ops_console.py
python -m unittest discover -s skills\ydz-create-accountset\tests
$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\ydz-create-accountset
$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\Administrator\.codex\skills\ydz-create-customer
```

## 2026-06-08: embedded backend login and completed integration privacy-phone preparation path

Changed:
- Removed the standalone `报税后台登录` form from the workbench main UI; backend login is now treated as an embedded prerequisite of account-set creation and privacy-number synchronization/preparation.
- The privacy-number sync script now defaults to ensuring the integration backend can query the privacy number: integration summary -> online copy when missing -> integration pull -> integration summary recheck.
- Workbench privacy-number results now treat `EXISTS` and `PULLED` as successful statuses and display integration summary counts.
- Backend task token selection now prefers a non-forbidden public-manage page with usable tokens, avoiding stale `403 / 无权访问` tabs.

Validation:
```powershell
python -m compileall -q src\chanjet_admin\task_query.py src\chanjet_admin\privacy_phone.py scripts\sync_privacy_phone.py scripts\ops_console.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_chanjet_admin_privacy_phone.py tests\unit\test_ops_console.py
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_chanjet_admin_privacy_phone.py
python tests\unit\test_ops_console.py
```

## 2026-06-08: suppressed Node deprecation warnings in workbench child jobs

Changed:
- `scripts/ops_console.py` now sets `NODE_NO_WARNINGS=1` for child processes launched by the workbench.
- This prevents Playwright's Node runtime `DEP0169 url.parse()` warning from appearing in operator task logs as if it were a business error.
- Privacy-number sync success/failure remains based on the script exit code and JSON result fields.

Observed:
- Workbench run `privacy_phone_20260608_155227` for `15500000003` completed successfully with `status=OK`, `summaryCount=1`, `detailCount=1`, and `copySuccess=true`; the visible `DEP0169` text was only a runtime warning.

Validation:
```powershell
python -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py
python tests\unit\test_ops_console.py
```

## 2026-06-08: added privacy-number preparation for integration account-set creation

Changed:
- Added `src/chanjet_admin/privacy_phone.py` for privacy-number summary/detail/copy/pull APIs.
- Integration account-set creation now checks integration privacy-number summary after resolving backend login info and before customer creation.
- If integration summary is empty, the flow copies privacy-number data in the online backend and then calls integration `pullPrivateDataByPrivatePhone`.
- Integration privacy-number endpoints omit the `token` header; live testing showed including `token` causes `用户身份证认证失败，请重新进行认证。`.
- Added a workbench `隐私号同步` job for the online privacy-number copy flow.
- Synced the same integration preparation behavior to the standalone `ydz-create-accountset` skill and installed local `ydz-create-customer` skill copy.

Observed:
- Live check with `15500000001` returned `EXISTS` from integration summary, so online copy and integration pull were not needed for that sample.
- Workbench was restarted and is listening on `127.0.0.1:8765`.

Validation:
```powershell
python -m compileall -q src\chanjet_admin\privacy_phone.py src\ydz\customer_creation.py scripts\sync_privacy_phone.py scripts\ydz_create_customers.py scripts\ops_console.py tests\unit\test_chanjet_admin_privacy_phone.py tests\unit\test_ydz_customer_creation.py tests\unit\test_ops_console.py
python tests\unit\test_chanjet_admin_privacy_phone.py
python tests\unit\test_ydz_customer_creation.py
python tests\unit\test_ops_console.py
python -m compileall -q skills\ydz-create-accountset\scripts\ydz_accountset_cli.py skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m unittest discover -s skills\ydz-create-accountset\tests
```

## 2026-06-08: retried YDZ readiness during login navigation

Changed:
- `src/ydz/customer_creation.py` now treats Playwright `Execution context was destroyed` during Yidaizhang readiness checks as a transient navigation state and keeps waiting.
- Synced the same retry behavior to the standalone `skills/ydz-create-accountset` CLI and installed local `ydz-create-customer` skill copy.
- Added regression coverage for retrying transient navigation context loss.

Observed:
- Current workbench job `accountset_inte_20260608_151349` had already failed before the fix with `Page.evaluate: Execution context was destroyed, most likely because of a navigation`.
- Workbench service remains listening on `127.0.0.1:8765`; Chrome CDP remains listening on `127.0.0.1:9222`.

Validation:
```powershell
python -m compileall -q src\ydz\customer_creation.py tests\unit\test_ydz_customer_creation.py skills\ydz-create-accountset\scripts\ydz_accountset_cli.py skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py
python tests\unit\test_ydz_customer_creation.py
python -m unittest discover -s skills\ydz-create-accountset\tests
```

## 2026-06-08: added standalone backend-login workbench task

Changed:
- `scripts/ops_console.py` now has a dedicated public-manage backend login form and `/api/login-backend` job endpoint.
- Backend login jobs run `scripts/ydz_create_customers.py --login-only --login-target backend`, reuse the selected Chrome CDP port, and write only sanitized readiness status under `output/backend_login_runs/<runId>/`.
- Temporary backend username/password/URL are passed only through the child process environment and are not written to display commands, job records, logs, or result JSON.
- `scripts/ydz_create_customers.py` can now run login-only without requiring tax numbers.
- Public-manage `403 / 无权访问` pages are detected as not logged in in both project code and the reusable account-set skill copies.
- Account-set creation now returns a per-tax-number `FAILED` result when backend login/source information cannot be found, instead of aborting the whole batch.

Validation:
```powershell
python -m compileall -q scripts\ydz_create_customers.py scripts\ops_console.py src\ydz\customer_creation.py tests\unit\test_ops_console.py tests\unit\test_ydz_create_customers_script.py tests\unit\test_ydz_customer_creation.py skills\ydz-create-accountset\scripts\ydz_accountset_cli.py skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py
python tests\unit\test_ydz_customer_creation.py
python tests\unit\test_ydz_create_customers_script.py
python tests\unit\test_ops_console.py
python -m unittest discover -s skills\ydz-create-accountset\tests
```

## 2026-06-08: changed account-set backend lookup to task categories 2,3

Changed:
- `src/chanjet_admin/task_query.py` now sends `taskCategorys: "2,3"` to `getTaskListInternal` and no longer sends `taskTypeId: "3"` in the request payload.
- The standalone `skills/ydz-create-accountset` CLI uses the same backend lookup payload.
- The installed local `ydz-create-customer` skill copy was synced to the same payload rule.
- Updated skill troubleshooting/workflow docs and recorded the backend API parameter decision.

Validation:
```powershell
python -m compileall -q src\chanjet_admin\task_query.py src\ydz\customer_creation.py scripts\ydz_create_customers.py tests\unit\test_chanjet_admin_task_query.py skills\ydz-create-accountset\scripts\ydz_accountset_cli.py skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_ydz_customer_creation.py
python tests\unit\test_ydz_create_customers_script.py
python tests\unit\test_coverage_framework.py
python -m unittest discover -s skills\ydz-create-accountset\tests
$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\ydz-create-accountset
$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\Administrator\.codex\skills\ydz-create-customer
```

## 2026-06-08: fixed account-set auto-login stuck and backend 403 false-ready state

Changed:
- `scripts/ydz_create_customers.py` now retries the Chanjet login submit button when the login form remains visible after the first click.
- The agreement checkbox handling now avoids toggling an already-selected custom checkbox off.
- Yidaizhang login now attempts to click the public-site `进入易代账` entry before direct-opening the workbench URL.
- Public-manage pages showing `403 / 无权访问` are no longer treated as a valid backend session just because storage tokens exist.
- Backend login now clears the forbidden page's local/session storage and opens the Chanjet login callback when credentials are configured.
- Applied the same fixes to the standalone account-set skill and the local `ydz-create-customer` skill copy.

Root cause:
- The failed run had Yidaizhang credentials filled, but the first scripted submit did not complete navigation until the login button was clicked again.
- The public-manage page had a token for an `admin` session but showed `403 无权访问`, so the old readiness check could misclassify it as logged in.

Validation:
```powershell
python -m compileall -q scripts\ydz_create_customers.py skills\ydz-create-accountset\scripts\ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py tests\unit\test_ydz_create_customers_script.py skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python tests\unit\test_ydz_create_customers_script.py
python -m unittest discover -s skills\ydz-create-accountset\tests
$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\ydz-create-accountset
```

## 2026-06-08: clarified workbench-first project structure and skill independence

Changed:
- Updated `README.md`, `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, and `AGENTS.md` to define the project as a local operator workbench for automatic login, collection verification, account-set creation, monitoring, and issue handling.
- Documented that command-line scripts are deterministic workbench executors and developer diagnostics, not the preferred operator interface.
- Strengthened the independence contract in `skills/ydz-create-accountset/SKILL.md`.
- Added skill tests to block imports from this repository's `src.*` and `scripts.*` modules and to catch project-only documentation dependencies.

Validation:
```powershell
python -m unittest discover -s skills\ydz-create-accountset\tests
python -m compileall -q main.py scripts src skills\ydz-create-accountset\scripts\ydz_accountset_cli.py
```

## 2026-06-08: enabled auto-login for operator console account-set creation

Changed:
- `scripts/ydz_create_customers.py` now tries automatic login by default when Yidaizhang or public-manage browser sessions are missing.
- The script reads environment-specific Yidaizhang secrets from `YDZ_INTE_*` or `YDZ_PROD_*`, and backend secrets from `TAX_BACKEND_*`; `--skip-auto-login` keeps the old session-only behavior.
- The operator console `创建账套` form now clearly selects 集测/线上 and can pass temporary Yidaizhang/backend credentials to the child process environment without writing them to command lines, job records, or result JSON.
- Added an optional `--env-file` path for local uncommitted secret files.

Validation:
```powershell
python -m compileall -q scripts\ydz_create_customers.py scripts\ops_console.py tests\unit\test_ops_console.py tests\unit\test_ydz_create_customers_script.py
python scripts\ydz_create_customers.py --help
python tests\unit\test_ydz_create_customers_script.py
python tests\unit\test_ops_console.py
```

## 2026-06-08: fixed YDZ account-set skill login flow

Changed:
- Added `login` command to `skills/ydz-create-accountset/scripts/ydz_accountset_cli.py`.
- `doctor --open` and `create` now try automatic login by default from environment variables or `--env-file`; `--skip-auto-login` keeps the old session-only behavior.
- Added Yidaizhang integration login handling that opens the configured `work.html` URL after authentication, covering the integration real-name-auth reminder redirect.
- Added public-manage backend login automation using the configured backend credentials.
- Updated `ydz-create-accountset` and local `ydz-create-customer` skill instructions so agents run `login/doctor/create` before asking the user for passwords.
- Bundled the fixed self-contained CLI into the local `ydz-create-customer` skill so hosts that only copy that skill can still run automatic login.

Validation:
```powershell
python -m compileall -q skills\ydz-create-accountset\scripts\ydz_accountset_cli.py skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m unittest discover -s skills\ydz-create-accountset\tests
python skills\ydz-create-accountset\scripts\ydz_accountset_cli.py --help
python skills\ydz-create-accountset\scripts\ydz_accountset_cli.py login --help
python C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py --help
python C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py login --help
python skills\ydz-create-accountset\scripts\ydz_accountset_cli.py doctor --env inte --open --skip-auto-login
python skills\ydz-create-accountset\scripts\ydz_accountset_cli.py create --env inte --tax-no 91120102754804355E --dry-run --skip-auto-login --session-timeout 30 --output-json output\accountset_runs\skill_fix_dryrun_91120102754804355E.json
$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\ydz-create-accountset
$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py C:\Users\Administrator\.codex\skills\ydz-create-customer
```

## 2026-06-08: added YDZ account-set creation to operator console

Changed:
- Added a `创建账套` entry in `scripts/ops_console.py`.
- The console now starts `scripts/ydz_create_customers.py` as an `accountset` job, writes tax numbers and logs under `output/accountset_runs/<runId>/`, and opens the sanitized `accountset_summary.json` result.
- Account-set jobs reuse the existing current-task panel, stop button, log tail, and tax-number progress table without being treated as batch verification reports.
- Added health checks for the account-set script and output directory.
- Added unit coverage for command construction, sanitized display commands, dry-run summaries, and account-set job status rendering.

Validation:
```powershell
python tests\unit\test_ops_console.py
python tests\unit\test_ydz_customer_creation.py
python scripts\ydz_create_customers.py --help
python -m compileall -q main.py scripts src
```

## 2026-06-08: packaged reusable YDZ account-set tool

Changed:
- Added portable skill package `skills/ydz-create-accountset/`.
- Added self-contained CLI `scripts/ydz_accountset_cli.py` inside the skill with `doctor` and `create` commands.
- Added reference docs for workflow, API field mapping, config/secrets, and troubleshooting.
- Added offline unittest coverage for tax-number parsing, login method mapping, payload defaults, tax-info saving fields, verification helpers, and password redaction.
- Updated project memory files to document the new package and design decision.

Validation:
```powershell
python -m compileall -q skills\ydz-create-accountset\scripts\ydz_accountset_cli.py skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m unittest discover -s skills\ydz-create-accountset\tests
$env:PYTHONUTF8='1'; python C:\Users\Administrator\.codex\skills\.system\skill-creator\scripts\quick_validate.py skills\ydz-create-accountset
python skills\ydz-create-accountset\scripts\ydz_accountset_cli.py --help
rg -n "<known-password-or-token-patterns>" skills\ydz-create-accountset
```

Security note: the package stores only non-secret defaults and secret variable names. It does not store real passwords, cookies, tokens, Authorization values, or raw backend `loginJson`.

## 2026-06-04：修复低覆盖率误报和批量汇总展示

修改内容：
- `scripts/compare_tax_forms.py`：低网页解析覆盖率只有在真实形成可比对 `web_missing` 时才进入 `quality_issues`；如果接口字段全部可正常比对、网页空值与接口 0 等价，则只保留日志，不再影响结果。
- `scripts/batch_collect_verify.py`：批量工作台不再直接根据 stderr 的 `low web extraction coverage` 日志生成需处理原因，改为以单表 JSON 的 `quality_issues` / `web_missing_count` 为准。
- `tests/unit/test_web_extraction_recovery.py`：新增低覆盖率质量门禁回归测试。
- `tests/unit/test_batch_handling_info.py`：新增批量汇总低覆盖率风险展示回归测试。

现场验证：
- 手动发起批次 `ops_20260604_141814`，税号 `91370102MA7D3P0D2P` 解析到两个 taskId：`2076981280669355836`、`2076981280669355835`。
- `2076981280669355836`：增值税主表、附表一至附表五、文化事业建设费均为 `match_rate=100%`，`web_missing=0`，`quality_issues=[]`。
- `2076981280669355835`：消费税主表、消费税附加税费计算表均为 `match_rate=100%`，`web_missing=0`，`quality_issues=[]`。
- 已刷新 `output\batch_runs\ops_20260604_141814\batch_summary.html` 和 `ops_status.json`，低覆盖率日志不再显示为需人工处理原因。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_web_extraction_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_vat_small_web_extraction_parsers.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

## 2026-06-04：优化网页缺失补救的性能

修改内容：
- `scripts/compare_tax_forms.py`：网页读取补救改为只围绕最终参与比对的字段执行，不再对接口本来无值、不会参与比对的映射字段做全量滚动补读。
- `scripts/compare_tax_forms.py`：通用滚动重试降级为“完全没有读到字段”时的兜底；只要已经读到部分字段，就交给外层按真实 `web_missing` 字段做定向补读。
- `scripts/compare_tax_forms.py`：低覆盖但没有可比对字段 `web_missing` 时，不再执行三轮昂贵恢复，避免附表三这类“接口 0 与网页空等价”的场景被反复滚动。
- `tests/unit/test_web_extraction_recovery.py`：增加回归测试，覆盖只抽取参与比对字段、低覆盖但无网页缺失时跳过昂贵恢复。

现场结论：
- 本次 `91370102MA7D3P0D2P` 全流程批次 `ops_20260604_132337` 中，`2076981723053210310` 的增值税主表、附表一、附表二均已完成且 `web_missing=0`。
- 慢的直接原因是旧版补救逻辑对附表一的 311 个映射、附表二的 93 个映射做了全量滚动补读，其中大量字段接口本来无值、不参与比对；附表三在 `web_missing=0` 时仍因覆盖率低进入三轮恢复。
- 当前已启动的旧进程不会自动加载修复，需要重新启动验证后生效。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_web_extraction_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_vat_small_web_extraction_parsers.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

## 2026-06-04：修复消费税主表底部行网页值偶发缺失

修改内容：
- `scripts/compare_tax_forms.py`：消费税主表首次读取缺少 14-17 行时，重试滚动从“顶部/底部”扩展为多段纵向扫描，覆盖中部、下中部、近底部和底部，适配山东未申报页的虚拟渲染。
- `scripts/compare_tax_forms.py`：消费税附加税费计算表内容已可见但左侧菜单选中态短暂未读到时，只要能读到足够业务字段，允许继续确认，避免误判目标页未确认。
- `tests/unit/test_consumption_tax_support.py`、`tests/unit/test_detail_form_switching.py`：补充消费税近底部虚拟行扫描和菜单选中态兜底测试。

现场结论：
- 当前批次 `ops_20260604_123518` 中 `2076981675808305083` 的 `web_missing=8` 发生在消费税主表底部 14-17 行：`bqybtse_*`、`bnljybtse_*`、城建税/教育费附加/地方教育附加的本期与累计字段。
- 当时 PDF 只抓到主表到“本期预缴税额 13”，说明税局页面底部行没有进入当前 DOM/PDF，而不是接口字段错或税局没有值。
- 修复后重跑 `2076981675808305083` 成功：消费税主表 `38/38`，消费税附加税费计算表 `29/29`，新报告为 `output\reports\2076981675808305083\compare_summary_2076981675808305083_20260604_125119.html`。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
.\.venv\Scripts\python.exe main.py --task-id 2076981675808305083 --log-level INFO
```

## 2026-06-04：修复同税号连续任务下消费税验证失败

修改内容：
- `scripts/compare_tax_forms.py`：未申报入口跳回统一登录页时，自动重新获取当前 taskId 税局登录态并重试一次。
- `scripts/compare_tax_forms.py`：状态未知且未申报首页没有目标税种入口时，允许切回已申报查询；状态明确未申报时仍失败，不掩盖真实入口问题。
- `scripts/compare_tax_forms.py`：已申报查询打开申报记录时带入接口所属期，避免只按表名打开上一期同名记录。
- `tests/unit/test_detail_form_switching.py`、`tests/unit/test_consumption_tax_support.py`：补充登录态重试、未申报入口缺失回退、已申报查询所属期传参的回归测试。

现场结论：
- `2076981650034436464` 和 `2076981650034436465` 是同一税号 `91370102MA7D3P0D2P`、同一个山东税局会话，但不是同一张表；`6465` 是增值税/文化事业费，`6464` 是消费税。
- `6464` 旧失败先是同税号连续任务刷新登录态后，消费税未申报入口被带回 `tpass/#/login`；补登录重试后又暴露出状态未知时可能进入上一期已申报记录的问题。
- 修复后重跑 `2076981650034436464` 成功：消费税主表 `38/38`，消费税附加税费计算表 `29/29`，新报告为 `output\reports\2076981650034436464\compare_summary_2076981650034436464_20260604_123005.html`。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_shanxi_query_recovery.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
.\.venv\Scripts\python.exe main.py --task-id 2076981650034436464 --log-level INFO
```

## 2026-06-04：修复一般纳税人附表五本期已缴税额假缺失

修改内容：
- `scripts/compare_tax_forms.py`：附表五文本解析增强列位对齐；当教育费附加/地方教育附加的减免性质代码及政策依据被税局页面拆成多行时，压掉说明文本造成的多余空占位，避免第 15 列 `bqyjse_*` 本期已缴税额错读为空。
- `scripts/compare_tax_forms.py`：同时保留稀疏零值行兜底；行名存在但没有任何数值时，仍不自动补 0。
- `tests/unit/test_vat_appendix5_extraction.py`：新增天津页面同款“多行减免说明”回归用例，并覆盖稀疏零值行保护。

现场结论：
- `2076614022309347199` 的附表五旧报告只缺 `bqyjse_jyfj`、`bqyjse_dfjyfj` 两个字段，接口值均为 `0.00`；根因是天津已申报详情页把减免代码 `0061042802/0099042802` 和政策依据拆成多行，旧解析器把代码当成数值列、把 `|` 当成空列，导致第 15 列错位为空。
- 修复后重跑 `2076614022309347199 --targets vat_general_appendix5 --skip-pdf` 成功，附表五 `18/18` 匹配、`web_missing=0`，新报告为 `output\reports\2076614022309347199\compare_summary_2076614022309347199_20260604_115041.html`。
- `2076981254899665895` 旧失败不是字段比对问题，而是未申报直达 URL 失败后首页兜底误点了“办税进度及结果查询”，随后左侧申报菜单找不到目标表；修复首页兜底后该 taskId 已重跑成功。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_vat_appendix5_extraction.py
.\.venv\Scripts\python.exe tests\unit\test_normalizer_comparator.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
.\.venv\Scripts\python.exe main.py --task-id 2076614022309347199 --targets vat_general_appendix5 --log-level INFO --skip-pdf
```

## 2026-06-04：补齐插件登录差异的低风险兜底

修改内容：
- `src/login/task_login_flow.py`：读取 `window.robotId` 时最多等待 8 秒；如果首次使用固定 `machineId` 导致 `getTaskCookie` 返回失败，会在发现真实 `robotId` 后自动重试一次。
- `src/login/task_login_flow.py`：direct fallback 打开青岛税局前，按 EtaxPlugin 同名逻辑定向清理 `TGCT`、`enable_gizqLgxJ4gkh` 两个青岛特殊登录 cookie。
- `src/login/task_login_flow.py`、`scripts/batch_collect_verify.py`：`needForceTax=true` 归类为需要人工确认是否强制进入税局，不默认自动调用 `forceEnterTax`。
- `tests/unit/test_task_login_flow.py`、`tests/unit/test_batch_handling_info.py`：补充机器码等待/重试、青岛 cookie 清理、`needForceTax` 归因测试。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_task_login_flow.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_shanxi_query_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_ops_console.py
.\.venv\Scripts\python.exe tests\unit\test_cbj_verification.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

说明：本轮未自动执行 `forceEnterTax`，因为插件原逻辑也是弹窗等待人工选择；自动强制进入可能打断已有税务任务，应只作为后续显式参数或运营台按钮实现。

## 2026-06-04：默认使用 EtaxPlugin 优先进税局并降低 loading 误判

修改内容：
- `main.py`、`scripts/compare_tax_forms.py`、`scripts/batch_collect_verify.py`：真实 taskId 验证默认 `--tax-login-strategy plugin_first`，优先走 EtaxPlugin 的清税局 cookie、关闭旧税局页、打开新 tpass 页流程；`direct_first` 保留为显式调试/兜底选项。
- `src/login/task_login_flow.py`：插件派发前补充结束旧 background taskId 的 `setEndCookie` 动作；插件优先等待窗口从 8 秒提升到最多 45 秒；税局 `/loading` 不再被判定为已登录；无插件 direct 注入脚本补充 `/loginb/` 读取 `tgtUrl` 后二跳。
- `src/login/login_detector.py`、`scripts/compare_tax_forms.py`：`/loading` 和 `tpass.*#/login` 不再作为可复用/已登录页面；申报查询持续 loading 会提前进入恢复路径，最终仍不可用时归类为税局登录态或数字账户认证未就绪。
- `src/cbj/verification.py`：残保金年度查询路径同步使用插件优先默认策略。
- `tests/unit/test_task_login_flow.py`、`tests/unit/test_detail_form_switching.py`、`tests/unit/test_batch_handling_info.py`：补充插件派发顺序、loading 登录误判、旧页不复用、未申报入口跳 tpass、loading 归因等回归测试。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_task_login_flow.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_shanxi_query_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_ops_console.py
.\.venv\Scripts\python.exe tests\unit\test_cbj_verification.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

现场结论：
- 河南 `2076981186177811385` 长期停留 `/loading` 的根因是 direct 登录过早被判定为可用，但申报查询/数字账户所需会话未完整建立。新策略默认使用插件清理旧税局会话并新开页，降低该类失败概率；若仍跳回 tpass 或持续 loading，结果会归类为登录态/数字账户认证未就绪。

## 2026-06-04：识别山东未申报入口跳回 tpass 登录页

修改内容：
- `scripts/compare_tax_forms.py`：未申报表单准备阶段如果目标入口跳回 `tpass.*#/login`，直接抛出 `DeclarationQueryAuthError`，明确归因为税局登录态或数字账户认证失效。
- `scripts/batch_collect_verify.py`：兼容已落盘的旧 `RuntimeError: Could not open undeclared tax form ... tpass ... #/login` 日志，批量汇总和工作台状态归一为税局登录认证失效，不再展示长串 RuntimeError。
- `tests/unit/test_detail_form_switching.py`、`tests/unit/test_batch_handling_info.py`：补充 tpass 登录页跳转和批量归因回归测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
```

现场结论：
- 当前批次 `ops_20260604_095016` 中，`91370102MA7D3P0D2P` 的 taskId `2076981662919583828` 已完成未申报增值税 6 张表验证；切换到 `culture_fee_main` 时，山东税局入口跳回 `https://tpass.shandong.chinatax.gov.cn:8443/#/login...`，因此文化事业建设费未申报表未打开。
- 该失败属于外部税局登录态/数字账户认证中断，不是接口字段比对失败。

## 2026-06-03：修复个税残保金后台补齐识别过窄

修改内容：
- `src/chanjet_admin/task_execution_log.py`：扩展残保金日志识别规则，支持通过 `personNum`、`personNumSum`、`monthNumSum`、`amountSum`、`申报月份汇总`、`申报人次汇总` 等特征识别个税残保金；汇算清缴标记仍优先于个税标记。
- `src/coverage/supplement.py`：后台补齐残保金候选在日志无法识别时，增加 task result 二次确认；如果 `sz_cbj` 结果中同时包含 `snzzzgrs_cbj` 和 `snzzzggzze_cbj`，且没有汇算清缴日志标记，则归类为 `CBJ_PERSONAL`。
- `src/coverage/supplement.py`：增加残保金任务类型来源诊断 `cbjModeSourceCounts`，区分执行日志识别、任务列表字段识别、API 结果字段识别、API 缺失或异常等来源。
- `tests/unit/test_task_execution_log.py`、`tests/unit/test_coverage_framework.py`：补充个税残保金日志特征、汇算优先级、API 字段兜底识别测试。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_task_execution_log.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

真实 taskId 抽查：
- `2076614073849978635` 当前可通过执行日志识别为 `backend`，即个税残保金。
- `2076614073849978635` 的 task result 可读取 `snzzzgrs_cbj=2`、`snzzzggzze_cbj=201442.82`。

## 2026-06-03：修复湖北已/未申报冲突后的查询恢复与进税局任务锁处理

修改内容：
- `scripts/compare_tax_forms.py`：未申报页提示“本属期已申报”后切回已申报查询时，恢复顺序改为先直接打开申报信息查询页，再使用 spHandler 兜底，避免湖北 spHandler 过早跳回统一登录页。
- `scripts/compare_tax_forms.py`：当前页恢复遇到统一登录页时，不立即终止；允许新开税局页再尝试一次申报查询恢复。
- `src/login/task_login_flow.py`：新增 `PendingTaxLoginJobError`，后台提示已有进税局任务未完成时最多短等待 90 秒，仍未释放则明确失败并带出占用进税局 taskId。
- `scripts/batch_collect_verify.py`、`scripts/ops_console.py`：新增进税局任务锁的中文原因归一化，结果页/工作台展示“已有进税局任务未完成”和占用任务号。
- `tests/unit/test_shanxi_query_recovery.py`、`tests/unit/test_task_login_flow.py`、`tests/unit/test_batch_handling_info.py`、`tests/unit/test_ops_console.py`：补充查询恢复、进税局任务锁解析和运营展示测试。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_ops_console.py
.\.venv\Scripts\python.exe tests\unit\test_task_login_flow.py
.\.venv\Scripts\python.exe tests\unit\test_shanxi_query_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
.\.venv\Scripts\python.exe main.py --task-id 2076614026604654385 --skip-browser --log-level INFO
.\.venv\Scripts\python.exe main.py --task-id 2076614026604654385 --log-level INFO
```

真实验证结果：
- `2076614026604654385` 的接口数据可解析为增值税小规模，且任务日志标记 `current-period=false`。
- 完整税局验证当前被后台进税局任务锁拦截：占用任务 `2076614043783903619` 未完成。新逻辑已在约 90 秒内明确失败，不再长时间卡住。
- 因外部进税局任务锁未释放，本次无法继续验证湖北申报查询恢复后的字段比对结果。

## 2026-06-03：修复山东未申报页面回首页后的入口恢复

修改内容：
- `scripts/compare_tax_forms.py`：新增未申报页面回落到税局首页/门户页的识别逻辑，命中后自动重新按目标税种进入申报表。
- `scripts/compare_tax_forms.py`：新增更稳健的首页申报入口点击函数，优先在包含目标税种名称的卡片/行内点击“填写申报表/我要填表/继续申报”，避免点到其它税种或停在首页。
- `scripts/compare_tax_forms.py`：在未申报表单准备、左侧菜单选择和目标表确认失败时增加一次首页恢复重试，恢复后重新执行表单准备流程。
- `tests/unit/test_detail_form_switching.py`：补充山东增值税首页回落识别和菜单选择失败后恢复的单元测试。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_shanxi_query_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
.\.venv\Scripts\python.exe main.py --task-id 2076614043783892312 --log-level INFO
```

真实验证结果：
- `2076614043783892312` 已成功进入山东未申报增值税主表、附表一至附表五，并完成文化事业建设费验证。
- 新报告：`output\reports\2076614043783892312\compare_summary_2076614043783892312_20260603_154856.html`

## 2026-06-03：残保金后台补齐查询改用 taxId=39

修改内容：
- `src/coverage/models.py`：新增 `backend_tax_ids`、`backendTaxIds`、`backendTaxId`、`backendQueryField`，把后台任务列表筛选维度和取数侧 `taxTypeId` 区分开。
- `src/coverage/registry.py`：残保金覆盖目标保留 `backend_tax_type_ids=(26,31)`，同时新增后台补齐查询用 `backend_tax_ids=(39,)`。
- `src/chanjet_admin/task_query.py`：后台任务列表查询新增 `tax_id` 参数，发送 `taxId:"39"`，不再把残保金后台筛选 ID 当作 `taxTypeId/taxTypeIds`。
- `src/coverage/supplement.py`：覆盖补齐分组支持 `taxId`，残保金两个目标合并为一次 `taxId=39` 查询；候选仍通过操作日志或字段判断 `CBJ_PERSONAL/CBJ_ANNUAL`。
- `scripts/batch_collect_verify.py`、`src/coverage/analyzer.py`：补齐日志、状态和结果页展示后台筛选字段，残保金可直观看到 `taxId:39`。
- `tests/unit/test_chanjet_admin_task_query.py`、`tests/unit/test_coverage_framework.py`：补充后台 `taxId` 查询和残保金补齐分组测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q src\coverage\models.py src\coverage\registry.py src\coverage\supplement.py src\chanjet_admin\task_query.py src\coverage\analyzer.py scripts\batch_collect_verify.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_chanjet_admin_task_query.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

## 2026-06-03：残保金后台补齐改为按操作日志区分个税/汇算清缴

修改内容：
- `src/coverage/registry.py`：`CBJ_PERSONAL` 和 `CBJ_ANNUAL` 共享残保金后台 taxTypeId `26`、`31`，避免 `taxTypeId=26` 但日志显示汇算清缴路径的任务被漏掉。
- `src/coverage/supplement.py`：后台补齐候选不再要求同时包含 `snzzzgrs_cbj` 和 `snzzzggzze_cbj`；改为优先读取“残保金任务返回结果”操作日志判断 `CBJ_PERSONAL` / `CBJ_ANNUAL`。
- `src/coverage/supplement.py`：日志无法判断时只保守兜底字段存在的个税残保金；否则标记为 `CBJ_UNKNOWN`，不自动匹配目标。
- `src/coverage/supplement.py`：按 `targetKey + taskId` 去重，避免同一残保金任务从 taxTypeId 26 和 31 两个查询条件重复进入候选。
- `scripts/batch_collect_verify.py`：结果页任务类型分布中将 `CBJ_UNKNOWN` 显示为“残保金类型未知”。
- `tests/unit/test_coverage_framework.py`、`tests/unit/test_batch_summary_rendering.py`：补充残保金日志识别、`taxTypeId=26` 汇算清缴归类、未知类型展示等测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q src\coverage\registry.py src\coverage\supplement.py scripts\batch_collect_verify.py tests\unit\test_coverage_framework.py tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
```

风险：
- 该规则依赖后台操作日志文案保持稳定；如后续“残保金任务返回结果”日志说明变更，需要补充 marker。
- 旧批次报告不会自动重算，需要重新生成或重跑批次后展示新补齐原因。

## 2026-06-03：优化后台补齐失败原因展示并修复乱码

修改内容：
- `scripts/batch_collect_verify.py`：新增后台补齐失败原因归一化逻辑，常见异常不再直接展示 `RuntimeError`、`getTaskCookie failed`、`Could not navigate...` 等底层文本。
- `scripts/batch_collect_verify.py`：对税局返回的错误详情做乱码检测和修复；无法可靠还原时，展示“原始返回内容不可读”并给出可处理原因。
- `scripts/batch_collect_verify.py`：后台补齐尝试记录和覆盖缺口说明共用同一套失败原因归一化；税号矩阵的“需处理原因”也复用该逻辑。
- `scripts/batch_collect_verify.py`：后台补齐尝试记录的原因列增加固定宽度、自动换行和长 URL 断行，避免一条异常撑宽整页。
- `tests/unit/test_batch_summary_rendering.py`：新增进不了申报查询页、getTaskCookie 乱码、验证失败原因复用归一化逻辑的测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\batch_collect_verify.py tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

结果：
- 已重新生成 `output\batch_runs\ops_20260603_103639\batch_summary.html`。
- 抽查确认最新页面不再包含原始 `RuntimeError`、`getTaskCookie failed`、`Could not navigate`、乱码替代符 `�/□`。

## 2026-06-03：后台补齐查询增加登录方式过滤

修改内容：
- `src/chanjet_admin/task_query.py`：后台任务查询新增 `login_type` 参数，请求 payload 增加 `loginType` 字段。
- `src/coverage/supplement.py`：覆盖补齐查询固定传入 `YSHDL,DLYW-YSHDL`，只查“税局隐私号登录”和“税局隐私号-代理登录”的成功取数任务。
- `tests/unit/test_chanjet_admin_task_query.py`、`tests/unit/test_coverage_framework.py`：新增断言，确保后台请求和补齐规划器都携带该登录方式条件。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q src\chanjet_admin\task_query.py src\coverage\supplement.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_chanjet_admin_task_query.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

风险：
- 后台补齐候选范围会变窄；如果某个缺口只有其它登录方式的成功任务，将不会被选作补齐代表任务。

## 2026-06-03：修复个税残保金后台补齐误选其它税种任务

修改内容：
- `src/coverage/supplement.py`：个税残保金后台补齐候选必须同时包含 `snzzzgrs_cbj` 和 `snzzzggzze_cbj`，缺少字段的后台成功任务不再匹配 `CBJ_PERSONAL:any`。
- `src/coverage/supplement.py`：补齐诊断新增必需字段缺失统计，并支持解析嵌套 JSON 字符串，避免只凭宽泛文本把消费税等任务误判为残保金。
- `scripts/batch_collect_verify.py`：批量结果页把该类缺口原因展示为中文直观说明，提示“缺少必需字段，不能作为该税种补齐任务”。
- `tests/unit/test_coverage_framework.py`、`tests/unit/test_batch_summary_rendering.py`：新增个税残保金字段校验和中文原因展示测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q src\coverage\supplement.py scripts\batch_collect_verify.py tests\unit\test_coverage_framework.py tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

风险：
- 旧批次 HTML 不会自动变化；需要重新跑批次或重新生成汇总页后，才会看到新的中文缺口原因。

## 2026-06-03：修复江西小规模未申报申报表确认失败

修改内容：
- `scripts/compare_tax_forms.py`：新增小规模增值税未申报专用入口 `/sbzx/view/lzsfjssb/#/declare/zzsxgmnsrsb?jyjkId=10`，不再复用一般纳税人入口 `zzsybnsrsb`。
- `scripts/compare_tax_forms.py`：`is_expected_undeclared_entry_url()` 区分一般纳税人和小规模未申报路由，避免把税局自动跳转后的页面误判为非目标页。
- `scripts/compare_tax_forms.py`：抽出 `is_undeclared_target_confirmed()`，让未申报页面等待阶段和截图/解析前二次确认使用同一套规则；当左侧菜单已选中且业务字段足够时允许通过，同时保留文化事业建设费嵌入表单的确认逻辑。
- `tests/unit/test_detail_form_switching.py`：新增小规模未申报 URL 和业务字段兜底确认测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_shanxi_query_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
```

风险：
- 已尝试用 `2076614018014433234` 复测 `vat_small_main`，但旧任务在 `getTaskCookie` 阶段返回“登录连接状态已失效，请重新发起任务”，未进入申报表确认阶段；真实链路仍需用重新发起后的新 taskId 或下一批后台补齐小规模未申报候选复测。
- 其他省份如果小规模未申报入口不是 `zzsxgmnsrsb`，还需要按省份补充入口策略。

## 2026-06-02：修复消费税主表延迟渲染导致网页值缺失

修改内容：
- `scripts/compare_tax_forms.py`：消费税网页抽取从“读取当前 DOM 一次”改为按当前、底部、顶部多位置滚动采集表格行并去重，触发税局页面延迟/虚拟滚动区域渲染。
- `scripts/compare_tax_forms.py`：消费税主表增加关键汇总字段哨兵；如果“本期应补（退）税额”、城建税、教育费附加、地方教育附加等字段首次仍缺失，会再次滚动重读。
- `tests/unit/test_consumption_tax_support.py`：新增模拟用例，覆盖初始 DOM 只有商品行、滚动后才出现第 14-17 行的真实页面场景。

验证：
```powershell
$env:PYTHONPYCACHEPREFIX='runtime\pycache_compile'; .\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe main.py --task-id 2076264472102157946 --targets auto --cdp-port 9222 --user-data-dir browser_profile\etax_compare_forms --plugin-path C:\Users\Administrator\Downloads\EtaxPlugin --log-level INFO --tax-timeout 600 --tax-login-strategy direct_first --skip-pdf
```

真实验证结果：
- `2076264472102157946` 消费税及附加税费申报表：`total=38 match=38 web_missing=0 match_rate=100.0%`。
- `2076264472102157946` 消费税附加税费计算表：`total=29 match=29 web_missing=0 match_rate=100.0%`。
- 报告：`output\reports\2076264472102157946\compare_summary_2076264472102157946_20260602_164349.html`。

风险：
- 为了触发完整渲染，消费税每张表解析前会多做少量滚动和等待，单表预计增加约 1 秒，但避免可见字段被误判为网页缺失。

## 2026-06-02：修复消费税主表网页缺失与文化事业建设费 fl_bys 比较规则

修改内容：
- `scripts/compare_tax_forms.py`：文化事业建设费申报表字段 `fl_bys` 不再进入字段比对和结果汇总。
- `scripts/compare_tax_forms.py`：增强消费税及附加税费申报表主表解析，对“本期应补（退）税额”、城建税、教育费附加、地方教育附加等汇总行，改为按业务关键词和栏次号识别，并从行尾金额列提取本月/累计值。
- `scripts/compare_tax_forms.py`：消费税网页表格抽取优先读取单元格内 `input/textarea/select` 的值，修复页面有值但 `td.innerText` 为空导致的 8 个 `web_missing`。
- `scripts/compare_tax_forms.py`：山东消费税未申报 direct URL 打开后增加目标入口确认；若回到首页则补走首页申报入口，首页入口点击改为“点击一步等一步”。
- `tests/unit/test_consumption_tax_support.py`：新增消费税主表汇总行解析测试，覆盖上次实际出现的 8 个网页值缺失字段；新增文化事业建设费 `fl_bys` 排除比较测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_vat_appendix5_compare_policy.py
.\.venv\Scripts\python.exe main.py --task-id 2076263995364848762 --targets auto --log-level INFO
```

真实验证结果：
- `2076263995364848762` 消费税主表：`total=38 match=38 web_missing=0 match_rate=100.0%`。
- `2076263995364848762` 消费税附加税费计算表：`total=29 match=29 web_missing=0 match_rate=100.0%`。
- 报告：`output\reports\2076263995364848762\compare_summary_2076263995364848762_20260602_162822.html`。

风险：
- `fl_bys` 是按用户确认的业务规则排除，不再用于文化事业建设费申报表通过率计算。
- 当前已单独复测失败的消费税 taskId；原批次 `ops_20260602_161841` 的状态文件仍保留失败记录，需重跑批次或重验该子任务后批量页才会刷新。

## 2026-06-02：禁止未完成后台取数任务进入验证

修改内容：
- `src/ydz/task_resolver.py` 将后台 taskId 选择规则改为只返回 `SUCCESS` 状态任务。
- `SCHEDULE`、`DOING`、`WAITING`、`TODO`、`FAILURE` 等非成功状态不再作为验证 taskId。
- `scripts/batch_collect_verify.py` 读取历史 state 时，如果 `resolvedTask(s)` 明确显示 taskId 非 `SUCCESS`，则过滤掉该 taskId，避免脏状态导致跳过重新取数或提前验证。
- 更新 `tests/unit/test_ydz_collector.py` 和 `tests/unit/test_batch_handling_info.py`，覆盖未成功任务不返回、不进入可验证列表。

验证：
```powershell
$env:PYTHONPYCACHEPREFIX='runtime\pycache_compile'; .\.venv\Scripts\python.exe -m compileall -q src\ydz\task_resolver.py scripts\batch_collect_verify.py tests\unit\test_ydz_collector.py tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_ydz_collector.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
```

风险：
- 如果后台任务长时间停留 `SCHEDULE/DOING`，批次会显示取数未完成，不会再提前验证；需要等待后台成功后重跑。

## 2026-06-02：表单矩阵改为显示字段校验结果

修改内容：
- `scripts/batch_collect_verify.py` 的“税号 × 表单矩阵”中，主表、附表等表单列不再显示“已申报/未申报”等申报状态。
- 表单列统一显示字段校验状况：无问题显示“通过”，有差异显示“1项/多项”，未执行显示“-”。
- 申报状态仍保留在“税种概览”和覆盖说明中，用于判断覆盖，不再污染表单级字段验证结果。
- 更新 `tests/unit/test_batch_summary_rendering.py`，覆盖“未知/未申报但字段全通过时表单列显示通过”的场景。

验证：
```powershell
$env:PYTHONPYCACHEPREFIX='runtime\pycache_compile'; .\.venv\Scripts\python.exe -m compileall -q scripts\batch_collect_verify.py tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
```

结果：
- 已重新生成 `output\batch_runs\ops_20260602_141625\batch_summary.html`，增值税主表和附表列显示“通过”，文化事业建设费主表显示“1项”。

## 2026-06-02：修复未知申报状态路由和未申报附表切换慢点

修改内容：
- `scripts/compare_tax_forms.py` 新增目标级有效申报状态：非残保金任务缺少“是否是当期”日志时，实际税局导航按未申报处理。
- 消费税等未知申报状态任务不再只在结果页显示“未申报”却走已申报查询页。
- 未申报增值税附表切换从“先等待目标内容超时，再点击左侧菜单”改为“当前页不是目标时立即点击菜单”，减少每张附表十几秒的无效等待。
- 更新消费税状态和未申报附表切换单元测试。

验证：
```powershell
$env:PYTHONPYCACHEPREFIX='runtime\pycache_compile'; .\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_consumption_tax_support.py tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe main.py --task-id 2076263982479535571 --targets auto --cdp-port 9222 --user-data-dir browser_profile\etax_compare_forms --plugin-path C:\Users\Administrator\Downloads\EtaxPlugin --log-level INFO --tax-timeout 600 --tax-login-strategy direct_first --skip-pdf
.\.venv\Scripts\python.exe main.py --task-id 2076263982479535572 --targets vat_general_appendix1 --cdp-port 9222 --user-data-dir browser_profile\etax_compare_forms --plugin-path C:\Users\Administrator\Downloads\EtaxPlugin --log-level INFO --tax-timeout 600 --tax-login-strategy direct_first --skip-pdf
```

真实验证结果：
- `2076263982479535571` 已不再走已申报“申报信息查询”页，而是按未知即未申报进入税局首页填表路径；当前仍失败，原因变为山东税局本期应申报列表没有消费税菜单，页面只展示增值税、企业所得税、财务报表等入口。
- `2076263982479535572` 的 `vat_general_appendix1` 直接点击左侧菜单后确认目标表，未再出现切表前的长等待，字段比对 `100%`。

风险：
- 消费税未申报真实入口仍依赖税局首页通用“填写申报表/我要填表”点击策略；如果山东税局本期应申报列表不展示消费税，流程会明确失败，需要后续确认消费税未申报是否有单独入口或任务本身是否应归为人工处理。

## 2026-06-02：调整残保金和未知申报状态的展示规则

修改内容：
- `scripts/batch_collect_verify.py` 中批量结果页把个税残保金展示为“已取数”、汇算清缴残保金展示为“已验证”，不再因为原始申报状态未知而标黄。
- 非残保金任务如果申报状态解析不到，统一先按“未申报”展示和参与覆盖统计。
- `src/coverage/analyzer.py` 将未知申报状态归入未申报覆盖目标。
- `src/coverage/supplement.py` 允许后台补齐时用申报状态未知的成功任务匹配未申报目标。
- `scripts/compare_tax_forms.py` 不再把未知申报状态写入质量风险，并把单任务报告里的未知状态显示为“未申报”。
- 更新批量展示、覆盖框架、消费税状态相关单元测试。

验证：
```powershell
$env:PYTHONPYCACHEPREFIX='runtime\pycache_compile'; .\.venv\Scripts\python.exe -m compileall -q scripts\batch_collect_verify.py scripts\compare_tax_forms.py src\coverage tests\unit\test_batch_summary_rendering.py tests\unit\test_coverage_framework.py tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
```

风险：
- 已经生成的旧批次 HTML 不会自动重算，需要重新生成或重新跑批次后才会体现新展示规则。

## 2026-06-02：修复山东文化事业建设费未申报入口和 iframe 解析

修改内容：
- `scripts/compare_tax_forms.py` 为山东文化事业建设费未申报任务增加专用入口 URL，按 API 所属期生成 `SssqQ/SssqZ`，进入后支持“继续申报 -> 我要填表”路径。
- 未申报目标确认和网页字段提取支持主页面加子 iframe 自动选择，避免文化费真实表单在 iframe 内时被误判为菜单找不到。
- 子页面选择增加实际表单 URL 权重，优先选择 `whsyjsf_BDA0610334ggy.html`，避免误选报表列表 `form/index.html`。
- 文化费网页字段解析改为优先读取单元格内 `input/select/textarea.value`，并按栏次后的本月/本年可取值单元格提取金额/费率。
- `tests/unit/test_detail_form_switching.py` 增加文化费 iframe 表单确认测试。

验证：
```powershell
$env:PYTHONPYCACHEPREFIX='runtime\pycache_compile'; .\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe main.py --task-id 2076264446332455641 --targets culture_fee_main --cdp-port 9222 --user-data-dir browser_profile\etax_compare_forms --plugin-path C:\Users\Administrator\Downloads\EtaxPlugin --log-level INFO --tax-timeout 240 --tax-login-strategy direct_first --skip-pdf
```

真实验证结果：
- 原失败点已修复：山东文化事业建设费可进入专用未申报页，完成“继续申报 -> 我要填表”，并选择真实表单 iframe。
- 网页字段解析覆盖从 `0/39` 提升为 `33/39`；6 个接口未返回字段按当前策略忽略。
- 当前仍有 1 个真实字段差异：`fl_bys` 接口值为 `0.00`，税局网页值为 `3.00%`，因此命令退出码仍为 1。

风险：
- 当前仅对山东文化事业建设费主表固化了专用 URL；其他省份或文化费减除清单如果页面结构不同，仍需补充省份/表单入口策略。

## 2026-06-02：未申报税种统一复用填表页验证逻辑

修改内容：
- `scripts/compare_tax_forms.py` 新增未申报支持税种集合，增值税小规模、企业所得税 A 类、文化事业建设费、消费税不再因未申报状态被流程阻断。
- 为上述税种补齐未申报填表页左侧表单关键字，复用“进入填表页 -> 选择目标表单 -> 确认目标表 -> 抽取字段/PDF”的流程。
- 目标页确认逻辑从只校验增值税一般纳税人扩展到所有支持未申报页的税种，降低截错表、解析错表风险。
- 更新消费税和未申报表单切换相关单元测试。
- 同步更新 `DECISIONS.md` 和 `TASKS.md`，记录“非残保金税种未申报验证复用同一填表页策略”。

验证：
```powershell
$env:PYTHONPYCACHEPREFIX='runtime\pycache_compile'; .\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_detail_form_switching.py tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
```

结果：
- 上述单元测试均通过。
- 常规 `compileall` 首次写入既有 `scripts\__pycache__` 时被 Windows 占用拦截，已改用独立 `PYTHONPYCACHEPREFIX` 完成编译校验。

残余风险：
- 本次按业务确认复用同一未申报页面结构；如果某省某税种真实入口 URL、按钮文案或菜单结构不同，会在目标表单确认阶段失败，需要按失败页面片段继续补充选择器。

## 2026-06-02：修复山东未申报增值税表单入口与附表切换确认

修改内容：
- `scripts/compare_tax_forms.py` 中未申报增值税页面不再把山东入口页的“销售额/税费计算信息”误判为正式报表页。
- 发现“我要填表/填写申报表”按钮时优先点击进入正式报表列表，再执行主表/附表切换。
- 左侧菜单定位从一次性查找改为等待菜单稳定，并在失败时输出实际可见菜单文本。
- 目标表确认从“全页面包含关键词”改为“激活菜单 + 正文区域或足够业务字段确认”，避免左侧菜单文字导致附表误判、截图仍停留在主表。
- 税局页复用逻辑跳过 `loginb` 首页，避免复用已失效首页后进入申报页跳回统一登录。
- 更新 `tests/unit/test_detail_form_switching.py`，覆盖跳过 `loginb`、复用真实详情页的场景。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_vat_appendix5_extraction.py
.\.venv\Scripts\python.exe tests\unit\test_vat_main_web_value_rules.py
.\.venv\Scripts\python.exe main.py --task-id 2076263982479497705 --targets auto --cdp-port 9222 --user-data-dir browser_profile\etax_compare_forms --plugin-path C:\Users\Administrator\Downloads\EtaxPlugin --log-level INFO --tax-timeout 600 --tax-login-strategy direct_first --browser-lock-timeout 3600
```

真实验证结果：
- `2076263982479497705` 的增值税一般纳税人主表、附表一、附表二、附表三、附表四、附表五均已正确进入目标表后生成 PDF/Excel/JSON。
- 上述 6 张增值税表字段比对均为 `100%`。
- 后续流程在 `culture_fee_main` 停止，原因是该 task 的当期标记为未申报，但文化事业建设费未申报税局页面策略尚未实现；这与本次增值税主表/附表定位问题无关。

残余风险：
- 山东未申报增值税页面仍依赖真实税局 DOM；如果“我要填表”入口或左侧报表列表结构变化，需要继续补充选择器。
- 文化事业建设费未申报场景需要单独实现税局页面策略。

## 2026-06-01：同步增值税一般纳税人主表 32 行本年累计规则到正式目录

修改内容：
- `scripts/compare_tax_forms.py` 中新增 `qmwjse_ybxm_bnlj` 强制扣减本月数规则。
- 主表 32 行“期末未缴税额(多缴为负数)”本年累计网页值按 `qmwjse_ybxm_bnlj - qmwjse_ybxm_bys` 计算，即使结果为负数也参与比对。
- 更新 `tests/unit/test_vat_main_web_value_rules.py`，覆盖累计值小于本月数时仍应得到负数的场景。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_vat_main_web_value_rules.py
.\.venv\Scripts\python.exe tests\unit\test_vat_main_web_value_rules.py
```

风险：
- 该规则仅作用于增值税一般纳税人主表 `qmwjse_ybxm_bnlj`，不影响 `qcwjse_ybxm_bnlj` 和 `qmldse_ybxm_bnlj` 的既有特殊规则。

## 2026-06-01：同步汇算清缴残保金查询修复到正式目录

修改内容：
- 将海南年度企业所得税申报查询的 Vue 调用改为 `DescribeSbmxcx2(formData)`，并保留“申报表种类=全部、结果中筛选 A100000”的查询策略。
- 汇算清缴残保金报告改为“不区分申报状态”，覆盖矩阵中 `CBJ_PERSONAL` 和 `CBJ_ANNUAL` 使用 `any` 单一目标，不再拆成已申报/未申报。
- 同步更新正式目录中的覆盖分析、后台补齐、批量汇总展示和相关单元测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q src\cbj\verification.py src\coverage scripts\batch_collect_verify.py tests\unit\test_cbj_verification.py tests\unit\test_coverage_framework.py tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_cbj_verification.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
```

风险：
- 已启动的旧批次进程不会自动加载新代码，需要重启工作台或重新跑批次。

## 2026-06-01：操作台增加“跳过后台补齐”选项

修改内容：
- `scripts/ops_console.py` 在任务参数区新增“跳过后台补齐”勾选项。
- 勾选后，操作台启动新批次、继续批次、单税号重验、重新取数等动作都会向批量脚本传递 `--skip-coverage-supplement`。
- `tests/unit/test_ops_console.py` 增加命令拼装断言，覆盖新批次和已有批次场景。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py
.\.venv\Scripts\python.exe tests\unit\test_ops_console.py
```

残余风险：
- 该选项只控制后台补齐阶段，不影响正常易代账发起取数、taskId 查询和已解析 taskId 的验证。

## 2026-06-01：修复山东/青岛税局路由和山东未申报增值税页面识别

修改内容：
- `src/login/task_login_flow.py` 增加任务省份归一化：后台返回 `shandong` 但税号登记机关为 `3702` 时，自动按 `qingdao` 构造 tpass、etax 和 cookie payload，避免青岛税号误进山东税局后长期停在 `/loading`。
- `scripts/compare_tax_forms.py` 在登录后使用修正后的 `info.province` 继续后续申报查询或未申报页面导航，避免前后省份不一致。
- `scripts/compare_tax_forms.py` 增强未申报增值税页面准备逻辑：支持页面已在申报表视图、更多填报/办理/进入按钮文案、更多菜单组件样式，并在目标表未确认时直接失败且输出页面文本片段。
- `scripts/compare_tax_forms.py` 新增山东实测场景处理：后台日志为 `current-period=false` 但税局未申报入口提示“本属期已申报增值税”时，自动切回已申报查询流程。
- `tests/unit/test_task_login_flow.py` 增加青岛税号路由和登录 URL payload 覆盖测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py src\login\task_login_flow.py tests\unit\test_task_login_flow.py
.\.venv\Scripts\python.exe tests\unit\test_task_login_flow.py
.\.venv\Scripts\python.exe tests\unit\test_shanxi_query_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_vat_main_web_value_rules.py
```

残余风险：
- 已尝试用青岛 taskId `2075110453042970385` 做真实复测，原 `/loading` 问题已变为正确进入 `qingdao` 统一登录域名，但青岛统一登录页未自动完成跳转，仍需继续定位青岛登录态。
- 山东济南 taskId `2075110453042966931` 真实复测已能识别“未申报标记与税局已申报提示冲突”并自动回退；但回退申报查询时山东税局入口跳回统一登录页，属于申报查询/数字账户认证失效，需后续处理。
- 山东未申报页面仍依赖真实税局 DOM；本次已把失败从“误继续截图/解析”改为“目标表未确认即失败并带页面片段”，后续遇到新 DOM 可按片段快速补选择器。

## 2026-06-01：残保金覆盖目标不再区分已申报/未申报

修改内容：
- `src/coverage/registry.py` 中 `CBJ_PERSONAL` 和 `CBJ_ANNUAL` 覆盖目标改为每类只生成一个“已验证”目标，不再生成未申报缺口。
- `src/coverage/supplement.py` 中后台补齐残保金候选不再要求解析申报状态；只要后台成功任务匹配残保金类型，就可以作为候选进入后续验证。
- 更新覆盖框架测试，确保 `CBJ_PERSONAL:unfiled` 和 `CBJ_ANNUAL:unfiled` 不再出现在覆盖矩阵。

验证：
```powershell
python -m compileall -q src\coverage tests\unit\test_coverage_framework.py scripts\batch_collect_verify.py
python tests\unit\test_coverage_framework.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_batch_handling_info.py
```

风险：
- 内部 target key 仍复用 `filed` 表示“已完成验证/已取数”，但对外展示为“已验证”；如果后续要完全去掉内部 `filed` 语义，需要扩展覆盖状态枚举。

## 2026-06-01：全量批次验证监控记录

执行内容：
- 使用前置 10 个税号重新跑 `202605` 批量完整链路，批次号 `ops_20260601_codex_full_monitor_1300`。
- 监控易代账取数、taskId 查询、税局验证、残保金验证和后台覆盖补齐全过程。

结果：
- 批量汇总页已生成：`output\batch_runs\ops_20260601_codex_full_monitor_1300\batch_summary.html`。
- 四川 `9151010545210680X0` 与河北 `91131102MA07X9YW6M` 的未申报增值税附表实际 JSON 均已正确切表，附表五 `web_missing=0`。
- 四川仅剩主表 `qmwjse_ybxm_bnlj` 真实字段差异。
- 河北存在主表 10 个真实差异、附表二 3 个真实差异。
- 上海消费税 `91310104MABT0TRL66` 易代账取数长期停留 `COLLECTING`，最终标记需人工介入。
- 河南年度残保金 `91410105MACWB5X52Y` 登录税局成功，但 A100000 查询返回 0 行。
- 后台补齐找到并验证了增值税一般纳税人已申报代表任务 `91610112MAK8FPYQX6 / 2075110487404909007`。

发现问题：
- 批量状态和结果页的“需处理原因”会读取同一 taskId 报告目录内历史旧报告，导致四川/河北显示旧的“网页缺失”原因；最新 JSON 结果并无这些缺失。
- 覆盖补齐查询阶段缺少进度日志，查询期间看起来像卡住。
- 取数轮询阶段会重复给已终态“无需取数”的税号写事件，造成事件日志噪声。

后续建议：
- 批量汇总原因只读取当前批次记录的 `summaryPath` 或本次运行时间戳对应报告，避免历史报告污染。
- 覆盖补齐阶段增加每个缺口的查询开始、命中数量、耗时和失败原因日志。
- 取数轮询只更新仍未终态的税号。

## 2026-06-01：修复未申报增值税附表解析覆盖率低

修改内容：
- 登录四川税局复现 `9151010545210680X0` 未申报增值税任务，定位低覆盖根因：未申报页左侧菜单会把父级菜单误当成目标表，导致附表证据仍停留在主表。
- 未申报增值税附表切换改为只点击叶子菜单，并在提取/PDF 前校验当前激活菜单和页面正文同时匹配目标表。
- 附表五解析兼容税局行式文本：把“请选择”和减免性质代码文本作为占位列处理，避免列错位。
- 附表五对税局未渲染的不适用零值行/区块归一为 `0.00`；如果页面出现对应标签但读不到值，仍保留为解析问题。
- 自动关闭附表五只读提示弹窗，避免覆盖截图和正文读取。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_vat_appendix5_extraction.py
.\.venv\Scripts\python.exe tests\unit\test_vat_appendix5_compare_policy.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe main.py --task-id 2075110435864476047 --targets vat_general_appendix5 --log-level INFO --tax-timeout 180 --skip-pdf
.\.venv\Scripts\python.exe main.py --task-id 2075110435864476047 --targets vat_general_main,vat_general_appendix1,vat_general_appendix2,vat_general_appendix3,vat_general_appendix4,vat_general_appendix5 --log-level INFO --tax-timeout 240 --skip-pdf
```

真实验证结果：
- 附表一至附表五均已正确切换目标表。
- 附表五从 `8/18`、`web_missing=10` 修复为 `18/18`、`web_missing=0`、通过率 `100%`。
- 整套增值税仍有主表字段 `qmwjse_ybxm_bnlj` 1 个差异，属于字段值差异，不是本次低覆盖解析问题。

风险：
- 附表五“不适用零值行”只在同表已解析到有效网格行、且页面完全没有对应标签时才补零；若后续省份展示方式变更，需要继续补充样例测试。

## 2026-05-29：操作台新增需要覆盖税种勾选项

修改内容：
- 本地操作台任务参数新增“需要覆盖税种”勾选项，默认全选项目当前支持的税种。
- 操作台启动、续跑、单税号重试都会把勾选结果传给批量脚本。
- 批量脚本新增 `--coverage-tax-types` 参数，并把选择写入批次 `state.json`。
- 覆盖矩阵、覆盖缺口、后台补齐和汇总页只按本批次选择的税种计算。
- 覆盖注册表支持按税种筛选目标，补充相关单元测试。
- `AGENTS.md` 补充批量命令的覆盖税种限定参数说明。

验证：
```powershell
python -m compileall -q scripts\ops_console.py scripts\batch_collect_verify.py src\coverage tests\unit\test_ops_console.py tests\unit\test_batch_handling_info.py tests\unit\test_coverage_framework.py
python tests\unit\test_ops_console.py
python tests\unit\test_batch_handling_info.py
python tests\unit\test_coverage_framework.py
python -m compileall -q main.py scripts src
```

风险：
- 当前勾选项控制“覆盖统计和后台补齐范围”，不改变易代账发起取数时的税种列表；如需按勾选项减少取数税种，需要单独增加取数税种映射规则。

## 2026-05-29：消费税自动取数补充 taxTypeId=30

修改内容：
- 自动发起易代账取数任务的默认税种列表新增 `30`，覆盖当前消费税账号返回的实际税种 ID。
- 覆盖补齐注册表中消费税后台税种 ID 从仅 `29` 调整为兼容 `29` 和 `30`，保留历史任务兼容性。
- 更新单元测试，确保默认取数列表包含 `30` 且继续排除社会保险费 `40`，并确保覆盖补齐目标包含消费税两个后台税种 ID。

验证：
```powershell
python -m compileall -q src\ydz\models.py src\coverage\registry.py tests\unit\test_ydz_collector.py tests\unit\test_coverage_framework.py
python tests\unit\test_ydz_collector.py
python tests\unit\test_coverage_framework.py
```

风险：
- 未实际重新发起真实消费税取数任务；真实环境仍需用 `91310104MABT0TRL66` 跑一遍批量链路确认后台能生成并解析 taskId。

本文件记录 Codex/AI agent 对项目的改动摘要。每次完成任务后追加或整理记录，保证项目记忆不依赖聊天历史。

## 2026-05-29：批量结果页覆盖展示改为全量矩阵

修改内容：
- 批量汇总页“覆盖缺口说明”改为“税种覆盖说明”，展示项目支持的每个税种和申报状态。
- 覆盖表新增“覆盖情况、代表税号、taskId、未覆盖原因”列，已覆盖和未覆盖都直接展示。
- 已覆盖目标展示代表任务链接；未覆盖目标保留后台补齐原因。
- 已用最新渲染逻辑重新生成 `output/batch_runs/ops_20260529_153932/batch_summary.html`。

验证：
```powershell
python -m compileall -q scripts\batch_collect_verify.py tests\unit\test_batch_summary_rendering.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_coverage_framework.py
```

风险：
- 该改动只影响 HTML 展示，不改变覆盖分析、后台补齐和验证逻辑。

## 2026-05-29：全局按接口返回字段比对

修改内容：
- 所有税种、所有表单比对前按接口结果 key 过滤字段，只保留接口实际返回的字段。
- 接口未返回的字段不进入总字段数、不统计为接口缺失，也不会进入批量差异明细。
- 增值税一般纳税人主表 `qcwjse_ybxm_bnlj` 网页值改为直接取同名位置，不再减去本月数。
- 增值税一般纳税人主表 `qmldse_*` 网页值改为使用 `sqldse_*` 同列值替换后再与接口比对，覆盖一般项目和即征即退项目的本月数、本年累计。
- 新增单元测试覆盖全局“网页有值但接口未返回时忽略该字段”的规则，以及 `qcwjse_ybxm_bnlj`、`qmldse_*` 主表网页取值规则。
- 更新 `DECISIONS.md` 记录该业务取舍。

验证：
```powershell
python -m compileall -q scripts\compare_tax_forms.py tests\unit\test_vat_main_web_value_rules.py tests\unit\test_vat_appendix5_compare_policy.py
python tests\unit\test_vat_main_web_value_rules.py
python tests\unit\test_vat_appendix5_compare_policy.py
python tests\unit\test_normalizer_comparator.py
```

风险：
- 接口返回空值但 key 存在时仍会参与比对，只有接口完全未返回的字段会被忽略。
- 该改动会降低“接口缺失”类问题数量，这是预期行为；后续排查应优先看接口已返回字段的差异。

## 2026-05-28：批量验证耗时优化

优化内容：
- 覆盖补齐后台查询改为按 `backendTaxTypeId` 合并查询。同一个后台税种 ID 只查一次，再按缺口目标的已申报/未申报状态分配候选任务。
- 数字账户等待改为状态驱动：等待过程中如果申报查询页已可用会立即返回；轮询间隔从 1 秒缩短为 0.35 秒，并记录可用耗时。
- 同一申报明细页内优先切换附表：连续同一税种、同一申报查询关键字的详情页目标，优先调用详情页内的主附表选择器；切换失败时回退到原申报查询页打开。

预期收益：
- 覆盖补齐阶段减少重复后台请求。
- 每个税局任务减少固定数字账户等待。
- 单个一般纳税人增值税任务减少多次回申报查询页的耗时。

验证：
```powershell
python -m compileall -q main.py scripts src tests\unit\test_detail_form_switching.py
python tests\unit\test_coverage_framework.py
python tests\unit\test_detail_form_switching.py
python tests\unit\test_batch_handling_info.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_models.py
python tests\unit\test_normalizer_comparator.py
python tests\unit\test_config_loader.py
python tests\unit\test_mapping_loader.py
python tests\unit\test_task_login_flow.py
```

## 2026-05-28：批量链路鲁棒性和覆盖展示修复

问题原因：
- 社会保险费失败被当成整条取数链路失败，导致不该人工介入的税号被阻断。
- `main.py --targets auto` 没有选出任何可验证表单时返回成功，批量页会出现“0 问题”的假成功。
- 个税残保金和汇算清缴残保金共用 `CBJ` 覆盖目标，可能复用 taxItemId=26 的任务覆盖年度残保金。
- 后台补齐没命中时，结果页只显示统计缺口，不显示具体查询原因。

修改内容：
- 社会保险费改为 `ignoredTaxItems` 记录，不再设置 `manualRequired`，也不参与失败原因优先级。
- 无可验证目标时 `compare_tax_forms.run_compare()` 返回非成功码，批量验证显示为“未覆盖/跳过”，不再标记成功。
- 覆盖模型拆分 `CBJ_PERSONAL` 和 `CBJ_ANNUAL`，年度残保金只匹配 taxItemId=31。
- 后台补齐增加诊断信息，记录每个缺口查询的后台 taxTypeId、查询数量、申报状态解析分布和未命中原因。
- 批量 HTML 增加“覆盖缺口说明”，并输出 `coverage_missing.csv`。
- 新增可选参数 `--reuse-existing-report`，用于明确复用同 taskId 已存在的验证报告以节省时间。

验证：
```powershell
python -m compileall -q main.py scripts src
python tests\unit\test_models.py
python tests\unit\test_normalizer_comparator.py
python tests\unit\test_config_loader.py
python tests\unit\test_mapping_loader.py
python tests\unit\test_ydz_collector.py
python tests\unit\test_batch_handling_info.py
python tests\unit\test_coverage_framework.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_cbj_verification.py
python tests\unit\test_ops_console.py
```

## 2026-05-08：创建项目协作文档

新增：

- `AGENTS.md`
- `PROJECT_CONTEXT.md`
- `ARCHITECTURE.md`
- `DECISIONS.md`
- `TASKS.md`
- `PLANS.md`
- `CHANGELOG_AI.md`

目的：

- 固化 AI agent 工作规则。
- 记录项目背景、架构、入口、任务优先级和后续计划。
- 明确 `main.py` 是推荐入口，真实 taskId 流程复用 `scripts.compare_tax_forms.run_compare()`。

## 2026-05-09 至 2026-05-12：真实链路和残保金验证增强

主要变化：

- 统一真实入口，避免双主线维护。
- 易代账自动登录、账套查找、发起取数任务、后台查询 taskId 的方案逐步落地。
- 完整链路支持批量发起取数后验证。
- 修复多省电子税局登录、重复打开页面、数字账户失效、申报查询导航等问题。
- 新增残保金验证逻辑：
  - 个税残保金检查后台字段 `snzzzgrs_cbj`、`snzzzggzze_cbj`。
  - 汇算清缴残保金进入税局年度企业所得税申报查询并与后台字段比对。

验证摘要：

- 多个真实 taskId 和税号跑过完整链路。
- 新增残保金相关单元测试和真实任务验证。

## 2026-05-26：第一阶段运营工作台

新增：

- `scripts/ops_console.py`
- `tests/unit/test_ops_console.py`
- `OPERATOR_GUIDE.md`

行为：

- 新增本地运营工作台，默认地址 `http://127.0.0.1:8765/`。
- 支持填写税号、所属期、企业、验证范围，并启动完整链路、只取数、只验证已有任务。
- 后台仍调用 `scripts/batch_collect_verify.py`，不新增第二套生产验证逻辑。
- 新增环境检查：项目文件、Python、Chrome、EtaxPlugin、CDP、易代账凭据、代理、输出目录、运行任务。
- 任务记录写入 `runtime/ops_console`，批量结果写入 `output/batch_runs`。

验证：

```powershell
python -m compileall -q main.py scripts src
python tests\unit\test_ops_console.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_batch_handling_info.py
```

## 2026-05-28：接入覆盖缺口后台补齐验证链路

问题原因：
- 之前只生成 `coverage_status.json` 和 `coverage_matrix.csv`，没有在批量主流程中调用后台补齐查询。
- 因此未覆盖税种/申报状态只会被标记为缺口，不会自动到后台查代表任务并继续验证。

修改内容：
- 批量验证结束前自动分析覆盖缺口。
- 对缺口税种/申报状态调用后台任务查询，筛选任务类型为取数、状态为成功、创建时间为当月 1 日至当前时间的代表任务。
- 找到代表任务后写入 `state.json`，再复用现有 `run_verify_phase()` 继续验证。
- 如果同一税号已有不同 taskId，不覆盖原记录，新增一个覆盖补齐项，避免丢失原验证结果。
- `coverage_status.json` 增加本次后台补齐状态、原因、候选数量和已应用项。
- 新增参数 `--skip-coverage-supplement` 用于显式跳过后台补齐。

验证：
```powershell
python -m compileall -q main.py scripts src
python tests\unit\test_coverage_framework.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_ops_console.py
python tests\unit\test_batch_handling_info.py
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_task_execution_log.py
python tests\unit\test_consumption_tax_support.py
```

## 2026-05-26：运营工作台凭据和监控闭环

行为：

- 工作台任务参数新增“易代账账号/密码”临时输入。
- 凭据仅传给当前批量任务子进程环境变量，不写入展示命令和任务记录。
- 批量脚本同步生成 `ops_status.json`，并将关键阶段写入 `ops_events.jsonl`。
- 工作台新增税号进度表，展示税号、地区、企业、阶段、状态、taskId、原因和操作。
- 新增继续未完成、继续验证、重试取数、跳过、重新生成汇总页等操作。
- 停止任务改为 Windows 进程树终止。

验证：

```powershell
python -m compileall -q main.py scripts src
python tests\unit\test_ops_console.py
python tests\unit\test_batch_handling_info.py
```

## 2026-05-26：运营问题处理闭环

行为：

- 新增 `ops_review.json`，保存字段差异的处理状态、处理人、备注和更新时间。
- 工作台新增“问题处理”视图。
- 证据链接自动匹配单 taskId 报告目录中的 HTML、PDF、接口填充 Excel。
- 新增问题清单导出，优先 `.xlsx`，失败时回退 `.csv`。
- 最近批次列表增加“已处理”数量。

验证：

```powershell
python -m compileall -q main.py scripts src
python tests\unit\test_ops_console.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_batch_handling_info.py
```

## 2026-05-26：批量汇总展示优化

行为：

- 批量 HTML 删除低价值统计模块。
- 差异明细改为按表单分组，同时按账户分组。
- 税种概览只显示被校验税种及已申报/未申报状态。
- 需处理原因只展示最直接人工处理原因，不展示冗长取数响应。

验证：

```powershell
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_batch_handling_info.py
```

## 2026-05-26：覆盖补齐基础框架

新增：

- `src/coverage/models.py`
- `src/coverage/registry.py`
- `src/coverage/analyzer.py`
- `src/coverage/supplement.py`
- `scripts/coverage_check.py`
- `tests/unit/test_coverage_framework.py`

行为：

- 登记当前支持税种：增值税一般纳税人、增值税小规模、企业所得税 A 类、文化事业建设费、残保金。
- 每个税种默认要求覆盖已申报和未申报。
- 批量汇总生成 `coverage_status.json` 和 `coverage_matrix.csv`。
- 工作台新增“覆盖检查”视图和 `/api/coverage`、`/api/analyze-coverage` 接口。
- 后台补齐候选任务骨架可将代表 taskId 写入批量 state，后续复用 `--skip-collect --verify`。

验证：

```powershell
python -m compileall -q main.py scripts src
python tests\unit\test_coverage_framework.py
python tests\unit\test_ops_console.py
python scripts\coverage_check.py --run-dir output\batch_runs\ops_20260526_105422
```

## 2026-05-26：后台任务查询与任务执行日志规则

新增/修改：

- `src/chanjet_admin/task_query.py`
- `src/chanjet_admin/task_execution_log.py`
- `src/coverage/supplement.py`
- `scripts/compare_tax_forms.py`
- `tests/unit/test_chanjet_admin_task_query.py`
- `tests/unit/test_task_execution_log.py`

行为：

- 后台 `getTaskListInternal` 查询能力扩展为按时间、税号、所属期、税种、任务状态查询。
- 新增任务执行日志查询封装，读取 `tTaskExecutionLog/getPageListByTaskId`。
- 增值税申报状态规则：

```text
logType = 成功保存数据-是否是当期
logInfo = true  -> 已申报
logInfo = false -> 未申报
```

- 已查询 taskId `2071433368332666061`，匹配 `logInfo=true`，判定为已申报。
- `scripts/compare_tax_forms.py` 和覆盖补齐逻辑复用同一日志解析封装。

验证：

```powershell
python -m compileall -q main.py scripts src
python tests\unit\test_task_execution_log.py
python tests\unit\test_coverage_framework.py
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_ops_console.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_batch_handling_info.py
```

## 2026-05-26：项目管理长期记忆体系整理

文件：

- `AGENTS.md`
- `PROJECT_CONTEXT.md`
- `ARCHITECTURE.md`
- `DECISIONS.md`
- `TASKS.md`
- `PLANS.md`
- `CHANGELOG_AI.md`

行为：

- 将根目录 7 个项目管理文件整理为长期项目记忆。
- 明确每次任务开始前的阅读顺序和完成后的更新要求。
- 固化仓库结构、运行入口、验证命令、安全边界和完成标准。
- 将当前对话中形成的易代账、批量验证、运营台、覆盖补齐、残保金、任务执行日志规则写入项目文档。

验证：

- 文档-only 修改，未运行代码测试。

## 2026-05-28：新增消费税两张表验证

修改内容：
- 新增消费税税种 `CONSUMPTION_TAX`。
- 新增两个真实验证目标：
  - `consumption_tax_main`：消费税及附加税费申报表，对应接口 `sz_xfs.xfszb_qc`。
  - `consumption_tax_surcharge`：消费税附加税费计算表，对应接口 `sz_xfs.xfsfb1_qc`。
- `--targets auto` 支持根据 `sz_xfs` 自动选择消费税两张表。
- 增加消费税专用网页解析，处理商品行、汇总行、附加税费行和减征比例列位。
- Excel 读取增加兼容层，处理用户提供消费税工作簿中的 openpyxl 不兼容保护属性。
- 后台 taskId API 和 `getClientJob` 在 Python requests 出现 SSL EOF 时增加 curl 兜底。
- 覆盖注册表加入消费税，后台税种 ID 为 `29`。

验证：
- `python -m compileall -q main.py scripts src`
- `python tests\unit\test_consumption_tax_support.py`
- `python tests\unit\test_coverage_framework.py`
- `python tests\unit\test_task_login_flow.py`
- `python tests\unit\test_api_client.py`
- `python main.py --task-id 2068825812082982843 --targets auto --skip-browser --log-level INFO`
- `python main.py --task-id 2068825812082982843 --targets auto --log-level INFO`

真实验证结果：
- 税号：`92320681MADFU3EX54`
- taskId：`2068825812082982843`
- 自动选择目标：`consumption_tax_main`, `consumption_tax_surcharge`
- 消费税及附加税费申报表：差异 0，网页缺失 0。
- 消费税附加税费计算表：差异 0，网页缺失 0。
- 汇总报告：`output/reports/2068825812082982843/compare_summary_2068825812082982843_20260528_105441.html`

风险：
- 消费税未申报页面策略尚未接入。
- 当前消费税 Excel 仍引用微信文件目录中的原始文件名，后续建议迁移到 `mappings/id_workbooks/` 形成稳定文件名。
- 当前环境访问后台接口时 Python requests 存在 SSL EOF，已用 curl 兜底，但长期应统一网络访问封装。

## 2026-05-28：批量链路鲁棒性问题修复

修改内容：
- 批量取数默认税种补齐消费税和汇算清缴残保金，仍过滤社会保险费。
- 取数阶段发现社会保险费失败时，直接标记需人工处理，避免长时间轮询。
- 批量任务增加网络预检，提前识别代理/VPN/证书类网络阻断。
- 税局登录默认改为直连 tpass 优先，插件打开作为兜底，减少固定等待。
- 残保金自动模式按后台税种 ID 区分个税残保金和汇算清缴残保金，汇算清缴未查到年度申报记录时不再静默回退。
- 覆盖矩阵 CSV 输出修正为驼峰字段，避免税种、地区、申报状态列为空。
- 批量展示页补充消费税、残保金税种识别，差异字段去重，并用更直接的原因展示接口缺失、网页有值等问题。

未修改：
- 未处理“失败 taskId 是否继续进入验证”的第二个问题，保持现有行为。

验证：
```powershell
python -m compileall -q main.py scripts src
python tests\unit\test_ydz_collector.py
python tests\unit\test_batch_handling_info.py
python tests\unit\test_coverage_framework.py
python tests\unit\test_ops_console.py
python tests\unit\test_cbj_verification.py
python tests\unit\test_task_login_flow.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_consumption_tax_support.py
python tests\unit\test_models.py
python tests\unit\test_normalizer_comparator.py
python tests\unit\test_config_loader.py
python tests\unit\test_mapping_loader.py
python tests\unit\test_vat_main_web_value_rules.py
python tests\unit\test_vat_appendix3_extraction.py
python tests\unit\test_vat_appendix5_extraction.py
python tests\unit\test_api_client.py
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_task_execution_log.py
python tests\unit\test_shanxi_query_recovery.py
```

## 2026-05-28：批量结束页展示税号对应 taskId

修改内容：
- 批量汇总 HTML 的“税号 × 表单矩阵”新增显式 `taskId` 列。
- 差异明细按账户分组的行中同步展示 `taskId=...`，便于运营人员从差异直接定位后台任务。
- 补充单元测试覆盖最终汇总页 taskId 展示。

验证：
```powershell
python -m compileall -q main.py scripts src
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_ops_console.py
python tests\unit\test_batch_handling_info.py
```
## 2026-05-28：批量验证监控问题修复

修改内容：
- 批量状态文件 `state.json`、`batch_summary.json`、`ops_status.json` 改为临时文件写入后原子替换，并增加重试，避免一次写文件异常中断整批任务。
- `ops_events.jsonl` 写入失败改为记录警告，不影响主流程。
- 残保金自动识别改为必须由覆盖补齐目标、后台税种 ID 或已完成的残保金税种项明确触发；`NOT_COLLECTED` 的残保金税种项不再抢占普通增值税验证链路。
- 有汇总报告但存在差异时，批量结果原因改为从比对 JSON 生成“表单：不一致/接口缺失/网页缺失”摘要，不再使用 `Playwright stopped` 等无意义尾日志。
- 数字账户等待增加页面 loading 检测和 12 秒软超时；检测不到可用状态时提前进入申报查询直连兜底，减少固定等待。

验证：
```powershell
python -m compileall -q main.py scripts src tests\unit\test_batch_handling_info.py tests\unit\test_shanxi_query_recovery.py
python tests\unit\test_batch_handling_info.py
python tests\unit\test_shanxi_query_recovery.py
python tests\unit\test_coverage_framework.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_task_login_flow.py
python tests\unit\test_detail_form_switching.py
python tests\unit\test_models.py
python tests\unit\test_normalizer_comparator.py
python tests\unit\test_config_loader.py
python tests\unit\test_mapping_loader.py
```

风险：
- 数字账户软超时会更早进入申报查询直连兜底；如果个别省份必须完整等待数字账户初始化，仍依赖后续原有查询页等待和恢复逻辑兜底。
- 残保金年度任务如果后台没有明确税种项或覆盖补齐标记，需要后续补充任务结果 JSON 中更稳定的判定字段。

## 2026-05-28：同批次 taskId 去重与税局页面复用隔离

修改内容：
- 批量验证在单次运行内记录已经执行过验证的 `taskId`，即使启用 `--rerun-verified`，同一个 `taskId` 在同一批次也只执行一次。
- 重复命中的税号会标记为 `skipped`，原因显示为“同一批次已验证相同 taskId，已跳过重复执行。”，避免重复打开税局、重复生成报告。
- 从接口返回的 `paramJson` 中提取当前任务税号，税局页面复用时必须确认页面正文包含该税号。
- 如果无法确认当前页面属于目标税号，则不复用已有税局页，改走任务登录流程，避免同省不同税号误用同一个税局页面。
- 补充单元测试覆盖同批次 taskId 去重、税局页按税号匹配复用、接口税号提取。

验证：
```powershell
python -m compileall -q main.py scripts src tests\unit\test_batch_handling_info.py tests\unit\test_detail_form_switching.py
python tests\unit\test_batch_handling_info.py
python tests\unit\test_detail_form_switching.py
python tests\unit\test_models.py
python tests\unit\test_normalizer_comparator.py
python tests\unit\test_config_loader.py
python tests\unit\test_mapping_loader.py
git diff --check -- scripts\batch_collect_verify.py scripts\compare_tax_forms.py tests\unit\test_batch_handling_info.py tests\unit\test_detail_form_switching.py
```

风险：
- 税局页面正文不展示税号时，本次策略会放弃复用并重新登录，速度略慢，但可以避免跨税号数据串用。
- 同一批次内同一个 `taskId` 失败后不会被再次自动重复验证；如果后续需要“失败任务可重试一次”，应单独加入受控重试策略。

## 2026-05-28：覆盖缺口展示改为中文可读标签

修改内容：
- 批量结果页“覆盖缺口说明”不再展示 `VAT_GENERAL:unfiled` 这类内部目标 key，只展示中文税种和中文申报状态。
- 后台补齐状态从 `no_candidates/not_run/verified` 等内部值改为中文。
- 申报状态解析分布从 `{'unknown': 33, 'filed': 3}` 改为“未知：33 个；已申报：3 个”。
- 补充单元测试防止覆盖缺口表格再次暴露内部 key。

验证：
```powershell
python -m compileall -q scripts\batch_collect_verify.py tests\unit\test_batch_summary_rendering.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_coverage_framework.py
```

风险：
- JSON/CSV 仍保留内部 key 供排查和程序读取；本次只调整 HTML 面向运营人员的展示。
## 2026-05-29：修复后台补齐失败时 diagnostics 未初始化

修改内容：
- `run_coverage_supplement_phase()` 在后台任务查询前初始化 `diagnostics` 和 `candidates`。
- 当畅捷通后台未登录、缺少 public-manage token、或后台查询失败时，覆盖补齐会记录失败状态并生成汇总，而不是抛出 `UnboundLocalError`。
- 补充单元测试覆盖后台补齐查询异常场景。

验证：
```powershell
python -m compileall -q scripts\batch_collect_verify.py tests\unit\test_batch_handling_info.py
python tests\unit\test_batch_handling_info.py
```

风险：
- 该修复只处理异常兜底。真实补齐仍要求 Chrome 中已登录畅捷通后台 `public-manage.chanjet.com`。

## 2026-05-29：运维工作台兼容缺失批次状态文件

修改内容：
- 运维工作台查询批次状态、覆盖情况、问题处理清单时，如果批次目录存在但 `state.json` 缺失，返回“批次文件缺失”的空状态。
- 避免新机器首次部署或失败残留批次导致 HTTP 线程反复打印 `FileNotFoundError`。
- 补充单元测试覆盖缺失 `state.json` 的状态、覆盖、问题接口。

验证：
```powershell
python -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py
python tests\unit\test_ops_console.py
```

风险：
- 该修复只影响运维页面容错展示，不会恢复已经缺失的批次数据；缺失批次需要重新发起或手工删除残留目录。

## 2026-05-29：修复运维工作台直接运行找不到 src

修改内容：
- `scripts/ops_console.py` 启动时自动把项目根目录加入 Python 导入路径。
- 修复新机器上执行 `python scripts\ops_console.py --open` 报 `ModuleNotFoundError: No module named 'src'` 的问题。

验证：
```powershell
python -m compileall -q scripts\ops_console.py
python scripts\ops_console.py --help
python tests\unit\test_ops_console.py
```

风险：
- 无业务流程变更，只影响脚本启动路径。

## 2026-05-29：整理无影云电脑部署材料

修改内容：
- 新增 `README.md`，说明项目用途、常用入口、运行产物和安全要求。
- 新增 `DEPLOY_WUYING.md`，整理 Windows 无影云电脑部署步骤、推荐目录、初始化、Chrome CDP、运维工作台、验证和常见问题。
- 新增 `scripts/windows/setup_wuying.ps1`，用于创建虚拟环境并安装依赖。
- 新增 `scripts/windows/start_chrome_cdp.ps1`，用于按实际路径启动带税局插件和 CDP 端口的 Chrome。
- 新增 `scripts/windows/start_ops_console.ps1`，用于启动本地运维工作台。
- `requirements.txt` 补充 `playwright`，避免新机器部署后导入浏览器自动化模块失败。

验证：
```powershell
python -m compileall -q main.py scripts src
powershell -NoProfile -Command "<PowerShell 脚本语法解析检查>"
```

风险：
- PowerShell 脚本不会保存账号密码；部署后仍需要在无影云电脑上手工确认 Chrome、EtaxPlugin、易代账、畅捷通后台和税局登录态可用。

## 2026-05-29：运维页面暴露浏览器和税局插件路径

修改内容：
- 运维工作台任务参数新增 `Chrome 路径`、`税局插件路径`、`浏览器数据目录` 三个输入项。
- 环境检查改为使用页面填写的 Chrome、插件、浏览器数据目录路径。
- 批量任务、续跑、单税号重试会把这些路径传给底层批量脚本。
- `batch_collect_verify.py`、`main.py`、`compare_tax_forms.py`、残保金/小规模兼容脚本新增或贯通 `--chrome-path`，保证需要自动拉起 Chrome 时使用页面配置。
- `YdzSession` 支持空 Chrome 路径回退默认值，避免配置为空时启动失败。

验证：
```powershell
python -m compileall -q main.py scripts\ops_console.py scripts\batch_collect_verify.py scripts\compare_tax_forms.py src\ydz\pipeline.py src\ydz\session.py tests\unit\test_ops_console.py
python tests\unit\test_ops_console.py
python scripts\batch_collect_verify.py --help
python main.py --help
python scripts\compare_tax_forms.py --help
python scripts\verify_cbj_task.py --help
python scripts\compare_vat_small_main.py --help
```

风险：
- 如果浏览器已手动启动并连接到同一 CDP 端口，Chrome 路径只用于环境检查和后续需要自动拉起 Chrome 的场景；当前连接优先逻辑不变。

## 2026-05-29：覆盖补齐区分增值税一般纳税人与小规模

修改内容：
- 覆盖补齐查询后台 `taxTypeId=1` 的增值税任务时，新增任务实际类型识别：从任务结果、表单名、字段名中识别一般纳税人或小规模。
- 对 `VAT_GENERAL` / `VAT_SMALL` 缺口，后台候选必须能明确匹配目标类型；识别不出或识别不一致时不再作为代表任务。
- 新增单元测试，防止 `91320118MAEGB3DU35` 这类一般纳税人任务被误用于小规模覆盖缺口。

验证：
```powershell
python -m compileall -q src\coverage\supplement.py tests\unit\test_coverage_framework.py
python tests\unit\test_coverage_framework.py
```

风险：
- 如果后台任务结果 JSON 本身不包含表单名、字段名或纳税人类型标记，增值税覆盖补齐会保守地保留缺口，需要后续补充更稳定的后台字段。

## 2026-05-29：工作台当前任务增加完成标识

修改内容：
- 运维工作台当前任务完成后显示中文状态：运行中、已完成、已失败、已结束或批次文件缺失。
- 当前任务区域新增结束时间、耗时和批次结果摘要，包含税号数、需处理数量、差异数量和异常退出码。
- 后端 `/api/jobs` 返回值补齐 `statusLabel`、`resultLabel`、`durationText` 等字段，前端不再只展示原始 `success/failed` 状态。
- 增加单元测试覆盖完成任务摘要展示字段。

验证：
```powershell
python -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py
python tests\unit\test_ops_console.py
```

风险：
- 如果工作台进程被重启后才发现旧任务已经结束，无法拿到真实退出码，只能显示“已结束”并依赖报告摘要判断结果。

## 2026-05-29：后台补齐排除 mock 且当期判断不再依赖日志编号

修改内容：
- 后台任务列表查询默认增加 `mockFlag=0`，用于覆盖补齐时排除 mock 任务；该字段已通过后台页面抓包确认。
- 当期判断日志改为只匹配日志类型 `成功保存数据-是否是当期`，不再要求 `lsn=sz_zzs`。
- 覆盖补齐、真实 taskId 验证和任务执行日志工具统一使用同一套当期判断规则。
- 更新相关单元测试和项目记忆文件。

验证：
```powershell
python -m compileall -q scripts\compare_tax_forms.py src\chanjet_admin\task_query.py src\chanjet_admin\task_execution_log.py src\coverage\supplement.py tests\unit\test_task_execution_log.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_coverage_framework.py
python tests\unit\test_task_execution_log.py
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_coverage_framework.py
```

风险：
- 本次只调整后台任务列表查询条件；如果后台未来改字段名，需要重新抓包并集中调整 `src/chanjet_admin/task_query.py`。

## 2026-05-29：新增无插件 tpass cookie 注入方案

修改内容：
- `TaskLoginFlow` 注册 document-start 初始化脚本，复刻 EtaxPlugin 在 tpass 页面解析 `cookie=`、写入 cookie/localStorage、设置 `etaxplgin` 和倒计时 cookie 的逻辑。
- `getTaskCookie` 浏览器内请求失败时增加 Python requests 兜底，减少无插件页面环境差异。
- `direct_first` 登录策略不再预先等待插件 bridge；插件事件打开新标签页仅作为 fallback。
- Chrome 自动启动支持 `--plugin-path` 为空、`none`、`disabled`、`false` 或 `0` 时不加载 EtaxPlugin。
- 更新登录流程测试，覆盖初始化脚本注册和 tpass URL cookie payload。
- 更新 `ARCHITECTURE.md`、`DECISIONS.md`、`PLANS.md`，记录插件降级为 fallback 的登录策略。

验证：
```powershell
python -m compileall -q src\login tests\unit\test_task_login_flow.py
python -m compileall -q main.py scripts src
python tests\unit\test_task_login_flow.py
python <临时调用器>  # 直接执行 test_task_login_flow.py 内测试函数
python <Playwright 脚本>  # 无扩展 Chrome 加载初始化脚本，确认浏览器可解析
```

风险：
- 未执行真实 taskId 进税局验证；该验证依赖畅捷通后台登录态、税局登录态和外部页面状态。
- 无插件方案覆盖 cookie/localStorage 注入；若某些省份依赖 EtaxPlugin 的会话续期、特殊跳转或强制进税局弹窗，仍需插件或人工兜底。
## 2026-05-29：监控批量验证并修复申报查询登录态卡点

修改内容：
- 监控批次 `ops_20260529_162547`，确认上海消费税任务 `2074761315154964890` 卡在电子税局申报查询页 `/loading`，且数字账户深链回到 tpass 统一登录页。
- `scripts/compare_tax_forms.py` 新增申报查询认证失效识别：当申报查询 handler 跳回 tpass 登录页时，直接抛出明确的税局登录态/数字账户认证失效原因，不再继续多轮 `/loading` 等待。
- 调整当前页恢复顺序：税局门户菜单恢复失败后优先验证数字账户 handler 是否仍认证有效，再决定是否继续直接查询。
- `scripts/batch_collect_verify.py`、`scripts/ops_console.py` 增加该错误的中文原因归类，方便结果页和工作台展示直接处理原因。
- 补充单元测试覆盖 handler 回到 tpass 时快速失败，以及失败后不再继续直接 loading 重试。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_shanxi_query_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

残余风险：
- 本次已完成批次仍保留旧失败原因；新逻辑从下一次验证开始生效。
- 如果某省份短暂跳回 tpass 后仍可自动恢复，当前策略会保守地标记为需人工重新进入税局/数字账户，以避免整批长时间卡住。
## 2026-06-01：修复易代账签名失效重试并完成一批取数验证

修改内容：
- 监控批次 `ops_20260601_codex_100530`，确认本次不再出现 `invalid signature`。
- `YdzSession` 增加易代账登录态刷新能力：只清理易代账相关页面的 token/signature storage，不影响 public-manage 后台登录态。
- 批量发起取数阶段首次遇到 `invalid signature` 时，自动重新进入易代账并重试当前税号一次。
- 将 `invalid signature` 归类为“易代账登录签名已失效”，便于运营在结果页判断处理动作。
- 补充单元测试覆盖该异常分类。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_ydz_collector.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

真实批次：
- 批次：`ops_20260601_codex_100530`
- 所属期：`202605`
- 汇总页：`output\batch_runs\ops_20260601_codex_100530\batch_summary.html`
- 结果：3 个残保金任务验证成功；2 个增值税任务完成验证但存在网页解析覆盖风险和差异；3 个税号返回无需取数；2 个税号取数长时间未完成需人工确认。

风险：
- 当前只对首次易代账签名失效自动刷新并重试一次。
- 若易代账登录出现验证码、二次确认、企业权限变化，仍需人工介入。
- 本批两个增值税任务的附表一、附表二、附表三网页解析覆盖率为 0，需要后续专项排查页面打开或附表切换逻辑。
## 2026-06-01：修复企业所得税覆盖补齐未识别未申报任务

修改内容：
- 定位 taskId `2075110904014780643` 未被识别的原因：覆盖补齐只对增值税读取 `成功保存数据-是否是当期` 日志，企业所得税直接返回 `unknown`。
- 将执行日志兜底判断扩展到企业所得税、文化事业建设费、消费税、汇算清缴残保金等需要申报状态的税种。
- 保留个税残保金不使用该日志兜底，避免误判非申报状态任务。
- 增加单元测试，覆盖企业所得税日志 `false` 判定为未申报。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_task_execution_log.py
.\.venv\Scripts\python.exe -m compileall -q src\coverage\supplement.py tests\unit\test_coverage_framework.py
```

补充验证：
- 直接读取 taskId `2075110904014780643` 的任务执行日志，`成功保存数据-是否是当期` 解析结果为 `false`。
- 修复后该 taskId 在企业所得税未申报目标下解析为 `unfiled`。

风险：
- 已生成的批次报告不会自动回写，需要重新跑覆盖补齐或重新跑批次后才会展示为已补齐。
## 2026-06-01：修复后台补齐 token 读取和税种误匹配

修改内容：
- `src/chanjet_admin/task_query.py` 读取 public-manage token 时增加页面稳定等待和重试，避免页面刷新导致 `Execution context was destroyed` 后整个补齐阶段失败。
- 后台任务查询增加客户端税种强校验：只接受 `taskTaxRelVOList.tTaxTypeId`、`taxTypeIds` 等字段真实包含目标税种 ID 的任务。
- 税种补齐查询支持翻页扫描；覆盖补齐默认 page size 从 50 调整为 500，降低有效任务在深页时漏查的概率。
- 补充单元测试覆盖 public-manage 页面导航中断重试，以及后台接口未按税种过滤时的客户端翻页过滤。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_chanjet_admin_task_query.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe -m compileall -q scripts\batch_collect_verify.py src\chanjet_admin\task_query.py src\coverage\supplement.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_coverage_framework.py
```

真实补齐验证：
```powershell
.\.venv\Scripts\python.exe scripts\batch_collect_verify.py --run-id ops_20260601_codex_100530 --period 202605 --enterprise 蓝天之爱 --skip-collect --verify --reuse-existing-report --skip-browser --targets auto --log-level INFO ...
```

结果：
- 后台补齐阶段成功找到 2 个代表任务。
- 企业所得税（A类）未申报补齐命中 taskId `2075110904014780643`。
- 文化事业建设费未申报补齐命中 taskId `2076005000243040722`。
- 不再出现 public-manage `Execution context was destroyed` 导致的补齐阶段失败。

风险：
- 后台接口当前仍不可靠支持服务端税种过滤，因此客户端翻页扫描会增加耗时。
- 本次真实补齐验证使用 `--skip-browser`，只验证了后台补齐查询和接口侧验证入口，未重新进入税局完成真实页面校验。
## 2026-06-01：增值税后台补齐按企业性质筛选

修改内容：
- 抓包确认后台任务列表企业性质筛选字段为 `taxPayerType`，一般纳税人为 `NORMAL_TAXPAYER`，小规模为 `SMALL_TAXPAYER`。
- `src/chanjet_admin/task_query.py` 支持传入 `taxpayer_type`，请求 payload 写入 `taxPayerType`，并对返回任务继续做客户端企业性质、税种、状态二次校验。
- `src/coverage/registry.py` 为 `VAT_GENERAL` 和 `VAT_SMALL` 登记对应后台企业性质。
- `src/coverage/supplement.py` 将后台补齐查询从“按税种 ID 合并”调整为“按税种 ID + 企业性质合并”，并用任务行 `taxPayerType` 识别增值税一般人/小规模。
- 补充单元测试覆盖企业性质入参、客户端过滤、VAT 覆盖目标登记和小规模任务识别。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_chanjet_admin_task_query.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe -m compileall -q src\chanjet_admin\task_query.py src\coverage tests\unit\test_chanjet_admin_task_query.py tests\unit\test_coverage_framework.py
```

真实补齐验证：
```powershell
.\.venv\Scripts\python.exe scripts\batch_collect_verify.py --run-id ops_20260601_codex_100530 --period 202605 --enterprise 蓝天之爱 --skip-collect --verify --reuse-existing-report --skip-browser --targets auto --log-level INFO ...
```

结果：
- 后台补齐阶段成功补齐 4 个代表任务。
- 增值税一般纳税人已申报命中 taskId `2075110422978017700`。
- 增值税小规模未申报命中 taskId `2075110444454676721`。
- 增值税小规模已申报当前查询窗口内未命中，诊断显示小规模候选任务均解析为未申报。

风险：
- 本次真实补齐验证使用 `--skip-browser`，验证了后台补齐查询和接口侧目标选择，没有重新进入税局完成页面级校验。
- 后台仍可能不完全遵守 `taxTypeId` 等服务端筛选，客户端二次校验必须保留。
## 2026-06-01：修复未确认切表仍生成截图/PDF的问题

修改内容：
- 定位税号 `91131102MA07X9YW6M` 的增值税附表截图错误原因：未申报增值税页面点击附表菜单后，代码虽然等待目标附表内容超时，但后续仍继续网页解析和 PDF 保存，导致主表页面被当作附表证据输出。
- `scripts/compare_tax_forms.py` 增加证据前置确认：截图/PDF/网页抽取前必须确认当前页面已经切换到目标表单。
- 未申报增值税附表确认同时检查左侧菜单激活状态和页面正文标题，避免“菜单切换信号异常但正文仍停留主表”时继续截图。
- 未申报增值税附表菜单未找到、切换后未确认目标附表、打开未申报表单失败时，直接抛出明确错误，不再继续生成错误证据。
- 已申报详情页同样收紧策略：目标表单不能被明确识别时，停止当前表单验证，避免跨表截图或错表解析。
- `tests/unit/test_detail_form_switching.py` 增加未申报增值税目标表单确认的单元测试。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_detail_form_switching.py
```

风险：
- 本次优先杜绝错误截图/PDF落盘；如果税局页面切换失败，新逻辑会让当前表单失败并给出原因，而不是继续产出错误证据。
- 未重新跑真实税局全链路；真实验证仍依赖当前税局会话、页面可用性和外部登录状态。

## 2026-06-01：批量报告隔离、日志脱敏与轮询鲁棒性优化

修改内容：
- `scripts/batch_collect_verify.py` 在每次验证前记录开始时间，批量结果页和“需处理原因”只读取本次新生成的 compare JSON，避免同一 taskId 历史报告污染本批次结果。
- 验证结果状态新增 `reportPaths`，批量汇总优先按该列表展示差异明细；历史批次无该字段时保持兼容旧逻辑。
- `NO_NEED_COLLECTED` 立即标记为成功并终止轮询，同一阶段相同事件不再重复写入工作台事件流。
- 取数轮询超时前增加一次后台 taskId 兜底解析；若后台已经生成可验证任务，则继续进入验证，不直接标记人工处理。
- `src/login/log_sanitizer.py` 新增敏感日志脱敏，税局登录等待和登录探测日志会遮蔽 URL/JSON 中的 cookie、token、证件号、手机号等值。
- 覆盖补齐增加进度回调和 `--coverage-supplement-timeout` 参数，后台查询过程中会记录当前查询税种、命中数量、目标诊断和超时状态。

验证：
```powershell
python -m compileall -q main.py scripts src tests\unit\test_batch_handling_info.py tests\unit\test_coverage_framework.py tests\unit\test_login_log_sanitizer.py
python tests\unit\test_login_log_sanitizer.py
python tests\unit\test_batch_handling_info.py
python tests\unit\test_coverage_framework.py
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_task_execution_log.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_ops_console.py
```

风险：
- 本次未重新跑真实全量税局链路；真实效果需要下一批次验证结果确认。
- 历史批次没有 `reportPaths` 时仍会按旧逻辑读取 taskId 目录下全部报告，这是为了兼容旧状态文件。
- 取数超时兜底依赖后台登录态；后台未登录时仍会保留原有人工处理路径。
## 2026-06-01：后台补齐支持多候选重试与尝试记录展示

修改内容：
- `src/coverage/supplement.py` 支持每个覆盖缺口保留多个后台候选任务，默认最多 3 个，不再只取第一个匹配任务。
- `scripts/batch_collect_verify.py` 将后台补齐改为按缺口逐个验证候选：一个候选未能覆盖目标时，继续尝试下一个候选。
- 批量状态新增 `coverageSupplement.attempts`，记录每个候选 taskId 的税号、尝试序号、验证结果、失败/完成步骤和直接原因。
- 批量结果页“税种覆盖说明”下新增“后台补齐尝试记录”，方便看到每个候选任务失败在哪一步。
- `src/coverage/analyzer.py` 优先使用当前批次 `verify.reportPaths` 计算覆盖，避免历史同 taskId 报告影响当前补齐判断。
- 新增 `--coverage-supplement-max-candidates` 参数，默认每个缺口最多尝试 3 个后台候选任务。

验证：
```powershell
python -m compileall -q main.py scripts src tests\unit
python tests\unit\test_coverage_framework.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_batch_handling_info.py
python tests\unit\test_ops_console.py
```

风险：
- 本次只跑了单元测试和编译检查，未重新跑真实全量税局链路。
- 如果后台候选很多，增加重试次数会增加真实税局验证耗时；默认 3 个用于控制时间。
- 失败步骤是根据验证返回原因归类，若底层错误文案变化，可能需要继续补充分类规则。

## 2026-06-01：修复残保金个税/汇算清缴自动分类

修改内容：
- 定位税号 `91460000MAE0TMR45K` 被误分为个税残保金的原因：批量脚本只按 `taxTypeId=26`、覆盖目标和文本关键字判断残保金子类型，没有读取后台操作日志。
- `src/chanjet_admin/task_execution_log.py` 新增“残保金任务返回结果”日志解析；当日志内容包含“数据库未查询到返回数据，调用汇算清缴取数接口查询”或“汇算清缴取数接口”时，判定为汇算清缴残保金。
- `scripts/batch_collect_verify.py` 在 `--cbj-mode auto` 下优先读取任务日志决定残保金模式，日志结论优先级高于 `taxTypeId=26` 的默认个税判断。
- 补充单元测试，覆盖“taxTypeId=26 但日志显示调用汇算清缴接口时应走 annual 模式”。

验证：
```powershell
python -m compileall -q src\chanjet_admin\task_execution_log.py scripts\batch_collect_verify.py tests\unit\test_task_execution_log.py tests\unit\test_batch_handling_info.py
python tests\unit\test_task_execution_log.py
python tests\unit\test_batch_handling_info.py
```

真实任务检查：taskId `2075110899720157073` 现在识别为 `annual`。

风险：
- 该规则依赖后台日志类型和文案保持稳定；如果后续后台将“调用汇算清缴取数接口查询”改成其他文案，需要继续补充 marker。
## 2026-06-01：关闭后台补齐多候选重试

修改内容：
- `scripts/batch_collect_verify.py` 将后台补齐候选数固定为 1；即使命令行传入更大的 `--coverage-supplement-max-candidates`，当前也只会保留并尝试第一个候选任务。
- `src/coverage/supplement.py` 在候选规划层强制每个覆盖缺口最多返回 1 个候选，避免后续入口绕过批量脚本再次启用多候选重试。
- `tests/unit/test_coverage_framework.py` 更新覆盖补齐测试，确认传入 `max_candidates_per_target=2` 时仍只返回 1 个候选。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\batch_collect_verify.py src\coverage\supplement.py tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
```

风险：
- 本次只关闭多候选重试，未重新跑真实全量税局链路。
- 已生成的历史批次中如果存在多候选尝试记录，历史结果页仍会展示当时的记录；新批次只会尝试一个候选。

## 2026-06-01：重新发起青岛税号验证并修复旧 taskId 复用

修改内容：
- 使用税号 `91370203334145023C`、所属期 `202605` 重新发起易代账取数，生成新的后台 taskId：`2076005047487626573`。
- `scripts/batch_collect_verify.py` 新增 `--reuse-collected-task` 显式选项；默认新批次没有 `verifyTaskId` 时会重新提交取数，不再直接复用历史已取数任务。
- `src/ydz/task_resolver.py` 在新提交取数后按提交时间过滤后台任务，只接受本次提交附近的新任务，避免命中旧 taskId。
- `src/login/task_login_flow.py` 修复青岛税号 tpass 参数覆盖顺序，确保最终 `province`、`tgtUrl`、`forceRedirectEtaxProvinces` 使用 `qingdao`，不被后台旧 taskInfo 中的其他省份值覆盖。
- 补充单元测试覆盖新批次强制取数、显式复用旧任务、按提交时间过滤旧 taskId、青岛 tpass 参数修正。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\batch_collect_verify.py src\ydz\task_resolver.py src\login\task_login_flow.py tests\unit\test_ydz_collector.py tests\unit\test_batch_handling_info.py tests\unit\test_task_login_flow.py
.\.venv\Scripts\python.exe tests\unit\test_ydz_collector.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_task_login_flow.py
```

真实运行结果：
- 批次目录：`output\batch_runs\ops_20260601_qingdao_91370203334145023C`
- 取数成功，已确认新 taskId 为 `2076005047487626573`，不是复用旧任务。
- 验证阶段已进入青岛 tpass/电子税局入口，但停在青岛统一登录页，最终失败原因是 `Tax bureau login timeout for province=qingdao`。

风险：
- 青岛税局本次阻塞点是统一登录认证未完成，不是旧 taskId 复用，也不是已申报/未申报状态判断错误。
- 后续如果要完成该税号网页验证，需要先在青岛税局页完成人工登录/扫码/滑块等认证，再继续用新 taskId 验证。

## 2026-06-01：支持同一税号对应多个取数 taskId

修改内容：
- `src/ydz/task_resolver.py` 新增多 taskId 解析能力：同一提交窗口内如果后台返回多个成功取数任务，会返回全部 taskId。
- `src/ydz/models.py` 的取数结果新增 `verify_task_ids`、`resolved_tasks`，输出到 state 时对应 `verifyTaskIds`、`resolvedTasks`；原 `verifyTaskId` 继续保留第一个 taskId 兼容旧逻辑。
- `scripts/batch_collect_verify.py` 支持一个税号多个 taskId：额外 taskId 会生成同税号内部子项，逐个调用 `main.py --task-id` 验证，并按 `verifyTasks` 分 taskId 保存结果。
- 批量汇总、问题明细、覆盖分析和运营台状态展示支持读取多个 taskId。
- `scripts/ydz_collect_and_verify.py` 也支持对一个取数结果中的多个 taskId 逐个验证。
- `ARCHITECTURE.md`、`PROJECT_CONTEXT.md`、`DECISIONS.md`、`TASKS.md` 已同步更新多 taskId 规则。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src tests\unit\test_ydz_collector.py tests\unit\test_batch_handling_info.py tests\unit\test_coverage_framework.py tests\unit\test_batch_summary_rendering.py tests\unit\test_ops_console.py
.\.venv\Scripts\python.exe tests\unit\test_ydz_collector.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
.\.venv\Scripts\python.exe tests\unit\test_ops_console.py
```

补充验证：
- 用本地 mock 批次验证 `91370102MA7D3P0D2P` 同时绑定 `2075110435864560097`、`2075110435864560096` 时，汇总页能展示两个 taskId，并能同时读取两个 taskId 的表单报告。

风险：
- 本次只完成代码和 mock 验证，未重新跑真实税局全链路。
- 多 taskId 会增加单税号验证耗时；但这是避免漏验的必要代价。

## 2026-06-01：真实验证山东税号多 taskId 场景

运行内容：
- 使用税号 `91370102MA7D3P0D2P`、所属期 `202605` 重新发起易代账取数和完整验证。
- 批次目录：`output\batch_runs\ops_20260601_91370102_rerun_175303`
- 本次取数解析到两个新 taskId：`2075110422978099686`、`2075110422978099685`，批量流程已逐个验证。

运行结果：
- `2075110422978099686`：验证增值税一般纳税人和文化事业建设费，状态为 `completed_with_differences`，差异为 `增值税纳税申报表（一般纳税人适用）/qmwjse_ybxm_bnlj` 1 个字段。
- `2075110422978099685`：验证消费税两张表，状态为 `success`。
- 批量汇总已生成：`output\batch_runs\ops_20260601_91370102_rerun_175303\batch_summary.html`

验证：
- 真实链路已完成：取数、后台 taskId 解析、税局登录、网页数据解析、PDF/Excel/JSON/HTML 输出。
- 本次没有修改业务代码，未额外运行单元测试。

风险：
- 第一个 taskId 存在 1 个字段差异，需要业务侧确认接口值和网页值差异原因。

## 2026-06-02：修复山东消费税未申报进税局切表失败

修改内容：
- `scripts/compare_tax_forms.py` 为消费税未申报增加直达入口 `/sbzx/view/lzsfjssb/#/declare/xfssb?jyjkId=30`。
- 当税局首页点击“填写申报表”打开新标签页时，自动切换到新打开的消费税申报页。
- 消费税主表左侧菜单选择改为匹配“消费税及附加税费申报表 + 主表”，避免把父级菜单误判为主表。
- 比对字段过滤改为只纳入接口非空值字段；接口空字符串按“未返回”忽略，不再产生 `api_missing`。
- `tests/unit/test_detail_form_switching.py`、`tests/unit/test_vat_appendix5_compare_policy.py` 增加消费税入口、子菜单选择、空接口值忽略测试。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_detail_form_switching.py tests\unit\test_consumption_tax_support.py tests\unit\test_vat_appendix5_compare_policy.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
.\.venv\Scripts\python.exe tests\unit\test_vat_appendix5_compare_policy.py
.\.venv\Scripts\python.exe main.py --task-id 2076264459216848195 --targets auto --cdp-port 9222 --user-data-dir browser_profile\etax_compare_forms --plugin-path C:\Users\Administrator\Downloads\EtaxPlugin --log-level INFO --tax-timeout 600 --tax-login-strategy direct_first --skip-pdf
```

结果：
- `2076264459216848195` 已成功完成消费税两张表验证。
- 消费税及附加税费申报表：38/38，100%。
- 消费税附加税费计算表：29/29，100%。

风险：
- 本次真实验证使用 `--skip-pdf`，未重新生成 PDF 截图。
- 直达 URL 已在山东税局验证；其他省份如果消费税未申报入口不同，仍需要按省份补充策略。
## 2026-06-02：修复未申报页面准备函数返回空页面对象

修改内容：
- `scripts/compare_tax_forms.py` 修复 `prepare_undeclared_page_for_target()` 在“目标表单内容已经可见”两个分支中只 `return`、未返回 `page` 的问题。
- 避免主流程执行 `tax_page = prepare_undeclared_page_for_target(...)` 后把可用税局页面覆盖成 `None`，导致后续 `page.url` 报 `AttributeError`。
- `tests/unit/test_detail_form_switching.py` 增加回归测试，覆盖未申报页面已打开时函数必须返回原页面对象。

验证：
```powershell
.\.venv\Scripts\python.exe -m compileall -q scripts\compare_tax_forms.py tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
```

风险：
- 本次只修复已定位的空页面对象崩溃，未重新跑真实税局链路；用户后续手动重跑确认山东多 taskId 场景。
# 2026-06-03：优化后台补齐查询耗时

修改内容：
- `src/coverage/supplement.py`：后台补齐搜索新增所属期参数，按本批次 `period` 查询候选任务，避免扫到当前月份其它所属期任务。
- `src/coverage/supplement.py`：同一次补齐搜索内缓存申报状态解析结果和 taskId 的“是否当期”日志判断结果；日志读取失败时降级为未知，不中断整个补齐搜索。
- `src/chanjet_admin/task_query.py`：后台任务查询缓存 public-manage 登录 token；遇到 401/403 或 token/authorization 类失败时，强制重读 token 并重试一次。
- `scripts/batch_collect_verify.py`：调用后台补齐时传入当前批次所属期。
- `tests/unit/test_chanjet_admin_task_query.py`、`tests/unit/test_coverage_framework.py`：补充 token 缓存/刷新、所属期查询参数测试。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_chanjet_admin_task_query.py
.\.venv\Scripts\python.exe tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe -m compileall -q src\chanjet_admin\task_query.py src\coverage\supplement.py scripts\batch_collect_verify.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_coverage_framework.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

风险：
- 本次只跑了单元测试和编译检查，未重新跑真实全量税局链路。
- 补齐候选现在会严格限定到当前所属期；如果后续需要跨所属期找代表任务，应新增显式配置，而不是默认放宽。
- 后台未登录时仍需要人工先登录 public-manage；本次只优化已有登录态的读取和失效刷新。
# 2026-06-03：修复增值税网页解析假缺失和错列

修改内容：
- `scripts/compare_tax_forms.py` 增加网页提取滚动重试：当附表类页面初次 DOM 提取覆盖率低时，自动滚动页面内可滚动容器和横向表格后重试缺失字段。
- `scripts/compare_tax_forms.py` 增加小规模增值税主表、附列资料（一）、附列资料（二）的文本解析器，避免通用 DOM 下标把“栏次”误读为金额，或漏读税率、减征比例等字段。
- 提高关键表单网页提取覆盖率门槛；如果零值字段因为网页空值被等价通过，但整体提取覆盖率异常，会明确标记质量风险，不再静默包装成通过。
- 修复 `scripts/compare_tax_forms.py` 中 JS 正则字符串的 `\s` 转义警告，降低 Python 3.14 部署噪音。
- 新增 `tests/unit/test_vat_small_web_extraction_parsers.py`，覆盖小规模主表错列、附表二税率/减征比例漏读、附表一全 0 表覆盖率和一般附表一低覆盖判定。

根因：
- 一般纳税人附表一存在表格虚拟滚动/横向滚动，初次只提取到可见区域，导致第 5 行 6% 税率字段网页值为空。
- 小规模主表通用提取器用 Excel 列号直接换算 DOM 下标，遇到“项目 + 栏次 + 四列金额”的表格时，把栏次 1/2/3 读成金额。
- 小规模附表二税率和减征比例列没有专用解析，旧逻辑读取不到，但接口非 0 时就显示网页缺失。
- 旧覆盖率门槛过低，且零值空值等价规则会掩盖大面积网页未提取。

验证：
```powershell
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe tests\unit\test_vat_small_web_extraction_parsers.py
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe tests\unit\test_vat_appendix5_extraction.py
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe tests\unit\test_consumption_tax_support.py
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe tests\unit\test_batch_summary_rendering.py
$env:PYTHONPATH='.'; .\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
.\.venv\Scripts\python.exe main.py --task-id 2076614026604697199 --log-level INFO
.\.venv\Scripts\python.exe main.py --task-id 2076614417445323010 --log-level INFO
```

真实回归结果：
- `2076614026604697199`：一般纳税人附表一原缺失字段 `kjskzzszyfpXse_5`、`kjskzzszyfpXxynse_5`、`kchXxynse_5` 已提取到网页值并匹配，整任务成功。
- `2076614417445323010`：小规模主表、附表一、附表二均 `web_missing=0`，主表不再错读栏次，整任务成功。

风险：
- 滚动重试会增加附表类解析耗时；本次真实回归中一般附表一多消耗约 30 秒。
- 其它省份如果使用完全不同的表格渲染组件，仍需按截图补专用解析器，但低覆盖门槛会更早暴露问题。
## 2026-06-04：收窄税局首页未申报入口兜底点击

修改内容：
- `scripts/compare_tax_forms.py` 的税局首页兜底点击逻辑新增禁点区域：办税进度及结果信息查询、申报查询、税费缴纳、发票业务、社保费业务、税务数字账户、我的待办、通知公告。
- 首页菜单点击不再按 DOM 顺序命中任意包含“办税”的按钮；会排除禁点区域，并优先完整/短文本匹配。
- 未申报入口恢复不再在全页面兜底点击任意“填写申报表/办理”按钮；必须在目标税种或申报区域内找到动作按钮，否则返回找不到入口。
- `tests/unit/test_detail_form_switching.py` 增加保护测试，防止恢复全页兜底和移除“办税进度及结果信息查询”禁点。

运行观察：
- 批次 `ops_20260604_105903` 中 `2076981254899665895` 暴露了首页兜底误点“办税进度及结果信息查询”的问题。
- 同批次 `2076981254899665894` 登录链路使用 8 秒快速回退后成功进入税局并完成消费税两张表验证，均为 100%。
- 修复后单独重跑 `2076981254899665895` 成功，未再进入“办税进度及结果信息查询”；增值税主表、附表一至五、文化事业建设费均为 100%，报告为 `output\reports\2076981254899665895\compare_summary_2076981254899665895_20260604_112423.html`。

验证：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_task_login_flow.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
.\.venv\Scripts\python.exe main.py --task-id 2076981254899665895 --targets auto --cdp-port 9222 --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir browser_profile\etax_compare_forms --plugin-path C:\Users\Administrator\Downloads\EtaxPlugin --log-level INFO --tax-timeout 600 --tax-login-strategy plugin_first --browser-lock-timeout 3600
```

风险：
- 修复后首页兜底更保守，遇到未知税局首页结构时可能更早失败并报告“找不到入口”，但不会继续误点查询进度类页面。
# 2026-06-08: YDZ integration customer batch operation

Change:
- Completed an external Yidaizhang integration-environment customer batch operation using the existing browser sessions and API workflow.
- No source-code behavior was changed. Sensitive values such as tax numbers, passwords, cookies, tokens, and Authorization headers were not written to project files.

Verification:
- Verified the operation through Yidaizhang customer query and dynamic tax-info query APIs.
- Code tests were not run because this was an external operational task with no code changes.

Risk:
- Results depend on the live Yidaizhang integration environment and public-manage backend sessions available at execution time.
# 2026-06-08: reusable YDZ customer creation workflow

Change:
- Added `src/ydz/customer_creation.py` with reusable Yidaizhang customer creation/update logic.
- Added `scripts/ydz_create_customers.py` as the operational CLI entry. It reads backend task login info from a logged-in public-manage browser session, creates missing customers, saves dynamic tax login info, and verifies both customer defaults and tax info.
- Added `tests/unit/test_ydz_customer_creation.py` for payload mapping and verification rules.
- Added `docs/ydz_customer_creation.md` and documented the new architecture entry.

Security:
- The workflow does not persist passwords, cookies, tokens, Authorization headers, or raw backend `loginJson`.

Verification:
- `python -m compileall -q main.py scripts src`
- `.\.venv\Scripts\python.exe -m compileall -q main.py scripts src`
- Manual runner for `tests/unit/test_ydz_customer_creation.py` passed 8 tests because pytest is not installed in this environment.
- `python scripts\ydz_create_customers.py --env inte --tax-no 91350105062259341P --dry-run --session-timeout 5 --no-launch-chrome`

## 2026-06-09 addendum: coverage blocker triage and declaration-query recovery

Change:
- Updated filed declaration-query navigation so the `/szzh/zhcx/sbxx/sbxxcx` Vue form is considered ready only after its query state is available.
- Refreshing filed declaration-query results now sets the tax period (`skssqq/skssqz`), clears declaration-date filters (`sbrqq/sbrqz`), and invokes the page search handler before selecting a declaration row.
- Added a controlled unique fallback for `cit_a_main`: if the period-specific row is not found, keyword-only selection is allowed only when it matches a single row.
- Classified filed declaration-row misses and expired `getTaskCookie`/task-cookie messages as actionable supplement failure categories instead of generic verification failures.

Validation:
- `python tests\unit\test_detail_form_switching.py`
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q main.py scripts src`
- Focused real run: `python main.py --task-id 2063992986034123594 --targets cit_a_main --tax-login-strategy plugin_first --log-level INFO`
- Full supplement observation run: `output\batch_runs\codex_full_20260609_204530`

Observed blockers:
- `CIT_A:filed` Shanghai candidate correctly applied the period query but the tax bureau still returned no target declaration row; this is source/tax-bureau state mismatch, not field comparison failure.
- `CIT_A:unfiled` Jiangsu candidate reached the tax bureau home, but only a hot-service/title entry was visible and no current-period unfiled target entry opened; classify as target entry unavailable.
- `CULTURE_FEE:unfiled` Beijing candidates repeatedly clicked `填写申报表` but returned to the home page or `tpass/code`; this needs faster auth/entry failure handling.
- `CBJ_ANNUAL` Xinjiang first candidate failed at expired `getTaskCookie`; the second candidate recovered from repeated `/loading` through a fresh tab and generated a report.

Risk:
- Remaining missing coverage is dominated by external tax-bureau session state, source-state conflicts, and province-specific undeclared-entry behavior.
- The current retry flow still spends too long on repeated home-entry clicks before moving to the next candidate.

## 2026-06-09 addendum: undeclared home-entry fast path and auth-code failure handling

Change:
- `src/login/login_detector.py` now treats `/mhzx/api/mh/tpass/code` and authorization-code-empty content as not logged in.
- `scripts/compare_tax_forms.py` now raises tax-auth failure immediately when undeclared navigation or target-page waiting lands on `tpass` login or `mhzx/api/mh/tpass/code`.
- Tax-home undeclared recovery now tries a visible target action before waiting through top navigation steps, clicks only one target action/title per evaluation, and stops when the same recovery click repeats.
- Undeclared form preparation now recovers from a tax-home redirect before waiting for fill buttons or left-menu items, shortening Beijing culture-fee and Jiangsu CIT A failure paths.

Validation:
- `python tests\unit\test_detail_form_switching.py`
- `python tests\unit\test_task_login_flow.py`
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q main.py scripts src`
- Real run `2077729330826989198 --targets culture_fee_main,culture_fee_deduction` succeeded: `culture_fee_main` 32/32 matched, `culture_fee_deduction` produced an evidence-only report because the backend API returned no comparable fields.
- Rebuilt `output\batch_runs\codex_full_20260609_204530\coverage_status.json`; coverage improved from 5/10 to 6/10 after counting `CULTURE_FEE:unfiled`.

Observed remaining blockers:
- `VAT_GENERAL:unfiled` task `2077729249222221038` now fast-fails with a tax-bureau already-declared message, so this is a source-state conflict rather than a parser mismatch.
- `CIT_A:unfiled` task `2077729322237848768` either lands on `tpass/code` auth failure or shows only a Jiangsu hot-service/title entry that does not open the target form.
- Remaining uncovered targets are `VAT_GENERAL:unfiled`, `VAT_SMALL:unfiled`, `CIT_A:filed`, and `CIT_A:unfiled`.

## 2026-06-09 addendum: CIT A filed query keyword audit

Change:
- Relaxed `cit_a_main` declaration-list matching from strict `A200000/A class` row text to `enterprise income tax + month + quarter` row text.
- Kept detail-form confirmation strict with `A200000`, so the broader list match cannot silently accept the wrong detail form.
- Added a focused regression assertion for this split.

Validation:
- `python tests\unit\test_detail_form_switching.py`
- `python -m compileall -q main.py scripts src`
- Real rerun `2063137046298926964 --targets cit_a_main` reached the Tianjin declaration query page but still found no CIT A row.
- Direct browser inspection showed the query results only contained culture fee and VAT rows for `2026-05-01~2026-05-31`; the tax home also listed only culture fee and VAT as current declared items.

Conclusion:
- The tested Tianjin `CIT_A:filed` candidate is a backend/tax-bureau source-state conflict, not a parser or keyword-match failure.
