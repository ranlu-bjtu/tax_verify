# ARCHITECTURE.md

## 2026-06-11 addendum: account-set skill lazy Playwright dependency

The standalone account-set skill keeps Playwright as a lazy optional dependency. Token/password API paths can complete without importing `playwright.sync_api`; the import is centralized in `load_sync_playwright()` and is reached only by browser/CDP paths. Missing Playwright now fails with a specific install hint instead of a raw `ModuleNotFoundError`.

This keeps copied skill usage lighter on hosts that can supply Yidaizhang/public-manage tokens or successful password-auth API contexts, while preserving browser fallback for manual verification and CDP reuse.

## 2026-06-11 addendum: account-set Chrome CDP fallback ports

The account-set browser path now connects through `connect_chrome_over_cdp()` instead of calling `chromium.connect_over_cdp()` directly. The helper records the caller's requested CDP port/profile, launches Chrome when needed, and catches the Playwright 1.60 `--enable-automation` compatibility failure that occurs when a normal user Chrome owns the requested port.

On that specific incompatibility, it keeps the existing browser untouched and retries with fallback ports `9333`, `9444`, `9555`, and `9666`. Each fallback port uses a sibling user-data directory with the port appended to the original profile name, so the managed automation browser does not share the user's normal Chrome profile. This logic is duplicated inside the standalone account-set skill to preserve its independence from project modules.

## 2026-06-11 addendum: public-manage backend auth provider

`src/chanjet_admin/auth.py` now owns public-manage backend authentication tokens. `ChanjetAdminTaskQuery` and `ChanjetPrivacyPhoneBridge` accept either a browser `BrowserContext` or a token provider:

- `StaticAdminAuthProvider` wraps externally supplied `TAX_BACKEND_AUTHORIZATION` and `TAX_BACKEND_TOKEN`/`TAX_BACKEND_ACCESS_TOKEN`.
- `ChanjetAdminPasswordAuthClient` performs the normal Chanjet SSO password login attempt, then calls public-manage `authorizeByJsonp` and `/token`.
- If password auth returns risk-control/manual verification, callers in `auto` mode fall back to the existing browser flow.

`scripts/ydz_create_customers.py --backend-auth-mode auto|token|password|browser` controls this selection. When both Yidaizhang and backend providers are token/password backed, backend-source account-set creation can run without opening the public-manage page. The integration privacy-phone client reuses the provider and still strips the `token` header for `data-task-management-chanapp.inte.chanjet.com`.

The standalone account-set skill contains an independent copy of this provider logic.

## 2026-06-11 addendum: production YDZ workbench app-list recovery

The account-set creation browser path now has a dedicated production workbench recovery step. When `wait_for_ydz_page()` cannot find a usable `cloud.chanjet.com/ydzee/.../work.html` page, the login helper tries:

1. redirectVM/public Yidaizhang entry recovery,
2. Chanjet workbench app list recovery at `workbench.chanjet.com/v2/myapp/list?orgId=<YDZ env org id>`,
3. direct configured `work.html` navigation.

The workbench selector scores visible rows/cards containing `易代账` plus `进入应用`, filters adjacent apps such as e-ticket, inventory, one-click tax filing, personal tax, and WeCom entries, and clicks the row's `进入应用` control. This is used both by `scripts/ydz_create_customers.py` and by the standalone `skills/ydz-create-accountset/` CLI. `src/ydz/session.py` uses the same more tolerant app-entry selector so long production rows with purchase dates and user-list controls are not rejected.

## 2026-06-10 addendum: YDZ account-set tax-login source methods

Account-set backend-source lookup is constrained to public-manage successful task rows with `taskCategorys=2,3`, no `taskTypeId` or tax-type filter, and `loginType=YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX`. The resolver still performs a local second-pass filter so unsupported, missing, or incomplete `loginJson` rows cannot be selected.

`YSHDL/DLYW-YSHDL` use `cTaxPreparerName` as the privacy number and may trigger integration privacy-phone copy/pull before customer creation. `SDSRDX/DLYW-SDSRDX` use `cTaxPreparerName` as the phone/login account and intentionally skip privacy-phone sync. `DLYW-*` methods set `cSiteLoginName` to the proxy company tax number.

The workbench manual-accountset entry validates the same method set, and the standalone `skills/ydz-create-accountset/` CLI contains an independent copy of the same constants, payload mapping, and skip rules.

## 2026-06-10 addendum: YDZ account-set accountant defaults resolve from login phone

Account-set creation no longer treats the assigned accountant as only a fixed environment constant. Before create/update, the Yidaizhang API client calls the frontend employee endpoint `trans/easyacctg/employee/getChildEmpListByUserId`, whose rows use the real frontend fields `userId`, `name`, `mobile`, `roleTypeEnum`, and `granted`.

The resolver filters out `roleTypeEnum=EASYACCTG_ADMIN`, matches the configured Yidaizhang login account phone against row `mobile`, and uses the matched row `userId` as `accountantEmployeeId` in `trans/easyacctg/customer/create`. If phone matching fails, it falls back to the current Yidaizhang `userId`, then to the packaged environment default (`user7793` for integration, `user-yAfUZb` for production). Verification checks the resolved `accountantEmployeeId`, not only the static default.

The standalone `skills/ydz-create-accountset/` CLI carries the same self-contained resolver and does not import project modules.

## 2026-06-10 addendum: YDZ integration captcha login can use accountVerify

Yidaizhang integration password auth now supports the login page's captcha interface path before browser fallback. For `inte`, the password-auth client calls `loginV2/accountVerify` with the configured account, password, and captcha code to obtain `verifyToken`, then submits `loginV2/accountLogin` with that token and the CIA `auth_code`.

The integration captcha defaults to `666666`. It can be overridden with `YDZ_INTE_LOGIN_CAPTCHA`, `YDZ_INTE_CAPTCHA`, `YDZ_INTE_VERIFY_CODE`, or the generic `YDZ_LOGIN_CAPTCHA`, `YDZ_CAPTCHA`, `YDZ_VERIFY_CODE`. Production has no default captcha code.

This is a normal frontend API login flow, not a slider/CAPTCHA bypass. If password auth succeeds but does not expose a usable Yidaizhang API token context, auto mode still falls back to browser login. The standalone `skills/ydz-create-accountset/` CLI carries the same self-contained behavior.

## 2026-06-10 addendum: YDZ account-set default auth is password-first auto

Account-set creation now defaults to `--ydz-auth-mode auto`. Auto mode tries the guarded password-auth client first; if it cannot produce a usable Yidaizhang API token context, it logs the password-auth status and falls back to the browser login path. Explicit `--ydz-auth-mode password` remains strict and fails before mutation when password auth is blocked.

The workbench's blank/default Yidaizhang auth option now means "auto, password first"; explicit `browser` can still be selected for debugging or when an operator wants to skip the password attempt.

## 2026-06-10 addendum: standalone account-set skill supports manual source mode

`skills/ydz-create-accountset/scripts/ydz_accountset_cli.py create --manual-source-env` now reads customer and tax-login source fields from `YDZ_MANUAL_*` variables. In this mode the standalone skill bypasses public-manage task lookup and integration privacy-phone copy/pull, then uses the normal Yidaizhang API path to check/create the customer, save tax-login information, and verify the result.

Manual source mode still requires a usable Yidaizhang API session through browser mode, token mode, or guarded password-auth mode. It remains self-contained inside the skill and does not import project `src/` or `scripts/`.

## 2026-06-10 addendum: YDZ password auth is a guarded token-context attempt

`src/ydz/password_auth.py` implements a direct Chanjet account-password login attempt for account-set creation. It uses the normal login endpoints, RSA-encrypts username and password with the login page public key, obtains the CIA auth code, and submits `loginV2/accountLogin`.

The resulting mode is exposed as `scripts/ydz_create_customers.py --ydz-auth-mode password` and in the workbench auth-mode selector. It only proceeds when a usable Yidaizhang API auth context (`work.html`, `iframeToken`, `ciaToken`, `orgId`, `userId`) can be built. Slider/CAPTCHA, SMS, phone binding, password-change prompts, and SSO success without exposed YDZ business tokens are reported as explicit blockers before customer mutation.

The standalone `skills/ydz-create-accountset/` CLI carries an independent copy of the guarded password-auth client and still does not import project `src/` or `scripts/`.

## 2026-06-10 addendum: YDZ account-set API auth context can be page or token based

`src/ydz/customer_creation.py::YdzCustomerApi` now accepts either:

- a logged-in Yidaizhang `work.html` browser page, or
- a supplied token auth context built from `work.html`, `iframeToken`, `ciaToken`, `orgId`, and `userId`.

Both modes call the same Yidaizhang customer APIs and share the same create, tax-info save, and verification code. Auto mode is the default and tries password before browser. Token mode is exposed through `scripts/ydz_create_customers.py --ydz-auth-mode token`.

Manual-source account-set jobs can use token mode without Chrome because they do not query public-manage and skip privacy-phone sync. Backend-source jobs can use token mode only for Yidaizhang API calls; public-manage source lookup and integration privacy-phone preparation still use the existing backend browser session.

The portable `skills/ydz-create-accountset/` CLI contains its own copy of this token-context logic and still does not import project `src/` or `scripts/`.

## 2026-06-10 addendum: standard supplement uses historical backend candidates with bounded retry

For coverage supplement targets other than CIT A and consumption tax, the runner verifies public-manage historical backend candidates directly. This applies to:

- `VAT_GENERAL`
- `VAT_SMALL`
- `CULTURE_FEE`
- `CBJ_PERSONAL`
- `CBJ_ANNUAL`

The verifier path remains the canonical `main.py --task-id` flow. No second comparison path is introduced, and standard supplement no longer tries to create fresh Yidaizhang taskIds by default.

For these standard targets, the supplement candidate pool honors the configured limit directly. The workbench/default limit is 3 candidates per missing target. If one candidate fails before form verification because of tax-bureau login readiness, the attempt keeps the real failure category and the next historical candidate can be tried.

Within that limit, backend candidate selection prefers different tax numbers for the same missing target before it falls back to additional taskIds under an already selected tax number. The same rule is applied inside a single backend query and again when merging results across search windows. This makes the 3-attempt fallback more likely to switch privacy-phone/login sources instead of retrying the same enterprise session repeatedly.

For standard targets, candidate search now uses a bounded preflight pool before final grouping. The raw backend pool can be larger than the final configured verification limit, then a lightweight login preflight checks `getClientJob` metadata and one `getTaskCookie` response. Candidates that are definitively not login-ready are removed before full form verification; candidates whose preflight cannot run because the browser page is unavailable remain in the pool and fall back to the normal verifier path.

If preflight removes candidates and a missing target no longer has enough candidates to fill the configured final limit, the same supplement run performs bounded refill backend searches with the newly not-ready taskIds excluded, then preflights the refill candidates before grouping. The current bound is 3 refill waves. This lets a single workbench action move past expired early pools instead of requiring the operator to rerun the job.

Refill searches also temporarily exclude taskIds already seen in the current run, including ready or unknown preflight candidates, so the backend query does not spend the refill pool on duplicates. Only definitive `not_ready` taskIds are persisted as stable exclusions for later runs.

Preflight `not_ready` taskIds are persisted in `coverageSupplement.loginPreflight` and are merged into the stable exclusion map on later supplement runs. This prevents a known-expired historical task from reappearing repeatedly when the operator reruns the same coverage supplement.

If a later candidate covers the target, the supplement round returns success for that target even when earlier candidates failed. If all configured candidates fail, the target remains uncovered and the attempts list shows the direct reason for each taskId/tax number.

CIT A keeps its separate explicit source-readiness flow, and consumption tax is excluded from this robustness target for now.

## 2026-06-10 addendum: tax-bureau login readiness is bounded for new candidates

Backend supplement candidates are still verified through the canonical `main.py --task-id` path. Previous successful taskIds or reports are not used as stable replacements for a new candidate.

Tax-bureau login readiness now has explicit guardrails:

- `getClientJob` metadata polling is bounded.
- Failed, incomplete, non-object, unresolved inner-task/province, or exhausted `getClientJob` metadata responses are classified as tax-login readiness failures, not generic verification failures.
- `getTaskCookie` polling is bounded by default even when a larger verification timeout is configured.
- Direct tax-page fallback can fast-fail when the browser remains on `tpass.*#/login`, authorization-code error pages, or `/loading`.
- These blockers are classified as tax-login readiness failures, while real form comparison differences remain normal verification results.

This keeps the workbench and batch runner from stalling at login while preserving real evidence from each new task.

## 2026-06-10 addendum: YDZ no-need is a CIT A source-readiness blocker

For CIT A fresh YDZ refresh, a successful submit can still return `NO_NEED_COLLECTED` and no backend taskId. The coverage supplement pipeline now classifies that as `ydz_no_need_collect` in `coverageSupplement.sourceReadiness`.

This is not a comparison failure and not a parser signal. It means the selected account set cannot produce a verifiable CIT A task for the current period, so the operator should change the candidate tax number or period before retrying the normal fresh-collection and `main.py` verification path.

## 2026-06-10 addendum: CIT A account-set source precheck

The workbench now has a CIT A account-set source precheck action for existing batch runs. It reads the batch `coverageSupplement` state, extracts only the current representative `CIT_A:filed` and `CIT_A:unfiled` source candidates, and launches the existing `scripts/ydz_create_customers.py` workflow with `--dry-run`.

This is a source-readiness action, not a verification implementation and not a mutating account-set creation step. It helps operators confirm whether the selected CIT A candidate tax numbers can be created/refreshed before they explicitly run a real account-set creation job. Credentials are still passed only through the child environment.

## 2026-06-10 addendum: open YDZ work-tab scan for CIT A source discovery

When the CIT A enterprise-scan option is enabled, the supplement flow now first scans already-open, ready YDZ `work.html` tabs other than the current collector page. A tab must reach batch declaration and expose YDZ API tokens before it is used. If the tab has CIT A account-row signals, the flow reuses the existing fresh collection and backend taskId resolution path, then verifies through `main.py`.

This gives operators a no-copy path after manually opening a target enterprise in the shared browser, while keeping normal runs unchanged.

## 2026-06-10 addendum: workbench passes CIT A work URLs as transient environment

The local workbench now exposes an optional `ydzSupplementWorkUrls` field in the batch verification form. When supplied, the workbench enables CIT A fresh refresh and passes the value to the child process through `YDZ_SUPPLEMENT_WORK_URLS`; the raw URL is not added to the displayed command.

This keeps the workbench as the default operator entry while preserving the same batch runner and `main.py` verification path.

## 2026-06-10 addendum: explicit YDZ work.html source for CIT A supplement

CIT A supplement can now accept explicit Yidaizhang cloud `work.html` URLs through:

- `--coverage-supplement-ydz-work-url`
- `YDZ_SUPPLEMENT_WORK_URLS`

The URL is used only as a controlled source context. `YdzSession.open_work_url()` opens the provided cloud workbench, navigates to batch declaration, waits for YDZ API tokens, and the supplement flow scans account rows for CIT A signals. When a signal exists, the flow reuses the existing fresh YDZ collection, backend taskId resolution, and canonical `main.py` verification path. It does not create a second comparison implementation.

Diagnostics store redacted labels such as `cloud.chanjet.com/.../work.html` or `inte-cloud.chanjet.com/.../work.html`; full URLs are not written into source-readiness output.

## 2026-06-10 addendum: YDZ authenticated landing recovery and workbench enterprise discovery

CIT A fresh-refresh no longer treats an authenticated Yidaizhang landing or `redirectVM` page without login inputs as a password-login page. `YdzSession` now tries the known `work.html` URL and waits for `iframeToken` plus `ciaToken` before declaring the session unusable.

Other-enterprise source discovery has a separate workbench discovery path:

- `workbench.chanjet.com/v2/home` is used to open the `切换企业` dialog and read selectable enterprise names.
- This path is source discovery only; coverage still requires a fresh YDZ taskId and the normal `main.py` verification flow.
- A selectable enterprise is not enough. It must expose an active YDZ cloud `work.html` entry, otherwise the scan is classified as `other_enterprise_scan_unavailable`.
- Current-enterprise no-CIT-signal, other-enterprise app-entry unavailable, and historical task tax-login expiry remain source/readiness blockers, not field comparison failures.

## 2026-06-10 addendum: YDZ token failures are source-readiness blockers

CIT A fresh-refresh depends on a valid Yidaizhang workbench API token. When the batch account-list API returns `http=701` or `token 不能为空`, coverage supplement classifies the gap as `ydz_login_required`.

This is distinct from field comparison failure:

- `batch_problem_details.csv` remains reserved for completed comparison evidence such as mismatches and web-missing fields.
- `coverageSupplement.sourceReadiness` and `coverage_missing.csv` explain that the operator must refresh/provide Yidaizhang login state before a fresh taskId can be generated.
- The workbench can pass temporary Yidaizhang credentials to the child process and can opt in to CIT A Yidaizhang enterprise scanning without exposing credentials in the displayed command.

Yidaizhang enterprise-selector opening is also guarded against stale tabs: pre-existing `cloud.chanjet.com/ydzee` workbench pages do not prove that the selector opened or that an enterprise switch happened.

## 2026-06-10 addendum: CIT A source discovery can scan other YDZ enterprises

When CIT A coverage remains source-blocked, an explicit diagnostic option can read-only scan other selectable Yidaizhang enterprises:

- `--coverage-supplement-scan-ydz-enterprises` enables the scan.
- `--coverage-supplement-ydz-enterprise-scan-limit` bounds how many enterprises are checked.
- `--coverage-supplement-ydz-enterprise-names` lets an operator prioritize known enterprise names.

The scan switches Yidaizhang enterprise context, reads the batch declaration account list for the current period, and records `accountCount`, `citSignalCount`, and sample tax numbers. It does not create customers, does not submit collection, and does not count as coverage. If it finds a CIT A signal in another enterprise, `coverageSupplement.sourceReadiness` tells the operator which enterprise to use for the next fresh-collection retry. If the enterprise selector cannot be opened because browser login state or credentials are missing, the gap is classified as `other_enterprise_scan_login_required`.

## 2026-06-10 addendum: supplement source readiness is first-class output

Coverage supplement now writes `coverageSupplement.sourceReadiness` for each missing target after backend candidate search and optional Yidaizhang fresh-refresh checks. This output summarizes:

- how many backend candidates exist for the target,
- whether the current Yidaizhang enterprise can refresh those candidates into a new taskId,
- how many current-enterprise account rows were scanned,
- how many rows exposed a CIT A signal,
- the direct source blocker and the next operator action.

`batch_summary.html` and `coverage_missing.csv` prefer this source-readiness explanation when a coverage gap is source-blocked. Field mismatch reports remain separate in `batch_problem_details.csv`; an empty problem list plus a source-readiness blocker means the current issue is sample/source availability, not parser evidence.

## 2026-06-10 addendum: CIT A current-enterprise refresh is bounded and signal-gated

When `--coverage-supplement-refresh-cit-from-ydz` is enabled, CIT A supplement can scan the current Yidaizhang enterprise after backend candidate tax numbers fail the account-set gate. This scan is intentionally bounded:

- It scans only the current batch period for fresh Yidaizhang collection.
- It reads a limited number of current-enterprise account pages.
- It submits collection only for accounts whose batch-list row exposes a CIT signal, such as `taxTypeId=2` or an enterprise-income-tax label.
- It uses a short representative-task discovery timeout instead of the normal full collection wait.

Historical backend candidates are still verified as fallbacks through `main.py`; current-enterprise scan is only a way to create fresh taskIds when the current enterprise actually has CIT-ready account rows. If the scan returns accounts but `citSignalCount=0`, the workflow records `current_enterprise_scan_no_cit_account_signal` and avoids random submissions.

## 2026-06-10 addendum: CIT A supplement can prefer fresh YDZ collection

Coverage supplement candidate ordering now prefers exact declaration-status evidence before unknown-status probes. For example, a `CIT_A:filed` candidate parsed as `filed` is tried before a newer `unknown` probe; unknown remains a fallback when no exact candidate is available.

An explicit `--coverage-supplement-refresh-cit-from-ydz` flag lets a CIT A supplement run try a fresh Yidaizhang collection before verifying backend historical candidates. This path is intentionally off by default. When enabled, the runner checks whether the backend candidate tax number exists as an account set in the current Yidaizhang enterprise. If it exists, the runner submits a forced collection for the candidate period, resolves the new backend taskId, and inserts that fresh task ahead of the historical candidate. If the account set is absent or no taskId is resolved, the runner records `coverageSupplement.freshYdzRefresh` and falls back to the historical backend task.

This keeps backend supplement source discovery independent from the current Yidaizhang enterprise, while giving CIT A gaps a controlled way to escape expired historical tax-login state when the same enterprise can produce a fresh task.

## 2026-06-10 addendum: CIT A status evidence and retry diagnostics

Coverage supplement now treats current-period status as target-tax-code scoped when execution logs contain an `lsn` value. CIT A reads `sz_qysds`, VAT reads `sz_zzs`, culture fee reads `sz_whsyjsf`, and consumption tax reads `sz_xfs`. If no matching tax-code marker exists, the status is unknown unless another accepted fallback applies.

For `CIT_A:filed`, unknown-status backend tasks can be used as filed probes by passing a declaration-status override into `main.py`. This override only selects the filed navigation route; it does not count as coverage. Coverage still requires the tax-bureau declaration query page to expose a CIT A/A200000 row for the target period and the normal verifier to complete successfully.

Supplement diagnostics persist `statusTaskIds` by parsed status. This lets operators audit whether a missing target had no backend tasks, only known-unfiled tasks, unknown probes, or candidates excluded because they already failed.

## 2026-06-10 addendum: target-scoped supplement-only retries

Backend coverage supplement now has two independent scopes:

- Batch coverage scope: `coverageTaxTypes` plus `coverageCollectStatuses`, persisted in `state.json` and used by the authoritative coverage matrix.
- Retry scope: optional `--coverage-supplement-targets`, persisted as `coverageSupplement.requestedTargetKeys` and used only to decide which currently missing targets to search/apply in this run.

`--coverage-supplement-only` runs only the backend supplement phase for an existing run state. It skips collection and existing-item verification, then rebuilds the normal batch summary. This is the supported way to retry a narrow coverage gap such as `CIT_A:filed,CIT_A:unfiled` without rewriting the batch's intended coverage.

CIT A undeclared hot-service shortcuts are treated as source-state evidence, not form-entry evidence. A tax-bureau home page must expose a CIT A/A200000/current-declare entry inside the declare/todo scope before the verifier clicks or waits for form-fill controls. Hot-service-only pages now fail before the generic undeclared fill-button polling loop.

## 2026-06-10 addendum: supplement problem details ignore superseded candidates

Batch problem details are current-state oriented. For backend supplement items, a non-clean report for a coverage target is excluded from `batch_problem_details.csv` once another supplement candidate has cleanly covered the same target in the same batch state. This does not delete the historical report under `output/reports/`; it only keeps stale supplement attempts out of the operator's current field-problem list.

Non-supplement task differences are unaffected, and an uncovered supplement target can still surface completed-with-differences reports so parser defects remain visible.

## 2026-06-09 addendum: coverage requires successful verification records

Coverage status is success-gated. A target is covered only when the current batch state has a successful verification record for the task (`status=success`, `returnCode=0`). Partial reports from failed, skipped, timed-out, or externally blocked candidates are retained on disk for audit but do not count as coverage and do not feed `batch_problem_details.csv`.

Backend coverage supplement uses the coverage matrix plus the current candidate's task-specific verification record. A candidate is marked `covered` only when both are clean. This prevents stale reports from stopping multi-candidate supplement retries.

Supplement backend searches are not restricted by privacy-login task rows. They stay constrained by period, successful collect-task status, backend tax kind, taxpayer type where needed, selected coverage status, and optional `--coverage-supplement-lookback-days`.

## 2026-06-09 addendum: selected tax types keep all registered forms visible

For verification coverage, selecting a tax type means all registered forms for that tax type remain part of the verification output. A form is no longer removed only because the backend API returned zero comparable fields for that specific table. Instead, the verifier still navigates to the selected form and writes an evidence report with `not_comparable=true` and `not_comparable_reason=api_no_comparable_fields`.

Auto target selection follows the same rule at the tax-type group level: once VAT general, VAT small, culture fee, or consumption tax is detected, the group's registered forms are kept together. This preserves the operator requirement that every selected tax type verifies all of its forms, while still avoiding unrelated tax types.

Long-running page recovery is bounded. `scripts/compare_tax_forms.py` caps expensive web extraction recovery at a short per-form budget, and `scripts/batch_collect_verify.py` wraps each `main.py` verification subprocess with `--verify-timeout` (0 means use the bounded default derived from `--tax-timeout`). A timeout fails the current task/candidate with a clear reason instead of blocking the whole batch.

When undeclared navigation lands back on the tax bureau home page, the verifier reads the target row status before retrying entry clicks. A home row showing the target as already declared is classified as already-declared/status-conflict logic, not as a missing entry or field comparison failure.

Tax-login lock handling also fast-fails repeated blockers: if `getClientJob` returns the same occupying taskId three consecutive times, the current candidate is marked as a pending tax-login lock instead of waiting through the full pending window. Backend supplement task-list queries remain serial for now because they share browser-derived public-manage auth state; parallelization should first split that state into independent request clients.

## 2026-06-09 addendum: coverage supplement verifies only the active target forms

When backend coverage supplement applies a representative task, verification no longer passes `--targets auto` blindly to `main.py`. If the batch item comes from `backend_supplement` and the active coverage target is known, `scripts/batch_collect_verify.py` converts that target to its registered `form_ids` and passes only those forms to the canonical verifier.

This keeps ordinary batch verification unchanged, but prevents multi-tax tasks from verifying unrelated forms before the missing coverage target. For example, a `CULTURE_FEE:filed` supplement task should run `culture_fee_main,culture_fee_deduction`, not the VAT general forms that may also exist in the same backend result. CBJ supplement still uses the dedicated CBJ verifier.

## 2026-06-09 addendum: non-VAT backend supplement tax filters

Coverage supplement task-list queries use public-manage `taxId` as the authoritative server-side tax filter. Live checks confirmed these mappings for the currently supported targets:

- VAT: `taxId=1`, with `taxPayerType` splitting normal and small taxpayer tasks.
- CIT A: `taxId=2`.
- Culture fee: `taxId=3`.
- Consumption tax: `taxId=26`.
- CBJ: `taxId=39`.

The public-manage `taxTypeId` request field can return mixed rows and should not be used as the primary supplement search filter. Row-level `taxTypeIds` and `taskTaxRelVOList` remain useful as returned metadata for diagnostics and target inference.

## 2026-06-09 addendum: coverage supplement status filtering

Workbench coverage range selection has two dimensions: tax types (`coverageTaxTypes`) and backend supplement collect statuses (`coverageCollectStatuses`). The UI labels statuses as `已取数` and `未取数`, while the command-line values are `collected` and `not_collected`.

`scripts/batch_collect_verify.py` persists both filters in `state.json`. Coverage analysis and backend supplement target generation use both fields. Internally, `collected` maps to the existing `filed` coverage target and `not_collected` maps to `unfiled`; tax types declared with `coverage_statuses=(any,)` remain status-independent.

VAT backend supplement uses public-manage `taxId=1`, not `taxTypeId=1`. Normal and small taxpayer targets are split by `taxPayerType`. Collect-task supplement searches use backend `taskTypeId=3` inside `find_collect_tasks_by_filters()`, while broader account-set source lookups continue to call `query_tasks()` without that forced collect-task filter.

## 2026-06-09 addendum: manual-source account-set entry

The workbench exposes a separate `手工创建账套` entry for account-set creation when the operator supplies the source fields directly. This path still reuses `scripts/ydz_create_customers.py` and the same Yidaizhang API workflow, but swaps the source resolver from public-manage backend lookup to `ManualCustomerSourceResolver`.

Manual-source jobs run the customer script with `--manual-source-env --skip-privacy-phone-sync`. The workbench writes the tax number to the normal run input file, while customer name, region, login method, proxy tax number, privacy number, and password are supplied through transient `YDZ_MANUAL_*` environment variables. These values are not added to the command line, job metadata, logs, or JSON summaries.

This path only needs a valid Yidaizhang session. It does not open public-manage backend pages, does not query backend task records, and does not run online/integration privacy-number synchronization or preparation. The normal `创建账套` entry remains the backend-source path and continues to embed backend login, task lookup, and integration privacy-number preparation.

## 2026-06-09 addendum: account-set manual verification handoff

Account-set creation treats Yidaizhang slider verification as an operator handoff. The child script does not attempt to bypass the slider. Instead, when password login triggers it, the script logs `MANUAL_VERIFICATION_REQUIRED` and keeps waiting for a valid Yidaizhang workbench session. `scripts/ops_console.py` parses this marker from the running job log and displays `需人工验证 / 等待易代账滑块` immediately.

Once the operator completes the slider in the shared Chrome window, the same process continues by rechecking the workbench session, then proceeds to public-manage login, backend source lookup, privacy-phone preparation, customer creation, tax-info save, and verification.

The browser startup flag `--disable-blink-features=AutomationControlled` remains a mitigation only. Account-set logs distinguish between a newly launched Chrome CDP browser and reuse of an existing browser, because startup flags cannot be added to a browser process that is already running.

## 2026-06-09 addendum: account-set login and source lookup hardening

Account-set creation treats Yidaizhang `passport.../vm/redirectVM` as a normal post-login handoff page. The script first attempts the page entry action, then opens the configured `work.html` URL directly when the handoff does not navigate. This applies to the workbench-wrapped project script and the reusable standalone account-set skill.

Public-manage source lookup for account-set creation keeps broad lookback support but never sends a single task-list query longer than 39 days. The resolver scans the newest windows first and stops at the latest successful task row that contains usable login information. This keeps the backend request compatible with the public-manage 40-day limit while preserving older-source lookup.

Tax-number input files are read with UTF-8 BOM tolerance because the workbench and Windows tools may create BOM-prefixed text files.

## 2026-06-08 addendum: Chrome launch automation marker mitigation

Project-owned Chrome launch paths now include `--disable-blink-features=AutomationControlled`. This applies to Yidaizhang account-set creation, Yidaizhang session launch, privacy-phone sync launch, the shared browser manager, the Windows CDP startup helper, and the standalone account-set skill. The flag is a best-effort mitigation for automation detection only; slider verification remains a manual handoff when it appears.

## 2026-06-08 addendum: workbench-first project boundary

The project is now organized around the local operator workbench. `scripts/ops_console.py` is the preferred user-facing entry for operational work:

- Yidaizhang and public-manage login readiness.
- Batch collection and tax-form verification.
- Customer/account-set creation.
- Current task monitoring, logs, result summaries, problem review, and coverage checks.

Command-line scripts remain important, but their role is to provide deterministic execution units that the workbench can wrap and tests can exercise. New operational flows should be exposed in the workbench unless they are strictly developer-only diagnostics.

The reusable account-set skill is a separate portability boundary. `skills/ydz-create-accountset/` must remain self-contained so it can be copied into another agent host. It must not import this project's `src/` modules, call project-only scripts, or rely on `output/`, `runtime/`, `browser_profile/`, or local project memory files.

## 2026-06-08 addendum: operator console account-set entry

`scripts/ops_console.py` now includes a `创建账套` entry for Yidaizhang customer/account-set creation. The console does not reimplement the API workflow; it wraps `scripts/ydz_create_customers.py` as a separate `accountset` job type.

Public-manage backend login is embedded into account-set creation and privacy-number preparation instead of being a standalone operator workflow. Those flows reuse the same Chrome CDP profile, pass temporary backend credentials through child-process environment variables only, and automatically refresh the backend session before querying task/login data or privacy-number APIs. The legacy `backend-login` job type is kept only as an internal diagnostic/compatibility path and stores sanitized readiness status under:

```text
output/backend_login_runs/<runId>/
```

This lets operators refresh backend login state before account-set creation without entering tax numbers or creating customers.

The account-set entry explicitly selects the target environment:

- `inte`: integration Yidaizhang, default accountant `user7793`.
- `prod`: production Yidaizhang, default accountant `user-yAfUZb`.

When no browser login state exists, `scripts/ydz_create_customers.py` attempts automatic login before creating customers. It reads Yidaizhang credentials from `YDZ_INTE_*` or `YDZ_PROD_*` according to the selected environment, and public-manage credentials from `TAX_BACKEND_*`. The console may pass temporary credentials through the child process environment, but it does not store them in job records, command arguments, logs, or result JSON.

Account-set runs write their tax-number input, log, and sanitized JSON result under:

```text
output/accountset_runs/<runId>/
```

The current-task panel can display account-set logs and sanitized results, while batch-specific progress, coverage, and review actions remain limited to normal `batch` jobs. This keeps account-set creation separate from the tax-form verification pipeline and avoids creating a second verification flow.

When backend task login information is missing for one tax number, the account-set workflow returns a per-tax-number `FAILED` result and continues with the remaining tax numbers. Missing backend source fields are treated as manual-handling reasons, not as permission to create a partial account set.

## 2026-06-08 addendum: portable YDZ account-set skill

`skills/ydz-create-accountset/` packages the Yidaizhang customer/account-set creation workflow as a portable skill for other agents. It follows the same folder shape as the shared `chanjet-jira-wiki` skill: `SKILL.md`, `_meta.json`, `references/`, `scripts/`, and `tests/`.

The bundled CLI `skills/ydz-create-accountset/scripts/ydz_accountset_cli.py` is self-contained and does not import this repo's `src/` modules. It uses Chrome CDP browser sessions, public-manage backend task APIs, Yidaizhang workbench APIs, idempotent customer creation, dynamic tax-info saving, and two-layer verification. The package stores only non-secret defaults and secret variable names; it must not contain passwords, cookies, tokens, Authorization values, or raw backend `loginJson`.

## 2026-06-04 补充：网页读取质量闸门

真实 taskId 验证在进入目标税局表单后，先确认目标页面和保存证据所需的表单范围，再按最终参与比对的字段读取网页值。网页恢复分两层：
- 通用读取只在完全没有读到字段时做兜底滚动。
- 进入比对前用同一套比较规则预判真实 `web_missing` 字段，只对这些字段做等待渲染、滚动和补读。

低覆盖率本身不再等同于失败条件；如果没有可比对字段形成 `web_missing`，流程继续比对并保留日志。接口本来无值、不参与比对的字段不会驱动昂贵滚动恢复，也不会用接口值反填网页值。

## 2026-06-04 补充：税局登录策略

真实 taskId 验证的登录层默认采用 `plugin_first`：先通过 EtaxPlugin bridge 派发清税局 cookie、关闭旧税局页、打开新 tpass 页，再在插件不可用或未完成时回退 direct tpass URL。`/loading`、`tpass.*#/login` 和空正文税局页不再视为可复用登录页。

登录前置还会短等待 `window.robotId`，并在固定机器码取 cookie 失败时用真实机器码重试一次。`needForceTax=true` 属于人工确认是否强制进入税局的边界，默认只做失败归因，不自动调用 `forceEnterTax`。

## 总体架构

项目分为五层：

1. 工作台入口层：`scripts/ops_console.py` and the local browser session it controls.
2. 任务编排层：易代账取数、后台 taskId 查询、覆盖分析、串行验证。
3. 外部系统层：易代账、畅捷通后台、任务执行日志、电子税局、EtaxPlugin。
4. 比对能力层：API 读取、Excel 映射、网页/PDF 提取、归一化、比较。
5. 报告与运营层：单 taskId 报告、批量汇总、覆盖矩阵、问题处理清单。
6. 可移植 skill 层：`skills/ydz-create-accountset/` for reuse outside this repository.

## 入口层

### `scripts/ops_console.py`

本地运营工作台，默认地址 `http://127.0.0.1:8765/`。

职责：

- 打开并监控 Chrome CDP、易代账、报税后台和电子税局相关状态。
- 临时传递易代账和后台账号密码到子进程环境变量，不落盘。
- 生成并启动批量取数验证任务。
- 生成并启动创建客户/账套任务。
- 展示环境检查、当前任务、税号进度、问题处理、覆盖检查、最近批次。
- 提供继续验证、重试取数、跳过、导出问题清单等操作。

工作台只做编排和展示，不复制底层业务 API 逻辑。底层能力必须通过可测试的脚本或 `src/` 模块提供。

### `main.py`

推荐统一入口。

- 有 `--task-id` 且非 `--dry-run` 时，调用真实 taskId 验证流程。
- `--skip-browser` 用于只验证接口和映射。
- `--dry-run` 走离线框架管线。

### `scripts/compare_tax_forms.py`

当前真实 taskId 比对核心实现。

职责：

- 定义并解析 `CompareTarget`。
- 加载 Excel ID 映射。
- 拉取任务 API 数据。
- 查询任务执行日志，判断增值税当期/未申报状态。
- 连接 Chrome CDP 并触发进税局。
- 定位申报查询或未申报页面。
- 抽取网页字段、保存 PDF、生成 JSON/HTML/Excel 证据。
- 消费税已接入两张表，使用专用网页解析处理商品行、汇总行、附加税费行和减征比例列位。

后续应逐步下沉到 `src/`，但不能另起生产流程。

### `scripts/batch_collect_verify.py`

批量主流程。

数据流：

```text
税号列表
  -> 易代账账套查询
  -> 发起取数任务
  -> 后台查询一个或多个取数 taskId
  -> 按每个 taskId 串行调用 main.py 验证
  -> 汇总 batch_summary.html / CSV / coverage_status.json
```

当一个税号解析到多个 taskId 时，批量状态会保留：

- `collect.verifyTaskId`：第一个 taskId，用于兼容旧逻辑。
- `collect.verifyTaskIds`：该税号本次解析到的全部 taskId。
- `collect.resolvedTasks`：每个 taskId 的后台任务元数据。
- `verifyTasks`：按 taskId 记录的验证结果。

额外 taskId 会生成同税号的内部子项，继续复用 `main.py --task-id` 主流程，不新增第二套验证逻辑。

## 核心模块

### `src/ydz`

易代账相关能力：

- 登录/会话管理。
- 账套查询。
- 批量取数任务提交。
- 取数状态轮询。
- 从后台解析可验证 taskId。

### `src/chanjet_admin`

畅捷通后台能力：

- `task_query.py`：调用 `getTaskListInternal` 查询任务列表，支持按时间、税号、所属期、税种、任务状态、是否 mock 查询。
- `task_execution_log.py`：调用 `tTaskExecutionLog/getPageListByTaskId` 查询任务执行日志。

增值税申报状态规则：

```text
logType = 成功保存数据-是否是当期
logInfo = true  -> 已申报
logInfo = false -> 未申报
```

### `src/coverage`

覆盖分析与补齐框架：

- `registry.py`：项目当前支持税种和目标状态注册表。
- `analyzer.py`：读取已有批次和单 taskId 报告，生成覆盖矩阵。
- `supplement.py`：根据缺口到后台找成功取数任务，选择代表 taskId，并可写入批量 state 供现有验证流程复用。

输出：

```text
output/batch_runs/<runId>/coverage_status.json
output/batch_runs/<runId>/coverage_matrix.csv
```

### `src/api`

根据 taskId 拉取任务结果，解析 `resultJson`，按税种代码组织数据。

当前接口读取优先使用 Python `requests`；当本机网络对 Python TLS 出现 `SSLEOFError / UNEXPECTED_EOF_WHILE_READING` 但 `curl` 可正常访问时，会自动用 `curl` 兜底读取，不改变返回结构。

### `src/compare`

- `value_normalizer.py`：金额、税率、日期、整数、文本、空值归一化。
- `comparator.py`：字段级比较、容差判断、状态统计。

### `src/login`

- Chrome/Playwright CDP 管理。
- `getClientJob` / `getTaskCookie` 税局任务登录。
- 无插件 tpass cookie 初始化脚本，复刻 EtaxPlugin 的 cookie/localStorage 注入。
- 税局登录状态识别。
- EtaxPlugin 打开标签页 fallback。
- 失效页、锁、验证码等外部阻塞分类。

### `src/cbj`

残保金验证：

- 个税残保金：后台字段 `snzzzgrs_cbj` 和 `snzzzggzze_cbj` 存在即可判断取数成功。
- 汇算清缴残保金：进入税局年度企业所得税申报查询，读取 A105050 与 A000000 指定字段后与后台字段对比。

## 报告与产物

单 taskId：

```text
output/reports/<taskId>/
```

批量：

```text
output/batch_runs/<runId>/
```

常见文件：

- `compare_summary_*.html`
- `*_compare_*.json`
- `*_api_filled.xlsx`
- `*.pdf`
- `batch_summary.html`
- `batch_summary.csv`
- `batch_problem_details.csv`
- `coverage_status.json`
- `coverage_matrix.csv`
- `ops_status.json`
- `ops_review.json`

## 关键数据流

### 完整批量链路

```text
运营台/命令行
  -> batch_collect_verify.py
  -> YdzSession / YdzCollector 发起取数
  -> ChanjetAdminTaskQuery 查询后台 taskId
  -> main.py --task-id
  -> compare_tax_forms.run_compare()
  -> APIClient 获取接口数据
  -> TaskLoginFlow 进入税局
  -> 页面/PDF/Excel 证据提取
  -> Comparator 比对
  -> 单任务报告
  -> 批量汇总和覆盖矩阵
```

### 后台补齐覆盖链路

```text
coverage_status.json 找缺口
  -> getTaskListInternal 查询当月成功取数任务
  -> 任务结果 JSON 或任务执行日志判断已申报/未申报
  -> 选一个代表 taskId
  -> 写入批量 state
  -> 复用 --skip-collect --verify 验证
```

## 设计边界

- 真实验证不应绕过 `main.py` 和 `run_compare()`。
- 运营台只包装现有脚本，不实现第二套业务逻辑。
- 覆盖补齐只选择代表任务，不为每个缺口批量扫全量企业。
- 未申报页面策略必须逐税种实现，不能假设与已申报查询页面一致。
# 2026-06-08 addendum: YDZ customer creation automation

`scripts/ydz_create_customers.py` is the reusable entry for creating or updating Yidaizhang customers from public-manage backend login information. It connects to a Chrome CDP browser session, reuses logged-in Yidaizhang/public-manage pages when available, attempts environment-specific automatic login when sessions are missing, resolves backend `loginJson`, prepares integration privacy-number data when `--env inte`, creates missing customers, saves dynamic tax login info, and verifies both customer defaults and tax info. Core payload and verification logic lives in `src/ydz/customer_creation.py`; privacy-number backend synchronization lives in `src/chanjet_admin/privacy_phone.py`; usage is documented in `docs/ydz_customer_creation.md`.

Integration privacy-number preparation has a specific header rule: the integration summary/pull endpoints under `data-task-management-chanapp.inte.chanjet.com` are called with `authorization` but without the `token` header. The online copy endpoints under `data-task-management.chanapp.chanjet.com` keep the normal public-manage headers.
