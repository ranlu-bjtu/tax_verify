# TASKS.md

## 2026-06-11 addendum: account-set skill lazy Playwright dependency

- Centralized standalone skill Playwright import behind `load_sync_playwright()`.
- API-only account-set paths no longer imply Playwright installation.
- Browser/CDP paths now show a focused install hint only when Playwright is missing.
- Updated standalone and installed skill docs to describe Playwright as optional.

Validation:
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m py_compile skills\ydz-create-accountset\scripts\ydz_accountset_cli.py C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py`

## 2026-06-11 addendum: account-set Chrome CDP fallback ports

- Account-set creation now connects to Chrome through a shared CDP helper instead of direct `9222` calls.
- Managed Chrome launches include `--enable-automation` and keep the existing automation-controlled flag.
- If the requested port is occupied by an incompatible user Chrome, the flow retries with `9333`, `9444`, `9555`, and `9666`.
- Fallback ports use port-suffixed browser profiles so the user's normal Chrome profile is not reused.
- Synced the same behavior into standalone `skills/ydz-create-accountset/` and installed `C:\Users\Administrator\.codex\skills\ydz-create-customer`.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests tests\unit\test_ydz_create_customers_script.py`
- `python -m py_compile C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py`

## 2026-06-11 addendum: public-manage backend API auth provider

- Added `src/chanjet_admin/auth.py` for public-manage backend token providers.
- `ChanjetAdminTaskQuery` and privacy-phone sync can now use backend tokens without a browser context.
- `scripts/ydz_create_customers.py` now supports `--backend-auth-mode auto|token|password|browser`.
- Default backend auto mode tries token variables, then public-manage password API login, then browser fallback.
- Strict backend password mode stops before customer mutation when SSO returns a blocker such as `访问拒绝`.
- Synced the same self-contained behavior into `skills/ydz-create-accountset/` and installed `C:\Users\Administrator\.codex\skills\ydz-create-customer`.

Validation:
- `python tests\unit\test_chanjet_admin_auth.py`
- `python tests\unit\test_chanjet_admin_task_query.py`
- `python tests\unit\test_chanjet_admin_privacy_phone.py`
- `python tests\unit\test_ydz_create_customers_script.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py src\chanjet_admin skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests tests\unit\test_chanjet_admin_auth.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_chanjet_admin_privacy_phone.py tests\unit\test_ydz_create_customers_script.py`
- Live public-manage token exchange from an authenticated SSO session queried backend tasks without a browser context.

## 2026-06-11 addendum: production YDZ app-entry crawl fixed

- Added production workbench app-list recovery to account-set creation.
- When no active YDZ `work.html` page is present, the browser path opens `workbench.chanjet.com/v2/myapp/list?orgId=<env org id>` and clicks the primary `易代账` `进入应用` entry before direct work-url fallback.
- The selector now accepts longer production app rows containing purchase dates, purchase state, and user-list controls, while filtering adjacent non-YDZ apps.
- Synced the same recovery into standalone `skills/ydz-create-accountset/` and installed `C:\Users\Administrator\.codex\skills\ydz-create-customer`.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py src\ydz skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`
- Live non-mutating smoke through current Chrome CDP opened `https://cloud.chanjet.com/ydzee/u7anoc8y5p7p/49le0svcsa/work.html#/home/dataBoard`.

## 2026-06-10 addendum: YDZ account-set manual captcha-code login methods

- Added `SDSRDX` and `DLYW-SDSRDX` to project account-set creation.
- Backend task lookup now sends `loginType=YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX` while preserving task categories `2,3` and no tax-type restriction.
- The resolver locally rejects rows without supported account-set login methods or required login fields.
- Dynamic tax-info save maps `SDSRDX/DLYW-SDSRDX` `cTaxPreparerName` to the phone/login account and still stores `cTaxPreparerPwd`.
- `DLYW-SDSRDX` stores the proxy company tax number in `cSiteLoginName`, same as other `DLYW-*` methods.
- Integration privacy-phone sync now runs only for `YSHDL/DLYW-YSHDL`.
- Workbench manual-accountset entry and standalone `skills/ydz-create-accountset/` were updated.
- Installed `C:\Users\Administrator\.codex\skills\ydz-create-customer` was synchronized with the same script/reference behavior.

Validation:
- `python tests\unit\test_ydz_customer_creation.py`
- `python tests\unit\test_ops_console.py`
- `python tests\unit\test_chanjet_admin_task_query.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`

## 2026-06-10 addendum: YDZ account-set accountant follows login phone

- Verified the real Yidaizhang frontend API definition: `getChildEmpListByUserId` maps to `trans/easyacctg/employee/getChildEmpListByUserId`.
- Account-set creation now resolves the assigned accountant from that employee list by matching the Yidaizhang login account phone to row `mobile`.
- The create payload sends the matched employee `userId` as `accountantEmployeeId`.
- If the lookup is unavailable or unmatched, the resolver falls back to current `userId`, then the packaged environment default.
- Saved customer verification now checks the resolved accountant id.
- Synced the same resolver into the standalone `skills/ydz-create-accountset/` CLI.

Validation:
- `python tests\unit\test_ydz_customer_creation.py`
- `python tests\unit\test_ydz_create_customers_script.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py src\ydz skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`

## 2026-06-10 addendum: YDZ integration captcha login uses API first

- Integration Yidaizhang password auth now calls `loginV2/accountVerify` with captcha code before `loginV2/accountLogin`.
- Default integration captcha code is `666666`; production does not default a captcha value.
- Captcha can be overridden with `YDZ_INTE_LOGIN_CAPTCHA`, `YDZ_INTE_CAPTCHA`, `YDZ_INTE_VERIFY_CODE`, or generic `YDZ_LOGIN_CAPTCHA`, `YDZ_CAPTCHA`, `YDZ_VERIFY_CODE`.
- Browser login fallback now also fills the configured captcha field when it is present.
- Synced the same behavior into the standalone `skills/ydz-create-accountset/` CLI.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- Direct function-call verification for `tests\unit\test_ydz_password_auth.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q scripts\ydz_create_customers.py src\ydz skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`

## 2026-06-10 addendum: CIT A remains optional in workbench coverage

- Enterprise Income Tax A-class is visible in the workbench coverage tax-type checklist.
- It is unchecked by default, so small-period default runs still exclude `CIT_A`.
- If selected explicitly, `CIT_A` is passed through `--coverage-tax-types` and the normal CIT A verification/supplement path can run.
- CIT A source-discovery controls remain hidden: work.html URL input, other-enterprise scan, and account-set precheck are not shown in the page.

Validation:
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py`

## 2026-06-10 addendum: completed-with-differences reports remain visible

- Treat `completed_with_differences` as a completed full verification result for the report matrix.
- Do not hide a completed difference report merely because another backend supplement candidate covers the same tax/status target cleanly.
- Failed, skipped, or login-blocked tasks without completed form reports remain out of the tax-number/form matrix.

Validation:
- `python tests\unit\test_batch_summary_rendering.py`
- `python -m compileall -q main.py scripts src`

## 2026-06-10 addendum: workbench small-period result display cleanup

- Batch summary tax-number/form matrix now renders only completed full verification form results.
- Tasks that did not enter the tax bureau or did not produce form results remain visible in progress/coverage/problem areas, but no longer appear in that matrix.
- Unfiled declaration status is treated as a normal state, not a warning.
- CBJ remains status-independent and does not display as unfiled.
- Coverage explanation table no longer includes backend tax ID/filter columns.
- Current small-period workbench UI no longer exposes CIT A work.html source, enterprise scan, or account-set precheck controls; the CIT A checkbox is available but unchecked by default, so the default coverage scope excludes `CIT_A`.

Validation:
- `python tests\unit\test_batch_summary_rendering.py`
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q main.py scripts src`

## 2026-06-10 addendum: YDZ account-set auth default is password-first auto

- Changed account-set `YDZ_AUTH_MODE` default from `browser` to `auto`.
- Auto mode tries guarded password auth first and falls back to browser login if no usable Yidaizhang token context is produced.
- Explicit `--ydz-auth-mode password` remains strict and fails before mutation when blocked.
- Workbench default auth option now displays `自动（账号密码优先）`; explicit browser mode is still available.
- Synced the same default into the standalone `skills/ydz-create-accountset/` CLI.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- `python tests\unit\test_ops_console.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m py_compile scripts\ydz_create_customers.py scripts\ops_console.py skills\ydz-create-accountset\scripts\ydz_accountset_cli.py`

## 2026-06-10 addendum: standalone YDZ account-set skill manual-source mode implemented

- Added `create --manual-source-env` to `skills/ydz-create-accountset/scripts/ydz_accountset_cli.py`.
- Manual mode reads `YDZ_MANUAL_*` customer and tax-login fields, including tax number, customer name, region, login method, proxy tax number, privacy number, and tax login password.
- Manual mode bypasses public-manage task lookup and integration privacy-phone sync.
- Manual mode can run with browser, token, or guarded password-auth Yidaizhang authentication.
- Updated skill docs and project memory.

Validation:
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m py_compile skills\ydz-create-accountset\scripts\ydz_accountset_cli.py`

## 2026-06-10 addendum: YDZ account-set password-auth mode implemented

- Added guarded direct Chanjet password-auth client for account-set creation.
- Added `--ydz-auth-mode password` to the project account-set script.
- Added workbench auth-mode option for account-password direct login.
- Added matching password-auth support to the standalone `skills/ydz-create-accountset/` CLI while preserving skill independence.
- Password mode reports slider/CAPTCHA, phone binding, password-change, and SSO-without-business-token blockers before customer mutation.
- Documented the mode and its boundaries in project docs, architecture, decisions, and skill references.

Validation:
- `python tests\unit\test_ydz_create_customers_script.py`
- `python tests\unit\test_ops_console.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- Direct function-call verification for `tests\unit\test_ydz_password_auth.py` because pytest is not installed locally.
- `python -m compileall -q main.py scripts src skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`

Next:
- If browser-free backend-source creation is required, add a separate public-manage token/client adapter.
- Re-check live password mode only with approved credentials; CAPTCHA or slider challenges must stay manual.

## 2026-06-10 addendum: YDZ account-set token-auth mode implemented

- Added page-independent Yidaizhang API auth context support for account-set creation.
- Added `--ydz-auth-mode token` to the project account-set script.
- Added token-mode support to the standalone `skills/ydz-create-accountset/` CLI while preserving skill independence.
- Manual-source creation can now run with valid token variables and no Chrome launch.
- Backend-source creation can use token mode for Yidaizhang APIs, but still needs public-manage login for source lookup and integration privacy-phone preparation.
- Updated workbench command construction to pass a non-sensitive auth-mode switch when requested.
- Documented required token variables and the boundary that this does not bypass slider/CAPTCHA.

Validation:
- `python tests\unit\test_ydz_customer_creation.py`
- `python tests\unit\test_ydz_create_customers_script.py`
- `python tests\unit\test_ops_console.py`
- `python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py`
- `python -m compileall -q main.py scripts src skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests`

Next:
- If full password-to-token login is still required, discover the Yidaizhang login handshake separately and only adopt it after proving it handles slider/manual verification boundaries without storing secrets.
- If backend-source creation must become browser-free, add a separate public-manage token/client adapter with equivalent no-secret handling.

## 2026-06-10 addendum: standard targets use historical candidates with 3-attempt fallback

- For future backend supplement runs, VAT general, VAT small, culture fee, CBJ personal, and CBJ annual now verify historical backend candidates directly.
- Enterprise Income Tax A-class and consumption tax remain intentionally excluded from this default robustness target.
- The default candidate limit remains 3 candidates per missing target.
- Standard supplement no longer generates fresh Yidaizhang taskIds by default and no longer requires the tax number to have a YDZ account set before validation.
- When one historical candidate fails at tax-bureau login readiness, the failure remains classified as `tax_login_expired` or `tax_login_blocked`, and the next backend candidate/tax number is tried.
- Candidate selection now prefers different tax numbers within the 3-attempt limit before spending attempts on multiple taskIds from the same tax number, including candidates merged from different search windows.
- Standard supplement now searches a larger bounded raw pool for login preflight, drops candidates definitively failing `getClientJob` or `getTaskCookie`, and then applies the configured 3-attempt final limit.
- If preflight drops the current raw pool below the final candidate limit, the same run immediately performs bounded refills with the not-ready taskIds excluded, then preflights the refill candidates. The current bound is 3 refill waves.
- Refill searches temporarily exclude all taskIds already seen in the current run, including ready/unknown preflight candidates, so repeat rows do not occupy the next refill pool.
- Preflight `not_ready` taskIds are now treated like stable failed supplement attempts on later runs and excluded from the next backend candidate search.
- If a later historical candidate covers the target, earlier failures no longer keep the supplement phase exit code failed.
- If all configured candidates fail, the target fails with the collected direct reasons.
- Removed the workbench fresh retry field and the standard fresh retry-wave CLI wiring.

Validation:
- `python tests\unit\test_coverage_framework.py`
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_task_login_flow.py`
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q main.py scripts src`

Additional regression now covered:
- A main-flow unit scenario where the first two historical `VAT_SMALL:unfiled` candidates fail at `getTaskCookie`, then the third historical candidate covers the target through the normal verifier path.
- A supplement-planner unit scenario where two newest backend rows share one tax number and a later row has another tax number; the planner selects the first and the other-tax-number row before retrying the same tax number.
- A cross-window candidate-merge unit scenario where the first window finds tax number A and the second window returns A then B; the merger keeps A and B.
- A login-preflight unit scenario where an incomplete `getClientJob` candidate is dropped while a candidate with valid `getClientJob` metadata and `getTaskCookie` data is kept.
- A formal-verification classification scenario where generic `getClientJob failed: ...` errors are normalized as `tax_login_expired`.
- A formal-verification classification scenario where unresolved `getClientJob` inner taskId/province metadata is normalized as `tax_login_expired`.
- The full supplement flow test confirms standard targets request a 3x raw candidate pool for preflight while preserving the final 3-attempt verification limit.
- A same-run refill regression confirms the first three preflight-expired candidates are excluded before the next backend candidate search, and the later ready candidate is verified.
- A duplicate-refill regression confirms a ready candidate from the first preflight pass is temporarily excluded from the next backend refill search.
- State exclusion regression now covers `coverageSupplement.loginPreflight` records, including skipping `not_ready` taskIds and preserving `unknown` preflight candidates.

Current status:
- This removes the default path where standard supplement needs fresh YDZ task generation before trying backend history.
- The broader goal is still active: we have not yet proven that every future supported candidate will pass without any tax-login failure.

## 2026-06-10 addendum: new-task tax-login blocker handling

- Do not use this project's previous successful report taskIds as stable-priority replacements for new backend candidates.
- New candidates continue through real `main.py --task-id` tax-bureau verification.
- Added bounded tax-login readiness handling so attempts do not hang indefinitely at `getClientJob`, `getTaskCookie`, `tpass.*#/login`, authorization-code pages, or `/loading`.
- Added classification for failed/incomplete/non-object/unresolved inner-task or province/exhausted `getClientJob` metadata responses as `tax_login_expired`.
- Field differences after a successful form read remain visible as comparison output.
- English same-province switch-limit messages are classified as `tax_login_blocked`.

Validation:
- `python tests\unit\test_task_login_flow.py`
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q main.py scripts src tests\unit\test_task_login_flow.py tests\unit\test_batch_handling_info.py`

Current status:
- Code-resolvable login-stage hanging risk is reduced.
- If the external tax-bureau session really needs manual login, slider, digital-account confirmation, or pending-task cleanup, the batch now reports that blocker and can continue instead of waiting without progress.

## 2026-06-10 addendum: current batch accepted after deferring CIT A

- User explicitly said Enterprise Income Tax A-class does not need to be covered for the current round.
- Refreshed authoritative run `output\batch_runs\codex_full_20260609_204530` with coverage scope:
  - `VAT_GENERAL`
  - `VAT_SMALL`
  - `CULTURE_FEE`
  - `CBJ_PERSONAL`
  - `CBJ_ANNUAL`
- Consumption tax remains outside the current round because its declaration status is not being judged yet.

Validation:
- `coverage_matrix.csv`: 8/8 in-scope targets covered.
- `coverage_missing.csv`: 0 rows.
- `batch_problem_details.csv`: 0 rows.
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_ydz_collector.py`
- `python -m compileall -q main.py scripts src`

Current status:
- The current agreed verification round is complete and clean.
- `CIT_A:filed` and `CIT_A:unfiled` remain later source-readiness follow-up items, not current-round blockers.

## 2026-06-10 addendum: CIT A no-need fresh source is now explicit

- Added `ydz_no_need_collect` source-readiness classification for CIT A fresh YDZ refresh.
- If a newly submitted YDZ collect request returns `NO_NEED_COLLECTED`, the batch summary and coverage gap text can now explain that no verifiable taskId was produced because the source is no-need for the period.
- This keeps no-need account sets out of the generic "no fresh source" bucket and gives the operator a concrete next action: change the candidate tax number or period.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python tests\unit\test_ydz_collector.py`
- `python -m compileall -q main.py scripts src`

Current status:
- Authoritative coverage remains `8/10`; missing targets remain `CIT_A:filed` and `CIT_A:unfiled`.
- There is still no mismatch, web-missing, parser, or mapping evidence in `batch_problem_details.csv`.

## 2026-06-10 addendum: CIT A account-set source precheck

- Added a workbench action to precheck account-set readiness for the current CIT A coverage blockers.
- The action extracts only the currently selected representative missing targets from batch state, then runs account-set creation in `--dry-run` mode.
- Verified against `codex_full_20260609_204530`: the precheck candidates are `91500105MAEQ3URL80` for filed CIT A and `91310115MA1HAHW684` for unfiled CIT A.
- This does not create customers or account sets; it is the safe step before deciding whether to create/import CIT A-ready account sets.

Validation:
- `python tests\unit\test_ops_console.py`
- `python -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py`

Current status:
- Coverage remains `8/10`; the next live step is to run the precheck with the correct YDZ environment/credentials, then explicitly create/import account sets only if the precheck result supports it.

## 2026-06-10 addendum: CIT A supplement retry after open-tab scan

- Reran `output\batch_runs\codex_full_20260609_204530` with target-scoped CIT A supplement, fresh YDZ refresh, and enterprise scan enabled.
- Current browser only had open YDZ work tabs for the current enterprise path, so open-tab scan did not provide a new source.
- Backend search found `2063992990329483939` for `CIT_A:unfiled`, but verification failed before form entry because `getTaskCookie` returned login connection expired.
- `CIT_A:filed` still has no clean filed source; candidates were unfiled, unknown already-failed, or excluded.
- `batch_problem_details.csv` remains header-only, so no parser, mapping, mismatch, or web-missing evidence exists.
- `coverage_missing.csv` now tells the operator to provide a valid work URL or manually open a target work tab in the shared browser before retrying.

Current status:
- Coverage remains `8/10`; missing targets remain `CIT_A:filed` and `CIT_A:unfiled`.

## 2026-06-10 addendum: open YDZ work tabs can feed CIT A source scan

- When `--coverage-supplement-scan-ydz-enterprises` is enabled, CIT A supplement now scans already-open ready YDZ `work.html` tabs before workbench enterprise switching.
- The current collector page is excluded, so this path is aimed at manually opened target-enterprise tabs.
- Ready tabs must expose batch declaration and YDZ API tokens before they can be scanned.
- CIT A account signals found in an open tab can now be submitted through the existing fresh YDZ collection path.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q scripts\batch_collect_verify.py src\ydz\session.py tests\unit\test_batch_handling_info.py`

Current status:
- If an operator manually opens a CIT A-ready YDZ work tab in the shared browser and reruns enterprise scan, the batch runner can try it automatically.

## 2026-06-10 addendum: workbench can pass explicit CIT A work URLs

- Added a workbench input for optional CIT A YDZ `work.html` URLs on the batch verification entry.
- When the field is filled, workbench-created and existing-run retry jobs enable `--coverage-supplement-refresh-cit-from-ydz`.
- The raw URL is passed only through child-process environment variable `YDZ_SUPPLEMENT_WORK_URLS`, not through the displayed command.

Validation:
- `python tests\unit\test_ops_console.py`
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q scripts\ops_console.py tests\unit\test_ops_console.py`
- `python -m compileall -q scripts\batch_collect_verify.py src\ydz\session.py tests\unit\test_batch_handling_info.py`

Current status:
- Operators can now retry the authoritative batch from the workbench once an active CIT A-ready `work.html` URL is available.

## 2026-06-10 addendum: explicit YDZ work.html source path implemented for CIT A

- Added an explicit YDZ `work.html` source path for CIT A supplement refresh.
- New inputs:
  - `--coverage-supplement-ydz-work-url`
  - `YDZ_SUPPLEMENT_WORK_URLS`
- The flow supports both `cloud.chanjet.com/ydzee/.../work.html` and `inte-cloud.chanjet.com/ydzee/.../work.html`.
- The URL is opened as a YDZ batch-declare context, scanned for CIT A account-row signals, and if possible reused to submit fresh YDZ collection and resolve a new backend taskId.
- Source-readiness classification now includes explicit work URL scan records together with other-enterprise scan records.
- Full URLs are redacted in diagnostics.

Validation:
- `python tests\unit\test_batch_handling_info.py`
- `python -m compileall -q scripts\batch_collect_verify.py src\ydz\session.py tests\unit\test_batch_handling_info.py`

Current status:
- This removes the app-entry discovery blocker when an operator can provide a valid active `work.html` URL.
- The authoritative batch remains source-blocked at `8/10` until a CIT A-ready URL/account set is available and produces a fresh taskId for normal verification.

## 2026-06-10 addendum: CIT A YDZ token blocker fixed, source now needs active CIT-ready account sets

- Fixed the Yidaizhang authenticated-entry recovery path: an already-authenticated YDZ landing/redirect page without login inputs now opens the known cloud workbench and waits for API tokens instead of trying to fill a non-existent login form.
- Reran `output\batch_runs\codex_full_20260609_204530` with YDZ credentials, CIT A fresh refresh, and enterprise scanning.
- Coverage remains `8/10`; `CIT_A:filed` and `CIT_A:unfiled` remain missing.
- The current enterprise scan now succeeds and reads 144 account rows for `202605`, but `citSignalCount=0`.
- `batch_problem_details.csv` remains header-only; no parser, mapping, mismatch, or web-missing evidence exists.
- Added workbench-based enterprise discovery; live probe can read 10 selectable enterprises from `workbench.chanjet.com`.
- Other enterprise switching still cannot generate fresh YDZ taskIds unless the target enterprise exposes an active YDZ cloud workbench entry. Sampled enterprises either lacked a usable entry or had YDZ unavailable/expired.

Next follow-up:
- Provide a valid active YDZ `work.html` URL for an enterprise with CIT A account rows, or create/import CIT A account sets into the current enterprise before retrying fresh collection.
- If an enterprise exposes an active YDZ app entry, rerun CIT A fresh refresh and only then continue parser work if a real A200000/current-declare form produces mismatch or web-missing evidence.
- Do not treat the remaining CIT A gaps as code parser failures until such page evidence exists.

## 2026-06-10 addendum: CIT A retry now blocked by YDZ token refresh, not parser evidence

- Hardened Yidaizhang enterprise-entry and enterprise-switch handling so stale cloud workbench tabs are not treated as successful selector opens.
- Added a workbench checkbox to opt into CIT A Yidaizhang fresh refresh and other-enterprise scanning.
- Classified `http=701 / token 不能为空` from Yidaizhang batch-list API as `ydz_login_required`.
- Added BOM-tolerant tax-number parsing and cleaned the temporary BOM duplicate introduced during the live retry.
- Reran `output\batch_runs\codex_full_20260609_204530` with target-scoped CIT A supplement.
- Coverage remains `8/10`; `CIT_A:filed` and `CIT_A:unfiled` remain missing.
- The retry found three backend candidates for each CIT A target, but fresh Yidaizhang refresh failed at token readiness before generating a new taskId.
- `batch_problem_details.csv` remains header-only; no parser, mapping, mismatch, or web-missing evidence exists.
- `coverage_missing.csv` now shows `ydz_login_required` and tells the operator to refresh/provide Yidaizhang login state before retrying.

Next follow-up:
- Relaunch or refresh Yidaizhang login state from the workbench temporary credential fields, then rerun CIT A fresh refresh with enterprise scanning enabled.
- If fresh refresh starts returning account rows, continue with source discovery: either find a CIT-ready enterprise or create/import CIT A account sets.
- Only change parsers after a CIT A task reaches a real A200000/current-declare A-class form and produces comparison evidence.

## 2026-06-10 addendum: CIT A other-enterprise scan added, credentials are the next blocker

- Added explicit other-enterprise source discovery for CIT A supplement gaps.
- The scan is enabled with `--coverage-supplement-scan-ydz-enterprises` and is bounded by `--coverage-supplement-ydz-enterprise-scan-limit`.
- It reads Yidaizhang batch account rows in other enterprises and reports `citSignalCount` plus sample tax numbers when found.
- Reran `output\batch_runs\codex_full_20260609_204530` with target-scoped CIT A supplement and other-enterprise scan.
- Coverage remains `8/10`; `CIT_A:filed` and `CIT_A:unfiled` remain missing.
- Current enterprise still has 144 scanned account rows and `citSignalCount=0`.
- Other-enterprise scan could not proceed because there was no `YDZ_USERNAME/YDZ_PASSWORD` in the terminal and the browser login state was insufficient to open the enterprise selector.
- `coverage_missing.csv` now shows `other_enterprise_scan_login_required` guidance via the source-readiness text.
- `batch_problem_details.csv` remains empty; no parser, mapping, mismatch, or web-missing evidence exists.

Next follow-up:
- Provide Yidaizhang credentials through the workbench temporary fields or environment, then rerun the scan.
- If the scan finds a CIT-ready enterprise, rerun CIT A fresh collection against that enterprise.
- If no enterprise has a CIT signal, create/import a CIT A account set before continuing parser work.

## 2026-06-10 addendum: CIT A source-readiness diagnostics are now visible

- Added `coverageSupplement.sourceReadiness` for missing coverage targets.
- `batch_summary.html` and `coverage_missing.csv` now show the source-readiness reason before generic backend diagnostic text.
- Reran the current batch `output\batch_runs\codex_full_20260609_204530` with target-scoped CIT A supplement and fresh-YDZ refresh.
- Coverage remains `8/10`; missing targets remain `CIT_A:filed` and `CIT_A:unfiled`.
- The latest retry found one backend candidate for each CIT A target, but both failed at `tax_login_expired`.
- Source readiness now records that the current Yidaizhang enterprise scanned 144 account rows for `202605`, with `ydzCitSignalCount=0` for both CIT A targets.
- `coverage_missing.csv` now tells the operator to switch to an enterprise with CIT A account rows or create/import such account sets before retrying.
- `batch_problem_details.csv` remains header-only; no mismatch, web-missing, parser, or mapping defect was produced.

Next follow-up:
- Add a controlled workbench action to scan selectable Yidaizhang enterprises for CIT-ready account rows, or reuse account-set creation to create/import a CIT-ready sample before fresh collection.
- Do not continue parser work until a CIT A task reaches a real A200000 filed row or an A-class current-declare form.

## 2026-06-10 addendum: CIT A current-enterprise scan is now bounded but source still missing

- Added current-enterprise account discovery for CIT A fresh Yidaizhang refresh.
- Tightened the scan after live retry evidence:
  - use only the batch period for current-enterprise fresh collection,
  - require a CIT signal in the account row before submitting,
  - cap fresh-task discovery with a short supplement-specific timeout.
- Reran `output\batch_runs\codex_full_20260609_204530` with target-scoped CIT A supplement and fresh-YDZ refresh.
- Current enterprise `蓝天之爱` returned 144 account rows for period `202605`, but `citSignalCount=0`; no fresh YDZ taskId was created.
- Backend fallback still failed for tax-login expiry or source-entry mismatch only.
- Coverage remains `8/10`; missing targets remain `CIT_A:filed` and `CIT_A:unfiled`.
- `batch_problem_details.csv` remains header-only; no mismatch, web-missing, parser, or mapping defect was produced.

Next follow-up:
- To finish CIT A coverage, use a Yidaizhang enterprise/batch period that has CIT-ready account rows, or create/import such account sets before running fresh collection.
- Filed coverage still needs a task whose tax-bureau declaration query page exposes a CIT A/A200000 row.
- Unfiled coverage still needs a task whose current-declare scope exposes a real A-class form entry.

## 2026-06-10 addendum: CIT A fresh YDZ refresh path tested, still source-blocked

- Added exact-status-first supplement candidate ordering and an explicit `--coverage-supplement-refresh-cit-from-ydz` flag.
- Reran `output\batch_runs\codex_full_20260609_204530` with target-scoped CIT A supplement and the fresh-YDZ flag.
- The run found 10 backend CIT A candidates: 5 filed probes and 5 unfiled candidates.
- Fresh YDZ refresh checked all 10 candidate tax numbers. All returned `no_ydz_account_in_current_enterprise` for enterprise `蓝天之爱`, so no fresh taskId was created.
- Historical candidate verification still covered 0 CIT A gaps. Nine candidates failed at expired tax-login/task-cookie state, and one `CIT_A:filed` candidate reached the query path but had no target A200000 declaration record.
- Coverage remains `8/10`; missing targets are still `CIT_A:filed` and `CIT_A:unfiled`.
- `batch_problem_details.csv` remains header-only. No mismatch, web-missing, parser failure, or mapping defect was produced.

Next follow-up:
- To finish CIT A coverage, provide or create CIT A account sets inside the current Yidaizhang enterprise, or run the fresh-collection path against an enterprise that contains the candidate tax numbers.
- If a fresh task reaches an actual A200000 page or current-declare A-class form and then produces field evidence, fix parser/mapping defects from that evidence.

## 2026-06-10 addendum: expanded CIT A retry still source-blocked

- Reran `output\batch_runs\codex_full_20260609_204530` with target-scoped CIT A supplement using a 540-day CIT lookback and up to 10 candidates per missing target.
- The run attempted 20 CIT A candidates: 10 filed probes and 10 unfiled candidates.
- Coverage stayed `8/10`; `CIT_A:filed` and `CIT_A:unfiled` remain missing.
- `batch_problem_details.csv` remains header-only. No field mismatch, parser failure, or web-missing row was produced.
- Filed probes mostly failed at expired tax-login state. Two Sichuan probes reached the declaration query page, refreshed the target quarter, and then found no CIT A/A200000 row for the period, so they remain source-state conflicts.
- Unfiled candidates all failed at expired tax-login state in this retry.

Next follow-up:
- Do not spend more time on parser changes until a CIT A candidate reaches an actual A200000 page or current-declare form and produces field evidence.
- Prefer fresh CIT A tasks with valid tax-login state. For filed coverage, the declaration query page must show a CIT A/A200000 row for the requested period. For unfiled coverage, the tax-bureau current-declare scope must show a real A-class entry.
- Keep `CIT_A:filed` unknown-status probes available as a controlled retry path, but treat successful backend collect rows without tax-bureau source evidence as insufficient for coverage.

## 2026-06-10 addendum: targeted CIT A supplement retry and remaining blocker

- Added a supplement-only execution path for existing runs: use `--coverage-supplement-only` with `--coverage-supplement-targets CIT_A:filed,CIT_A:unfiled` to retry only the missing CIT A targets without changing the batch coverage scope or re-verifying all original items.
- Reran the current batch `output\batch_runs\codex_full_20260609_204530` with target-scoped CIT A supplement. Coverage stayed `8/10`; `CIT_A:filed` and `CIT_A:unfiled` are still missing.
- The run found three newer `CIT_A:unfiled` candidates. They failed for tax-login expiry or source/entry-state mismatch. `batch_problem_details.csv` remains header-only, so there are still no actionable field mismatches or web-missing rows.
- Tightened Guangdong CIT A undeclared handling: hot-service-only resident-enterprise CIT shortcuts are no longer clicked as if they were current-declare entries. A live rerun of `2063992496406681785` now fails at tax-home precheck in about 28 seconds with `UndeclaredTaxTargetUnavailableError`.

Next follow-up:
- To finish the original coverage goal, the remaining need is not a parser fix but usable CIT A source evidence: a filed task whose tax-bureau query result actually contains an A200000 row, and an unfiled task whose `本期应申报` scope contains a real A-class/current-declare action.
- Keep using `--coverage-supplement-targets` for future CIT-only retries; do not narrow `coverageTaxTypes` just to retry missing targets.

## 2026-06-10 addendum: codex_full_20260609_204530 current status after VAT small and CIT triage

- Current authoritative coverage for `output\batch_runs\codex_full_20260609_204530` is `8/10`.
- Covered targets: `VAT_GENERAL:filed`, `VAT_GENERAL:unfiled`, `VAT_SMALL:filed`, `VAT_SMALL:unfiled`, `CULTURE_FEE:filed`, `CULTURE_FEE:unfiled`, `CBJ_PERSONAL:any`, and `CBJ_ANNUAL:any`.
- `VAT_SMALL:unfiled` is now covered by task `2076981259194503123`; `vat_small_main`, `vat_small_appendix1`, and `vat_small_appendix2` all completed without mismatch or web-missing fields after split-DOM and percent-rate parsing fixes.
- `batch_problem_details.csv` for this run currently has no problem rows. The old `2077489396773357438` VAT small supplement differences are suppressed because the same target is now covered by a clean successful supplement candidate.
- Remaining gaps are `CIT_A:filed` and `CIT_A:unfiled`.
- A targeted CIT supplement retry with a 365-day CIT lookback found no usable `CIT_A:filed` candidate for period `202605`; returned successful collect tasks were parsed as `unfiled` or `unknown`.
- The targeted CIT retry attempted eight `CIT_A:unfiled` candidates. Failures were tax-login expiry or tax-bureau/source-state mismatches where the live page only exposed B-class, deemed-assessment, hot-service, or no current A-class undeclared entry. No field mismatch or web extraction defect was produced.

Next follow-up:
- To cover `CIT_A:filed`, obtain or create a successful backend collect task for period `202605` whose execution log has current-period=true and whose tax-bureau query page contains the A200000/CIT A row.
- To cover `CIT_A:unfiled`, prefer a fresh task where the live tax-bureau home page lists an actual A-class or resident-enterprise bookkeeping-assessment undeclared row with a fill action, not only a hot-service shortcut.
- Keep `batch_problem_details.csv` focused on successful/current comparison reports; use supplement attempts for external source-state and login blockers.

## 2026-06-09 addendum: codex_full_20260609_204530 remaining coverage triage

- Rebuilt coverage for `output\batch_runs\codex_full_20260609_204530` after the undeclared-entry/auth fast-fail fixes.
- Current authoritative coverage is `6/10`: `VAT_GENERAL:filed`, `VAT_SMALL:filed`, `CULTURE_FEE:filed`, `CULTURE_FEE:unfiled`, `CBJ_PERSONAL:any`, and `CBJ_ANNUAL:any` are covered.
- `CULTURE_FEE:unfiled` is now covered by task `2077729330826989198`; `culture_fee_main` matched `32/32`, and `culture_fee_deduction` produced an evidence-only report because the backend API returned no comparable fields.
- Expanded backend supplement to 6 candidates per remaining target with 120-day normal lookback and 180-day CIT lookback. The run found 23 candidates and tried the remaining missing targets, but none produced a clean report.
- `VAT_GENERAL:unfiled` has only external/source-state blockers in tested candidates so far: the tax bureau reports the target as already declared or requires manual force-enter confirmation.
- A forced fresh Yidaizhang collection attempt for `91120112MA06GE876Y` did not create a new task because the current enterprise has no matching Yidaizhang account set for that tax number.
- `VAT_SMALL:unfiled` remains uncovered; tested candidates are source-state conflicts or expired tax-login/session cases, not confirmed parser failures.
- `CIT_A:filed` remains uncovered; tested filed candidates either have no target declaration row for the queried period or expired tax-login state. A focused Tianjin rerun reached the declaration query page and direct browser inspection showed only culture fee and VAT rows, confirming source-state conflict for that candidate.
- `CIT_A:unfiled` remains uncovered; the Jiangsu sample reached the tax bureau home but exposed only a hot-service/title entry that did not open an editable CIT form, while other candidates expired at tax-login.

Next follow-up:
- Try additional backend supplement candidates for `VAT_GENERAL:unfiled`, `VAT_SMALL:unfiled`, `CIT_A:filed`, and `CIT_A:unfiled`, preferably from fresher task rows.
- If a CIT A unfiled candidate reaches a province home page with an actual editable entry, capture the page text/click result and add a province-specific entry rule.
- Keep treating tax-bureau already-declared messages for known-unfiled backend tasks as source-state conflicts, not successful filed coverage.

## 2026-06-09 addendum: coverage supplement gating and backend search follow-up

- Fixed coverage gating so only clean successful verification records count as covered.
- Rebuilt `codex_full_20260609_172724` coverage after the fix; stale failed-candidate rows no longer count as coverage or problem details.
- Added controlled supplement lookback with `--coverage-supplement-lookback-days`.
- Removed the privacy-login filter from coverage supplement backend search. Live diagnostics then found CIT A and CBJ personal candidates that were previously hidden.
- Covered `VAT_GENERAL:unfiled` with task `2077729274992279442`.
- Covered `CBJ_PERSONAL:any` with task `2077729713080388191`.
- Current coverage for `codex_full_20260609_172724` is `6/10`; `batch_problem_details.csv` currently has 0 rows.

Remaining follow-up:
- `VAT_SMALL:unfiled`: backend candidates exist, but tested live tax-bureau pages report already declared.
- `CULTURE_FEE:unfiled`: backend candidates exist, but tested live pages either lack the undeclared entry or report already declared.
- `CIT_A:unfiled`: backend candidates exist; the Jiangsu sample reaches the portal and clicks the `居民企业（查账征收）企业所...` hot-service entry, but no editable CIT form opens.
- `CIT_A:filed`: no successful filed CIT A candidate was found in the 38-day successful collect-task search; returned CIT A candidates were parsed as unfiled.

## 2026-06-09 addendum: full coverage run follow-up after `codex_full_20260609_172724`

- Fixed the remaining code-resolvable mismatch in VAT general filed sample `2077729644358679384`.
- Root cause: appendix1 `hjxse_6` API returned `0.0`, while the equivalent main-form immediate-refund current-period sales fields returned `17699.12` and matched the tax-bureau page.
- Added a narrow fallback for appendix1 `hjxse_6` and verified appendix1 now reports `134/134` matches.
- Reran the batch item for `9111011457522550X2`; the batch summary now marks `VAT_GENERAL:filed` as success.
- Opened backend supplement to try multiple candidates per missing target. A rerun with `--coverage-supplement-max-candidates 3` found 9 candidates and attempted additional VAT small, VAT general, and culture-fee unfiled samples.
- Fixed the Shanghai VAT general undeclared retained-tax cumulative rule. Replaying the captured web evidence for `2077729330827119155` now reports `158/158` matches for `vat_general_main`; live rerun is blocked because the tax bureau now says the period is already declared.
- Hardened Yunnan undeclared tax-home navigation so repeated page-navigation interruptions are not reported as raw Playwright failures.
- Confirmed Yunnan `CULTURE_FEE:unfiled` task `2077729644358674126` now fails for the real external reason: the current tax-bureau home page has no culture-fee undeclared entry for the target period.
- `batch_problem_details.csv` can still contain stale rows from the pre-fix Shanghai timed-out run because the live tax-bureau state no longer allows regenerating that undeclared page. The code-level replay has verified the mismatch is fixed.

Remaining follow-up:
- Find another representative task for `CULTURE_FEE:unfiled`, or correct the tax-bureau/backend state for `91532522MA6KL66M5N`.
- `VAT_SMALL:unfiled` and one `VAT_GENERAL:unfiled` sample are status conflicts where the backend task says unfiled but the tax-bureau page shows already declared or no matching undeclared menu.
- `CIT_A:filed` and `CIT_A:unfiled` still have no successful backend collect samples in the scanned range.
- Pending tax-login locks and `needForceTax=true` remain external operator actions, not comparison/parser failures.

## 2026-06-09 addendum: batch stability fixes after `ops_20260609_161052`

- Monitored run `ops_20260609_161052` through completion.
- Fixed selected tax-type verification so all registered forms remain visible; selected forms with zero comparable API fields now generate `not_comparable` evidence reports instead of being filtered out.
- Added bounded web extraction recovery so a single form recovery loop cannot block the batch indefinitely.
- Added `--verify-timeout` to cap each `main.py` verification subprocess from the batch runner.
- Added tax-home status detection for undeclared navigation; if the target row already shows declared, the flow avoids repeated undeclared-entry recovery and falls into declared-query/status-conflict handling.
- Fixed final batch verification for no-taskId items so they end as `task_unresolved/manual` instead of staying `collect_checked/running`.
- Added fast failure for repeated pending tax-login task locks when the backend keeps returning the same occupying taskId.
- Verified with focused unit tests, compileall, and a `--skip-browser` check for consumption-tax task `2077729270697418910`.
- Live browser verification after the fix:
  - `2077729644359026066` kept `culture_fee_deduction` despite 0 API comparable fields and then surfaced the expected already-declared/status-conflict reason.
  - `2077729270697418910` completed `consumption_tax_main` and `consumption_tax_surcharge`, both with 29/29 matches.

Remaining follow-up:
- Pending tax-login task locks now fail faster after repeated same-task evidence; a later workbench policy can still decide whether to retry these items at the end or expose a dedicated operator action.
- Backend supplement task-list queries remain serial in this pass because they share browser-derived login/token state; parallelization should first split them into independent request clients.
- Province-specific undeclared home-page structures may still need targeted entry rules when new failures appear.

## 2026-06-09 addendum: VAT small appendix2 refund column parsing fixed

- Confirmed task `2077729738850235767` had three false mismatches in `vat_small_appendix2`: `bqybtse_cjs`, `bqybtse_jyfj`, and `bqybtse_dfjyfj`.
- Root cause: the page text parser mapped columns only through the seventh numeric value and left `bqybtse_*` to the default `0.00` path.
- Fixed `bqybtse` to read the ninth numeric value in each surcharge row.
- Live rerun of `vat_small_appendix2` for the task now reports `total=32 match=32 mismatch=0`.

## 2026-06-09 addendum: backend supplement target-scoped verification

- Monitored run `ops_20260609_152646` and confirmed the main avoidable time sink was backend supplement verification using `--targets auto` on multi-tax tasks.
- Fixed supplement verification so the active coverage target limits the form list passed to `main.py`.
- This specifically avoids culture fee supplement attempts running VAT general forms first.
- Remaining time sinks are external tax-bureau waits: declaration-query `/loading` recovery and pending tax-login job locks.
- Future speed work should consider configurable fast-fail/skip for pending tax-login locks and safe sharding by separate operator/browser profile/CDP port; simple parallel verification in one browser/profile is not safe.

## 2026-06-09 addendum: non-VAT supplement query filters audited

- Checked public-manage `getTaskListInternal` filters for CIT A, culture fee, consumption tax, and CBJ after the VAT `taxTypeId` regression.
- Confirmed `taxTypeId` request filters can return mixed rows and are not reliable for coverage supplement.
- Fixed coverage registry mappings to use `taxId=2` for CIT A, `taxId=3` for culture fee, `taxId=26` for consumption tax, and existing `taxId=39` for CBJ.
- Verified live backend wrapper queries return rows containing the requested tax kind; multi-tax rows such as VAT+CIT or VAT+culture are expected when they contain the requested `taxId`.

## 2026-06-09 addendum: VAT small filed supplement query fixed

- Confirmed task `2077729738850235767` is `VAT_SMALL:filed`: direct task API selected small VAT forms and task logs parsed `current-period=true`.
- Root cause: coverage supplement queried VAT with backend `taxTypeId=1`, but the public-manage task-list API only narrowed VAT reliably with `taxId=1`; the collect-task query also lacked server-side `taskTypeId=3`, so valid small VAT rows were pushed beyond the scanned pages.
- Fixed VAT coverage targets to use `taxId=1`, and fixed collect-task searches to send `taskTypeId=3`.
- Live backend supplement check now matches `2077729738850235767` for `VAT_SMALL:filed`.

## 2026-06-09 addendum: Tianjin unfiled VAT status conflict fixed

- Confirmed backend supplement selected task `2077729648653721147` as `VAT_GENERAL:unfiled`; the missing coverage was not caused by backend query filters.
- Hardened undeclared tax-home recovery for Tianjin-style cards by allowing target-title expansion followed by scoped action-button click.
- Changed known-unfiled handling so a tax-bureau "already declared" blocker is reported as a status conflict instead of falling back to declared-query verification.
- Verified the live Tianjin task now stops at the expected conflict message when the tax bureau says the period is already declared.

## 2026-06-09 addendum: coverage supplement collect-status filter

- Added `已取数` and `未取数` options to the workbench coverage range.
- Backend supplement now uses selected tax types and selected collect statuses together.
- Added `--coverage-collect-statuses` to `scripts/batch_collect_verify.py` and persisted selections in `state.json` as `coverageCollectStatuses`.
- Existing batches without the new state field keep the old default of both statuses.

## 2026-06-09 addendum: workbench manual account-set source entry

- Added a `手工创建账套` workbench entry for operators who already have customer name, tax number, region, tax login method, privacy number, proxy tax number, and password.
- Manual-source account-set jobs use `--manual-source-env --skip-privacy-phone-sync` and pass customer login fields through transient child-process environment variables.
- Manual-source jobs skip public-manage backend page login/query and skip integration privacy-number synchronization/preparation.
- Added regression coverage for workbench HTML, command generation, child-process environment mapping, manual source resolution, and script-level backend-page skipping.

## 2026-06-09 addendum: account-set slider handoff made operator-visible

- Added a stable `MANUAL_VERIFICATION_REQUIRED` log marker when Yidaizhang password login triggers slider verification.
- Workbench account-set jobs now display `需人工验证 / 等待易代账滑块` while the process is still running, with an operator action telling the user to complete the slider in Chrome.
- After manual slider completion, the existing script continues waiting for a valid workbench session and then resumes backend login/source lookup and customer/account-set creation.
- Added logs that distinguish reusing an existing Chrome CDP session from launching a new browser with `--disable-blink-features=AutomationControlled`.
- Fixed Windows workbench PID detection to query processes without sending signals.
- Synced the behavior into the standalone account-set skill and installed local `ydz-create-customer` skill copy, then refreshed `skills/ydz-create-accountset.zip`.

## 2026-06-09 addendum: account-set full-flow retry fixes

- Fixed the Yidaizhang integration login handoff that can stop on `passport.../vm/redirectVM` after authentication; the flow now clicks the entry when possible and falls back to opening `work.html`.
- Fixed public-manage source lookup for long lookbacks by querying in <=39-day windows, avoiding the backend 40-day range limit.
- Fixed tax-number file parsing for UTF-8 BOM files generated by Windows tooling.
- Synced the fixes into the standalone `ydz-create-accountset` skill and the installed local `ydz-create-customer` skill copy.
- Verified `91330YYJ3200684` from a clean run: login and backend querying now proceed, but the tax number has no successful backend task with login info and is correctly marked `FAILED`.
- Verified the full successful integration path with `91110112MA7JR5JN75`: existing customer was found, tax login info was saved/verified, and integration privacy-phone data was pulled successfully.

## 2026-06-08 addendum: Chrome automation marker mitigation added

- Added `--disable-blink-features=AutomationControlled` to project-owned Chrome startup paths related to Yidaizhang/account-set work and the shared CDP browser startup helper.
- Synced the same startup argument to the standalone account-set skill and installed local `ydz-create-customer` skill copy.
- Kept Yidaizhang slider detection and manual handoff because this browser flag is only a mitigation, not a guaranteed bypass.

## 2026-06-08 addendum: Yidaizhang slider login handoff fixed

- Account-set creation now detects the 易代账 slider verification page and waits for the operator to complete it instead of repeatedly submitting the login form.
- After backend login finishes, the flow re-checks 易代账 readiness so a manually completed slider can be picked up before failing.
- Account-set creation no longer closes the shared Chrome CDP browser, preserving the operator's manual login state for later tasks.

## 2026-06-08 addendum: backend login is embedded in account-set/privacy flows

- Removed the standalone backend-login form from the workbench main UI.
- Account-set creation remains the normal place to provide backend credentials; the flow logs in automatically before querying backend login information.
- Privacy-number synchronization/preparation also uses automatic backend login instead of requiring a separate pre-login operation.
- Kept the backend-login script/job path only for internal diagnostics and compatibility.

## 2026-06-08 addendum: integration account-set privacy-number preparation

- Added privacy-number synchronization support for integration account-set creation.
- After resolving backend login information, integration creation now queries `data-task-management-chanapp.inte.chanjet.com/.../privatePhone/summary` with payload `{"privatePhone": "<value>"}`.
- If the integration summary is empty, the flow runs the online backend copy sequence, then calls integration `pullPrivateDataByPrivatePhone`.
- Integration privacy-number endpoints deliberately omit the `token` header; keeping `token` causes `用户身份证认证失败，请重新进行认证。`.
- Added a workbench `隐私号同步` entry for the online copy operation and synced the integration preparation logic into the standalone account-set skill and installed local skill copy.
- Verified with unit tests, compileall, standalone skill tests, and a live check showing `15500000001` already exists in integration summary.

## 2026-06-08 addendum: workbench backend login and missing source handling

- Added a dedicated public-manage backend login entry to the local workbench.
- The new job runs only backend login readiness and stores sanitized status under `output/backend_login_runs/<runId>/`.
- Backend credentials entered in the workbench are passed only through the child process environment.
- `scripts/ydz_create_customers.py` supports `--login-only --login-target backend` without tax numbers.
- Public-manage `403 / 无权访问` is now treated as not logged in in the project script and reusable account-set skill copies.
- If account-set creation cannot find backend login/source information for one tax number, that tax number is marked `FAILED` and the remaining tax numbers continue.

## 2026-06-08 addendum: account-set backend source query uses task categories

- Updated public-manage task-list payload for account-set source lookup to send `taskCategorys: "2,3"`.
- Removed `taskTypeId: "3"` from that request payload so the lookup matches the `国税/取票` backend filter.
- Kept collect-task client-side filtering for verification and coverage callers that still need only collect tasks.
- Synced the same rule to the standalone account-set skill and the installed local `ydz-create-customer` skill copy.
- Added regression coverage for the project query payload and the standalone skill payload.

## 2026-06-08 addendum: fixed account-set login retry and backend 403 detection

- Fixed Chanjet login automation to retry submit when the login form remains visible.
- Avoided toggling an already-selected custom agreement checkbox off.
- Added Yidaizhang public-site `进入易代账` handoff before direct workbench open.
- Treated public-manage `403 / 无权访问` as not logged in, even when storage tokens exist.
- Synced the same login fixes to the standalone `ydz-create-accountset` skill and local `ydz-create-customer` skill copy.
- Verified with compileall, `tests/unit/test_ydz_create_customers_script.py`, standalone skill unittest, and skill validation.

## 2026-06-08 addendum: clarified workbench-first project and standalone skill boundary

- Reframed the project as a local operator workbench for Yidaizhang login, tax collection verification, account-set creation, monitoring, and issue handling.
- Updated project rules and memory so new operational work should be exposed through the workbench instead of remaining as isolated command-line flows.
- Documented that `skills/ydz-create-accountset/` is a reusable standalone skill package for other agents.
- Added static tests that prevent the account-set skill from importing this repository's `src.*` or `scripts.*` modules, and from documenting project-only dependencies.

## 2026-06-08 addendum: operator console account-set auto-login

- Updated `scripts/ydz_create_customers.py` so account-set creation auto-logins to the selected Yidaizhang environment and public-manage when no browser login state exists.
- 集测 uses `YDZ_INTE_*`; 线上 uses `YDZ_PROD_*`; public-manage uses `TAX_BACKEND_*`.
- Added `--env-file` and `--skip-auto-login` to preserve local secret-file and existing-session-only workflows.
- Updated the `创建账套` workbench entry to pass environment-specific temporary credentials through the child process environment only.
- Verified with script help, compileall, `tests/unit/test_ydz_create_customers_script.py`, and `tests/unit/test_ops_console.py`.

## 2026-06-08 addendum: fixed account-set skill login

- Added `login` command to the portable YDZ account-set CLI.
- `doctor --open` and `create` now auto-login from configured environment variables or `--env-file` by default.
- Added integration workbench direct-open handling after authentication to avoid getting stuck on the real-name-auth reminder redirect.
- Updated portable and local YDZ skill instructions to run `login` before asking the user for passwords.
- Bundled the fixed self-contained CLI into the local `ydz-create-customer` skill for hosts that use that skill folder directly.
- Verified with unit tests, compileall, skill validation, CLI help, `doctor`, and a dry-run against `91120102754804355E`.

## 2026-06-08 addendum: operator console account-set creation entry

- Implemented a `创建账套` form in the local operator console.
- Reused `scripts/ydz_create_customers.py` for backend-source lookup, idempotent customer creation, dynamic tax-info save, and verification.
- Added `accountset` job rendering so the current-task panel shows sanitized results without treating them as tax-form verification batches.
- Added health checks for the account-set script and output directory.
- Verified with `tests/unit/test_ops_console.py`, `tests/unit/test_ydz_customer_creation.py`, `scripts/ydz_create_customers.py --help`, and `compileall`.

## 2026-06-08 addendum: packaged YDZ account-set automation

- Implemented portable skill package `skills/ydz-create-accountset/`.
- Added self-contained CLI `skills/ydz-create-accountset/scripts/ydz_accountset_cli.py` with `doctor` and `create` commands.
- Added references for workflow, field mapping, secret handling, and troubleshooting.
- Added offline tests under `skills/ydz-create-accountset/tests/`.
- Verification completed with compileall, unittest, skill validation, CLI help, and sensitive-value scan.

## 2026-06-04 补充：低覆盖率误报已修复
- 已实现：单表比较结果中，低网页解析覆盖率只有在真实形成可比对 `web_missing` 时才进入 `quality_issues`；无网页缺失、全字段可通过时不再影响结果。
- 已实现：批量工作台汇总不再直接使用 stderr 中的 `low web extraction coverage` 日志作为需处理原因，改为读取报告 JSON 的质量问题。
- 已验证：`ops_20260604_141814` 中 `2076981280669355836`、`2076981280669355835` 全部表单 `match_rate=100%`、`web_missing=0`、`quality_issues=[]`。
- 已刷新：`output\batch_runs\ops_20260604_141814\batch_summary.html` 和 `ops_status.json`，本轮结果不再显示低覆盖率人工处理原因。

## 2026-06-04 补充：网页缺失补救性能优化
- 已实现：网页读取只对最终参与比对的字段做抽取和补读，避免接口无值字段拖慢滚动恢复。
- 已实现：只有真实会形成 `web_missing` 的字段才触发昂贵恢复；低覆盖但无网页缺失时只记录日志并继续比较。
- 已实现：通用滚动重试只在完全没有读到字段时兜底，避免内外两层重复扫完整页面。
- 已验证：`tests/unit/test_web_extraction_recovery.py`、`tests/unit/test_vat_small_web_extraction_parsers.py`、`tests/unit/test_consumption_tax_support.py`、`compileall` 通过。
- 现场结论：`ops_20260604_132337` 当前旧进程慢在附表一/二/三全量补读；新逻辑需重启验证后生效。

## 2026-06-04 补充：消费税主表底部行虚拟渲染缺失修复
- 已实现：消费税主表读取缺少 14-17 行时，滚动重试改为多段纵向扫描，覆盖近底部虚拟渲染区域。
- 已实现：消费税附加表内容可见但菜单选中态短暂未读到时，用业务字段数量兜底确认目标页。
- 已验证：`tests/unit/test_consumption_tax_support.py`、`tests/unit/test_detail_form_switching.py`、`compileall` 均通过。
- 已验证：`2076981675808305083` 重跑成功，消费税主表 `38/38`、消费税附加税费计算表 `29/29`，报告 `output\reports\2076981675808305083\compare_summary_2076981675808305083_20260604_125119.html`。
- 现场结论：本次 `web_missing=8` 是山东消费税未申报页底部 14-17 行未进入 DOM 的虚拟渲染问题，不是接口缺字段，也不是进错所属期。

## 2026-06-04 补充：同税号连续消费税验证恢复
- 已实现：未申报入口返回统一登录页时，当前 taskId 自动重登一次并重试目标表。
- 已实现：后台状态未知、未申报首页无目标税种入口时，自动切回已申报查询；后台明确未申报时不切回。
- 已实现：已申报查询按接口所属期选择申报记录，避免打开上一期同名消费税记录。
- 已验证：`tests/unit/test_detail_form_switching.py`、`tests/unit/test_consumption_tax_support.py`、`tests/unit/test_shanxi_query_recovery.py`、`compileall` 均通过。
- 已验证：`2076981650034436464` 重跑成功，消费税主表 `38/38`、消费税附加税费计算表 `29/29`，报告 `output\reports\2076981650034436464\compare_summary_2076981650034436464_20260604_123005.html`。
- 现场结论：`2076981650034436464` 与 `2076981650034436465` 确实是同一税号、同一山东税局会话；旧失败不是字段不存在，而是连续任务登录态刷新、状态未知入口回跳、以及已申报查询未按所属期选记录叠加造成。

## 2026-06-04 补充：附表五多行减免说明列位修正
- 已实现：一般纳税人附表五对减免性质代码和政策依据被拆成多行的情况做列位修正，避免 `bqyjse_*` 本期已缴税额错读为空。
- 已实现：稀疏零值行只对 `bqyjse_*` 做窄兜底，行名存在但没有数值时仍不补 0。
- 已验证：`tests/unit/test_vat_appendix5_extraction.py`、`tests/unit/test_normalizer_comparator.py`、`compileall` 均通过。
- 已验证：`2076614022309347199 --targets vat_general_appendix5 --skip-pdf` 重跑成功，附表五 `18/18` 匹配、`web_missing=0`。
- 现场结论：`2076614022309347199` 的 `bqyjse_jyfj`、`bqyjse_dfjyfj` 是网页解析假缺失，不是税局页面没有值，也不是接口字段错误。

## 2026-06-04 补充：对齐插件登录剩余差异
- 已实现：`window.robotId` 未初始化时短等待；如果固定 `machineId` 取 cookie 失败，发现真实 `robotId` 后自动重试一次。
- 已实现：direct fallback 对青岛定向清理 `TGCT`、`enable_gizqLgxJ4gkh`，补齐 EtaxPlugin 对青岛登录态的特殊处理。
- 已实现：`needForceTax=true` 在验证结果中归类为需要人工确认是否强制进入税局，不默认自动 `forceEnterTax`。
- 后续关注：用新启动的批量任务观察真实成功率；如青岛仍卡登录，再考虑把青岛清理域名扩展到父域 `.chinatax.gov.cn`，不要全省份推广。

## 2026-06-04 补充：默认插件优先进税局并减少 loading 卡点
- 已实现：真实验证默认 `--tax-login-strategy plugin_first`，批量脚本和运营台新启动任务会优先走 EtaxPlugin 清 cookie、关闭旧税局页、打开新 tpass 页。
- 已实现：插件派发前尝试结束旧 background taskId，减少后续 getClientJob 被旧进税局任务占用的概率。
- 已实现：登录检测和旧页复用均排除 `/loading`、`tpass.*#/login` 和空正文页面，避免把半登录状态当作可验证页面。
- 已实现：direct fallback 注入脚本补充 `/loginb/` 的 `tgtUrl` 二跳；申报查询持续 loading 会提前进入恢复路径，并最终归类为登录态/数字账户认证未就绪。
- 后续关注：`needForceTax=true` 暂不默认自动强制进入税局；如运营需要，应增加显式按钮或参数，并在结果页明确风险。

## 2026-06-03 补充：增值税网页解析假缺失修复

- 已实现：一般纳税人附表一初次网页提取覆盖率低时，自动滚动纵向/横向可滚动容器并重试缺失字段。
- 已实现：小规模增值税主表改用专用文本解析，避免把“栏次”读成金额。
- 已实现：小规模附列资料（一）和附列资料（二）改用专用文本解析，附表二可稳定读取税率、减征比例等列。
- 已实现：关键表单网页提取覆盖率门槛提高，避免“接口 0 + 网页空”大面积静默通过。
- 已验证：`2076614026604697199` 真实回归成功，原一般附表一 3 个网页缺失字段已匹配。
- 已验证：`2076614417445323010` 真实回归成功，小规模主表、附表一、附表二均 `web_missing=0`。
- 后续关注：其它省份/税种如果仍出现网页低覆盖，应按表单结构补专用解析器，而不是继续扩大通用 DOM 猜列逻辑。

## 2026-06-03 补充：个税残保金后台补齐识别
- 已实现：残保金日志识别支持 `personNum`、`personNumSum`、`monthNumSum`、`amountSum`、`申报月份汇总`、`申报人次汇总` 等个税残保金特征。
- 已实现：汇算清缴残保金标记优先级高于个税标记，避免汇算任务被误归类。
- 已实现：后台补齐阶段对日志无法识别的残保金任务增加 task result 二次确认；`sz_cbj` 中同时存在 `snzzzgrs_cbj` 和 `snzzzggzze_cbj` 时，可归类为个税残保金。
- 已验证：`2076614073849978635` 当前可识别为个税残保金，且两个后端字段均可读取。
- 后续关注：下一次全量批次确认 `CBJ_PERSONAL:any` 覆盖缺口是否被补齐，并观察 `cbjModeSourceCounts` 里 API 兜底命中数量和耗时。

## 2026-06-03 补充：湖北申报查询恢复与进税局任务锁

- 已实现：从未申报页冲突切回已申报查询时，优先直接打开申报信息查询页，spHandler 仅作为兜底。
- 已实现：当前页恢复遇到统一登录页时，允许新税局页再恢复一次。
- 已实现：后台提示已有进税局任务未完成时，短等待后明确失败并展示占用任务号。
- 已验证：`2076614026604654385 --skip-browser` 可解析为增值税小规模未申报；完整验证当前被进税局任务锁 `2076614043783903619` 拦截，新逻辑约 90 秒内给出明确失败原因。
- 后续关注：等待占用进税局任务释放或后台处理后，重新跑 `2076614026604654385`，确认湖北查询恢复后是否还存在小规模/一般纳税人页面状态冲突。

## 2026-06-03 补充：山东未申报入口恢复

- 已实现：未申报页面回到税局首页/门户页时，自动按目标税种重新点击申报入口，再继续表单准备和表单确认。
- 已验证：`2076614043783892312` 重新运行成功，山东未申报增值税主表、附表一至附表五和文化事业建设费均完成验证。
- 后续关注：其它省份如出现不同首页卡片结构，按失败截图继续补充目标税种入口选择器。

本文件维护当前任务、待办和优先级。完成任务后需要更新。

## 当前状态

截至 2026-06-02：

- `main.py` 是推荐真实验证入口。
- 批量完整链路已支持：税号列表 -> 易代账取数 -> 后台 taskId 查询 -> 验证 -> 批量汇总。
- 本地运营工作台已支持任务启动、进度监控、问题处理、覆盖检查。
- 当前支持税种覆盖框架：增值税一般纳税人、增值税小规模、企业所得税 A 类、文化事业建设费、消费税、残保金。
- 除残保金外，当前支持税种均区分已申报/未申报；未申报验证复用税局填表页逻辑，并在截图/解析前确认目标表单。
- 非残保金任务如果后台日志没有解析到申报状态，结果展示和税局实际导航均先按“未申报”处理。
- 消费税已接入两张已申报表：消费税及附加税费申报表、消费税附加税费计算表；已用 `2068825812082982843` 完成真实税局验证。

## P0：必须优先处理

### P0-1：启用后台补齐代表任务闭环

现状：

- 覆盖矩阵和后台补齐骨架已存在。
- 增值税可用任务执行日志判断已申报/未申报。
- 其他税种的申报状态字段或日志规则尚未完全确认。

目标：

- 对缺口目标自动查询当月成功取数任务。
- 判断任务是否满足目标税种和申报状态。
- 选一个代表 taskId 写入批量 state。
- 复用 `--skip-collect --verify` 继续验证。

下一步：

- 明确文化事业建设费、企业所得税、残保金等税种的后台状态判断字段；当期判断日志只依赖日志类型，不依赖日志编号。
- 为补齐流程增加运营台按钮和测试。

### P0-2：未申报场景逐税种页面策略

现状：

- 增值税一般纳税人、小规模、企业所得税 A 类、文化事业建设费、消费税未申报任务已统一放行到税局填表页策略。
- 未申报页会在提取和 PDF 前确认目标表单，避免停留在错误表单仍继续验证。
- 未申报增值税附表切换已改为当前页不匹配时立即点击菜单，避免每张附表先等待超时。
- 山西等省份未申报场景需要恢复导航。
- 后续其他税种或省份如果入口 URL、按钮、菜单结构不同，需要按失败截图和页面片段补充选择器。

目标：

- 每个支持税种都能真实进入未申报状态页面验证。
- 页面不可用时给出明确人工处理原因。

下一步：

- 用真实未申报任务分别回归小规模、企业所得税 A 类、文化事业建设费、消费税，确认各省税局入口和菜单关键字是否足够。
- 为新增税种记录未申报入口、页面字段抽取策略、失败截图。

### P0-3：继续降低外部登录卡点

现状：

- 已处理部分税局登录超时、数字账户失效、重复打开税局页面问题。
- 仍可能出现进税局任务锁、验证码、代理导致请求失败。

目标：

- 运营台展示直接原因和下一步动作。
- 自动关闭或避开失效页、重复税局页。
- 不把外部阻塞误判为数据比对失败。

## P1：近期高价值优化

### P1-1：新增税种接入规范

目标：

- 明确新增税种需要改哪些文件。
- 新增税种必须包含映射、CompareTarget、覆盖注册、测试、报告展示。
- 消费税接入可作为新增税种的当前参考样例。

验收：

- `PROJECT_CONTEXT.md`、`ARCHITECTURE.md`、`TASKS.md` 中能读到接入路径。
- 至少有一个新增税种模板或示例。

### P1-2：中文编码治理

现状：

- 历史文件中存在中文显示乱码风险。

目标：

- 统一关键文档为 UTF-8。
- 对依赖中文表单名、按钮名、sheet 名的逻辑增加更稳健匹配。

### P1-3：批量报告和运营台继续增强

目标：

- 一页内更清楚展示全部差异。
- 问题处理清单可追踪处理人、状态、证据。
- 覆盖矩阵可直接触发补齐验证。

## P2：中期工程质量

### P2-1：真实流程模块化

目标：

- 逐步拆分 `scripts/compare_tax_forms.py`。
- 优先下沉稳定能力到 `src/`。

候选模块：

- 目标表定义。
- Excel 映射加载。
- 任务执行日志。
- 税局页面导航。
- 网页字段抽取。
- 报告写入。

### P2-2：测试分层

目标：

- 默认测试不依赖真实浏览器和外部税局。
- 浏览器 E2E 和真实 taskId E2E 由人工显式触发。
- 覆盖补齐、任务日志、后台查询等纯逻辑有单元测试。

## P3：长期治理

### P3-1：敏感信息和运行产物治理

目标：

- 检查 `.gitignore`。
- 防止提交 browser profile、output、runtime、cookie、token、账号密码。
- 日志脱敏。

### P3-2：项目记忆持续维护

目标：

- 每次任务结束更新 `CHANGELOG_AI.md`。
- 规则变化更新 `AGENTS.md`。
- 架构变化更新 `ARCHITECTURE.md`。
- 取舍变化更新 `DECISIONS.md`。
- 待办变化更新本文件。

## 2026-06-01 当前补充状态

- 已修复批量汇总读取同一 taskId 历史报告导致的当前批次误报风险；新批次通过 `verify.reportPaths` 绑定本次验证产物。
- 已增加税局登录日志脱敏，避免 cookie、token、证件号、手机号等敏感值进入运行日志。
- 已优化取数轮询：`NO_NEED_COLLECTED` 视为完成；重复事件去重；取数超时前会尝试后台 taskId 兜底解析。
- 已增强覆盖补齐可观察性：后台查询会输出进度并支持 `--coverage-supplement-timeout`。
- 下一步真实验证重点：重新跑全量批次，确认消费税取数超时场景是否能被后台兜底解析接住，并确认新批次结果页不再展示历史网页缺失问题。
## 2026-06-01 补充：残保金覆盖规则

- 已实现：残保金不再区分“已申报/未申报”，覆盖矩阵只展示个税残保金和汇算清缴残保金的“已验证”目标。
- 已实现：后台补齐残保金候选不再依赖申报状态解析，后续仍走残保金专用验证逻辑。
- 下一步：下一次真实批量运行后确认覆盖缺口中不再出现残保金未申报项。

## 2026-06-01 补充：青岛税号重新验证

- 已确认：`91370203334145023C` 重新发起取数后生成新 taskId `2076005047487626573`，不再复用旧任务。
- 已实现：新批次默认重新发起取数；如需复用历史已取数任务，必须显式使用 `--reuse-collected-task`。
- 已实现：青岛税号进税局时强制使用 `qingdao` 省份和青岛 tpass 跳转参数，避免被后台旧省份字段覆盖。
- 待处理：青岛税局当前停在统一登录页，仍需人工完成登录认证后继续验证，或增加快速失败和运营提示。

## 2026-06-01 补充：后台补齐多候选重试

- 已实现：每个覆盖缺口最多保留并尝试 3 个后台候选任务。
- 已实现：批量结果页展示每个候选 taskId 的失败/完成步骤和直接原因。
- 已实现：覆盖分析优先使用当前批次 `verify.reportPaths`，减少历史报告干扰。
- 下一步：用真实全量批次确认覆盖率改善、耗时增加幅度，以及失败步骤分类是否足够准确。

## 2026-06-01 补充：残保金子类型识别

- 已实现：残保金自动模式优先读取后台“残保金任务返回结果”日志。
- 已实现：当日志显示“数据库未查询到返回数据，调用汇算清缴取数接口查询”时，即使 `taxTypeId=26`，也按汇算清缴残保金处理。
- 下一步：真实批量运行后确认 `91460000MAE0TMR45K` 的报告由 `CBJ_PERSONAL` 改为 `CBJ_ANNUAL`，并确认年度企业所得税表查询是否存在外部登录或页面卡点。

## 2026-06-01 补充：同一税号多个 taskId

- 已实现：一次取数解析到多个成功 taskId 时，批量流程会全部记录并逐个验证。
- 已实现：`collect.verifyTaskId` 保留第一个 taskId，`collect.verifyTaskIds` 保存全部 taskId。
- 已实现：额外 taskId 生成同税号内部子项，结果页和覆盖分析可以展示全部验证结果。
- 下一步：用真实税号 `91370102MA7D3P0D2P` 重新跑完整链路，确认 `2075110435864560097`、`2075110435864560096` 这类多任务场景全部被验证。
## 2026-06-04 补充：税局首页兜底入口安全规则

- 已实现：未申报直达 URL 失败、回到税局首页时，兜底入口点击会排除“办税进度及结果信息查询”等查询/进度类卡片。
- 已实现：兜底不再全页扫描任意“填写申报表/办理”按钮，必须位于申报区域或目标税种卡片内。
- 已验证：`tests/unit/test_detail_form_switching.py`、`tests/unit/test_task_login_flow.py`、`tests/unit/test_batch_handling_info.py`、`compileall` 均通过。
- 已验证：用修正后的代码重跑 `2076981254899665895` 成功，确认首页兜底不再误进查询进度页；增值税主表、附表一至五、文化事业建设费均为 100%。
- 后续关注：其他省份如果首页结构不同，应按失败截图补省份/税种安全入口，而不是恢复宽泛点击。
# 2026-06-08 addendum: YDZ customer creation automation

- Implemented reusable operational entry `scripts/ydz_create_customers.py`.
- Implemented core module `src/ydz/customer_creation.py` for backend source extraction, idempotent customer create/update, dynamic tax-info save, and verification.
- Added usage documentation in `docs/ydz_customer_creation.md`.

## 2026-06-09 coverage blocker follow-up

- Done: real batch observation run `codex_full_20260609_204530` completed and produced updated coverage/supplement records.
- Done: filed declaration-query refresh now sets the target tax period and handles `cit_a_main` unique fallback safely.
- Done: supplement failure categories now distinguish source-state conflicts, target-entry unavailable, tax-login expired, tax-login blocked, timeout, and generic verification failure.
- Next: optimize undeclared home-entry click flow so one failed target action/title does not repeat the same click for minutes before failing.
- Next: update login detection so `/mhzx/api/mh/tpass/code` and authorization-code error pages are treated as auth failures immediately.
- Next: add focused regression coverage for Beijing `CULTURE_FEE:unfiled` repeated `填写申报表` and Jiangsu `CIT_A:unfiled` hot-service/title-only homepage behavior.
- Next: investigate `VAT_GENERAL:unfiled` timeout in appendix recovery and decide whether to cap expensive recovery per form in supplement mode.
