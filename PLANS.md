# PLANS.md

## 2026-06-11 completed: protect user Chrome with account-set CDP fallback ports

Goal: let account-set creation continue when port `9222` is occupied by a normal Chrome that Playwright cannot control, without disrupting the user's browser.

Result:
- Added a shared CDP connection helper to the project account-set script.
- Added `--enable-automation` to managed Chrome startup flags.
- If the requested CDP port fails because Chrome lacks automation-compatible startup flags, the flow retries on `9333`, `9444`, `9555`, then `9666`.
- Fallback ports use sibling browser profiles suffixed with the port number.
- Updated login-only and create flows to use the helper.
- Synced the same self-contained behavior into `skills/ydz-create-accountset/` and installed `ydz-create-customer`.

Validation:
```powershell
python tests\unit\test_ydz_create_customers_script.py
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m compileall -q scripts\ydz_create_customers.py skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests tests\unit\test_ydz_create_customers_script.py
python -m py_compile C:\Users\Administrator\.codex\skills\ydz-create-customer\scripts\ydz_accountset_cli.py
```

Residual boundary:
- This handles the known Playwright automation-flag incompatibility. If all candidate ports are occupied by incompatible browsers or Chrome cannot launch at all, the flow still needs the operator to free a port or fix Chrome availability.

## 2026-06-11 completed: add public-manage backend API auth for account-set creation

Goal: reduce backend-source account-set creation's dependence on an open public-manage browser page by supporting backend API token authentication.

Result:
- Added a provider-based backend auth module for public-manage `Authorization` and `access_token`.
- `ChanjetAdminTaskQuery` can query task rows with a token provider and no browser context.
- Privacy-phone online copy and integration pull use the same provider; integration requests still omit `token`.
- `scripts/ydz_create_customers.py` supports `--backend-auth-mode auto|token|password|browser`.
- `auto` tries configured backend tokens, then guarded account-password API login, then browser fallback.
- Standalone `skills/ydz-create-accountset/` and installed `ydz-create-customer` were synchronized.

Validation:
```powershell
python tests\unit\test_chanjet_admin_auth.py
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_chanjet_admin_privacy_phone.py
python tests\unit\test_ydz_create_customers_script.py
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m compileall -q scripts\ydz_create_customers.py src\chanjet_admin skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests tests\unit\test_chanjet_admin_auth.py tests\unit\test_chanjet_admin_task_query.py tests\unit\test_chanjet_admin_privacy_phone.py tests\unit\test_ydz_create_customers_script.py
```

Live checks:
- Backend password API attempt returned `MANUAL_VERIFICATION_REQUIRED` / `访问拒绝` for the current account.
- With a valid SSO-derived backend token, `ChanjetAdminTaskQuery(token_provider=...)` queried tax number `91110112MA7JR5JN75` without a browser context and found task rows.

Residual boundary:
- Account-password backend login is still subject to SSO risk controls. Browser fallback remains required for slider, SMS, MFA, access-denied, password-change, or other visible verification states.

## 2026-06-11 completed: fix production YDZ app-entry crawling for account-set creation

Goal: make production account-set creation recover automatically when the browser is logged in but stuck on the Yidaizhang landing page, redirectVM page, or Chanjet workbench instead of the cloud workbench.

Result:
- Added a workbench app-list recovery helper to `scripts/ydz_create_customers.py`.
- The helper opens the configured org's app list, clicks the primary `易代账` `进入应用` control, and waits for the normal `cloud.chanjet.com/ydzee/.../work.html` API context.
- Updated no-credential/manual-session waiting to use the same recovery path.
- Hardened `src/ydz/session.py` app-entry selection so longer production rows are accepted.
- Synced the same self-contained recovery into `skills/ydz-create-accountset/` and installed `ydz-create-customer`.

Validation:
```powershell
python tests\unit\test_ydz_create_customers_script.py
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m compileall -q scripts\ydz_create_customers.py src\ydz skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests
```

Live non-mutating smoke through the current Chrome CDP returned:
```text
https://cloud.chanjet.com/ydzee/u7anoc8y5p7p/49le0svcsa/work.html#/home/dataBoard
```

Residual boundary:
- This recovery still needs a valid Chanjet browser login state. If production account-password auth returns access denial/manual verification and no browser SSO exists, the operator must complete the visible challenge.

## 2026-06-10 completed: support SDSRDX account-set login methods

Goal: add the two tax bureau manual captcha-code login methods to account-set creation after verifying the live Yidaizhang page configuration.

Result:
- Added `SDSRDX` and `DLYW-SDSRDX` normalization and validation to the project account-set flow.
- Backend-source lookup now passes `loginType=YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX` and locally filters unsupported or incomplete rows.
- `SDSRDX/DLYW-SDSRDX` save the phone/login account through `cTaxPreparerName`; `DLYW-SDSRDX` saves the proxy company tax number through `cSiteLoginName`.
- Integration privacy-phone copy/pull is skipped for manual captcha-code methods.
- Workbench manual-accountset form exposes the two new methods and labels the shared input as privacy number/phone.
- Standalone `skills/ydz-create-accountset/` script, references, and tests were updated.
- Installed `C:\Users\Administrator\.codex\skills\ydz-create-customer` was synchronized with the updated standalone script/reference behavior.

Validation:
```powershell
python tests\unit\test_ydz_customer_creation.py
python tests\unit\test_ops_console.py
python tests\unit\test_chanjet_admin_task_query.py
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
```

Residual boundary:
- This run validates code and payload mapping with unit tests. It does not create a live account set for a real tax number.

## 2026-06-10 completed: resolve account-set accountant from login phone

Goal: make the account-set assigned accountant default to the accountant corresponding to the logged-in Yidaizhang phone number.

Result:
- Confirmed the Yidaizhang frontend employee endpoint `trans/easyacctg/employee/getChildEmpListByUserId` from downloaded static assets.
- Project account-set creation now queries the employee list, filters out admin-only rows, matches login phone to `mobile`, and uses row `userId` as `accountantEmployeeId`.
- Fallback order is current Yidaizhang `userId`, then environment default.
- Result output includes `accountantId` and `accountantSource`.
- Standalone `skills/ydz-create-accountset/` has the same self-contained behavior and tests.

Validation:
```powershell
python tests\unit\test_ydz_customer_creation.py
python tests\unit\test_ydz_create_customers_script.py
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m compileall -q scripts\ydz_create_customers.py src\ydz skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests
```

Residual boundary:
- This was verified against real frontend API definitions and mocked real response shapes. The current shell has no authenticated Yidaizhang token context, so a live employee-list API response was not fetched in this run.

## 2026-06-10 completed: use YDZ integration captcha API before browser fallback

Goal: let integration Yidaizhang account-set creation pass the default captcha code through the normal login interface path, reducing Playwright dependence for the login step.

Result:
- Project password auth calls `loginV2/accountVerify` with encrypted account/password and captcha code before `loginV2/accountLogin`.
- Integration defaults the captcha code to `666666`; production has no default captcha value.
- Browser fallback fills a visible captcha field with the configured value when present.
- Standalone `skills/ydz-create-accountset/` has the same self-contained behavior and tests.

Validation:
```powershell
python tests\unit\test_ydz_create_customers_script.py
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m compileall -q scripts\ydz_create_customers.py src\ydz skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests
```

Residual boundary:
- This is not a slider/SMS/manual-verification bypass.
- If the HTTP login flow does not expose `iframeToken` and `ciaToken`, `auto` still needs browser fallback to initialize Yidaizhang business tokens.

## 2026-06-10 completed: make YDZ account-set auth password-first by default

Goal: make password mode higher priority than browser mode without losing browser fallback when password auth cannot produce business tokens.

Result:
- Changed project and standalone skill `resolved_ydz_auth_mode()` default to `auto`.
- Auto mode tries password auth first, then falls back to browser login on missing credentials, slider/CAPTCHA blockers, password-change blockers, or SSO-without-business-token states.
- Explicit `password`, `browser`, and `token` modes remain available.
- Updated workbench auth selector to show `自动（账号密码优先）` as the default blank option and added explicit browser selection.

Validation:
```powershell
python tests\unit\test_ydz_create_customers_script.py
python tests\unit\test_ops_console.py
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m py_compile scripts\ydz_create_customers.py scripts\ops_console.py skills\ydz-create-accountset\scripts\ydz_accountset_cli.py
```

Residual boundary:
- Auto mode still falls back to browser when password auth cannot expose a Yidaizhang API token context.
- Explicit password mode remains strict and may fail on manual verification challenges.

## 2026-06-10 completed: add manual source mode to standalone YDZ account-set skill

Goal: let copied skill users create/update account sets when the user already provides customer and tax-login fields, without requiring public-manage backend access.

Result:
- Added `--manual-source-env` and `--skip-privacy-phone-sync` to the standalone skill CLI.
- Added `ManualSourceResolver` and `manual_source_from_env()` inside the skill.
- Manual source mode reads `YDZ_MANUAL_*`, skips public-manage lookup, skips privacy-phone sync, and reuses the same Yidaizhang create/save/verify API flow.
- Updated skill references with the required variables and usage.

Validation:
```powershell
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m py_compile skills\ydz-create-accountset\scripts\ydz_accountset_cli.py
```

Residual boundary:
- Manual mode does not remove the need for valid Yidaizhang auth.
- If area code is not supplied and Yidaizhang tax geo cannot resolve it, the manual source fails as incomplete.

## 2026-06-10 completed: add guarded YDZ account-password auth mode

Goal: try normal Chanjet account-password login before falling back to browser/token mode, without bypassing verification challenges or persisting secrets.

Result:
- Added `src/ydz/password_auth.py` with RSA encryption, CIA auth-code retrieval, account-login submission, response classification, and token-context extraction.
- Added `scripts/ydz_create_customers.py --ydz-auth-mode password`.
- Added a workbench auth-mode option for password auth.
- Copied equivalent self-contained logic into `skills/ydz-create-accountset/scripts/ydz_accountset_cli.py`.

Validation:
```powershell
python tests\unit\test_ydz_create_customers_script.py
python tests\unit\test_ops_console.py
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m compileall -q main.py scripts src skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests
```

Residual boundary:
- The local environment does not have pytest, so `tests\unit\test_ydz_password_auth.py` was verified by directly calling its test functions.
- Password mode does not bypass slider/CAPTCHA, SMS, phone binding, or password-change prompts.
- If SSO succeeds but Yidaizhang business tokens are not exposed outside browser-initialized `work.html`, the flow stops with `SSO_READY_TOKEN_UNAVAILABLE`.
- Public-manage backend lookup is still browser-session based.

## 2026-06-10 completed: reduce YDZ account-set page dependency with token auth

Goal: let account-set creation reuse valid Yidaizhang API tokens directly when another host or operator already has them, while keeping browser mode as a verified fallback login path.

Result:
- `YdzCustomerApi` accepts a browser page or a token auth context.
- `scripts/ydz_create_customers.py --ydz-auth-mode token` reads token values from environment variables or `--env-file`.
- Manual-source token-mode runs can avoid Chrome entirely because no backend lookup or privacy-phone sync is needed.
- Backend-source token-mode runs still use the public-manage browser session for backend source data.
- The standalone `skills/ydz-create-accountset/` package has matching token-auth support without project imports.

Validation:
```powershell
python tests\unit\test_ydz_customer_creation.py
python tests\unit\test_ydz_create_customers_script.py
python tests\unit\test_ops_console.py
python skills\ydz-create-accountset\tests\test_ydz_accountset_cli.py
python -m compileall -q main.py scripts src skills\ydz-create-accountset\scripts skills\ydz-create-accountset\tests
```

Residual boundary:
- This does not implement a direct password-to-token login client. It only removes the page dependency after a valid Yidaizhang API token context is already available.
- Public-manage backend lookup is still browser-session based.

## 2026-06-10 in progress: make standard backend candidates avoid tax-login failures

Goal: except for consumption tax and Enterprise Income Tax A-class, future backend supplement candidates should not end in tax-bureau login failures.

Latest progress:
- Removed the default fresh-Yidaizhang refresh step for VAT general, VAT small, culture fee, CBJ personal, and CBJ annual supplement targets.
- The runner now verifies historical public-manage backend candidates directly through the normal `main.py --task-id` path.
- Standard targets honor the configured candidate limit directly; the default remains 3 candidates per missing target.
- If one historical candidate fails at tax-bureau login readiness, the attempt preserves the direct failure category and the runner tries the next backend candidate/tax number.
- The supplement phase final exit code follows final coverage state, so a later successful historical candidate clears earlier failed attempts for the same target.
- If all configured historical candidates fail, the target remains failed with the collected reasons.
- Backend candidate selection now prefers distinct tax numbers inside the configured candidate limit before falling back to more taskIds from the same tax number, including when results are merged from multiple search windows.
- Failed, incomplete, non-object, unresolved inner-task/province, or exhausted `getClientJob` metadata responses are now classified as tax-login readiness failures, so they can be retried/excluded consistently with expired `getTaskCookie` candidates.
- Standard supplement now runs a lightweight login preflight against a bounded raw candidate pool before full verification. Definitively not-ready `getClientJob`/`getTaskCookie` candidates are dropped, then the normal configured final candidate limit is applied.
- When that preflight drops a target below the final limit, the same run now performs up to 3 bounded refills from backend history with the newly not-ready taskIds excluded, then preflights and merges the refill candidates.
- Refill searches temporarily exclude taskIds already seen in the current run, including ready and unknown preflight candidates, so duplicate taskIds do not take refill slots.
- Preflight `not_ready` records are merged into future supplement exclusions, so reruns skip taskIds already proven not login-ready.
- Removed the workbench fresh retry count field and standard fresh retry-wave CLI wiring.
- CIT A and consumption tax are explicitly excluded from this default route.
- Verification still goes through `main.py --task-id`; the change only affects candidate selection and fallback behavior.

Validated:
```powershell
python tests\unit\test_batch_handling_info.py
python tests\unit\test_ops_console.py
python tests\unit\test_coverage_framework.py
python tests\unit\test_task_login_flow.py
python -m compileall -q main.py scripts src
```

Regression coverage now includes a `run_coverage_supplement_phase` unit scenario where `history-1` and `history-2` fail at tax-login readiness, then `history-3` covers the standard target.
Supplement planner regression coverage also verifies that when the newest two candidates share one tax number and a later candidate has another tax number, the planner picks the different-tax-number candidate before retrying the same tax number.
Cross-window merge regression coverage verifies that when one search window finds tax number A and the next returns A then B, the merged pool keeps A and B.
Tax-login classification coverage verifies incomplete `getClientJob` metadata, generic `getClientJob failed: ...` errors, and unresolved inner taskId/province metadata are categorized as `tax_login_expired`.
Login-preflight regression coverage verifies candidates with incomplete `getClientJob` metadata are dropped before full verification while candidates with valid `getClientJob` and `getTaskCookie` responses are kept.
State exclusion regression coverage verifies preflight `not_ready` records exclude their taskIds on later supplement runs.
Same-run refill regression coverage verifies an expired first preflight pool is excluded before the next backend search and that the ready refill candidate is verified.
Duplicate-refill regression coverage verifies a ready candidate from the first pass is excluded from the next refill query.

Remaining work:
- Prove the behavior on a real supported target run before calling the broader robustness goal complete.
- If live evidence still shows distinct historical tax-number candidates all failing at tax-login readiness, inspect whether backend login information itself is stale or whether a separate account-set/preparation flow is required.

## 2026-06-10 completed: prevent new backend candidates from hanging at tax login

Goal: keep new backend supplement candidates on the real tax-bureau verification path while making login readiness failures bounded and diagnosable.

Result:
- No historical successful taskId/report reuse was added. New candidates still run through `main.py --task-id`.
- Tax-login readiness waits are now bounded for client-job metadata, task-cookie polling, direct `/loading`, `tpass.*#/login`, and authorization-code pages.
- Persistent login/auth readiness pages raise `TaxLoginNotReadyError` and are normalized into tax-login blocker output rather than field-comparison failures.
- English same-province switch-limit messages are classified as `tax_login_blocked`.
- Field mismatches after forms are reached remain visible as completed comparison output.

Validation:
```powershell
python tests\unit\test_task_login_flow.py
python tests\unit\test_batch_handling_info.py
python -m compileall -q main.py scripts src tests\unit\test_task_login_flow.py tests\unit\test_batch_handling_info.py
```

Residual boundary:
- The code cannot make an externally invalid tax-bureau session valid. Slider, digital-account confirmation, expired tax-login state, or pending backend "enter tax bureau" jobs can still block a candidate, but they should now surface as classified blockers instead of an indefinite wait.

## 2026-06-10 in progress: finish full coverage after CIT A source blockers

Goal: keep the full batch coverage objective intact while reducing all code-resolvable failures and identifying the remaining source blockers.

Latest update:
- User explicitly deferred Enterprise Income Tax A-class coverage for this round. The authoritative batch report was refreshed with coverage scope `VAT_GENERAL,VAT_SMALL,CULTURE_FEE,CBJ_PERSONAL,CBJ_ANNUAL`; consumption tax remains out of scope for the current round.
- Under the current agreed scope, `coverage_matrix.csv` has 8 covered targets, `coverage_missing.csv` has 0 rows, and `batch_problem_details.csv` has 0 rows.
- The full batch objective is complete for the current agreed scope; `CIT_A:filed` and `CIT_A:unfiled` remain a later source-readiness follow-up, not a current parser or comparison blocker.
- Added `ydz_no_need_collect` source-readiness classification. When a fresh YDZ collect request is accepted but returns `NO_NEED_COLLECTED`, the remaining CIT A gap now tells the operator that the account set cannot produce a verifiable taskId for the period and that the next step is to change the tax-number candidate or period.
- Added a workbench CIT A account-set precheck action. It reads the current batch's CIT A source-readiness state, extracts the representative filed/unfiled candidate tax numbers, and runs the existing account-set workflow in `--dry-run` mode only.
- A command-build check against `codex_full_20260609_204530` extracted `91500105MAEQ3URL80` for `CIT_A:filed` and `91310115MA1HAHW684` for `CIT_A:unfiled`; the generated command includes `--dry-run`.
- A live CIT-only supplement retry with enterprise scan enabled found `2063992990329483939` for `CIT_A:unfiled`, but verification stopped at expired `getTaskCookie` before reaching a CIT A form. `CIT_A:filed` still lacks a clean filed source. Problem details remain empty.
- CIT A enterprise scanning now checks already-open ready YDZ `work.html` tabs before attempting workbench enterprise switching. This lets an operator manually open a target enterprise tab and rerun the scan without copying the URL.
- The workbench batch form now has an optional CIT A YDZ `work.html` URL field. When filled, it passes `YDZ_SUPPLEMENT_WORK_URLS` to the child process and enables CIT A fresh refresh without exposing the raw URL in the displayed command.
- Added an explicit YDZ `work.html` source path for CIT A supplement refresh. Operators can pass `--coverage-supplement-ydz-work-url` or `YDZ_SUPPLEMENT_WORK_URLS`; the flow opens the URL, requires YDZ API token readiness, scans CIT A account rows, and reuses existing fresh collection plus `main.py` verification when a taskId is resolved.
- Fixed Yidaizhang authenticated landing/redirect recovery. If no login inputs exist, the session now opens the known workbench URL and waits for API tokens instead of failing with `Could not locate Yidaizhang login inputs`.
- Live CIT A retry now reaches current-enterprise YDZ API and scans 144 account rows; `citSignalCount=0`.
- Workbench enterprise discovery can read 10 selectable enterprises from `workbench.chanjet.com`.
- Other selectable enterprises still do not yield fresh taskIds unless their YDZ app exposes an active cloud workbench entry. Sampled entries were unavailable/expired or did not open `work.html`.
- Hardened Yidaizhang enterprise-selector and enterprise-switch handling so stale cloud workbench tabs do not count as a successful selector open or switch.
- Added a workbench option to pass CIT A fresh-refresh and Yidaizhang enterprise-scan flags to the batch runner.
- Reran the current batch's CIT A supplement with fresh refresh and scan enabled.
- Coverage remains `8/10`, with `CIT_A:filed` and `CIT_A:unfiled` still missing.
- The latest source blocker is no active CIT A-ready YDZ account source in the current enterprise, plus no usable active YDZ cloud app entry from sampled other enterprises.
- `coverage_missing.csv` now shows current-enterprise no-CIT-source guidance instead of the previous YDZ token/login blocker.
- `batch_problem_details.csv` remains empty; there is still no mismatch, web-missing, parser, or mapping evidence.

Current result:
- Authoritative run: `output\batch_runs\codex_full_20260609_204530`.
- Coverage is `8/10`.
- Covered: VAT general filed/unfiled, VAT small filed/unfiled, culture fee filed/unfiled, CBJ personal, and CBJ annual.
- Missing: `CIT_A:filed` and `CIT_A:unfiled`.
- Latest CIT-only supplement retry confirmed current-enterprise fresh scan is bounded and signal-gated, attempted backend fallbacks, and persisted per-target `sourceReadiness`. It produced no mismatch or web-missing rows.

Validated evidence:
- `batch_problem_details.csv` has 0 rows.
- `python tests\unit\test_batch_handling_info.py`, `python tests\unit\test_ydz_collector.py`, and `python -m compileall -q main.py scripts src` pass after the no-need source classification change.
- The latest retry found three backend candidates for each CIT A target, current-enterprise YDZ scanning reached 144 account rows, and none exposed a CIT A signal.
- Workbench enterprise list is discoverable, but sampled other enterprises could not open a usable YDZ cloud workbench entry for scanning.
- `coverage_missing.csv` currently shows current-enterprise no-CIT-source guidance for both CIT A targets.
- No fresh Yidaizhang taskId was created in the current retry.

Next options:
- Provide a valid active YDZ `work.html` URL for an enterprise that has CIT A account rows through the workbench field, `--coverage-supplement-ydz-work-url`, or `YDZ_SUPPLEMENT_WORK_URLS`; alternatively create/import CIT A account sets in the current enterprise for the batch period.
- Or manually open a CIT A-ready YDZ `work.html` tab in the shared browser, enable enterprise scanning, and rerun the CIT A supplement refresh.
- If account scanning succeeds in an active enterprise, rerun the CIT A supplement refresh so it can create a fresh taskId and then verify through the normal `main.py` path.
- For filed coverage, the fresh task must expose an A200000 row in the declaration query page for the target period.
- For unfiled coverage, the current-declare scope must contain an actual A-class form entry.
- Once such a candidate reaches a real CIT A form and produces mismatch/web-missing evidence, fix the parser or mapping if needed.

## 2026-06-09 completed: reduce backend supplement verification waste

Goal: monitor the running coverage-supplement batch and identify work that can be shortened or safely parallelized.

Result:
- Confirmed backend supplement task-list search took roughly two minutes, while real tax-bureau verification was the larger cost.
- Found a concrete waste pattern: `CULTURE_FEE:filed` and `CULTURE_FEE:unfiled` supplement attempts used `--targets auto`, so multi-tax backend tasks could run or fail on VAT forms before reaching culture fee.
- Fixed supplement verification to scope the `main.py` form list to the active coverage target's registered forms.
- Confirmed CBJ personal verification is already fast through the backend-only path; CBJ annual is still limited by tax-bureau login and can be blocked by pending tax-login jobs.

Follow-up options:
- Add a configurable fast-fail or operator "skip pending tax-login lock" behavior for repeated pending job IDs.
- Consider backend supplement search parallelism by independent `taxId` groups; expected gain is modest compared with tax-bureau verification.
- Consider parallel verification only by sharding across separate Chrome profiles, CDP ports, and ideally separate operators. A single shared tax-bureau session should remain serialized.

Validation:
```powershell
python tests\unit\test_batch_handling_info.py
python -m compileall -q scripts\batch_collect_verify.py tests\unit\test_batch_handling_info.py
```

## 2026-06-09 completed: backend taxId audit for coverage supplement

Goal: check whether supported non-VAT tax types had the same public-manage `taxTypeId` filtering problem as VAT.

Result:
- Confirmed `getTaskListInternal` `taxTypeId` request filters can return mixed rows and are not reliable supplement filters.
- Coverage supplement now uses `taxId=1` for VAT, `taxId=2` for CIT A, `taxId=3` for culture fee, `taxId=26` for consumption tax, and `taxId=39` for CBJ.
- Returned row metadata such as `taxTypeIds` and `taskTaxRelVOList` remains diagnostic/inference data, not the primary server-side query field.

Validation:
```powershell
python tests\unit\test_coverage_framework.py
python tests\unit\test_chanjet_admin_task_query.py
python -m compileall -q src\coverage\registry.py src\coverage\supplement.py src\chanjet_admin\task_query.py tests\unit\test_coverage_framework.py tests\unit\test_chanjet_admin_task_query.py
```

## 已完成任务：整理项目为工作台主线并固化 skill 独立性

任务名称：工作台主线与建账 skill 边界整理

目标：
- 明确项目主目标是本地运营工作台。
- 工作台覆盖自动登录易代账、取数验证、创建账套、监控和问题处理。
- 自动登录并创建账套的 skill 抽取为可复制给其他智能体使用的独立包。
- 防止 skill 反向依赖项目源码。

实施结果：
- 更新 README、项目记忆和 agent 规则，把工作台作为默认运营入口。
- 明确命令行脚本是工作台执行器和开发调试入口。
- 更新 `skills/ydz-create-accountset/SKILL.md` 的独立性约束。
- 新增 skill 静态测试，检查 CLI 不导入项目 `src.*` / `scripts.*`，文档不绑定项目路径。

状态：完成整理；后续新增运营能力应优先接入工作台，并同步检查 skill 独立性。

## 已完成任务：工作台创建账套按环境自动登录

任务名称：创建账套入口补齐集测/线上登录能力

目标：
- 工作台创建账套时明确选择集测或线上环境。
- 没有浏览器登录态时，按环境自动登录易代账，并自动登录报税后台。
- 避免账号密码进入代码、命令行、任务记录或结果文件。

实施结果：
- `scripts/ydz_create_customers.py` 默认先尝试自动登录，再进入后台查询和客户创建流程。
- 集测读取 `YDZ_INTE_*`，线上读取 `YDZ_PROD_*`，报税后台读取 `TAX_BACKEND_*`。
- `scripts/ops_console.py` 的创建账套表单可临时传入对应环境的登录信息，子进程环境传递，不落盘。
- 保留 `--skip-auto-login` 作为只复用已有登录态的调试路径。

验证方式：
```powershell
python -m compileall -q scripts\ydz_create_customers.py scripts\ops_console.py tests\unit\test_ops_console.py tests\unit\test_ydz_create_customers_script.py
python scripts\ydz_create_customers.py --help
python tests\unit\test_ydz_create_customers_script.py
python tests\unit\test_ops_console.py
```

状态：完成代码改造；真实自动登录仍依赖已配置的环境变量、env 文件或工作台临时填写的账号密码。

## 已完成任务：对齐 EtaxPlugin 登录前置清理和人工强制边界

任务名称：补齐插件登录差异的稳定性兜底

目标：
- 减少因 `window.robotId` 初始化慢导致的 `getTaskCookie` 失败。
- 补齐青岛税局登录的插件特殊 cookie 清理。
- 明确 `needForceTax` 是人工确认场景，不在自动验证里默认强制进入。

实施结果：
- `TaskLoginFlow` 会等待真实 `robotId`，并在固定 `machineId` 失败时用真实机器码重试一次。
- direct fallback 对青岛清理 `TGCT`、`enable_gizqLgxJ4gkh`。
- `needForceTax=true` 会快速归类为人工确认原因，批量/运营台不再展示为底层异常。

状态：完成本轮代码改造；仍需后续用新启动的真实批量验证观察成功率。

## 已完成任务：降低税局登录 loading 和半登录失败概率

任务名称：真实验证默认插件优先进税局

目标：
- 验证时尽量快速进入完整可用的税局/数字账户会话。
- 参照 EtaxPlugin 手动登录逻辑，减少 direct tpass 半登录导致的 `/loading` 和 tpass 回跳。
- 保留 direct 路径作为插件不可用时的 fallback。

实施结果：
- 真实 taskId 验证默认改为 `plugin_first`。
- 插件派发补充旧 background taskId 的 `setEndCookie`。
- 登录检测、旧页复用和申报查询恢复均排除 `/loading` 半登录状态。
- direct fallback 补充 `/loginb/` 读取 `tgtUrl` 的二跳。

验证方式：
```powershell
.\.venv\Scripts\python.exe tests\unit\test_task_login_flow.py
.\.venv\Scripts\python.exe tests\unit\test_detail_form_switching.py
.\.venv\Scripts\python.exe tests\unit\test_batch_handling_info.py
.\.venv\Scripts\python.exe tests\unit\test_shanxi_query_recovery.py
.\.venv\Scripts\python.exe tests\unit\test_ops_console.py
.\.venv\Scripts\python.exe tests\unit\test_cbj_verification.py
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

状态：完成本轮代码改造；仍需后续用新批次真实验证观察成功率。

## 已完成任务：新增消费税税种验证

任务名称：消费税两张表接入真实税局验证

目标：
- 支持 `sz_xfs` 消费税接口数据自动选择验证目标。
- 支持消费税及附加税费申报表、消费税附加税费计算表两张表。
- 使用 taskId `2068825812082982843` 完成真实税局验证。

实施结果：
- 已完成 CompareTarget、Excel 映射加载、网页专用解析、覆盖注册、测试和真实验证。
- 已处理后台接口 requests SSL EOF，增加 curl 兜底。

验证方式：
```powershell
python tests\unit\test_consumption_tax_support.py
python tests\unit\test_coverage_framework.py
python main.py --task-id 2068825812082982843 --targets auto --skip-browser --log-level INFO
python main.py --task-id 2068825812082982843 --targets auto --log-level INFO
```

状态：完成。

## 已完成任务：无插件 tpass cookie 注入

任务名称：方案 2 去插件化进税局验证

目标：
- 保留真实 taskId 主流程和畅捷通 `getClientJob` / `getTaskCookie` 来源。
- 在项目内复刻 EtaxPlugin 的 tpass cookie/localStorage 注入逻辑。
- 让未加载 EtaxPlugin 的 Chrome 也能通过 tpass URL 进入税局。

实施结果：
- `TaskLoginFlow` 在浏览器上下文注册 document-start 初始化脚本，解析 tpass URL 的 `cookie=` 参数并写入登录态。
- `getTaskCookie` 增加 Python requests 兜底，减少无插件浏览器页面环境差异。
- `direct_first` 不再预先等待插件 bridge；插件打开新标签页仅作为 fallback。
- Chrome 自动启动支持传空插件路径来不加载 EtaxPlugin。

验证方式：
```powershell
python -m compileall -q src\login tests\unit\test_task_login_flow.py
python tests\unit\test_task_login_flow.py
```

状态：完成。

本文件记录长任务计划、里程碑和验证方式。超过 30 分钟、跨多个模块或影响生产流程的任务，应先更新本文件。

## 当前长期任务：覆盖补齐闭环

目标：

- 当前输入税号不能覆盖所有支持税种和已申报/未申报状态时，自动从后台查询成功取数任务补齐代表样本。
- 补齐后仍复用现有批量验证流程，不新增第二套生产验证逻辑。

不做：

- 不批量验证后台查询到的所有历史任务。
- 不绕过 `main.py` 和 `scripts/compare_tax_forms.py::run_compare()`。
- 不假设所有税种未申报页面相同。

### Milestone 1：覆盖矩阵基础

状态：完成

改动范围：

- `src/coverage/registry.py`
- `src/coverage/analyzer.py`
- `scripts/coverage_check.py`
- `scripts/batch_collect_verify.py`
- `scripts/ops_console.py`

验证方式：

```powershell
python tests\unit\test_coverage_framework.py
python scripts\coverage_check.py --run-dir output\batch_runs\<runId>
```

### Milestone 2：后台任务查询与日志规则

状态：完成

改动范围：

- `src/chanjet_admin/task_query.py`
- `src/chanjet_admin/task_execution_log.py`
- `src/coverage/supplement.py`
- `scripts/compare_tax_forms.py`

已完成规则：

- 增值税：`成功保存数据-是否是当期 / sz_zzs / logInfo=true|false`。
- 增值税覆盖补齐：后台任务列表使用 `taxId=1` 和 `taskTypeId=3`，一般纳税人/小规模用 `taxPayerType` 区分。

验证方式：

```powershell
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_task_execution_log.py
python tests\unit\test_coverage_framework.py
```

### Milestone 3：补齐候选任务落入批量 state

状态：进行中

改动范围：

- `src/coverage/supplement.py`
- `scripts/batch_collect_verify.py`
- `scripts/ops_console.py`

待办：

- 在运营台增加“自动补齐覆盖缺口”动作。
- 查询缺口目标对应的当月成功取数任务。
- 选代表任务写入当前批次 state。
- 使用 `--skip-collect --verify` 对补齐任务继续验证。

验证方式：

```powershell
python tests\unit\test_coverage_framework.py
python tests\unit\test_ops_console.py
```

人工验证：

```powershell
python scripts\ops_console.py --open
```

### Milestone 4：其他税种状态规则

状态：未开始

目标：

- 企业所得税 A 类状态规则。
- 文化事业建设费状态规则。
- 残保金状态规则。
- 小规模增值税是否与 `sz_zzs` 同源，需要结合表单/纳税人性质识别。

验证方式：

- 使用用户提供的代表 taskId 查询任务执行日志和后台结果 JSON。
- 增加单元测试固定字段路径或日志规则。

### Milestone 5：未申报真实税局验证

状态：未开始

目标：

- 每个支持税种补齐未申报页面导航与字段抽取策略。
- 不同省份异常时输出人工可处理原因。

验证方式：

```powershell
python main.py --task-id <未申报代表taskId> --log-level INFO
```

## 当前长期任务：运营人员友好化

目标：

- 运营人员尽量通过本地工作台完成批量验证、问题处理和覆盖检查。

### 已完成

- 本地工作台启动任务。
- 临时易代账账号密码输入。
- 税号进度展示。
- 重试、跳过、继续验证。
- 问题处理视图。
- 问题清单导出。
- 覆盖检查视图。
- 易代账创建账套入口，复用现有账套创建脚本并展示脱敏结果。

### 下一步

- 覆盖补齐按钮。
- 失败原因标准化字典。
- 新税种接入检查清单。
- 更明显的“需要人工处理”分类。

验证方式：

```powershell
python scripts\ops_console.py --open
python tests\unit\test_ops_console.py
```

## 当前长期任务：真实流程模块化

目标：

- 降低 `scripts/compare_tax_forms.py` 维护成本。

原则：

- 分阶段拆分。
- 每拆一块都保持行为等价。
- 不改变 `main.py` 用户入口。

候选阶段：

1. 任务执行日志和覆盖规则下沉：已开始。
2. CompareTarget 定义下沉。
3. Excel 映射加载下沉。
4. 税局导航策略下沉。
5. 网页抽取策略下沉。
6. 报告写入下沉。

验证方式：

```powershell
python -m compileall -q main.py scripts src
python main.py --task-id <taskId> --skip-browser --log-level INFO
```

## 风险

- 后台接口字段可能随版本变化。
- 税局页面变化会导致导航和解析失败。
- 不同省份相同税种页面不完全一致。
- 批量任务依赖登录态，代理或验证码会导致非代码失败。
- 历史中文编码问题可能影响关键词匹配。

## 2026-06-01 临时任务：青岛税号重新发起验证

状态：完成取数，验证被外部登录阻塞

目标：

- 使用 `91370203334145023C` 重新发起取数，避免复用旧 taskId。
- 验证山东/青岛进税局路径是否仍存在卡点。

结果：

- 已生成新 taskId：`2076005047487626573`。
- 已修复新批次默认复用旧 taskId 的问题，旧任务复用改为 `--reuse-collected-task` 显式选项。
- 已修复青岛税号 tpass 参数被旧省份值覆盖的问题。
- 当前仍停在青岛统一登录页，属于税局登录认证未完成，需要人工完成青岛税局登录后继续验证。

后续：

- 如果青岛税局可以人工登录成功，使用新 taskId 继续验证并观察申报表页面解析。
- 如果青岛长期不能自动进税局，需要增加“统一登录页/滑块/扫码”快速失败与运营处理提示，减少 120 秒等待。
## 2026-06-04：山东首页兜底误点回归验证

目标：
- 用修正后的首页兜底点击规则重跑 `2076981254899665895`。
- 重点确认不再进入“办税进度及结果信息查询”，若找不到安全申报入口则明确失败。
- 保留 `plugin_first` 8 秒快速回退，继续验证其减少 loading 等待的效果。

验证入口：
```powershell
python main.py --task-id 2076981254899665895 --log-level INFO
```

结果：
- 已完成。`2076981254899665895` 修复后重跑成功，没有再进入“办税进度及结果信息查询”。
- 输出报告：`output\reports\2076981254899665895\compare_summary_2076981254899665895_20260604_112423.html`。
