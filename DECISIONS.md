# DECISIONS.md

## 2026-06-11: Account-set skill keeps Playwright optional

Status: Accepted

Context: The reusable account-set skill should be easy to copy to other agent hosts. Hosts that use Yidaizhang/public-manage token variables or successful password-auth API contexts should not have to install Playwright just to run API-only customer creation.

Decision:
- Do not bundle Playwright, browser binaries, `node_modules`, or virtual environments into the skill.
- Do not make Playwright a default prerequisite for API-only paths.
- Import Playwright only inside browser/CDP paths.
- When a browser path needs Playwright and it is missing, print a targeted install hint for `python -m pip install playwright`.
- Do not recommend `playwright install chromium` by default because the CLI normally launches or connects to local Chrome through CDP.

Consequences:
- Token/password API paths stay lightweight for copied skills.
- Browser login fallback remains available when needed.
- Hosts without Playwright get a clear dependency prompt only at the point where browser automation is actually required.

## 2026-06-11: Account-set browser fallback must not take over port 9222

Status: Accepted

Context: Users may already have a normal Chrome listening on `9222`. Playwright 1.60 can reject that browser with a message that the current Chrome lacks `--enable-automation`. Restarting or controlling the user's normal Chrome would disrupt their session.

Decision:
- Keep `9222` as the preferred port when it is compatible.
- Add `--enable-automation` to managed Chrome launches while preserving `--disable-blink-features=AutomationControlled`.
- If the requested port is incompatible, do not close or relaunch that browser.
- Retry with managed fallback ports `9333`, `9444`, `9555`, and `9666`.
- Use a port-suffixed user-data directory for fallback ports.
- Copy the same self-contained logic into the standalone account-set skill and the installed `ydz-create-customer` skill.

Consequences:
- The account-set flow can recover when `9222` is occupied by an ordinary Chrome.
- Existing user browsing state is left alone.
- If every fallback port is occupied by incompatible browsers, the run still fails with a clear CDP connection error.

## 2026-06-11: Public-manage backend auth is provider based with browser fallback

Status: Accepted

Context: Backend-source account-set creation previously needed a public-manage browser page because task query and privacy-phone sync read `Authorization` and `access_token` from browser storage. The public-manage frontend shows the real token flow: SSO `authorizeByJsonp` with client id `f5b78222-5ade-465b-b080-cc31abc0f2b8`, then `GET /token?code=...`. A live password attempt for the current backend account returned `访问拒绝`, so account-password direct login cannot be treated as guaranteed.

Decision:
- Add a backend token provider abstraction.
- Prefer explicit backend token variables when supplied.
- In `auto`, try guarded public-manage password API login, then fall back to browser login when SSO risk controls block the password attempt.
- Keep explicit `--backend-auth-mode password` strict: if no tokens are produced, stop before customer mutation.
- Preserve the old browser path for manual verification and stale-token recovery.
- Reuse the same provider for task query and privacy-phone sync; keep integration privacy endpoints without the `token` header.
- Copy the implementation into the standalone account-set skill instead of importing project code.

Consequences:
- Other agents can run backend-source account-set creation with no public-manage page when they have valid backend token variables.
- Password-only backend login remains best effort and may require browser fallback.
- Tokens are treated as secrets and must come from environment variables, host secret stores, or a transient caller process, never committed files.

## 2026-06-11: Production YDZ browser fallback recovers through Chanjet workbench

Status: Accepted

Context: Production account-password direct auth can return access denial/manual verification and therefore cannot always produce a usable Yidaizhang token context. A live production account-set creation showed that the browser could be authenticated at `ydz.chanjet.com` or Chanjet workbench while no active `cloud.chanjet.com/.../work.html` page existed. Manual navigation through `workbench.chanjet.com`, selecting org `90011827608`, and clicking the `易代账` app's `进入应用` control produced the valid workbench page.

Decision:
- Keep password auth as a guarded best-effort path and do not treat production access-denied/manual-verification responses as bypassable.
- Add a browser fallback step that opens `workbench.chanjet.com/v2/myapp/list?orgId=<YDZ environment org id>`.
- Select the primary `易代账` app row/card by visible text and click its `进入应用` control.
- Filter adjacent apps such as e-ticket, inventory, one-click tax filing, personal tax, and WeCom so the click targets the main Yidaizhang application.
- Use this recovery in the project account-set script and the standalone account-set skill; keep the skill implementation self-contained.

Consequences:
- A valid production browser SSO session can be converted into the cloud `work.html` API context without asking the operator to manually copy the work URL.
- The flow still cannot bypass slider, SMS, phone binding, access denial, or other visible verification challenges.
- If the configured org id changes or the user lacks the main Yidaizhang app in that org, the run fails as a login/app-entry readiness issue before customer mutation.

## 2026-06-10: YDZ account-set supports manual captcha-code tax login

Status: Accepted

Context: The user confirmed from the Yidaizhang customer page that login method `SDSRDX` is "tax bureau manual captcha-code login" and `DLYW-SDSRDX` is the proxy variant. The live page configuration shows these methods use the same dynamic tax-info save endpoint as privacy-number login. For `DLYW-SDSRDX`, selecting the method exposes the proxy company tax-number field.

Decision:
- Treat `YSHDL`, `DLYW-YSHDL`, `SDSRDX`, and `DLYW-SDSRDX` as the backend-source account-set login method set.
- Query public-manage task rows with `taskCategorys=2,3`, no tax-type restriction, and `loginType=YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX`.
- Keep a local supported-login and required-field filter before choosing the latest backend row.
- Map `SDSRDX/DLYW-SDSRDX` `cTaxPreparerName` to the phone/login account, not a privacy number.
- Keep `cTaxPreparerPwd` as the personal user password.
- Use `cSiteLoginName` for all `DLYW-*` proxy company tax numbers.
- Run integration privacy-phone summary/copy/pull only for `YSHDL/DLYW-YSHDL`.
- Keep manual-source mode using `YDZ_MANUAL_PRIVACY_NO` as the storage variable name for both privacy number and phone/login account to avoid another external config key.

Consequences:
- Backend-created account sets can now save the two manual captcha-code login methods without Playwright field clicking.
- Manual captcha-code methods no longer fail because the integration privacy-phone bridge cannot find a privacy-number record.
- The variable name `YDZ_MANUAL_PRIVACY_NO` is historically named; docs now clarify that it means privacy number or phone/login account depending on method.

## 2026-06-10: YDZ account-set assigned accountant resolves from login account

Status: Accepted

Context: The user asked whether account-set creation can default the assigned accountant to the accountant corresponding to the logged-in Yidaizhang phone number, rather than always using the hard-coded integration/production default. The downloaded Yidaizhang frontend bundle exposes `getChildEmpListByUserId` at `trans/easyacctg/employee/getChildEmpListByUserId`, and the employee/auth UI uses rows with `userId`, `name`, `mobile`, `roleTypeEnum`, and `granted`.

Decision:
- Before customer create/update, query `trans/easyacctg/employee/getChildEmpListByUserId`.
- Ignore `EASYACCTG_ADMIN` rows for assignment.
- Match the configured Yidaizhang login account phone to row `mobile`; use the matched `userId` as `accountantEmployeeId`.
- If no phone match exists, try the current Yidaizhang `userId`; if still unresolved, use the environment default accountant.
- Record the resolved accountant id/source in CLI output and verify the saved customer against that id.
- Keep the same behavior in the standalone skill without importing project code.

Consequences:
- Different login phones can create account sets assigned to their corresponding accountant when Yidaizhang exposes that employee row.
- Existing integration and production defaults remain as safe fallbacks.
- A live authenticated employee-list call is still required during real creation; if it fails, the run continues with the documented fallback and reports `accountantSource=env_default`.

## 2026-06-10: YDZ integration captcha login uses accountVerify before browser fallback

Status: Accepted

Context: The integration Yidaizhang login page exposes a captcha verification step in its normal frontend API flow. The user asked whether captcha login can call an interface instead of operating the browser, and requested integration captcha login with default code `666666` in the project and standalone skill.

Decision:
- For account-set creation password auth, call `loginV2/accountVerify` with encrypted username, encrypted password, and captcha code when no external `verifyToken` is supplied.
- Use the returned `verifyToken` in `loginV2/accountLogin`.
- Default the integration captcha code to `666666`.
- Allow environment overrides through `YDZ_INTE_LOGIN_CAPTCHA`, `YDZ_INTE_CAPTCHA`, `YDZ_INTE_VERIFY_CODE`, and generic fallback names.
- Do not default a production captcha code.
- Keep browser fallback in `auto` mode when password auth cannot build a usable Yidaizhang API token context.
- Sync the same behavior into the standalone account-set skill without importing project modules.

Consequences:
- Normal integration account-set creation can pass the simple captcha step through the same interface used by the frontend.
- This does not bypass slider, SMS, phone binding, password-change, or other manual verification challenges.
- Explicit `--ydz-auth-mode password` remains strict and still stops before mutation if token context is unavailable.

## 2026-06-10: Workbench small-period defaults exclude CIT A source controls

Status: Accepted

Context: The current operation period is a small tax period. Enterprise Income Tax A-class is only expected during large tax periods, so showing CIT A work.html source fields, enterprise scanning, and account-set precheck controls in the default workbench confused the normal small-period flow.

Decision:
- Keep the underlying CIT A supplement and account-set helper functions available for future large-period or historical-run use.
- Remove CIT A from the workbench's current default coverage tax-type set.
- Keep CIT A visible as an optional coverage checkbox, unchecked by default, so an operator can explicitly include it during a large tax period.
- Remove CIT A work.html source input, other-enterprise scan checkbox, and CIT A account-set precheck button from the workbench page.
- Keep report evidence tied to completed verification output: the tax-number/form matrix only renders items with form results, while login/collection/manual blockers remain visible in progress and coverage sections.
- Include completed reports with field differences in the tax-number/form matrix and problem details, even when another backend supplement sample already covers the same target cleanly.
- Treat unfiled as a normal declaration state in result styling; CBJ remains status-independent and should not be displayed as unfiled.

Consequences:
- Current small-period workbench runs focus on VAT, culture fee, consumption tax, and CBJ unless a caller explicitly supplies a different coverage scope.
- Future large-period support can use the existing CIT A checkbox without changing the underlying verification path; source-discovery controls can be reintroduced separately if needed.

## 2026-06-10: YDZ account-set auto auth tries password before browser

Status: Accepted

Context: The user asked to raise password mode priority ahead of browser default. Password auth is useful when it can produce a Yidaizhang API token context, but it remains a guarded best-effort path because slider/CAPTCHA, phone binding, password change, and SSO-without-business-token states can occur.

Decision:
- Make `YDZ_AUTH_MODE` default to `auto` for account-set creation.
- In `auto`, try password auth first and fall back to browser login when no usable token context is produced.
- Keep explicit `--ydz-auth-mode password` strict: if password auth cannot produce token context, stop before mutation.
- Keep explicit `--ydz-auth-mode browser` available for debugging or operator-forced browser login.
- Update the workbench default auth option to mean "auto, password first".

Consequences:
- Normal workbench/account-set runs prefer the interface-based password attempt.
- Password-auth blockers no longer stop default runs; they become a logged reason before browser fallback.
- Browser fallback remains necessary for visible verification challenges and browser-initialized business tokens.

## 2026-06-10: Standalone YDZ account-set skill supports manual source input

Status: Accepted

Context: The main project script already supports creating an account set from operator-provided customer and tax-login fields via `YDZ_MANUAL_*`, bypassing public-manage. The standalone skill did not yet include that capability, so copied skill users still needed backend task-list access even when the user already had the login information.

Decision:
- Add `create --manual-source-env` to the standalone `skills/ydz-create-accountset/` CLI.
- Read `YDZ_MANUAL_TAX_NO`, `YDZ_MANUAL_CUSTOMER_NAME`, `YDZ_MANUAL_AREA_CODE`, `YDZ_MANUAL_AREA_NAME`, `YDZ_MANUAL_LOGIN_METHOD`, `YDZ_MANUAL_PROXY_TAX_NO`, `YDZ_MANUAL_PRIVACY_NO`, and `YDZ_MANUAL_PASSWORD`.
- In manual mode, skip public-manage task lookup and skip integration privacy-phone sync.
- Keep Yidaizhang customer creation, tax-info save, and verification on the same API path as backend-source mode.
- Keep the skill self-contained; do not import project modules.

Consequences:
- Other agents can use the skill when the user supplies login information directly.
- Manual mode still needs valid Yidaizhang auth through browser, token, or guarded password-auth mode.
- The user is responsible for supplying complete and correct manual login fields; missing required fields fail before mutation.

## 2026-06-10: YDZ password auth is allowed only as a guarded best-effort path

Status: Accepted

Context: The user asked to implement account-password direct login to obtain Yidaizhang tokens and reduce dependence on Playwright for Yidaizhang login. The login pages expose account-password endpoints and RSA client-side encryption, but the flow can still require Aliyun slider, SMS, phone binding, password change, or a browser-initialized Yidaizhang business token.

Decision:
- Add `--ydz-auth-mode password` to the project account-set script, workbench command builder, and standalone skill CLI.
- Submit only the normal Chanjet login endpoints; do not bypass or crack slider/CAPTCHA or other manual verification.
- Continue customer/account-set creation only when password mode produces the same validated token context required by token mode.
- If password mode reaches SSO but cannot extract `iframeToken` / `ciaToken` from `work.html`, fail with `SSO_READY_TOKEN_UNAVAILABLE` and no mutation.
- Do not log or persist plaintext passwords, cookies, tokens, Authorization values, or raw login responses.

Consequences:
- Operators can try a browser-light Yidaizhang login path when the login service returns enough token context.
- Browser mode remains the default and most reliable route when the frontend must initialize business tokens or complete a visible challenge.
- Backend-source creation still needs public-manage login through the existing browser-session path.

## 2026-06-10: YDZ account-set creation supports token-context API mode

Status: Accepted

Context: Yidaizhang customer/account-set creation already uses backend HTTP APIs after the browser page exposes `iframeToken`, `ciaToken`, org id, user id, and the cloud `work.html` base path. The fragile part is browser login and token extraction, especially when a slider or other manual verification appears. The user asked whether the flow can avoid Playwright by logging in through interfaces and then continuing with API calls.

Decision:
- Add a token-auth context for Yidaizhang customer APIs: `work.html` URL, `iframeToken`, `ciaToken`, org id, and user id.
- Keep browser mode as the fallback path because it is still the most reliable way in this project to handle visible verification and browser-initialized Yidaizhang tokens.
- Add `--ydz-auth-mode token` for callers that already have valid tokens from a host secret store, prior browser session, or another trusted token capture process.
- Do not store tokens, cookies, Authorization headers, or passwords in the repository, skill files, command line, job metadata, or result JSON.
- Keep public-manage backend source lookup on its existing browser-session path for now. Token mode only removes the Yidaizhang workbench-page token read.
- Keep the standalone `skills/ydz-create-accountset/` package self-contained by copying the token-context logic into its bundled CLI rather than importing project modules.

Consequences:
- Manual-source account-set creation can run without opening Chrome when the caller supplies source fields and valid Yidaizhang token variables.
- Backend-source creation can avoid Yidaizhang page readiness but still needs public-manage login until a separate backend-token adapter is implemented.
- This is not a CAPTCHA/slider bypass and does not prove a password-to-token login API is stable or acceptable. If Yidaizhang invalidates the supplied token or the org id does not match, the run fails before mutation.

## 2026-06-10: Standard supplement targets use historical backend candidates with bounded retry

Status: Accepted

Context: The robustness objective is to prevent future backend supplement candidates, except CIT A and consumption tax, from getting stuck at tax-bureau login failures. A default fresh-Yidaizhang task strategy was considered, but it requires the tax number to already have an account set in the current YDZ enterprise. That can block validation before the backend historical evidence is even tried. The user explicitly requested removing the fresh-task feature and using historical tasks directly, trying alternative privacy-phone/tax-number candidates up to 3 times before failing.

Decision:
- For VAT general, VAT small, culture fee, CBJ personal, and CBJ annual supplement targets, verify historical backend task candidates directly.
- Keep CIT A on its existing explicit source-readiness path and leave consumption tax out of this default route.
- Keep `main.py --task-id` as the only verification path.
- Honor the configured supplement candidate limit directly; the default remains 3 candidates per missing target.
- Within that limit, prefer candidates from distinct tax numbers before selecting extra taskIds from the same tax number, both inside a backend query and while merging candidates from multiple search windows.
- For standard targets, search a bounded raw candidate pool before the final limit and run login preflight on that pool. Drop candidates that are definitively not ready at `getClientJob` or `getTaskCookie`, then apply the configured final candidate limit to the remaining candidates.
- If preflight drops a standard target below the configured final candidate limit, perform bounded same-run refill searches with the newly not-ready taskIds excluded, then preflight and merge the refill candidates before final grouping. The current bound is 3 refill waves.
- Refill searches temporarily exclude all taskIds already seen in the current run, including ready and unknown preflight candidates, while only definitive `not_ready` taskIds are persisted as stable future exclusions.
- Persist preflight `not_ready` taskIds as stable exclusions for future supplement runs.
- If one candidate fails with tax-login readiness or another verification blocker, record the direct failure category and move to the next backend candidate/tax number.
- If a later candidate covers the target, the supplement phase final exit code follows the final coverage state and returns success for the target.
- If all configured historical candidates fail, fail the target with the collected attempt reasons. Do not convert the failure into a retryable fresh-task state.
- Remove the workbench and CLI wiring for standard fresh-task retry waves.

Consequences:
- Standard supplement no longer depends on an existing YDZ account set before validation.
- Operators can see which historical taskId/tax number failed and why, then the run advances to the next candidate up to the configured limit.
- When backend history contains multiple taskIds for one enterprise plus candidates from other enterprises, the first attempts now diversify by tax number so a single stale privacy-phone/login source does not consume the whole retry budget.
- Definitive login-readiness failures can be filtered before full form verification, so they do not consume the normal 3 verification attempts when later ready candidates are available in the raw backend pool.
- A single supplement run can now move past expired early raw pools if later backend history has usable candidates, without requiring the operator to click retry after a preflight-only filter.
- Refill pools are less likely to be consumed by duplicate ready/unknown taskIds from earlier in the same run.
- Repeated runs can move past taskIds already proven not login-ready during preflight instead of rechecking the same stale history.
- This is aligned with the requested fallback model, but it does not prove all future external tax-login blockers are eliminated. Live supported-target evidence is still required before the broader goal can be called complete.

## 2026-06-10: New backend candidates must not be replaced by previous successful reports

Status: Accepted

Context: Backend supplement can find newly selected taskIds whose tax-bureau login state is unstable. Reusing taskIds or reports that previously succeeded would make coverage look stable, but it would not prove the newly selected task can still enter the tax bureau and verify current fields.

Decision:
- Do not prioritize or reuse this project's previous successful taskIds/reports as stable candidates for new backend supplement work.
- Each selected candidate must still run the normal `main.py --task-id` verification path.
- Completed field comparison with differences remains valid output and must be shown to the operator.
- Tax-bureau login readiness failures must be bounded, classified, and allowed to advance to the next candidate instead of hanging the batch.
- `getClientJob` responses that fail, are incomplete, are non-object, cannot resolve the inner taskId/province, or are still unusable after bounded retries are treated as tax-login readiness failures because they do not provide usable enter-tax-bureau metadata for the selected task.

Consequences:
- Coverage evidence remains tied to the task currently being verified.
- External login blockers are visible as login/auth readiness issues, not hidden behind historical success.
- Batch runtime is protected by fast-fail limits around tax-login readiness.
- Stable `getClientJob` metadata failures can be excluded from future supplement reuse like other tax-login blocker categories.

## 2026-06-10: YDZ no-need collect is a source blocker, not a verifier failure

Status: Accepted

Context: During CIT A coverage work, newly created or refreshed YDZ account sets can accept a collect request but return `NO_NEED_COLLECTED`. In that case no backend taskId is produced, so the normal `main.py --task-id` verification path has no evidence to run against. Previously this could collapse into a generic "no fresh source" message.

Decision:
- Classify fresh YDZ records with `collectStatus=NO_NEED_COLLECTED` as `ydz_no_need_collect`.
- Surface the status through `coverageSupplement.sourceReadiness`, coverage gap text, and next-action guidance.
- Do not treat it as parser failure, comparison failure, login failure, or successful coverage.
- The next action is to change the candidate tax number or period and try to produce a fresh taskId through the existing YDZ collect plus backend resolution path.

Consequences:
- Operators can distinguish no-need account sets from expired historical taskIds and missing YDZ login state.
- The full verification path remains unchanged and still requires a real taskId plus successful comparison evidence.
- The current full-coverage goal remains open until usable CIT A filed and unfiled source samples are found.

## 2026-06-10: CIT A account-set preparation starts with a dry-run precheck

Status: Accepted

Context: The remaining full-coverage blockers are `CIT_A:filed` and `CIT_A:unfiled`. Current evidence shows no parser or field-comparison failure; the blocker is that historical backend taskIds have expired tax-login state and the current YDZ enterprise has no CIT A account-row signal. Creating account sets can change external customer data, so the workbench needs a safe preparation step before mutation.

Decision:
- Add a workbench CIT A account-set source precheck for existing batch runs.
- Extract only the current representative missing-target candidates from `coverageSupplement`, not every historical failed CIT A task.
- Reuse `scripts/ydz_create_customers.py` and force `--dry-run` for the precheck.
- Do not create customers, do not save tax login info, and do not submit YDZ collection in this precheck action.
- Continue to require an explicit real account-set creation/import step before the batch can generate fresh CIT A taskIds.

Consequences:
- Operators can confirm whether the selected CIT A candidate tax numbers are suitable for account-set preparation without changing external data.
- The verification path remains unchanged: after an account set exists, fresh collection and `main.py --task-id` still provide the evidence.
- The current batch remains uncovered at `8/10` until precheck plus explicit preparation produces a fresh verifiable CIT A task.

## 2026-06-10: Open YDZ work tabs are optional CIT A source candidates

Status: Accepted

Context: Operators may manually open a valid YDZ cloud `work.html` page for another enterprise while troubleshooting CIT A source readiness. Copying the URL into the workbench is useful but should not be the only way to reuse that already-open source context.

Decision:
- When `--coverage-supplement-scan-ydz-enterprises` is enabled, scan already-open ready YDZ `work.html` tabs before attempting workbench enterprise switching.
- Exclude the current batch collector page from the open-tab scan to avoid just repeating the current-enterprise no-CIT result.
- Require batch-declare readiness and YDZ API tokens before using an open tab as a source context.
- If a CIT A account-row signal is found, reuse the existing fresh YDZ collection and standard backend taskId resolution path; verification still goes through `main.py`.

Consequences:
- Manual operator navigation can now become an automatic source candidate without copying full work URLs into commands or files.
- Open-tab scan remains opt-in through the existing enterprise-scan flag and does not affect normal batch runs.
- A ready open tab without CIT A signal remains source-readiness evidence, not parser evidence.

## 2026-06-10: Explicit YDZ work.html URLs are controlled CIT A source inputs

Status: Accepted

Context: The current YDZ enterprise can be authenticated and scanned, but it has no CIT A account-row signal. Workbench enterprise discovery can list other enterprises, yet some selected enterprises do not expose a usable YDZ cloud app entry automatically. Operators may still have a valid cloud `work.html` URL for the target enterprise.

Decision:
- Add `--coverage-supplement-ydz-work-url` and `YDZ_SUPPLEMENT_WORK_URLS` as explicit source inputs for CIT A supplement refresh.
- Accept both production `cloud.chanjet.com/ydzee/.../work.html` and integration `inte-cloud.chanjet.com/ydzee/.../work.html` URLs.
- Open these URLs through `YdzSession.open_work_url()`, require batch-declare readiness and API tokens, then scan CIT A account rows.
- If a CIT A row is found, reuse the existing fresh YDZ collection and normal backend taskId resolution path; verification still goes through `main.py`.
- Store only redacted source labels such as `host/.../work.html` in diagnostics, not full URLs.

Consequences:
- A valid work URL can bypass the current app-entry discovery blocker without creating a second verification flow.
- If the URL has no CIT A signal or cannot produce a fresh taskId, the coverage gap remains a source-readiness blocker, not a parser failure.
- Parser work still waits for a real A200000 filed row or current-declare A-class form with comparison evidence.

## 2026-06-10: Authenticated YDZ workbench recovery does not prove CIT A source readiness

Status: Accepted

Context: The latest CIT A supplement retry no longer fails at Yidaizhang password-login input discovery. The session can recover from an authenticated landing or `redirectVM` page, open the cloud workbench, and read 144 current-enterprise account rows for period `202605`. However, those rows expose `citSignalCount=0`. Workbench enterprise names are discoverable from `workbench.chanjet.com`, but a selectable enterprise still is not a usable source unless its Yidaizhang app opens an active cloud `work.html` entry.

Decision:
- Treat authenticated Yidaizhang landing recovery as login readiness only; it is not evidence that the current enterprise can produce CIT A taskIds.
- Require a CIT A signal in the Yidaizhang batch account row before submitting fresh CIT A collection.
- Classify sampled other enterprises that do not expose an active Yidaizhang cloud workbench entry as `other_enterprise_scan_unavailable`.
- Keep empty `batch_problem_details.csv` as evidence that no parser, mapping, mismatch, or web-missing defect has been produced yet.
- Continue to require the standard `main.py --task-id` verification path for any fresh taskId generated later.

Consequences:
- The remaining `CIT_A:filed` and `CIT_A:unfiled` gaps are source-readiness blockers until an active CIT-ready account set is available.
- The next operator action is to switch to an active Yidaizhang enterprise with CIT A account rows, provide that enterprise's `work.html` URL, or create/import a CIT A account set in the current enterprise.
- Parser work should resume only after a fresh or usable historical task reaches a real A200000 filed row or current-declare A-class form and produces comparison evidence.

## 2026-06-10: YDZ token-empty refresh failures are login-readiness blockers

Status: Accepted

Context: The latest CIT A supplement retry found backend candidates for both filed and unfiled targets, but fresh Yidaizhang refresh failed before account scanning with `/trans/easyacctg/query/getBatchList failed: http=701 ... token 不能为空`. This is not a parser or field-comparison failure; it means the Yidaizhang API token in the browser/session is unusable.

Decision:
- Classify `http=701` / `token 不能为空` Yidaizhang refresh failures as `ydz_login_required`.
- Show that status in `coverageSupplement.sourceReadiness`, `coverage_missing.csv`, and the batch summary coverage gap text.
- Keep these rows out of `batch_problem_details.csv` unless a real comparison completes and produces mismatch or web-missing evidence.
- Harden enterprise-selector and enterprise-switch logic so stale pre-existing Yidaizhang cloud pages do not count as successful selector opening or switching.

Consequences:
- Operators get the correct next action: refresh/provide Yidaizhang login state, then rerun CIT A fresh refresh.
- Repeated historical backend task retries are less likely to be mistaken for parser defects.
- Workbench-triggered scans can pass temporary credentials through the child environment without exposing them in the command display.

## 2026-06-10: Other-enterprise CIT A scan is read-only and explicit

Status: Accepted

Context: The current batch still lacks `CIT_A:filed` and `CIT_A:unfiled`. The current Yidaizhang enterprise has no CIT A account signal for `202605`, while backend historical candidates are stale or source-blocked. The next useful step is to find whether another selectable Yidaizhang enterprise has CIT-ready account rows.

Decision:
- Keep other-enterprise scanning off by default and enable it only with `--coverage-supplement-scan-ydz-enterprises`.
- Make the scan read-only: switch enterprise context and read account rows, but do not submit collection or create account sets.
- Persist scan results under `coverageSupplement.freshYdzRefresh` and summarize them in `coverageSupplement.sourceReadiness`.
- If the enterprise selector cannot be opened due to missing Yidaizhang login state or credentials, classify the gap as `other_enterprise_scan_login_required` instead of hiding it behind the current-enterprise no-signal result.

Consequences:
- Operators can see whether the next action is switching enterprise, providing Yidaizhang credentials, or creating/importing a CIT-ready account set.
- The full verification flow still uses `main.py` and the existing supplement pipeline for any actual task verification.
- The scan may require workbench-provided credentials when the browser does not already expose the enterprise selector.

## 2026-06-10: Source readiness explains coverage gaps before parser work

Status: Accepted

Context: The latest CIT A retries produced no mismatch or web-missing rows. Backend historical candidates still failed at expired tax-login state, while the current Yidaizhang enterprise scan found 144 account rows for period `202605` and `citSignalCount=0`. Without a first-class source diagnosis, the workbench could still present the gap as a generic uncovered target.

Decision:
- Persist per-target source diagnostics under `coverageSupplement.sourceReadiness`.
- Prefer source-readiness messages in `coverage_missing.csv` and batch coverage-gap text when no clean verification covers the target.
- Keep parser/mapping problem output in `batch_problem_details.csv`; do not treat source-readiness blockers as field-comparison failures.

Consequences:
- Operators can see when the next action is switching Yidaizhang enterprise or creating/importing CIT-ready account sets.
- Repeated retries against expired backend taskIds are easier to avoid.
- Parser changes should wait until a task reaches a real CIT A/A200000 filed row or current-declare A-class form and produces field evidence.

## 2026-06-10: CIT A current-enterprise fresh scan requires current period and CIT signal

Status: Accepted

Context: A live CIT A supplement retry against `codex_full_20260609_204530` showed that backend candidate tax numbers were absent from the current Yidaizhang enterprise. The first current-enterprise scan then tried historical candidate periods such as `202512` and `202603`, which Yidaizhang rejected because their collection windows had already passed. Trying arbitrary accounts for `202605` also produced no taskId when the batch-list rows had no CIT tax item signal.

Decision:
- Current-enterprise fresh scan for CIT A uses the batch period only.
- The scan submits collection only for accounts with a CIT signal in the Yidaizhang batch-list row.
- If no current-period account has a CIT signal, the workflow records `current_enterprise_scan_no_cit_account_signal` and falls back to backend historical candidates.
- Fresh-task discovery uses a short supplement-specific polling timeout, not the normal batch collection timeout.

Consequences:
- The supplement loop avoids submitting non-CIT accounts and avoids expired historical Yidaizhang collection windows.
- Current-enterprise scan becomes a precise source-discovery step rather than an unbounded retry mechanism.
- A remaining CIT A gap can now be diagnosed as "current enterprise has no CIT-ready account for the batch period" instead of a parser or field-comparison failure.

## 2026-06-10: CIT A supplement fresh collection is explicit and account-set gated

Status: Accepted

Context: The remaining `CIT_A:filed` and `CIT_A:unfiled` coverage gaps are dominated by expired historical tax-login task cookies and source-state conflicts. A fresh Yidaizhang collection can generate a new taskId only when the candidate tax number exists in the current Yidaizhang enterprise; many backend supplement candidates come from other enterprises and cannot be refreshed locally.

Decision:
- Add `--coverage-supplement-refresh-cit-from-ydz` as an explicit flag; do not make fresh Yidaizhang collection the default backend supplement behavior.
- When enabled, try fresh collection only for CIT A supplement candidates.
- Before submitting collection, check that the candidate tax number exists in the current Yidaizhang enterprise for the candidate period.
- If a fresh taskId is resolved, put it ahead of the backend historical candidate for the same coverage target.
- If no account set exists or no taskId is resolved, persist the reason under `coverageSupplement.freshYdzRefresh` and continue with the historical backend candidate.
- Sort supplement candidates by fresh-source priority, exact declaration-status match, then recency. Unknown-status probes stay behind exact status candidates.

Consequences:
- The workflow can use new taskIds to avoid expired historical tax-login state without submitting collection for arbitrary backend tax numbers.
- Ordinary supplement runs keep the previous read-only backend behavior unless the operator explicitly requests fresh CIT A collection.
- Remaining CIT A gaps can be diagnosed as "no account in current enterprise" instead of repeatedly trying expired backend taskIds.

## 2026-06-10: CIT A unknown-status filed probes require tax-bureau row evidence

Status: Accepted

Context: CIT A successful backend collect tasks often have no tax-code-specific current-period marker in task execution logs. To avoid missing potential filed samples, the supplement planner can probe unknown-status CIT A tasks as filed by passing a declaration-status override into the canonical verifier.

Decision:
- Permit `CIT_A:filed` supplement retries to use unknown-status backend tasks as filed probes.
- The override only chooses the filed navigation path when logs are unknown; explicit current-period true/false markers still win.
- A filed probe counts only if the tax-bureau declaration query page contains the CIT A/A200000 row for the target period and the normal comparison succeeds.
- If the refreshed declaration query page has no matching CIT A row, classify the attempt as source-state conflict, not as a parser failure or coverage hit.

Consequences:
- The system can explore ambiguous backend tasks without corrupting coverage.
- Coverage remains evidence-based: successful backend collection alone is not enough for CIT A filed coverage.
- Operators can distinguish "candidate was worth probing" from "candidate proved coverage."

## 2026-06-10: current-period log markers are target-tax-code scoped when possible

Status: Accepted

Context: Multi-tax collection tasks can contain multiple current-period marker rows. A later VAT or culture-fee marker can otherwise override the CIT A marker and select the wrong filed/unfiled route.

Decision:
- When the target tax code is known, read current-period marker rows whose `lsn` matches that target tax code.
- Use `sz_zzs` for VAT, `sz_qysds` for CIT A, `sz_whsyjsf` for culture fee, and `sz_xfs` for consumption tax.
- Fall back to the previous latest-marker behavior only when no tax-code-specific marker exists.
- Persist status-task diagnostics so operators can see which task IDs were parsed as filed, unfiled, or unknown.

Consequences:
- Multi-tax tasks no longer let unrelated tax-type status markers steer CIT A or other target verification.
- Unknown statuses remain explicit and can be handled by target-specific retry policy.

## 2026-06-10: Target-scoped supplement retries do not change coverage scope

Status: Accepted

Context: While retrying only the remaining CIT A coverage gaps, using `--coverage-tax-types CIT_A` temporarily rewrote the batch state and made the coverage matrix look like a CIT-only run until the state was restored. That is risky for operator workflows because "what to supplement now" is not the same as "what this batch is supposed to cover."

Decision:
- Add `--coverage-supplement-targets` for target-scoped retries such as `CIT_A:filed,CIT_A:unfiled`.
- Add `--coverage-supplement-only` so an existing run can search/apply supplement candidates without re-verifying all original tax numbers.
- Store `requestedTargetKeys` under `coverageSupplement`, but leave `coverageTaxTypes` and `coverageCollectStatuses` unchanged.
- If a user supplies invalid supplement target keys, fail early instead of falling back to a full supplement run.

Consequences:
- Operators can retry one missing coverage gap without corrupting the batch's authoritative coverage scope.
- The coverage matrix remains full-scope, while supplement diagnostics show the narrowed retry request.
- Future workbench controls should use supplement target keys for focused retries rather than rewriting tax-type coverage selection.

## 2026-06-10: CIT A hot-service shortcuts are not undeclared current-declare entries

Status: Accepted

Context: Guangdong tax-bureau home pages can show `本期应申报` with no data while also showing resident-enterprise CIT under `热门服务`. Clicking that shortcut does not prove the current-period A-class undeclared form exists; it can leave the verifier waiting for fill buttons on the home page for close to a minute.

Decision:
- For CIT A undeclared coverage, only the current-declare scope can satisfy the target entry requirement.
- Hot-service-only resident-enterprise CIT text is treated as source/entry-state mismatch and is not clicked as a target title.
- When the tax-bureau home page has no CIT A current-declare entry, fail before the generic fill-button polling loop.

Consequences:
- CIT A source-state blockers fail faster and more explicitly.
- Parser work remains focused on pages where a real A200000/CIT A form is actually opened.
- A valid province-specific CIT A current-declare row can still be handled if it appears inside the declare/todo scope.

## 2026-06-10: Superseded supplement differences do not feed the current problem list

Status: Accepted

Context: In `codex_full_20260609_204530`, an older backend supplement candidate for `VAT_SMALL:unfiled` still had a `completed_with_differences` report from before the parser fix. A later candidate covered the same target cleanly, but the stale difference report still populated `batch_problem_details.csv`, making the current batch look like it still had field failures.

Decision:
- For backend-supplement items only, if a coverage target already has a clean successful supplement verification, non-clean supplement reports for the same target are skipped when building the current dashboard problem details.
- Ordinary user/batch task differences remain visible.
- If a supplement target is not yet covered by a clean candidate, its completed-with-differences report still remains visible so parser defects are not hidden.

Consequences:
- `batch_problem_details.csv` now reflects current actionable field problems instead of stale failed supplement attempts.
- Historical reports remain on disk for audit.
- Supplement attempts remain the place to inspect failed candidates and external blockers.

## 2026-06-10: CIT A undeclared home entries must come from the declare scope

Status: Accepted

Context: CIT A undeclared candidates can land on provincial tax-bureau home pages that mention resident-enterprise CIT in hot services while the actual current-declare list contains only VAT, B-class CIT, deemed-assessment CIT, or no target row. Clicking those hot-service shortcuts does not prove the A200000 undeclared form is available and can lead to misleading retries.

Decision:
- Treat a CIT A undeclared home page as a valid target only when the A-class/bookkeeping-assessment CIT text is found inside the current declaration/todo scope.
- Reject B-class or deemed-assessment CIT text for the A-class target.
- Hot-service-only CIT shortcuts are not accepted as the undeclared entry. They are reported as source/entry-state mismatch unless a later page proves the A200000 form is open.

Consequences:
- CIT A undeclared failures are classified as tax-bureau/source-state blockers instead of parser failures when the live page lacks the actual A-class undeclared row.
- This may reduce false positives from broad CIT labels, while still allowing province-specific A-class entries that use resident-enterprise bookkeeping-assessment wording.

## 2026-06-09: CIT A filed list matching is broad, detail confirmation remains strict

Status: Accepted

Context: A Tianjin CIT A filed supplement candidate reached the declaration information query page. The original list-row keywords required `A200000` and `A class`, but some tax-bureau list titles may only show a business title such as enterprise income tax monthly/quarterly declaration. A rerun with broader row keywords still found no CIT row, and direct page inspection showed only culture fee and VAT rows for the queried period.

Decision:
- Match `cit_a_main` rows in filed declaration lists with broad keywords: enterprise income tax, month, and quarter.
- Keep detail-form selection and confirmation strict with `A200000` and the A-class prepayment form title.
- Continue classifying a filed candidate as a source-state conflict when the declaration query results contain no CIT A row for the task period.

Consequences:
- Province list-title variants are less likely to cause false misses.
- Opening the wrong row should still be caught by strict detail-form confirmation before field comparison.
- The known Tianjin candidate remains uncovered because the live tax-bureau query results do not contain CIT A for the requested period.

## 2026-06-09: Undeclared home-entry recovery is single-click and auth-fast-fail

Status: Accepted

Context: Beijing culture-fee and Jiangsu CIT A unfiled candidates could loop through repeated tax-home entry clicks, wait for fill buttons or menus after the page had already returned to the home page, or treat `/mhzx/api/mh/tpass/code` authorization-code pages as reusable tax-bureau login state. This made external blockers look like long verifier hangs.

Decision:
- Treat `/mhzx/api/mh/tpass/code` URLs and authorization-code-empty page content as tax-login/authentication failure, not as logged-in tax-bureau pages.
- Check for auth failure after entering the tax bureau, after undeclared-entry clicks, while waiting for undeclared pages, and before long fill-button/menu waits.
- When on a tax-bureau home page, try the visible target action before walking broader navigation steps.
- Click only one matched target action/title per evaluation and stop recovery when the same click result repeats.
- If undeclared preparation is redirected back to tax home, recover the target entry before waiting for form fill buttons or left-menu items.

Consequences:
- External auth loss and province-specific missing entries fail faster with actionable categories.
- The verifier avoids repeated action clicks that can re-trigger home redirects or hide the actual final page state.
- Genuine target-entry absence remains a coverage blocker, while parser fixes stay focused on completed pages that produce field mismatches or web-missing evidence.

## 2026-06-09: Coverage targets require clean verification, not just report presence

Status: Accepted

Context: Backend supplement for `codex_full_20260609_172724` marked `VAT_GENERAL:unfiled` as covered even though the candidate verification had failed/timed out. The coverage matrix counted partial reports from failed tasks, so subsequent supplement runs skipped a real missing target and `batch_problem_details.csv` showed stale mismatch rows from a failed candidate.

Decision:
- Coverage analysis counts a target as covered only when the batch state has a successful verification record for that task (`status=success`, `returnCode=0`).
- Supplement attempts are marked covered only when the coverage matrix is covered and the current candidate's own verification record is clean.
- Batch problem details load reports only from successful or completed-with-differences verification records, not from failed/skipped candidates.

Consequences:
- Failed, timed-out, and external-state-blocked candidates no longer hide real coverage gaps.
- Stale partial reports remain on disk for audit, but they do not drive current coverage or field-problem summaries.
- Operators see failed candidates through the supplement attempt list, while field mismatch tables stay focused on valid completed comparisons.

## 2026-06-09: Coverage supplement backend search is not restricted to privacy-login task rows

Status: Accepted

Context: The broadened coverage run could not find any CIT A samples while the supplement query sent `loginType=YSHDL,DLYW-YSHDL`. A direct read-only backend check showed valid successful CIT A collect tasks for period `202605`, but they were excluded by that login-type filter.

Decision:
- Remove the privacy-login `loginType` filter from coverage supplement task-list searches.
- Keep task search constrained by period, successful collect task, tax kind, taxpayer type where applicable, and optional lookback window.
- Add `--coverage-supplement-lookback-days` for controlled previous-window supplement searches while preserving the current-month default.

Consequences:
- CIT A and CBJ personal representative tasks can be found even when their backend task rows do not use privacy-login methods.
- Account-set source lookup remains separate and can keep its own login-information requirements.
- Broader supplement searches may find more external-state-blocked candidates, so candidate verification remains serial and target-scoped.

## 2026-06-09: Backend supplement may try multiple candidates per missing target

Status: Accepted

Context: The full coverage run showed several missing targets where the first backend representative task was blocked by external tax-bureau state, such as already-declared conflicts, missing undeclared entries, pending tax-login locks, or expired task cookies. The command-line option `--coverage-supplement-max-candidates` existed, but both the planner and batch grouping hard-capped it to one candidate.

Decision:
- Honor `max_candidates_per_target` in `CoverageSupplementPlanner.find_candidates()`.
- Honor `--coverage-supplement-max-candidates` when grouping and applying backend supplement candidates.
- Keep candidate verification serial in the existing batch flow, because tax-bureau browser/login state is still shared.

Consequences:
- One bad representative task no longer blocks trying newer or older backend rows for the same coverage target.
- Batch runtime can increase when the user asks for multiple candidates.
- Parallel verification remains out of scope until browser/session sharding is introduced.

## 2026-06-09: VAT general undeclared retained-tax cumulative fields subtract current period

Status: Accepted

Context: Shanghai undeclared VAT general task `2077729330827119155` produced two mismatches on the captured tax page: `sqldse_ybxm_bnlj` and `qmldse_ybxm_bnlj`. The tax-bureau undeclared page showed the current-period retained-tax value as `15520.77` and the cumulative column as `0`, while the backend API returned `-15520.77`. Replaying the captured evidence proved that the backend convention for these undeclared fields is cumulative minus current-period value.

Decision:
- For `vat_general_main` only, when `current_period_flag is False`, force current-period subtraction for `sqldse_ybxm_bnlj` and `qmldse_ybxm_bnlj`.
- Do not apply this rule to filed tasks; filed retained-tax cumulative values keep the direct tax-page value.
- Keep the existing general current-period subtraction rules unchanged for other cumulative VAT fields.

Consequences:
- Replaying the captured Shanghai undeclared main-form evidence now reports `158/158` matches.
- A live rerun could not regenerate the report because the tax bureau now blocks the same period as already declared; the replay remains the strongest available evidence for this state-specific rule.
- The rule is limited to two observed retained-tax fields to avoid over-adjusting unrelated cumulative columns.

## 2026-06-09: VAT general appendix1 hjxse_6 may fall back to main-form immediate-refund current sales

Status: Accepted

Context: Live task `2077729644358679384` showed a single remaining VAT general filed mismatch after main-form parsing was fixed. Appendix1 `hjxse_6` returned `0.0` from the backend API, while the tax-bureau page showed `17699.12`. The same amount was present in main-form API fields `asysljsxse_jzjtxm_bys` and `yshwxse_jzjtxm_bys`; the paired tax amount `hjXxynse_6` already matched `xxse_jzjtxm_bys`.

Decision:
- Apply a field-level API fallback only for VAT general appendix1 `hjxse_6`.
- Use the direct appendix API value when it is non-zero.
- When the direct appendix value is empty or zero, use `asysljsxse_jzjtxm_bys`, then `yshwxse_jzjtxm_bys`, from the VAT general main-form API data if either value is non-zero.
- Do not introduce broad cross-form aliasing for other appendix1 rows without equivalent live evidence.

Consequences:
- The known Beijing filed sample now compares appendix1 with `134/134` matches.
- Future backend API omissions for this specific equivalent field will not surface as false data mismatches.
- A true non-zero appendix API value still wins, so the fallback should not overwrite deliberate backend values.

## 2026-06-09: Undeclared tax-home navigation interruptions are classified by final page state

Status: Accepted

Context: Yunnan culture-fee unfiled task `2077729644358674126` repeatedly interrupted tax-home click JavaScript with Playwright `Execution context was destroyed` while the page was navigating. Treating this as a raw verifier error hid the real final state: the page either moved to a tax auth-code error page or returned to a tax-bureau home page that did not list the culture-fee undeclared entry.

Decision:
- Retry tax-home declare-entry clicks after navigation-context destruction, with a short page-settle wait between attempts.
- If repeated navigation interruptions continue, stop raising the raw Playwright exception and let the existing target-page/auth-state checks classify the final page.
- Treat `/mhzx/api/mh/tpass/code` and authorization-code-empty pages as tax-bureau login/authentication failures.
- Keep an absent undeclared target on the tax-bureau home page as `UndeclaredTaxTargetUnavailableError`, not a field comparison failure.

Consequences:
- Batch summaries now show actionable external-state reasons instead of low-level browser exceptions for this class of navigation race.
- The current Yunnan culture-fee sample remains uncovered because the live tax-bureau home page has no target undeclared entry.
- The verifier still fails the task when the target entry is genuinely unavailable, preserving coverage correctness.

## 2026-06-09: Selected tax-type verification keeps all registered forms

Status: Accepted

Context: Live monitoring of run `ops_20260609_161052` showed two stability gaps. First, a selected tax type could hide one of its registered forms when that form had zero comparable API fields, which conflicts with the operator requirement that each tax type verifies all of its tables. Second, a VAT general appendix recovery path blocked the batch for many minutes, and an undeclared consumption-tax attempt spent time retrying the home-page entry even though the home row showed the target was already declared.

Decision:
- Treat tax-type selection as a request to keep all registered forms for that tax type visible in the verification output.
- Do not drop selected forms only because API field coverage is `0/N`; emit an evidence report with `not_comparable=true` instead.
- Bound expensive web extraction recovery and the child `main.py` verification process so one form cannot block the batch indefinitely.
- Classify a tax-home target row that shows already declared before retrying undeclared entry clicks.
- Final batch verification must convert no-taskId items to a manual terminal stage instead of leaving them `running`.
- Repeated pending tax-login task locks with the same occupying taskId should fast-fail after short repeated evidence instead of waiting the full polling window.
- Backend supplement task-list queries remain serial until the shared browser-derived login/token state is split into independent request clients.

Consequences:
- Coverage output can now show forms that were attempted but had no comparable backend fields.
- Some hard-to-render fields may become explicit `web_missing` results sooner, which is preferable to an unbounded batch.
- External state conflicts such as already-declared pages and missing taskIds surface as operational handling reasons rather than silent coverage gaps.
- A real pending tax-login lock is surfaced faster for operator handling; safe backend query parallelization is deferred to avoid auth/cache contention.

## 2026-06-09: Backend supplement verification is target-scoped

Status: Accepted

Context: Live monitoring of run `ops_20260609_152646` showed that a backend supplement task for `CULTURE_FEE:filed` was verified with `--targets auto`. The task result also contained VAT data, so the verifier spent most of the run on VAT general forms before culture fee. A `CULTURE_FEE:unfiled` candidate then failed on `vat_general_main` before reaching the intended culture fee target.

Decision:
- Keep normal batch verification on the user-requested `--targets` value.
- For `backend_supplement` items, when the current coverage target is known and the requested target mode is `auto`, pass only the coverage target's registered `form_ids` to `main.py`.
- Preserve explicit non-auto target requests unchanged.
- Keep CBJ supplement on its dedicated verifier instead of mapping CBJ pseudo-form IDs to `main.py` targets.

Consequences:
- Backend supplement attempts spend less time on unrelated forms.
- A multi-tax task can no longer fail a culture fee coverage attempt because VAT forms were tried first.
- Coverage supplement remains a wrapper over the canonical verifier; it only narrows the form list.

## 2026-06-09: Coverage supplement backend task-list filters use taxId for supported tax types

Status: Accepted

Context: After fixing VAT supplement lookup, the same backend task-list behavior was checked for other supported tax types. Live `getTaskListInternal` calls showed that `taxTypeId` filters are not reliable server-side filters and can return mixed first pages. Reliable filters are `taxId=2` for CIT A, `taxId=3` for culture fee, `taxId=26` for consumption tax, and `taxId=39` for CBJ.

Decision:
- Coverage supplement targets use `backend_tax_ids` for CIT A, culture fee, consumption tax, VAT, and CBJ.
- CIT A uses `taxId=2`.
- Culture fee uses `taxId=3`.
- Consumption tax uses `taxId=26`; the old `taxTypeId=29/30` values are not used for public-manage supplement search.
- CBJ keeps `taxId=39`.
- Keep `taxTypeId` parsing only as row metadata/client-side inference where needed, not as the primary backend supplement query field.

Consequences:
- Supplement searches avoid being starved by unrelated first-page rows when the backend ignores `taxTypeId`.
- Multi-tax rows, such as VAT plus CIT or VAT plus culture fee, can still be returned when they contain the requested `taxId`; this is expected and still filtered by target status later.
- Existing account-set backend source lookup remains unchanged because it intentionally uses a broader task category search.

## 2026-06-09: VAT coverage supplement uses backend taxId and collect taskTypeId

Status: Accepted

Context: Task `2077729738850235767` is a filed small-taxpayer VAT collect task. Direct task API parsing selected small VAT targets and parsed `current-period=true`, but coverage supplement did not find it. Live backend task-list checks showed that `taxTypeId=1` does not reliably filter VAT rows, while `taxId=1` does. The collect-task search also needs backend `taskTypeId=3`; otherwise the first pages are filled with unrelated task categories and local filtering can miss valid collect tasks.

Decision:
- VAT coverage targets use `backend_tax_ids=(1,)` and no `backend_tax_type_ids`.
- Coverage supplement collect-task searches send `taskTypeId=3` through `find_collect_tasks_by_filters()`.
- Keep plain `query_tasks()` unchanged so account-set backend source lookup can still use the broader `taskCategorys="2,3"` flow without a forced collect-task filter.
- Continue using `taxPayerType` to split VAT normal taxpayer and small taxpayer targets after the backend has narrowed the VAT collect-task set.

Consequences:
- `VAT_SMALL:filed` and `VAT_SMALL:unfiled` supplement searches are no longer starved by unrelated backend task rows.
- Existing account-set source lookup behavior remains separate from coverage supplement.
- Diagnostics now show VAT supplement queries as `backendQueryField=taxId`, `backendTaxId=1`.

## 2026-06-09: Known-unfiled tax tasks do not fall back when the tax bureau reports already declared

Status: Accepted

Context: Tianjin task `2077729648653721147` was selected by backend coverage supplement as `VAT_GENERAL:unfiled` because the task execution log parsed `current-period=false`. The direct Tianjin undeclared VAT page loaded, but the tax bureau displayed a blocking message saying the period was already declared and should be handled through declaration correction or voiding.

Decision:
- If the backend declaration-status marker is explicitly `false`, tax-bureau "already declared" from the undeclared page is treated as a source-state conflict.
- Do not switch to declared-query verification in that case, because doing so would incorrectly mark an unfiled coverage sample as filed coverage.
- Declared-query fallback remains allowed only when the backend declaration status is unknown and the tax-bureau page itself proves the record is already declared.
- Keep undeclared home recovery separate: the verifier may still retry homepage/card entry clicks before deciding the target is unavailable or conflicting.

Consequences:
- Coverage supplement will no longer silently consume a known-unfiled target as a filed verification result.
- Operators see a direct manual-handling reason when backend task status and live tax-bureau status disagree.
- Some historical taskIds can fail intentionally if their backend execution log is stale relative to the current tax-bureau state.

## 2026-06-09: Coverage supplement filters by selected tax types and collect statuses

Status: Accepted

Context: The workbench coverage range previously let operators select tax types only. Backend supplement then generated both internal coverage statuses for every selected tax type. Operators need to limit backend supplement to only selected collect statuses, such as only `已取数` or only `未取数`, while still filtering by checked tax types.

Decision:
- Add workbench checkboxes for backend supplement collect statuses: `已取数` and `未取数`.
- Pass selected statuses to the batch script with `--coverage-collect-statuses collected,not_collected`.
- Persist selected statuses in batch state as `coverageCollectStatuses`.
- Map `collected` to the existing internal `filed` coverage target and `not_collected` to `unfiled`, preserving current analyzer and supplement matching logic.
- Tax types with `coverage_statuses=(any,)`, such as CBJ targets, remain status-independent when the tax type is selected.

Consequences:
- Backend supplement now uses the selected tax types and selected collect statuses together.
- Existing runs without `coverageCollectStatuses` default to both statuses, preserving old behavior.
- Coverage UI, coverage JSON/CSV, and supplement search all use the same state-backed status filter.

## 2026-06-09: Manual account-set source mode skips public-manage and privacy-phone preparation

Status: Accepted

Context: Operators sometimes already have all customer and tax login fields and need the workbench to create/save the Yidaizhang account set directly. In that case, going through public-manage task lookup and privacy-number synchronization is unnecessary and can introduce unrelated backend-page blockers.

Decision:
- Add a separate workbench entry for manual-source account-set creation instead of overloading the backend-source form.
- Pass manual customer/login fields to `scripts/ydz_create_customers.py` through `YDZ_MANUAL_*` environment variables and run with `--manual-source-env`.
- Always add `--skip-privacy-phone-sync` for this entry.
- Manual-source runs only require Yidaizhang login readiness; they do not open public-manage backend pages, query backend tasks, or prepare integration privacy-number data.
- Keep passwords out of command lines, job records, logs, and result JSON.

Consequences:
- Operators can create an account set from known login information even when backend task lookup or privacy-number sync is intentionally skipped.
- Backend-source account-set creation remains unchanged for the normal automated lookup path.
- Manual mode still validates required fields before running and may query Yidaizhang tax geo only when the supplied region cannot be mapped locally.

## 2026-06-09: Account-set slider verification is an operator handoff, not a bypass target

Status: Accepted

Context: `--disable-blink-features=AutomationControlled` can reduce browser automation signals, but it does not guarantee that Yidaizhang will skip slider verification. A workbench account-set run for `913306046851112034` triggered a slider and looked like a normal long-running task until timeout.

Decision:
- Keep the Chrome startup flag as a best-effort mitigation only.
- When Yidaizhang password login displays the slider, emit the stable log marker `MANUAL_VERIFICATION_REQUIRED`.
- The workbench must parse that marker and show `需人工验证 / 等待易代账滑块` while the child process keeps waiting.
- After the operator completes the slider in Chrome, the same process continues by detecting the Yidaizhang workbench session; it should not require a separate rerun unless the wait times out.
- Account-set logs must state whether the run reused an existing Chrome CDP browser or launched a new one, because startup flags cannot be applied retroactively to an already-running browser.

Consequences:
- Operators get immediate, accurate feedback when manual slider completion is required.
- The automation remains compliant with security verification instead of trying to bypass it.
- Existing logged-in sessions remain the preferred stable path for avoiding repeated password-login risk.

## 2026-06-09: Account-set source lookup slices backend task-list time ranges

Status: Accepted

Context: A full integration account-set run reached public-manage source lookup but the backend returned `查询时间范围不能超过40天` when the configured lookback sequence included multi-month or multi-year windows. Account-set creation still needs a broad lookup because operators may create customers from older successful task records.

Decision:
- Keep the existing broad lookback configuration, but execute it as multiple task-list requests with windows of at most 39 days.
- Query newer windows first and return the latest usable successful task with login information.
- Keep account-set task-list filters as `taskCategorys: "2,3"` and continue omitting `taskTypeId`.
- Apply the same behavior to the project script, the standalone `skills/ydz-create-accountset` CLI, and the installed local `ydz-create-customer` skill copy.

Consequences:
- Backend source lookup no longer fails on the public-manage 40-day range limit.
- Older login source tasks can still be found without widening any single backend request beyond its accepted range.
- Long lookbacks may issue more backend requests, but stop as soon as a usable source row is found.

## 2026-06-09: Yidaizhang redirectVM is a normal post-login handoff page

Status: Accepted

Context: After successful Yidaizhang integration authentication, the browser may land on a `passport.../vm/redirectVM` page titled `进入应用` instead of navigating directly to the workbench. Treating this page as not logged in caused account-set creation to fail even though credentials and session state were valid.

Decision:
- Detect Yidaizhang `redirectVM` pages as a valid logged-in handoff state.
- Try the page's visible entry action first.
- If that does not open the workbench quickly, open the configured Yidaizhang `work.html` URL directly in the same browser context.
- Mirror the behavior in the standalone account-set skill and installed local skill copy.

Consequences:
- Successful login no longer depends on the redirect page completing its own navigation.
- True missing sessions still fail through the existing login readiness checks.
- Slider or MFA challenges remain manual handoff cases and are not bypassed.

## 2026-06-08: Chrome launches include AutomationControlled mitigation

Status: Accepted

Context: Yidaizhang login may show a slider challenge after submitting credentials. One possible mitigation is launching Chrome with `--disable-blink-features=AutomationControlled` so the browser exposes fewer automation markers. This does not guarantee slider avoidance and must not replace the manual verification handoff.

Decision:
- Add `--disable-blink-features=AutomationControlled` to project-owned Chrome launch commands used by Yidaizhang account-set creation, Yidaizhang sessions, privacy-phone sync, the shared browser manager, and the Windows CDP startup script.
- Mirror the same launch argument into the standalone `skills/ydz-create-accountset` CLI and the installed local `ydz-create-customer` skill copy.
- Keep existing slider detection and manual completion flow as the reliable fallback.

Consequences:
- Fresh Chrome sessions may be less likely to trigger automation-based slider checks.
- Existing Chrome processes are not affected until they are closed and relaunched.
- Slider/CAPTCHA/MFA can still appear and remains an external manual verification step.

## 2026-06-08: Yidaizhang auto-login must preserve manual verification handoff

Status: Accepted

Context: Yidaizhang integration login can require a slider challenge after the username/password form is submitted. The script cannot reliably complete that challenge. A failed account-set run showed that the browser became logged in after manual completion, but the script had already cached an earlier "Yidaizhang not ready" state or later closed the shared Chrome CDP browser, causing subsequent runs to lose the manually established session.

Decision:
- Treat visible Yidaizhang slider verification as a manual verification handoff, not as a password-submit retry loop.
- While waiting for login readiness, preserve the login page and use the public Yidaizhang `进入易代账` page or a separate workbench tab to open `work.html`.
- After public-manage backend login, re-check Yidaizhang readiness so a manually completed slider can be picked up before failing the run.
- Do not call `browser.close()` on a browser obtained through Chrome CDP for account-set creation; leave the shared operator browser and login state alive.

Consequences:
- The script still cannot bypass slider verification, but it can continue automatically after the operator completes it.
- Manual login state is preserved for subsequent workbench account-set tasks.
- Login failures should be reported as an external verification handoff rather than a generic bad password.

## 2026-06-08: Backend login is embedded in operational workflows

Status: Accepted

Context: The workbench briefly exposed a standalone public-manage backend login form. Operationally, backend login is not a user goal by itself; it is a prerequisite for account-set creation, backend login-info lookup, and privacy-number synchronization/preparation. Showing it as a separate primary entry made the workflow look split and encouraged operators to run a manual pre-step.

Decision:
- Remove the standalone backend-login form from the workbench main UI.
- Keep backend username/password inputs inside the account-set creation flow, where they are used only as transient child-process environment variables.
- Let privacy-number synchronization/preparation also perform backend login automatically from supplied transient credentials or existing browser state.
- Keep the existing backend-login command/job code only as an internal diagnostic and compatibility path, not as a normal operator entry.

Consequences:
- Operators use "创建账套" or "隐私号同步" directly; those flows handle backend login readiness themselves.
- Passwords remain out of command lines, job records, logs, and result JSON.
- Tests now assert that the workbench HTML does not expose the standalone backend-login form.

## 2026-06-08: Integration account-set creation prepares privacy-number data before customer creation

Status: Accepted

Context: Integration account-set creation saves tax login information from backend `loginJson`. When the privacy number exists online but has not been synchronized into the integration backend, Yidaizhang integration creation can save a privacy-number login that the integration backend cannot resolve. The manual backend flow checks integration privacy-number configuration first, then copies from online and pulls into integration when missing.

Decision:
- During `--env inte` account-set creation, after resolving backend login information and before creating/updating the Yidaizhang customer, query integration privacy-number summary:
  `POST https://data-task-management-chanapp.inte.chanjet.com/pub-tax-management/api/privatePhone/summary`
  with payload `{"privatePhone":"<privacy number>"}`.
- If integration summary has records, continue without mutation.
- If integration summary is empty, run the online backend copy sequence:
  `summary`, `ref/getDetail`, and `copyDataByPrivatePhone`.
- After online copy succeeds, call integration:
  `GET https://data-task-management-chanapp.inte.chanjet.com/pub-tax-management/api/privatePhone/pullPrivateDataByPrivatePhone?privatePhone=<privacy number>`.
- Do not send the `token` header to integration privacy-number endpoints. Live testing showed that including `token` returns `用户身份证认证失败，请重新进行认证。`; keeping `authorization` and omitting `token` succeeds.
- Mirror the behavior in the standalone account-set skill and installed local `ydz-create-customer` skill copy.

Consequences:
- Integration account-set creation is blocked when required privacy-number preparation fails, instead of creating a customer with unusable privacy-number backend data.
- Dry runs report whether integration privacy-number data exists without calling online copy or integration pull.
- Online and integration privacy-number APIs intentionally use different payload/header contracts.

## 2026-06-08: Workbench has a dedicated backend login job

Status: Accepted

Context: Account-set creation depends on public-manage login state to query backend task login information. When the backend tab is not logged in, or the browser has a stale unauthorized session, operators need a direct way to refresh the backend login state before creating account sets.

Decision:
- Add a standalone backend login form and `/api/login-backend` endpoint to `scripts/ops_console.py`.
- Run backend login through `scripts/ydz_create_customers.py --login-only --login-target backend` so it reuses the same browser automation and Chrome CDP profile as account-set creation.
- Store backend login runs separately under `output/backend_login_runs/<runId>/` with sanitized readiness status only.
- Pass backend username/password/URL only through the child process environment.
- Treat public-manage `403 / 无权访问` as not logged in, even if browser storage still contains tokens.

Consequences:
- Operators can repair backend login state from the workbench before account-set creation.
- Backend login does not require tax numbers and does not create or update customers.
- Passwords remain transient and are not written to commands, job records, logs, or JSON results.

## 2026-06-08: Missing backend login/source information is a per-tax-number failure

Status: Accepted

Context: Account-set creation may not find a successful public-manage task with login information for every requested tax number. Aborting the entire batch on the first missing source makes later tax numbers impossible to process and hides which records need manual handling.

Decision:
- If backend source resolution fails for one tax number, return a sanitized `FAILED` result for that tax number.
- Keep the batch running for subsequent tax numbers.
- Surface the missing reason in the result errors, such as no successful backend task or incomplete source fields like `loginMethod`, `password`, or `proxyTaxNo`.

Consequences:
- Operators get a clear manual-handling list instead of a stopped batch.
- No partial customer/account-set write is attempted when required backend source fields are missing.
- Follow-up action is to rerun or fix the backend task, or manually provide the missing login source before retrying.

## 2026-06-08: Account-set backend source lookup uses task categories 2,3

Status: Accepted

Context: Account-set creation resolves enterprise name, region, login method, privacy number, proxy tax number, and password from the public-manage task list. The previous API payload constrained the list with `taskTypeId: "3"`, which narrowed the lookup to the old collection-task type and did not match the requested backend page filter of `国税/取票`.

Decision:
- Query `getTaskListInternal` with `taskCategorys: "2,3"` for account-set backend source lookup.
- Do not send `taskTypeId: "3"` in the task-list request body for this lookup.
- Keep existing client-side collection-task filtering in callers that explicitly need collect tasks for verification or coverage workflows.
- Mirror the same payload rule in the standalone `ydz-create-accountset` skill and the installed local `ydz-create-customer` skill copy.

Consequences:
- Backend login information lookup now matches the manual filter of task categories `国税/取票`.
- Rows from a broader backend category set may be returned, so source resolution continues to prefer rows containing `loginJson` and then picks the latest row by `createdStamp`.
- Verification and coverage callers still filter returned rows by collect-task metadata after the backend response.

## 2026-06-08: Public-manage 403 is not a ready login session

Status: Accepted

Context: During account-set creation, public-manage could show `403 / 无权访问` while still having token values in local or session storage. The old readiness check treated token presence as a usable backend session, which let the workflow continue or wait even though the current account could not access the task list.

Decision:
- Treat public-manage `403 / 无权访问` as not logged in for account-set creation.
- If backend credentials are configured, clear the forbidden page's local/session storage and open a Chanjet login callback to log in again.
- If no backend credentials are configured, fail with a login-readiness message instead of attempting backend task queries.

Consequences:
- The workflow will no longer misclassify an unauthorized backend account as ready.
- Operators must use a backend account with task-list permission.
- Token presence alone is insufficient for backend readiness checks where permission errors are visible.

## 2026-06-08: Project is workbench-first and account-set skill is standalone

Status: Accepted

Context: The repository has accumulated command-line flows for tax verification, Yidaizhang collection, public-manage querying, and account-set creation. The intended product direction is now the local operator workbench, while the automatic-login/account-set creation workflow also needs to be reusable by other agent hosts as a copied skill.

Decision:
- Treat `scripts/ops_console.py` as the default user-facing operational entry.
- Keep command-line scripts as deterministic execution units for the workbench and for developer diagnostics.
- New operational capabilities should be surfaced in the workbench unless they are strictly developer-only.
- Keep `skills/ydz-create-accountset/` as a standalone reusable skill package.
- The account-set skill must contain its own CLI, defaults, API calls, login flow, field mapping, and verification logic.
- The skill must not import this repository's `src.*` or `scripts.*`, call project-only scripts, or rely on project runtime directories and memory files.

Consequences:
- Operators should not need to understand script sequencing for normal work.
- The workbench can evolve as the integrated product without breaking the portable skill.
- Shared business behavior may be mirrored between project code and skill code, but the dependency direction must not point from the skill back into this repository.
- Skill independence is covered by static tests in `skills/ydz-create-accountset/tests/`.

## 2026-06-08: Operator console account-set creation should auto-login by environment

Status: Accepted

Context: The operator console account-set entry wrapped `scripts/ydz_create_customers.py`, but that script only waited for existing Yidaizhang and public-manage browser login state. Fresh workbench sessions failed with "Login session is not ready" even though the selected environment and credentials were known operational inputs.

Decision:
- Keep `scripts/ydz_create_customers.py` as the console's account-set creation entry, but add automatic login before session checks.
- Use the selected environment to choose credential names: `YDZ_INTE_*` for 集测 and `YDZ_PROD_*` for 线上.
- Use `TAX_BACKEND_*` for public-manage login.
- Let the console pass optional temporary credentials through the child process environment only.
- Keep `--skip-auto-login` for debugging an existing browser session and `--env-file` for local uncommitted secret files.
- Do not store passwords in code, docs, command arguments, job records, logs, or result JSON.

Consequences:
- Workbench account-set creation no longer fails immediately just because the Chrome profile lacks a login state.
- 集测 and 线上 account credentials, enterprise selection, default work URL, and accountant defaults remain separated.
- If credentials are not configured and no browser session exists, the script still opens the correct pages and reports the specific missing configuration path instead of silently mixing environments.

## 2026-06-08: Account-set skill should auto-login before asking for passwords

Status: Accepted

Context: The account-set skill previously relied on existing logged-in browser tabs. In fresh agent sessions or Qoder, this caused the agent to ask for passwords or stop at login pages. The integration Yidaizhang login can also land on a `passport.inte.chanjet.com/vm/redirectVM` real-name-auth reminder instead of continuing to `inte-cloud`.

Decision:
- Add a `login` command to the portable account-set CLI.
- Let `doctor --open` and `create` attempt automatic login by default using configured environment variables or `--env-file`.
- Preserve `--skip-auto-login` for debugging existing browser sessions.
- After Yidaizhang authentication, open the configured `work.html` URL directly so integration can reuse the token even if the reminder page blocks redirect.
- Do not embed real passwords in the skill; credentials must come from host-managed secrets, environment variables, or an uncommitted env file.

Consequences:
- Other agents have a deterministic login step instead of reconstructing browser clicks from prose.
- The skill should ask the user only for missing secrets or manual CAPTCHA/MFA/SMS/enterprise-selection steps.
- Live runs still depend on external login prompts and valid configured secrets.

## 2026-06-08: Add account-set creation to the operator console as a separate job type

Status: Accepted

Context: Operators already use `scripts/ops_console.py` as the local workbench for tax collection and verification. Yidaizhang account-set creation is now automated by `scripts/ydz_create_customers.py`, but running it directly still requires command-line use.

Decision:
- Add a `创建账套` form to the operator console.
- Start the existing `scripts/ydz_create_customers.py` script instead of duplicating Yidaizhang API logic in the console.
- Store account-set run inputs, logs, and sanitized JSON results under `output/accountset_runs/<runId>/`.
- Mark these jobs with `jobType=accountset` so the console can show logs and per-tax-number results without invoking batch-only coverage, review, or report actions.
- Keep credentials out of command arguments and result files; the workflow continues to rely on browser login state or host-managed secrets.

Consequences:
- Operators can create account sets from the workbench without opening PowerShell.
- The account-set workflow remains separate from the tax-form verification pipeline.
- Live creation still depends on logged-in Yidaizhang and public-manage browser sessions.

## 2026-06-08: Package YDZ account-set automation as skill plus CLI

Status: Accepted

Context: The Yidaizhang customer/account-set creation workflow is repeatedly used by agents and includes fragile steps: backend source lookup, login-method mapping, customer creation, dynamic tax-info saving, and post-save verification. A prompt-only skill is too easy for another agent to misapply, especially by skipping `taxInfo/saveCustTaxAndBusiInfo` or by asking for passwords unnecessarily.

Decision:
- Package the workflow as `skills/ydz-create-accountset/`, matching the portable skill folder shape used by `chanjet-jira-wiki`.
- Put the deterministic implementation in `scripts/ydz_accountset_cli.py` instead of relying on an agent to reconstruct API calls from prose.
- Keep `SKILL.md` concise and move detailed workflow, field mapping, secret handling, and troubleshooting into `references/`.
- Do not embed real passwords, cookies, tokens, Authorization values, or raw backend `loginJson`; use browser login state and host-managed environment/secret names.
- Require verification of both customer defaults and dynamic tax-info fields before returning `OK`.

Consequences:
- Other agents can run a stable command (`doctor` or `create`) instead of replaying browser clicks.
- The skill can be copied outside this repo because the CLI is self-contained.
- Live runs still depend on logged-in browser sessions and may require manual CAPTCHA/MFA/enterprise selection.

## 2026-06-04：网页读取恢复按可比对网页缺失字段触发

状态：已采纳

背景：为避免各税种网页字段偶发缺失，系统增加了统一低覆盖恢复。但在 `91370102MA7D3P0D2P` 的 `ops_20260604_132337` 现场运行中，增值税附表一、附表二会对大量接口本来无值、不参与比对的映射字段做滚动补读；附表三在 `web_missing=0` 时仍因覆盖率低进入昂贵恢复，导致全流程明显变慢。

选择：
- 网页读取和补读的主集合以 `mappings_for_comparison()` 结果为准，即只围绕最终参与比对的字段。
- 通用滚动重试只在完全没有读到字段时兜底；部分字段已读到时，由外层按真实 `web_missing` 字段做定向补读。
- 低覆盖但没有可比对字段 `web_missing` 时，不再触发多轮恢复；该情况只作为日志信息保留。
- 仍然不允许用接口值反填网页值；真实 `web_missing` 仍会触发渲染等待、滚动补读和最终质量问题。

影响：
- 降低一般纳税人附表一、附表二、附表三等大表在未申报页面的滚动读取耗时。
- 保留网页缺失拦截能力，但避免把“接口无值字段”或“零空等价字段”当成必须补读的网页缺失。
- 已经启动的验证子进程不会自动加载新逻辑，需要重新启动任务后生效。

## 2026-06-04：消费税未申报页底部行按虚拟渲染处理

状态：已采纳

背景：山东消费税未申报页的主表底部 14-17 行并不总是在直接打开页面或单次滚到底后进入 DOM。`2076981675808305083` 首次验证只读到“本期预缴税额 13”，导致 8 个底部字段 web_missing；同类 taskId 在另一次页面渲染中又能读到，说明这是虚拟滚动/懒渲染时机问题。

选择：
- 消费税主表如果首次读取缺少底部哨兵字段，使用多段纵向扫描重读表格行，而不是只读顶部和底部。
- 消费税目标页确认不只依赖左侧菜单 active 状态；当目标内容可见且业务字段数量足够时，可以认为目标页有效。
- 不用接口值反填网页值；缺失字段必须来自税局页面 DOM 重新渲染后的读取结果。

影响：
- 降低山东消费税未申报主表底部行偶发 `web_missing`。
- 保持字段比对证据来源仍为税局页面，不把解析失败包装成成功。
- 后续如其它税种也出现虚拟渲染，应优先增加表单专用滚动扫描，而不是放宽比较规则。

## 2026-06-04：未申报入口失效与已申报查询必须按所属期恢复

状态：已采纳

背景：同一税号 `91370102MA7D3P0D2P` 在同一批次生成两个 taskId：`2076981650034436465` 覆盖增值税/文化事业费并成功，`2076981650034436464` 覆盖消费税。消费税任务没有“成功保存数据-是否是当期”日志，旧逻辑先按未申报入口处理；连续任务刷新税局登录态后，入口可能跳回统一登录页或回到山东税局首页。补登录后如果切到已申报查询，旧逻辑只按表名点击第一条消费税记录，可能打开上一期申报记录，造成大量金额不一致。

选择：
- 未申报入口遇到 `tpass.*#/login` 时，只对当前目标自动重新执行一次 taskId 税局登录并重试。
- 后台申报状态未知且未申报首页没有目标税种入口时，可以切回已申报查询；如果后台明确为未申报，则不自动切回。
- 已申报查询打开申报记录时必须带接口所属期，优先从 `paramJson.period`、`numberData` 或接口所属期字段解析起止日期。
- 找不到目标所属期记录时快速失败，不再用同名表的第一条记录代替。

影响：
- 降低同税号连续 taskId 验证时因旧登录态、旧进税局任务、税局首页回跳导致的假失败。
- 避免消费税、文化事业费等同名表多期记录被误选上一期。
- 后续新增税种若复用已申报查询，也应传入接口所属期；否则多期同名表会有取错记录风险。

## 2026-06-04：附表五多行减免说明必须做列位修正

状态：已采纳

背景：天津任务 `2076614022309347199` 的一般纳税人附表五中，教育费附加和地方教育附加两行实际显示“本期已缴税额”为 `0.00`。税局已申报详情页把减免性质代码和政策依据拆成多行，例如 `0061042802/0099042802` 后跟多行说明和 `|` 分隔符。旧文本解析器把纯数字代码当成一个数值列，又把说明里的 `|` 当成空列，导致后续第 15 列 `bqyjse_*` 错位为空；通用 DOM 兜底也因为该行没有独立栏次单元格而没有接住。

选择：
- 附表五专用解析器在行值数量超过标准 14 列时，优先压掉减免说明文本产生的多余空占位，再按映射列号取值。
- 附表五保留严格行值保护：行名存在但没有任何数值时，仍不自动补 0。
- 稀疏零值行兜底仅用于第 15 列 `bqyjse_*` 本期已缴税额，且必须已有可解析数值作为行存在证据。

影响：
- 可消除政策依据多行文本导致的附表五列位错位和网页假缺失。
- 后续如果其它省份把减免说明渲染成不同结构，应继续在附表五专用解析器中处理，不应把空值零值等价规则扩大到比较器。

## 2026-06-04：`needForceTax` 不默认自动强制进税局

状态：已采纳

背景：EtaxPlugin 在 `taskInfo.needForceTax=true` 时不会自动继续，而是弹出“稍后再试/强制进入”的人工确认。用户点击强制进入后才调用 `/api/client/forceEnterTax`，且会使用返回的新 `taskInfo.taskId` 继续取 cookie。该动作可能结束或抢占已有税务任务。

选择：
- 自动验证默认不调用 `forceEnterTax`。
- 发现 `needForceTax=true` 时快速失败，并在批量/运营展示中归类为“已有进行中的任务，需要人工确认是否强制进入税局”。
- 后续如需要自动强制进入，必须新增显式参数或运营台按钮，并提示会打断/覆盖当前税务任务。

影响：
- 避免自动化在无人确认时抢占税局任务。
- 失败原因会更早、更清晰，不再被包装成字段比对失败或长期 loading。

## 2026-06-04：真实验证默认采用 EtaxPlugin 优先进税局

状态：已采纳

背景：当前批量验证中，河南 `2076981186177811385` 使用 `direct_first` 时，tpass 直开路径在税局首页层面被判定为登录成功，但进入数字账户/申报信息查询后长期停留 `/loading`，后续 `spHandler` 又可能跳回统一登录页。人工用 EtaxPlugin 手动登录不复现，说明插件的清 cookie、结束旧任务、关闭旧税局页、新开 tpass 页和登录后跳转副作用对会话完整性有帮助。

选择：
- `main.py`、`scripts/compare_tax_forms.py`、`scripts/batch_collect_verify.py` 默认改为 `--tax-login-strategy plugin_first`。
- `direct_first` 保留为显式调试选项，不再作为运营台和批量验证默认路径。
- 插件派发前尝试读取 background 旧 taskId 并发送 `setEndCookie`，再派发 `clearTaxCookiesAndOpenNewTab`。
- 登录检测不再把税局 `/loading` 或 `tpass.*#/login` 判定为成功；旧税局页如果是 loading、tpass 或空正文，不再复用。
- 无插件 direct 注入保留为 fallback，并补充 `/loginb/` 读取 `tgtUrl` 后二跳，尽量贴近插件行为。
- 申报查询持续 loading 最终归类为税局登录态或数字账户认证未就绪，不作为字段比对失败。

选择原因：
- 插件路径会先清理旧税局会话和旧进税局任务，能降低跨税号、跨省份、跨任务的脏会话污染。
- 直接打开 tpass URL 速度快，但容易形成“首页可达、数字账户不可用”的半登录状态；批量验证更需要成功率和可恢复性。
- loading 长等通常不是字段问题，提前归类能减少单任务无效等待，并让运营人员知道需要重新进入税局/数字账户。

影响：
- 新发起的真实验证默认比旧 `direct_first` 多一次插件 bridge/新页等待，但能更接近人工插件登录路径。
- 如果 EtaxPlugin bridge 不可用，流程仍会回退到 direct tpass URL。
- 已经启动的旧子进程不会自动切换策略，需要重新发起验证才生效。

## 2026-06-03：个税残保金补齐识别必须支持日志业务特征和 API 字段兜底

状态：已采纳

背景：后台手工查询可以找到满足个税残保金条件的任务，例如 `2076614073849978635`。该任务的执行日志没有直接写“个税/个人所得税”，但包含 `残保金任务返回结果`、`personNum`、`personNumSum`、`monthNumSum`、`amountSum`、`申报月份汇总` 等个税残保金业务特征；最终 task result 中也返回 `sz_cbj.snzzzgrs_cbj` 和 `sz_cbj.snzzzggzze_cbj`。旧规则只识别“个税/个人所得税”文字或任务列表行里的 `snzzz*` 字段，导致该类任务被归为 `CBJ_UNKNOWN`。

选择：
- 残保金子类型识别仍优先读取任务执行日志。
- 汇算清缴标记优先级最高；只要日志出现“数据库未查询到返回数据”或“调用汇算清缴取数接口”，即归为 `CBJ_ANNUAL`。
- 个税残保金日志标记扩展为收入/人数汇总类特征，包括 `personNum`、`personNumSum`、`monthNumSum`、`amountSum`、`申报月份汇总`、`申报人次汇总` 等。
- 日志无法识别时，后台补齐阶段允许拉取 task result 二次确认；若 `sz_cbj` 中同时存在 `snzzzgrs_cbj` 和 `snzzzggzze_cbj`，则作为 `CBJ_PERSONAL` 候选。
- 为避免批量补齐过慢，同一次补齐内缓存 taskId 的日志识别和 API 字段识别结果。

原因：
- 执行日志记录真实业务路径，适合作为残保金个税/汇算清缴子类型的首要判断依据。
- 个税残保金任务并不稳定包含“个税”文字，实际更稳定的是人数、月份、收入汇总字段和 `sz_cbj` 返回字段。
- `snzzz*` 字段适合验证个税残保金是否取数成功，但不应只依赖任务列表行；字段可能只存在于 task result 详情里。

影响：
- 类似 `2076614073849978635` 的任务可以被后台补齐识别为个税残保金。
- 结果页诊断可看到残保金识别来源分布，便于区分日志命中、API 字段命中、API 缺失或未知。
- 如果后台未来调整日志文案，需要继续补充 marker；但汇算清缴优先规则可以降低误把汇算任务归为个税的风险。

## 2026-06-03：申报查询恢复优先直接 URL，进税局任务锁快速失败

状态：已采纳

背景：
湖北补齐任务 `2076614026604654385` 对应税号 `91422801MAKDPNAG9P`。后台任务日志判断为未申报，但税局未申报填报页提示“本属期已申报”，系统需要切回已申报的申报信息查询流程。原恢复路径在门户菜单失败后优先走 `/szc/szzh/sjswszzh/spHandler?cdlj=/szzh/zhcx/sbxx/sbxxcx`，湖北会跳回统一登录页，导致误报为数字账户认证失效。后续重跑又遇到后台提示已有进税局任务 `2076614043783903619` 未完成，新的 getClientJob 被拒绝，说明批量场景还需要明确处理进税局任务锁。

选择：
- 申报查询恢复路径优先使用直接查询 URL `/szzh/zhcx/sbxx/sbxxcx`；spHandler 只作为最后兜底。
- 当前页恢复触发统一登录页时，允许新开税局页再尝试一次查询恢复，避免单页状态污染直接终止。
- getClientJob 返回“之前执行过进税局且暂未完成”时，最多短等待 90 秒；仍未释放则抛出 `PendingTaxLoginJobError`，并解析提示里的占用进税局 taskId。
- 批量汇总和运营台将该错误归一化为中文可处理原因，不展示底层异常栈作为主要原因。

选择原因：
- 已申报查询页在多数省份可以通过直接 URL 到达，spHandler 更容易受数字账户/tpass 中间态影响，不应作为优先路径。
- 外部进税局任务锁不是字段验证失败，长时间等待会拖住批量队列；明确失败并给出占用任务号更利于人工处理。

影响：
- 湖北、四川、山西等从未申报页或 loading 页恢复到申报查询时，会减少跳统一登录页的概率。
- 如果后台进税局任务锁一直存在，验证会更快失败，并在结果页提示占用任务号；需要等待或后台处理后重试。
- 本决策不改变 taskId 验证主入口，也不改变字段比较规则。

## 2026-06-03：未申报税局入口必须支持首页回落恢复

状态：已采纳

背景：山东未申报增值税任务 `2076614043783892312` 曾经打开固定未申报 URL 后短暂进入申报壳页，但点击填表后又被税局带回 `/loginb/` 首页，导致后续左侧菜单选择阶段找不到“主表/附表”，报错 `Undeclared tax menu item was not found`。这说明固定 URL 只能作为首选入口，不能作为已进入目标表单的充分条件。

选择：
- 未申报流程继续优先打开各税种固定入口 URL。
- 表单准备、菜单选择、目标表确认阶段如果发现页面回到税局首页/门户页，自动按目标税种重新点击“填写申报表/我要填表/继续申报”。
- 首页点击必须优先在包含目标税种名称的卡片或行内查找操作按钮；只有页面整体能确认存在目标税种时，才允许兜底点击页面级操作按钮。
- 恢复只重试一次，避免外部页面异常时无限循环。

选择原因：
- 各省税局会因会话、倒计时、异步跳转或门户状态把直达 URL 带回首页。
- 目标税种卡片内点击比全页面找第一个“填写申报表”更安全，能降低跨税种误点概率。
- 一次恢复能覆盖偶发回首页，同时保留明确失败信号，便于继续补充省份差异。

影响：
- 山东未申报增值税、消费税、文化事业建设费等已接入未申报填表页策略的税种，遇到首页回落时会自动二次进入。
- 如果税局首页文案或卡片结构再次变化，结果仍会失败，但失败点会停留在目标入口恢复阶段，便于按截图补充选择器。

## 2026-06-03：残保金后台补齐查询改用 taxId=39

状态：已采纳

背景：运营在 public-manage 后台手动选择“残保金”税种查询时，抓到 `getTaskListInternal` 的真实筛选参数是 `taxId:"39"`。项目此前在后台补齐阶段复用了易代账取数侧/任务结果侧的 `taxTypeId=26/31`，导致残保金候选查询范围不准确，表现为后台明明有残保金任务但补齐阶段查不到或全部归为 `CBJ_UNKNOWN`。

选择：
- 易代账发起取数侧继续保留现有 `26/31`，不改变取数税种选择逻辑。
- 后台补齐查询侧新增独立字段 `backend_tax_ids`，残保金登记为 `taxId=39`。
- `ChanjetAdminTaskQuery` 新增 `tax_id` 参数，调用后台任务列表时发送 `taxId:"39"`，不再把 `39` 当作 `taxTypeId/taxTypeIds`。
- 候选任务查到后，仍通过“残保金任务返回结果”操作日志优先区分个税残保金和汇算清缴残保金；无法判断时标记为残保金类型未知，不自动匹配成功。

原因：
- `taxId` 是后台任务列表筛选维度，`taxTypeId` 是取数任务/结果侧历史维度，二者不能混用。
- 使用 `taxId=39` 可以先正确捞到残保金任务池，再用日志做子类型判定，符合当前后台实际行为。

影响：
- 后台补齐日志和结果页会同时展示 `taxTypeId` 与 `taxId`，残保金补齐应显示 `taxId:39`。
- 旧批次报告不会自动变更，需要重新生成或重跑批次后生效。

## 2026-06-03：后台补齐查询按所属期收敛并缓存登录态/日志判断

状态：已采纳

背景：后台补齐阶段用于从当月成功取数任务中寻找覆盖缺口代表任务。真实批量运行中，缺口会按税种、纳税人性质分组查询后台；如果不带所属期过滤，后台会返回同月其它所属期任务，增加扫描和状态解析成本。同时，同一次补齐阶段每组查询都会重复读取 public-manage token，同一个 taskId 的“是否当期”日志也可能被重复拉取。

选择：
- 补齐查询调用 `getTaskListInternal` 时传入本批次 `period`，只查当前所属期的成功取数任务。
- `ChanjetAdminTaskQuery` 在同一个查询实例内缓存后台 token；遇到 HTTP 401/403 或后台返回 token/authorization 类失败时，强制重读 token 并重试一次。
- `CoverageSupplementPlanner` 在同一次补齐搜索中缓存 `(taskId, taxType)` 的申报状态解析结果，并缓存 taskId 的“成功保存数据-是否是当期”日志判断结果。
- 任务日志读取失败时，该 taskId 的状态降级为 unknown，不让整个补齐搜索中断。

选择原因：
- 所属期过滤能直接减少后台候选行数量，是最稳定的耗时收益。
- token 缓存减少浏览器 storage 读取和页面就绪等待，失效刷新保留可恢复性。
- 日志缓存避免已申报/未申报双目标或跨查询条件时重复请求执行日志。

影响：
- 后台补齐只会使用当前批次所属期的候选任务；如果运营确实要跨所属期补样本，需要后续增加显式参数，而不是默认扩大范围。
- token 刷新仍依赖 public-manage 页面已有登录态；如果后台未登录，仍会明确失败并提示登录。
- 该改动不改变 `main.py --task-id` 真实税局验证入口，也不改变字段比对逻辑。

## 2026-06-03：残保金后台补齐候选改为按操作日志区分子类型

状态：已采纳，替代同日“个税残保金后台补齐必须校验残保金专属字段”的候选筛选规则。

背景：
此前为了避免消费税等任务被误选为个税残保金候选，补齐阶段要求候选结果 JSON 同时包含 `snzzzgrs_cbj` 和 `snzzzggzze_cbj`。实际运行发现该条件过严：部分残保金任务会先进入残保金链路，再通过操作日志说明“数据库未查询到返回数据，调用汇算清缴取数接口查询”，这类任务可能没有提前返回两个字段，但应归为汇算清缴残保金候选。

选择：
- 残保金补齐候选按残保金后台 taxTypeId 查询，`CBJ_PERSONAL` 和 `CBJ_ANNUAL` 均允许查询 `26`、`31`。
- 对候选 taskId 读取任务执行日志，优先用日志类型“残保金任务返回结果”判断子类型。
- 日志显示“数据库未查询到返回数据”或“调用汇算清缴取数接口”时，归为汇算清缴残保金。
- 日志显示个税/个人所得税链路时，归为个税残保金。
- `snzzzgrs_cbj`、`snzzzggzze_cbj` 不再作为候选匹配门槛；它们仍是个税残保金后续验证阶段的字段要求。
- 日志无法判断且字段也无法兜底时，不自动匹配，结果页显示“残保金类型未知”。

原因：
- 操作日志记录的是残保金任务实际执行路径，比单纯检查字段存在性更接近真实业务。
- 字段存在性适合用于验证结果是否成功，不适合提前决定候选是否可用。
- 未知类型不自动匹配，可以继续避免消费税等其他任务误补齐到残保金。

影响：
- `taxTypeId=26` 但日志显示汇算清缴路径的任务，可以进入 `CBJ_ANNUAL:any` 补齐候选。
- 同一残保金 taskId 可能从 26 和 31 查询条件重复返回，规划器会按 `targetKey + taskId` 去重。
- 旧批次 HTML 不会自动变化，需要重新生成或重跑批次后体现新规则。

## 2026-06-03：后台补齐任务只查询税局隐私号登录类型

状态：已采纳
背景：后台补齐用于从历史成功取数任务中选择代表样本。为避免补齐到非目标登录链路产生的任务，用户要求查询条件增加 `loginType:"YSHDL,DLYW-YSHDL"`，即只选择“税局隐私号登录”和“税局隐私号-代理登录”。
选择：
- `src/chanjet_admin/task_query.py` 查询层新增 `login_type` 参数，并按后台字段名写入请求 payload 的 `loginType`。
- `src/coverage/supplement.py` 后台补齐固定传入 `YSHDL,DLYW-YSHDL`。
- 普通按税号解析新发取数 taskId 的查询不默认加该条件，避免改变已有取数解析链路。
选择原因：
- 覆盖补齐是从后台任务池挑代表任务，登录方式属于候选任务筛选条件，应在后台查询阶段约束。
- 将参数能力放在查询层，后续如果运营或其它流程也需要指定登录方式，可以复用同一接口。
影响：
- 后台补齐候选范围会收窄到指定登录方式，减少跨登录链路误补齐。
- 如果后台没有符合这两种登录方式的成功任务，对应覆盖缺口会保持未补齐。

## 2026-06-03：个税残保金后台补齐必须校验残保金专属字段

状态：已采纳
背景：批量后台补齐阶段查询 `CBJ_PERSONAL:any` 时，曾把消费税任务 `2076614043783844600` 作为个税残保金候选。该 taskId 实际已完成消费税验证并通过，但因为残保金目标不区分申报状态，旧规则只要后台任务结果能匹配宽泛的申报状态就可能被误选。
选择：
- 个税残保金后台补齐候选必须在任务结果 JSON 中同时包含 `snzzzgrs_cbj` 和 `snzzzggzze_cbj`。
- 缺少上述字段的后台成功任务不再作为个税残保金候选，即使任务本身是成功状态。
- 批量结果页对该场景展示中文原因：后台任务结果缺少残保金必需字段，不能作为该税种补齐任务。
选择原因：
- 个税残保金验证的成功标准就是后台返回这两个字段；没有字段的任务不能代表残保金取数成功。
- 消费税、增值税等其它税种任务也可能是后台成功任务，必须用目标税种的业务字段做二次约束，避免跨税种误复用。
影响：
- 类似 `2076614043783844600` 的消费税任务不会再被误归到个税残保金覆盖缺口。
- 如果后台存在 taxTypeId 相近但结果 JSON 缺少残保金字段的任务，会在结果页明确显示为“缺少必需字段”，而不是表现为模糊的任务失败。

## 2026-06-02：文化事业建设费 fl_bys 不纳入比对，消费税主表汇总行按关键词和栏次解析

状态：已采纳

背景：
上次验证中，文化事业建设费申报表 `fl_bys` 字段网页显示默认费率 `3.00%`，但接口返回 `0.00`。用户确认该字段不需要和网页做对比，也不纳入最终结果汇总。另一个问题是消费税及附加税费申报表主表中 8 个网页值实际存在，但解析器没有取到，集中在本期应补退税额、城市维护建设税、教育费附加、地方教育附加等汇总行。
本次监控 `2076263995364848762` 时还确认：山东消费税未申报 direct URL 可能短暂回到税局首页；同时消费税主表部分金额在 `input.value` 中，`td.innerText` 为空。

选择：
- `culture_fee_main.fl_bys` 在比较映射阶段直接排除，不生成字段结果，不参与通过率和批量汇总。
- 消费税主表汇总行不再只依赖固定行名开头匹配，改为按业务关键词和栏次号共同识别。
- 汇总行取值从行尾金额列提取，本月数取倒数第二个金额、累计数取最后一个金额；仅本月字段取最后一个金额。
- 更具体的附加税行优先于通用“本期应补退税额”匹配，避免城市维护建设税等行被误归到主税应补退字段。
- 消费税网页表格抽取优先读取单元格内控件值，再读取 `title/innerText`。
- 未申报 direct URL 打开后必须确认目标入口；如果没有落到目标页，则走税局首页申报入口兜底，首页入口点击按步骤等待异步菜单展开。

选择原因：
- `fl_bys` 属于用户明确排除字段，继续比较会制造无效差异。
- 税局页面行名可能包含括号、序号、公式或布局拆分，按关键词和栏次号比固定字符串更稳。
- 页面实际金额通常在行尾，行尾取值能避开栏次号和计算公式。
- 税局表格金额经常由输入框控件渲染，读取单元格文本会误判网页缺失。
- 山东税局未申报页存在跳转回首页的情况，导航必须以目标页确认作为准入条件。

影响：
- 文化事业建设费主表通过率不再受 `fl_bys` 影响。
- 消费税主表应能解析上次缺失的 8 个网页字段。
- 后续新增税种如存在“页面默认值不应比对”的字段，应在比较映射阶段显式排除并记录原因。

## 2026-06-02：后台 taskId 只有 SUCCESS 才能进入验证
状态：已采纳
背景：易代账取数超时后，批量脚本会到后台兜底查询 taskId。本次 `91370102MA7D3P0D2P` 超时后找到 `2076375887846644298`，但后台状态为 `SCHEDULE`，接口尚未生成 `resultJson`，直接进入 `main.py` 后失败为 `API fetch failed: no_resultJson`。
选择：
- `VerifyTaskResolver` 只返回后台状态为 `SUCCESS` 的取数任务。
- `SCHEDULE`、`DOING`、`WAITING`、`TODO`、`FAILURE` 等非成功任务只记录为未就绪，不进入验证。
- 批量状态读取时，如果历史 `resolvedTask(s)` 明确标注某 taskId 非 `SUCCESS`，则不再把它当作可验证 taskId，也不用于跳过重新取数。
原因：
- 项目验证入口依赖后台任务结果 JSON；非成功任务没有稳定结果数据，提前验证只会产生误导性接口失败。
- 取数未完成应展示为“取数未完成/需人工或等待”，而不是字段验证失败。
影响：
- 取数超时兜底不会再把 `SCHEDULE` 任务交给税局验证。
- 如果后台只有未完成任务，批次会保持取数超时/任务未就绪原因，等待后续重新发起或重跑。

## 2026-06-02：申报状态未知先按未申报处理，残保金不参与状态拆分
状态：已采纳
背景：批量结果页中，残保金本身不区分已申报/未申报，但历史报告或后台任务可能带出“未知”状态，导致页面标黄；同时其他税种如果申报状态暂时解析不到，覆盖和补齐链路会把它归为 unknown，既不能覆盖已申报，也不能覆盖未申报。
选择：
- 残保金结果展示固定按业务语义显示：个税残保金为“已取数”，汇算清缴残保金为“已验证”，不再因为原始申报状态 unknown 标黄。
- 非残保金任务如果申报状态未知，先按“未申报”处理和展示。
- 非残保金任务如果申报状态未知，实际税局导航也按“未申报”入口执行，不能只在结果页展示为未申报。
- 覆盖分析中 unknown 申报状态归入未申报覆盖目标。
- 后台补齐候选中，解析状态 unknown 的成功任务允许匹配未申报目标。
原因：
- 残保金验证逻辑不依赖申报状态，继续按 unknown 标黄会误导运营。
- unknown 任务需要有保守兜底路径；按未申报处理可以进入税局未申报页继续验证，后续如发现已申报会由税局页面或字段比对暴露。
影响：
- 结果页不再把残保金 unknown 作为黄色异常。
- 消费税等任务缺少“是否是当期”日志时，会进入未申报填表页策略，而不是错误进入已申报查询页。
- 覆盖缺口会优先减少未申报缺口；已申报缺口仍需要明确已申报任务覆盖。

## 2026-06-02：山东文化事业建设费未申报页使用专用入口并支持 iframe 表单
状态：已采纳
背景：`2076264446332455641` 的山东文化事业建设费任务被判定为未申报。山东税局文化事业建设费未申报流程不是增值税 `lzsfjssb` 页面，而是 `sdsfsgjssb/#/yyzx/whsyjsf/tb/yssb`；进入后还需要先点击“继续申报”，再点击“我要填表”。点击后真实申报表在内嵌 iframe `whsyjsf_BDA0610334ggy.html` 中，主页面只显示标题、倒计时和提交按钮。
选择：
- 对山东文化事业建设费固化到已验证的未申报入口 URL，并从 API `numberData` 读取所属期生成 `SssqQ/SssqZ`。
- 保留首页逐步点击作为兜底，但优先使用专用 URL，减少页面菜单变更和人工路径的不确定性。
- 未申报页目标确认和网页字段提取支持主页面加子 iframe 自动选择，优先选择真实表单 iframe，而不是报表列表 iframe。
- 文化费表格字段读取优先取 `input/select/textarea.value`，并按栏次后的本月/本年可取值单元格解析。
原因：
- 专用 URL 能稳定绕过首页多层菜单，路径短且参数清晰；逐步点击只作为 URL 不可用时的兜底。
- 文化费页面表单在 iframe 内，继续只读主页面会误判“菜单找不到”或得到 0 覆盖率。
- 山东页面公式列和历史 Excel 行名不完全一致，文化费金额定位应以栏次和控件值为主。
影响：
- 山东文化事业建设费未申报任务可以完成“继续申报 -> 我要填表 -> iframe 表单解析”链路。
- 对 iframe 表单的选择逻辑也可复用于后续类似省份/税种，但仍保留目标表单确认，避免错表截图和错表解析。
- 当前真实验证中 `fl_bys` 已能解析出网页值 `3.00%`，若接口返回 `0.00` 会作为真实字段差异输出。

## 2026-06-02：非残保金税种未申报验证复用同一填表页策略

状态：已采纳

背景：此前代码只允许增值税一般纳税人进入未申报税局页面，增值税小规模、企业所得税 A 类、文化事业建设费、消费税在后台日志判断为未申报时会快速失败。最新业务确认：这些税种的未申报处理逻辑与增值税一般纳税人一致，均可进入税局未申报填表页，再按目标表单切换并抽取网页字段。

选择：
- 非残保金的当前支持税种都允许走未申报填表页策略。
- 为增值税小规模、企业所得税 A 类、文化事业建设费、消费税补齐未申报页表单菜单关键字。
- 提取网页数据和生成 PDF 前，所有未申报税种都必须确认目标表单，而不是只对增值税一般纳税人确认。

原因：
- 覆盖矩阵已经要求这些税种区分已申报/未申报，验证入口也应一致。
- 继续按税种阻断会导致后台补齐找到未申报代表任务后仍无法验证。
- 目标表单确认是防止截错表、解析错表的核心保护，应适用于所有未申报税种。

影响：
- 这些税种未申报任务不再因“策略未实现”直接失败，会尝试进入同一未申报填表页并选择对应表单。
- 如果某省某税种真实入口 URL 或菜单结构不同，流程会在目标表单确认阶段明确失败并输出可见菜单或页面片段。

## 2026-06-01：山东任务需要按税号修正青岛独立税局域名，未申报页必须确认目标表

状态：已采纳

背景：本轮山东批次暴露两个独立问题：青岛税号 `91370203334145023C` 的后台任务省份返回 `shandong`，但青岛使用独立的 `qingdao` tpass/etax 域名，继续按山东域名会卡在 `/loading`；山东济南未申报增值税任务已经进入未申报页面，但页面按钮和菜单结构与既有假设不一致，只按固定“我要填表”按钮识别会误判打不开表。

选择：
- 当任务省份为 `shandong` 且税号登记机关代码为 `3702` 时，在登录 URL、redirect、tgtUrl 和 cookie payload 中统一改为 `qingdao`。
- 登录成功后，后续税局导航使用 `TaskLoginInfo.province` 的修正结果，而不是继续使用任务 API 原始省份。
- 未申报增值税页先识别是否已进入申报表视图，再兼容更多填报入口文案和菜单组件；提取或截图前必须确认目标表已选中且正文匹配目标表，否则立即失败并输出页面片段。

原因：
- 青岛是山东省内计划单列税局，电子税局域名和统一登录域名独立，不能只依赖后台返回的 `province` 字段。
- 未申报页属于真实税局操作页，页面文案和组件变化频率高，单一按钮文案会导致误判。
- 目标表确认前禁止继续提取，可以阻断“停在主表却截成附表”的错误证据。

影响：
- 青岛税号会自动走 `tpass.qingdao.chinatax.gov.cn` 和 `etax.qingdao.chinatax.gov.cn`。
- 山东未申报增值税页面失败时会给出更直接的页面文本片段，便于后续按真实 DOM 补充选择器。
- 其它山东非青岛税号仍按 `shandong` 处理，不改变原路径。

## 2026-06-01：未申报增值税附表证据必须确认目标表，附表五不适用零值行可补零

状态：已采纳

背景：四川未申报增值税任务中，左侧菜单父级节点包含全部附表名称，自动化按文本匹配时可能点到父级容器，页面仍停留在主表但后续继续截图和解析，造成附表覆盖率为 0 或截图错误。附表五还存在动态表单：不适用的“地方教育附加”行、留抵扣除/投资额区块可能完全不渲染，但接口返回对应字段为 `0.00`。

选择：
- 未申报增值税附表切换只选择叶子菜单项，不把父级折叠菜单作为候选。
- 提取网页数据和 PDF 前必须确认当前激活菜单和正文都匹配目标表，否则直接失败。
- 附表五解析时保留减免性质代码占位列，保证金额列不偏移。
- 附表五只在已解析到有效网格行、且页面完全没有对应行/区块标签时，把不适用字段补为 `0.00`；如果标签存在但值未解析到，继续报解析问题。

原因：
- 目标表确认比事后靠覆盖率判断更可靠，可以直接阻断“截错表还继续通过”的情况。
- 附表五动态隐藏不适用零值行是税局页面表现，不应被统计为网页解析失败。
- 补零必须有限制条件，避免把真实页面结构变化或解析失败误判为通过。

影响：
- 未申报增值税附表切换失败会更早暴露为流程错误。
- 附表五在不适用零值场景下覆盖率和通过率更接近真实业务含义。

## 2026-05-29：覆盖目标允许按税种选择

状态：已采纳

背景：运营人员并非每次都需要覆盖项目支持的全部税种。如果固定按全量税种生成覆盖矩阵和后台补齐，会在结果页展示无关缺口，并增加后台查询时间。

选择：
- 本地操作台提供“需要覆盖税种”勾选项，默认全选。
- 批量脚本新增 `--coverage-tax-types` 参数，选择结果写入批次 `state.json`。
- 覆盖矩阵、覆盖缺口、后台补齐和汇总页按本批次选择的税种生成。
- 取数任务的税种列表暂不跟随覆盖勾选项变化，仍按项目默认自动取数税种执行。

原因：
- 覆盖目标属于本次验收范围，应该由运营人员按批次配置。
- 把选择写入 `state.json`，可以保证刷新操作台、重新生成汇总、续跑时仍使用同一批次的覆盖范围。
- 取数税种和覆盖税种不是完全等价关系，直接联动可能误跳过后续验证需要的数据，因此先只控制覆盖分析和补齐。

影响：
- 未勾选的税种不会计入覆盖缺口，也不会触发后台代表任务补齐。
- 批量命令可通过 `--coverage-tax-types VAT_GENERAL,CONSUMPTION_TAX` 指定覆盖税种。

## 2026-05-29：消费税取数同时兼容 taxTypeId 29 和 30

状态：已采纳

背景：批量运行中 `91310104MABT0TRL66` 的易代账明细返回消费税 `taxTypeId=30`，但项目默认自动取数列表只包含 `29`，导致自动批次没有发出该消费税取数项，后续也无法在批次查询窗口内解析到新 taskId。

选择：
- 易代账自动取数默认税种列表新增 `30`。
- 覆盖补齐的消费税后台税种 ID 保留 `29`，同时新增 `30`。

原因：
- 当前真实消费税账号已确认返回 `taxTypeId=30`，必须纳入自动取数请求。
- 历史项目决策和历史任务中消费税曾使用 `29`，直接删除会降低旧任务补齐兼容性。

影响：
- 后续自动批量发取数时会包含消费税 ID `30`，减少“易代账显示已取数但后台没有新 taskId”的情况。
- 覆盖补齐阶段会对消费税多查一个后台税种 ID，耗时略有增加，但只影响消费税缺口查询。

本文件记录重要架构决策、业务规则和取舍原因。新增外部接口、登录策略、覆盖规则、数据结构时必须更新。

## 2026-05-29：字段比对以接口实际返回字段为准

状态：已采纳

背景：税局网页、PDF、Excel 映射通常覆盖整张申报表，但后台接口可能只返回本次取数真正保存的字段。如果把接口未返回的字段都统计为“接口缺失”，会把非本次取数范围的问题混入差异结果，影响运营判断。增值税一般纳税人主表中，`qcwjse_ybxm_bnlj` 对应“期初未缴税额(多缴为负数)”行“本年累计”列，应直接与接口字段同名值对比，不应套用其他累计字段的差值规则；`qmldse_*` 对应“期末留抵税额”栏次 `20=17-18`，网页侧应使用“上期留抵税额”栏次 `13` 的同列值替换后再与接口比对。

选择：
- 所有税种、所有表单在比对前都按接口结果 key 过滤映射字段，只保留接口实际返回的字段。
- 接口未返回的字段不进入总字段数、不产生 `api_missing`，也不进入批量差异统计。
- 接口返回空值但 key 存在时仍参与比对；只有接口完全未返回的字段会被忽略。
- `qcwjse_ybxm_bnlj` 网页值直接取同名位置，不再减去 `qcwjse_ybxm_bys`。
- `qmwjse_ybxm_bnlj` 对应主表 32 行“期末未缴税额(多缴为负数)”本年累计，网页侧必须按同一行本年累计减本月数计算，即使结果为负数也参与比对。
- `qmldse_ybxm_bys`、`qmldse_ybxm_bnlj`、`qmldse_jzjtxm_bys`、`qmldse_jzjtxm_bnlj` 的网页值分别取 `sqldse_*` 同列值；其中 `qmldse_ybxm_bnlj` 也不再做本月数扣减。

原因：
- 验证目标应以接口实际返回字段为准，避免网页存在但接口未取的字段造成误报。
- 全局规则比单表特例更容易维护，后续新增税种时不会重复遇到同类问题。
- `qcwjse_ybxm_bnlj` 是独立单元格，不属于“网页累计值需要换算成本年累计差额”的场景。
- `qmwjse_ybxm_bnlj` 属于期末未缴税额本年累计换算场景，不能因为累计值小于本月数就跳过扣减。
- 主表期末留抵税额网页栏次是计算行，当前验证要求以栏次 13 的上期留抵税额作为网页侧对比值。

影响：
- 各表单报告中的总字段数会减少到接口实际返回字段数。
- 批量汇总页不再因为网页有值但接口未返回而展示大量接口缺失。
- 如果未来接口补齐字段，新增返回字段会自动进入比对范围。

## 2026-05-28：耗时优化必须保留原流程兜底

状态：已采纳

背景：批量验证耗时主要来自三处：后台覆盖补齐重复查询、数字账户固定等待、同一申报详情内附表切换时反复返回申报查询页。直接删除等待或强行复用页面会提高误判风险。

选择：
- 后台补齐按 `backendTaxTypeId` 合并查询，一次查询结果复用给同税种 ID 的多个覆盖缺口。
- 数字账户等待改为状态驱动，检测申报查询页或数字账户页面可用后立即继续，但保留原超时和恢复路径。
- 同一申报详情页内只在“同税种、同查询关键字、连续详情页目标”时优先切换附表；切换失败自动回退到申报查询页。

原因：
- 这三项优化都减少重复等待或重复请求，不改变比对数据来源。
- 保留 fallback 可以避免省份页面差异导致流程中断。

影响：
- 真实链路日志中应能看到数字账户可用耗时和更少的“returning to declaration query”。
- 新增税种时，如同一详情页包含多张附表，可复用 `can_switch_detail_form_between()` 的规则，必要时扩展分组判断。

## 2026-05-28：取数失败和覆盖复用必须按“支持税种目标”判断

状态：已采纳

背景：批量链路中，易代账可能返回社会保险费失败；后台也可能存在同一税号、同一期间但 taxItemId 不同的取数任务。如果把这些外部状态直接当作整条链路结果，会出现两类误判：社会保险费失败阻断后续验证，或 taxItemId=26 的个税残保金任务被复用为年度汇算清缴残保金。

选择：
- 社会保险费不属于当前自动取数验证目标，失败只记录到 `ignoredTaxItems`，不设置 `manualRequired`。
- 没有自动选出项目支持表单时，验证结果必须是“未覆盖/跳过”，不能算成功。
- 覆盖目标拆分为 `CBJ_PERSONAL` 和 `CBJ_ANNUAL`，分别对应 taxItemId=26 和 taxItemId=31。
- 后台补齐任务必须记录查询诊断，包括后台 taxTypeId、查询数量、申报状态解析分布和未命中原因。

原因：
- 批量验证的成功标准必须以项目支持的税种和申报状态为准，而不是以后台任务是否返回任意成功 taskId 为准。
- 外部系统返回非验证目标的失败，不应影响后续可验证税种。
- 年度残保金和个税残保金验证路径不同，合并覆盖会造成错误复用。

影响：
- 批量汇总页会展示未覆盖目标和补齐失败原因。
- 后续新增税种时，必须同步更新覆盖注册表、后台 taxTypeId 和申报状态解析策略。

## 2026-05-08：统一 `main.py` 作为用户入口

状态：已采纳

背景：
项目曾同时存在 `main.py` 框架管线和多个真实 taskId 脚本。真实流程更接近生产，但多入口会导致用户和维护者混乱。

选择：

- 用户推荐入口统一为 `python main.py --task-id <taskId>`。
- 真实 taskId 流程复用 `scripts/compare_tax_forms.py::run_compare()`。
- 旧脚本只保留为兼容包装或调试工具。

原因：

- 降低使用成本。
- 避免真实逻辑分散到多条主线。
- 允许后续逐步把稳定逻辑下沉到 `src/`。

影响：

- 新功能应接入统一入口或批量脚本。
- 不新增第二套生产验证流程。

## 2026-05-08：保留 `--skip-browser` 作为诊断模式

状态：已采纳

背景：
完整验证依赖浏览器、易代账登录、税局登录、EtaxPlugin、验证码和外部页面状态。很多失败不是接口或映射问题。

选择：

```powershell
python main.py --task-id <taskId> --skip-browser --log-level INFO
```

原因：

- 快速确认 taskId、接口、自动选表、映射覆盖。
- 将外部登录阻塞与数据问题分开。

影响：

- 涉及真实 taskId 问题时，优先先跑 `--skip-browser`。

## 2026-05-09：完整税局验证依赖 Chrome CDP 与 EtaxPlugin

状态：已采纳

背景：
电子税局和畅捷通进税局流程依赖浏览器扩展、持久 profile 和真实登录态。

选择：

- 默认使用 Chrome CDP 端口 `9222`。
- 默认插件路径 `C:\Users\Administrator\Downloads\EtaxPlugin`。
- 尽量复用现有登录态，必要时通过任务 cookie 进税局。

原因：

- 更接近人工操作路径。
- 支持 EtaxPlugin。
- 可在异常时由人工接管页面。

影响：

- 真实 E2E 不作为默认自动测试。
- 运营台需要展示浏览器连接和登录阻塞原因。

## 2026-05-12：残保金分两类验证

状态：已采纳

背景：
残保金存在个税侧取数和汇算清缴侧取数，两者验证路径不同。

选择：

- 个税残保金：取数后只检查后台结果字段 `snzzzgrs_cbj` 和 `snzzzggzze_cbj` 是否存在。
- 汇算清缴残保金：发取数任务后登录税局，查询年度企业所得税 A 类申报表，取：
  - A105050 职工薪酬支出及纳税调整明细表第 1 行第 5 列工资薪金支出税收金额。
  - A000000 企业所得税年度纳税申报基础信息表 104 从业人数。
  - 与后台字段 `snzzzggzze_cbj`、`snzzzgrs_cbj` 对比。

原因：

- 个税残保金不需要真实进税局即可判断后台取数是否成功。
- 汇算清缴残保金需要税局申报表作为可信来源。

影响：

- CBJ 验证逻辑独立在 `src/cbj/`。
- 批量脚本自动识别 CBJ 并走专用验证。

## 2026-05-26：建立运营工作台而不是要求运营人员写命令

状态：已采纳

背景：
后续会批量处理多个税号，运营人员没有开发经验。单靠 PowerShell 命令容易填错参数、难以观察进度。

选择：

- 新增 `scripts/ops_console.py` 本地工作台。
- 工作台只包装 `scripts/batch_collect_verify.py`，不新增第二套验证逻辑。
- 易代账账号密码只通过当前子进程环境变量传递，不写入命令展示或任务记录。

原因：

- 保留统一生产流程。
- 降低操作成本。
- 方便监控、重试、跳过、导出问题清单。

影响：

- 批量脚本必须持续输出 `ops_status.json` 和可读失败原因。
- 运营台应优先展示直接可处理原因。

## 2026-05-26：批量结果按差异明细而非统计优先展示

状态：已采纳

背景：
用户更关心哪个税号、哪个税种、哪个表、哪个字段不一致，而不是整体统计排行榜。

选择：

- 批量 HTML 删除低价值统计模块。
- 差异明细按表单分组，同时按账户分组。
- 需处理原因只展示最直接原因。

原因：

- 运营处理需要直达问题，不需要先看统计。

影响：

- `batch_problem_details.csv` 和运营台问题处理视图成为主要工作对象。

## 2026-05-26：税种覆盖使用“项目支持税种 × 已申报/未申报”矩阵

状态：已采纳

背景：
用户输入的一批税号可能无法覆盖项目当前支持的所有税种和申报状态。后续需要自动从后台找成功任务补齐代表样本。

选择：

- `src/coverage/registry.py` 登记当前支持税种。
- 每个税种默认覆盖已申报和未申报。
- 覆盖分析输出 `coverage_status.json` 和 `coverage_matrix.csv`。
- 后台补齐只需为每个缺口找一个代表任务。

原因：

- 让验证覆盖缺口可视化。
- 不要求用户手工准备所有代表税号。
- 后续新增税种只需更新注册表和对应验证策略。

影响：

- 新增税种必须同步更新覆盖注册表、测试和文档。
- 未申报状态仍需真实进入税局验证，页面策略需逐税种补齐。

## 2026-05-26：增值税申报状态优先用任务执行日志判定

状态：已采纳

背景：
后台任务结果 JSON 中申报状态字段不稳定，但任务执行日志有明确标记。

选择：

增值税取数任务中，读取任务执行日志：

```text
logType = 成功保存数据-是否是当期
logInfo = true  -> 已申报
logInfo = false -> 未申报
```

原因：

- 字段语义明确。
- 已用 taskId `2071433368332666061` 验证，`logInfo=true` 判定为已申报。
- 可复用于覆盖补齐和真实比较流程。

影响：

- 相关封装位于 `src/chanjet_admin/task_execution_log.py`。
- `scripts/compare_tax_forms.py` 和 `src/coverage/supplement.py` 复用同一规则。

## 2026-05-28：消费税按两张表接入真实验证

状态：已采纳

背景：
消费税任务 `2068825812082982843` 的接口结果包含 `sz_xfs`，其中两张表分别为 `xfszb_qc` 和 `xfsfb1_qc`。本次需求要求不用重新发取数任务，直接用现有 taskId 登录税局验证。

选择：
- 在 `scripts/compare_tax_forms.py` 增加 `CONSUMPTION_TAX` 的两个 `CompareTarget`：
  - `consumption_tax_main` -> `sz_xfs.xfszb_qc`
  - `consumption_tax_surcharge` -> `sz_xfs.xfsfb1_qc`
- Excel 映射沿用用户提供的两份消费税 ID 工作簿。
- 消费税网页取数使用专用解析器，而不是完全依赖通用表格列位。
- 覆盖注册表增加消费税，后台税种 ID 使用易代账税种 ID `29`。

原因：
- 消费税主表商品行没有稳定栏次号，通用解析会漏取商品行字段。
- 消费税附加税费计算表在网页中比 Excel 表头多出“征收品目”和“小微减免性质”列，必须按真实网页列位解析。
- 税局“减征比例”显示为 `50.00`，接口字段为 `0.5`，需要按百分比语义折算。

影响：
- `--targets auto` 能在接口返回 `sz_xfs` 时自动选择消费税两张表。
- 单 taskId 报告会输出消费税 JSON、HTML、PDF 和接口回填 Excel。
- 覆盖矩阵新增消费税已申报/未申报两个目标。

后续：
- 消费税未申报场景入口尚未补齐。
- 如果后续消费税 Excel 文件名变更，建议迁移到 `mappings/id_workbooks/` 下稳定命名，避免依赖微信文件目录。

## 2026-05-28：后台任务接口增加 curl 兜底

状态：已采纳

背景：
本机访问 `data-task-management.chanapp.chanjet.com` 时，Python `requests` 持续出现 `SSLEOFError / UNEXPECTED_EOF_WHILE_READING`，但 `curl` 可以正常返回 JSON。

选择：
- `src/api/api_client.py` 在 requests 触发 SSL EOF 时自动用 `curl` 兜底读取 taskId 数据。
- `src/login/task_login_flow.py` 的 `getClientJob` requests fallback 也增加同类 curl 兜底。

原因：
- 该问题属于本机 TLS/网络栈和目标服务兼容性问题，不应阻断真实验证流程。
- curl 兜底只在 requests 失败时触发，不改变业务返回结构。

影响：
- 遇到同类 SSL EOF 时，完整验证可继续拿到接口数据和内部 taskId。
- 仍保留 requests 作为首选路径，便于常规环境下保持原行为。

后续：
- 如果后续所有环境都稳定出现 requests SSL EOF，可以考虑将该域名默认切换为 curl 或统一封装网络客户端。
## 2026-05-28：批量状态持久化不得中断验证主流程

状态：已采纳

背景：
批量验证过程中曾在写入 `state.json` 时触发 Windows `OSError: [Errno 22] Invalid argument`，导致后续税号未继续验证。状态文件是监控和运营展示需要，但不应成为验证主流程的单点故障。

选择：
- 批量状态 JSON 使用临时文件写入、JSON 校验、原子替换。
- 状态、汇总、运营状态分开写入；写入失败只记录警告，不抛出到主流程。
- 单个任务的“需处理原因”优先由结构化比对结果生成，避免从浏览器关闭日志推断原因。

原因：
- 批量链路的首要要求是尽量跑完所有税号。
- 状态文件可重试、可重建，不能因为偶发文件锁或杀毒扫描导致整批失败。
- 运营处理需要直接原因，而不是底层浏览器生命周期日志。

影响：
- `scripts/batch_collect_verify.py` 的状态写入具备更强容错性。
- 后续新增运营状态文件时应复用同一安全写入策略。

## 2026-05-28：同批次 taskId 不重复验证，税局页复用必须匹配税号

状态：已采纳

背景：
批量验证中出现过两个风险：
- 启用 `--rerun-verified` 后，同一个 `taskId` 会在同一批次内被多次验证，浪费时间并反复打开税局页面。
- 同省不同税号连续验证时，已有税局页面可能被复用到另一个税号，导致网页数据和接口数据不属于同一纳税人。

选择：
- 批量运行期间维护本次已验证 `taskId` 集合，单批次内同一个 `taskId` 只允许执行一次验证。
- `--rerun-verified` 只表示允许重跑历史批次中已完成的任务，不允许突破本批次去重规则。
- 税局页面复用必须满足“省份匹配 + 页面正文包含当前任务税号”；不能确认时重新走 taskId 登录。

原因：
- `taskId` 是一次取数任务的唯一验证对象，同一批次重复验证没有新增覆盖价值。
- 税局页面状态强依赖当前登录纳税人，跨税号复用属于高风险优化，应以数据正确性优先。

影响：
- 批量验证耗时减少，结果页中重复 `taskId` 会显示跳过原因。
- 税局页面复用更保守，部分场景会重新登录，速度可能略慢，但避免跨税号串页。

后续：
- 如果需要对失败的同一 `taskId` 做自动重试，应新增明确的最大重试次数和失败类型白名单，不应复用 `--rerun-verified` 语义。

## 2026-05-29：税局登录优先使用无插件 tpass cookie 注入

状态：已采纳

背景：
完整验证原来依赖 EtaxPlugin content script 在 tpass 页面解析 `cookie=` 参数，并写入税局 cookie/localStorage。用户希望降低对插件的硬依赖，但仍保留现有 `getClientJob`、`getTaskCookie` 和真实 taskId 主流程。

选择：
- `TaskLoginFlow` 在浏览器上下文中注册 document-start 初始化脚本，复刻 EtaxPlugin 的 `cont-insert-cookie-tpass-login.js` 行为。
- `getTaskCookie` 浏览器内请求失败时，使用 Python requests 直接请求调度接口兜底。
- 默认 `direct_first` 继续直接打开 tpass 登录 URL；无插件脚本负责解析 `cookie=`、写 cookie/localStorage、设置 `etaxplgin` 标识和倒计时 cookie。
- EtaxPlugin 的 `clearTaxCookiesAndOpenNewTab` 事件仅作为打开新标签页、清 cookie 的 fallback。
- Chrome 自动启动时，`--plugin-path` 传空、`none`、`disabled`、`false` 或 `0` 可不加载插件。

原因：
- 保留畅捷通任务登录材料来源，不新增第二套生产验证流程。
- 去掉 tpass cookie 注入对插件 content script 的依赖，降低无影云电脑插件安装和加载失败带来的阻塞。
- 保留插件 fallback，便于省份差异或真实环境异常时回退。

影响：
- 已登录畅捷通后台且能访问 `getTaskCookie` 时，可以连接未加载 EtaxPlugin 的 Chrome 进入税局。
- 若真实税局后续依赖插件的其他功能，例如会话续期浮窗、特殊省份后台跳转，仍可能需要插件或人工兜底。

## 2026-05-29：后台补齐排除 mock 任务且当期判断不依赖日志编号

状态：已采纳

背景：覆盖补齐需要从后台成功取数任务中挑选真实代表任务。后台任务列表存在 mock 任务时会污染覆盖样本；同时任务执行日志中“成功保存数据-是否是当期”的日志编号不稳定，不一定是 `sz_zzs`。

选择：
- 后台补齐和任务列表查询默认带 `mockFlag=0`，排除 mock 任务。
- 当期判断只匹配日志类型 `成功保存数据-是否是当期`，不再过滤 `lsn`。
- 多条同类型日志存在时，仍按 `createdStamp` 取最新一条。

原因：
- 覆盖补齐应使用真实取数任务，避免 mock 数据进入验证链路。
- 日志类型的业务语义更稳定，日志编号属于税种或实现细节，不适合作为强过滤条件。

影响：
- `src/chanjet_admin/task_query.py` 查询 payload 默认包含 `mockFlag=0`。
- `src/chanjet_admin/task_execution_log.py`、`scripts/compare_tax_forms.py`、`src/coverage/supplement.py` 统一使用只按日志类型判断当期的规则。
- 该字段已通过已登录后台页面抓包确认：选择“是否mock：否”时，`getTaskListInternal` 请求 payload 为 `mockFlag: 0`。
## 2026-05-29：申报查询深链回到 tpass 时快速失败

状态：已采纳

背景：
批量验证中，上海消费税任务已完成取数并成功进入税局首页，但进入申报信息查询时持续停留在 `/loading`。进一步日志显示数字账户申报查询 handler 已跳回 tpass 统一登录页，说明当前税局登录态或数字账户认证不可用于申报查询。原逻辑仍按慢加载处理，导致单个税号耗满 `--tax-timeout 600`。

选择：
- 当申报查询 handler 跳回 tpass 统一登录页时，判定为税局登录态/数字账户认证失效。
- 该场景直接失败当前税号并返回明确人工处理原因，不再继续多轮直接查询和数字账户重试。
- 批量汇总和运营台将该异常归类为“税局登录态或数字账户认证已失效”。

选择原因：
- tpass 统一登录页表示当前深链不具备有效认证，继续等待 `/loading` 不能提升成功率。
- 批量流程更需要快速跳过外部登录阻塞，继续验证后续税号。
- 明确原因比底层 `Could not navigate to declaration query page` 更便于运营处理。

影响：
- 同类卡点预计从接近 10 分钟缩短到恢复路径确认失败后即结束。
- 可能牺牲少量“继续等可能偶发恢复”的情况，但避免整批被单个税局会话拖慢。
## 2026-06-01：易代账 invalid signature 自动刷新一次登录态

状态：已采纳

背景：
批量发起取数时，浏览器仍停留在易代账云应用页，但其 `iframeToken` / `ciaToken` 已被服务端判定为 `invalid signature`，导致所有税号在 `getBatchList` 阶段同时失败。该问题属于易代账会话签名失效，不是单个税号或后台 taskId 查询问题。

选择：
- 只清理易代账官网和易代账云应用页面的 token/signature storage，不清理 public-manage 后台登录态。
- 批量发起阶段首次遇到 `invalid signature` 时，自动重新进入易代账、必要时使用运行时凭据登录并选择企业，然后重试当前税号一次。
- 如果刷新后仍失败，按“易代账登录签名已失效，需要重新登录易代账后再发起取数”输出人工处理原因。

选择原因：
- 同一 JWT 同时导致整批税号失败，说明应按会话级问题处理，而不是逐税号失败。
- 保留后台登录态可以继续查询 taskId、执行覆盖补齐和查看任务日志。
- 只重试一次可以恢复常见登录态过期场景，同时避免验证码、权限异常等外部阻塞导致无限重试。

影响：
- 批量取数对易代账 token 过期更鲁棒。
- 如果登录页出现验证码、二次确认、账号权限变化或企业选择变化，仍需人工处理。
## 2026-06-01：覆盖补齐的当期日志判断扩展到企业所得税等申报税种

状态：已采纳

背景：
后台覆盖补齐查询企业所得税成功取数任务时，部分任务结果 JSON 不包含稳定的申报状态字段，但任务执行日志存在 `成功保存数据-是否是当期`。例如 taskId `2075110904014780643` 的该日志结果为 `false`，应判定为企业所得税未申报。

选择：
- 覆盖补齐先从任务结果 JSON 解析申报状态。
- 若解析不到状态，则对增值税、企业所得税、文化事业建设费、消费税、汇算清缴残保金等需要申报状态的税种，继续读取任务执行日志 `成功保存数据-是否是当期`。
- `logInfo=true` 判定为已申报，`logInfo=false` 判定为未申报。
- 个税残保金仍不使用该日志兜底，避免把非申报状态任务误归类。

选择原因：
- 日志类型的业务含义比任务结果 JSON 字段更稳定，且不依赖日志编号。
- 企业所得税等税种与增值税一样需要覆盖已申报/未申报状态，不能只对增值税使用日志兜底。

影响：
- 后续后台补齐能识别企业所得税未申报代表任务。
- 如果某税种没有该日志，仍保持 unknown，不会强行复用。
## 2026-06-01：后台补齐查询对税种做客户端强校验和翻页扫描

状态：已采纳

背景：
`getTaskListInternal` 在当前后台接口表现中不会可靠按 `taxTypeId/taxTypeIds` 过滤；实际测试发现传入不同税种 ID 仍可能返回同一批增值税任务。这样会导致企业所得税、文化事业建设费、消费税等覆盖缺口误用增值税任务。

选择：
- 仍向后台接口传入税种参数，保留未来后端支持过滤时的兼容性。
- 对返回结果再读取 `taskTaxRelVOList.tTaxTypeId`、`taxTypeIds` 等字段做客户端强校验，只有真实包含目标税种 ID 的任务才可作为候选。
- 当指定税种 ID 时，允许翻页扫描后台列表，覆盖补齐默认单页大小调整为 500，减少有效任务在深页时被漏掉。
- 如果翻页扫描后仍无真实税种匹配任务，保持缺口，不再复用无关任务。

选择原因：
- 数据正确性优先于查询速度，不能用接口未过滤的任务补齐覆盖缺口。
- 客户端校验使用后台任务明细里稳定的税种关联字段，比依赖请求过滤字段更可靠。

影响：
- 后台补齐耗时会增加，尤其是税种候选很靠后的场景。
- 能避免多个不同税种缺口误匹配到同一个无关 taskId。
## 2026-06-01：增值税覆盖补齐使用企业性质区分一般人与小规模

状态：已采纳

背景：后台任务列表中增值税统一使用税种 ID `1`，仅靠 `taxTypeId=1` 无法区分“一般纳税人”和“小规模纳税人”。此前补齐逻辑只能从任务结果 JSON、表单名或字段名推断，很多后台任务行没有这些信息，导致增值税候选被统计为 `unknown`，无法补齐。

选择：
- 通过后台 `getTaskListInternal` 抓包确认查询字段为 `taxPayerType`。
- 一般纳税人使用 `taxPayerType=NORMAL_TAXPAYER`。
- 小规模纳税人使用 `taxPayerType=SMALL_TAXPAYER`。
- 覆盖补齐仍保留 `taxTypeId=1/taxTypeIds=["1"]` 入参，同时在客户端继续校验 `taskTaxRelVOList.tTaxTypeId` 和 `taxPayerType`。
- 补齐查询按“后台税种 ID + 企业性质”合并，同一类目标的已申报/未申报共用一次查询，不同企业性质分开查询。

原因：
- `taxPayerType` 是后台任务行中的稳定结构化字段，比从 JSON 文本或表单名猜测更可靠。
- 后台当前对部分筛选项存在不完全过滤现象，客户端二次校验可以保证数据正确性。
- 按企业性质分组后，增值税一般人和小规模不会互相污染候选任务。

影响：
- `VAT_GENERAL` 覆盖目标会查询并校验 `NORMAL_TAXPAYER`。
- `VAT_SMALL` 覆盖目标会查询并校验 `SMALL_TAXPAYER`。
- 后台补齐诊断中新增 `backendTaxPayerType`，便于判断缺口为什么没有命中。

后续：
- 如果后台未来修改企业性质枚举，需要集中调整 `src/coverage/registry.py`。
- 如果后台正式修复 `taxTypeId` 服务端过滤，客户端二次校验仍可保留作为安全兜底。
## 2026-06-01：截图/PDF证据必须先确认目标表单

状态：已采纳

背景：
税号 `91131102MA07X9YW6M` 的增值税未申报场景中，附表菜单切换后页面未确认成功，但流程仍继续网页抽取和 PDF 保存，导致主表截图被保存为附表截图。此类错误会误导人工复核，比直接失败更危险。

选择：
- 网页数据抽取、PDF 保存和字段比对前，必须先确认当前浏览器页面属于当前 `CompareTarget`。
- 未申报增值税附表同时通过左侧菜单激活状态和页面正文标题确认目标附表；任一信号不匹配则当前表单失败，不生成截图/PDF证据。
- 已申报详情页继续使用表单标题、页面正文、映射字段等信号确认目标表单；确认失败同样停止。

选择原因：
- 证据文件的正确性优先于流程继续率。
- 错误截图会让后续人工检查以为系统已经进入目标表单，增加误判风险。
- 失败并暴露“未确认切表”原因，便于后续针对具体省份或页面做导航修复。

影响：
- 税局页面结构变化或附表切换失败时，验证会更早失败。
- 批量报告会显示需要处理原因，不再产出错误表单的 PDF。
- 后续新增税种或表单切换逻辑，也应复用“先确认目标表单，再生成证据”的规则。

## 2026-06-01：批量结果必须绑定本次验证产物，运行日志必须脱敏

状态：已采纳

背景：
同一个 taskId 会在多次批量运行中重复验证，`output/reports/<taskId>` 会保留历史 compare JSON。此前批量汇总按 taskId 目录全量读取报告，导致旧的网页缺失、解析失败等问题污染当前批次。真实运行日志里还可能出现带 cookie/token 的 tpass URL，存在敏感信息泄露风险。

选择：
- 每次调用 `main.py` 验证前记录开始时间，只把本次新生成的 compare JSON 写入当前 item 的 `verify.reportPaths`。
- 批量汇总和当前批次需处理原因优先使用 `verify.reportPaths`，旧状态文件没有该字段时才回退到历史兼容逻辑。
- 登录流程日志统一通过 `src/login/log_sanitizer.py` 脱敏，遮蔽 cookie、token、Authorization、证件号、手机号等敏感值。
- 覆盖补齐和取数轮询必须输出可观察进度；取数超时前先尝试从后台解析 taskId，避免后台已成功但前端轮询未更新时误判人工处理。

选择原因：
- 当前批次结果必须可审计、可复核，不能被历史报告污染。
- 真实运行产物和日志可能被复制到无影云电脑或发给运营排查，敏感值不应明文出现。
- 外部系统状态更新存在延迟，后台 taskId 是更接近验证入口的兜底来源。

影响：
- 新批次 state 会多出 `verify.reportPaths` 字段。
- 运营台事件流会减少重复“等待取数”事件，`NO_NEED_COLLECTED` 会显示为完成。
- 覆盖补齐新增 `--coverage-supplement-timeout` 参数；默认 600 秒。
- 历史批次仍按旧逻辑兼容展示，必要时可重新跑批次生成新的 `reportPaths`。
## 2026-06-01：后台补齐不再只依赖单个代表任务

状态：已采纳

背景：
后台存在符合税种和申报状态的成功取数任务，但第一个候选任务进入税局后可能因为登录态失效、申报记录未找到、页面策略不匹配或表单切换失败而无法完成验证。此前每个覆盖缺口只选择一个代表任务，导致“后台有任务”但结果页仍显示未覆盖，且看不到其他候选任务是否也尝试过。

选择：
- 后台补齐查询阶段每个覆盖缺口保留多个候选任务，默认最多 3 个。
- 验证阶段按覆盖缺口逐个尝试候选任务；某个候选生成有效报告并覆盖目标税种/申报状态后停止该缺口的后续尝试。
- 每次尝试写入 `coverageSupplement.attempts`，记录候选税号、taskId、尝试序号、验证结果、失败/完成步骤和直接原因。
- 批量结果页展示“后台补齐尝试记录”，覆盖缺口原因优先说明已尝试候选的最后失败步骤。
- 覆盖分析优先使用当前批次 `verify.reportPaths`，避免历史同 taskId 报告干扰补齐是否成功的判断。

选择原因：
- 后台任务可用性和税局页面可验证性不是同一件事，必须用真实验证结果决定是否覆盖。
- 多候选重试能降低单个任务登录失效、页面异常对覆盖补齐的影响。
- 记录每个候选失败步骤后，运营可以区分“后台没任务”“任务找到了但税局登录失败”“任务找到了但申报表未找到”等不同处理路径。

影响：
- 批量运行时间可能随候选重试次数增加；默认 3 个候选控制耗时。
- `state.json`、`coverage_status.json` 和结果页会新增补齐尝试记录。
- 后续如果要进一步加速，可以按失败类型决定是否继续同税种重试，例如登录态整体失效时暂停后续候选。
## 2026-06-01：残保金覆盖不区分已申报和未申报

状态：已采纳

背景：
残保金取数验证的业务目标不是判断当期是否已申报，而是确认后台残保金字段是否取回，并在汇算清缴场景下与税局年度企业所得税申报表指定字段一致。因此继续把残保金拆成“已申报/未申报”会制造无意义覆盖缺口。

补充：
- 内部覆盖状态统一使用 `any` 表示“不区分申报状态”，即 `CBJ_PERSONAL:any`、`CBJ_ANNUAL:any`。
- 报告展示仍使用运营可读文案，例如“不区分申报状态”“已取数”“已验证”。

选择：
- `CBJ_PERSONAL` 和 `CBJ_ANNUAL` 覆盖目标各保留一个“已验证”目标。
- 不再生成 `CBJ_PERSONAL:unfiled`、`CBJ_ANNUAL:unfiled` 覆盖缺口。
- 后台补齐残保金候选时，不要求解析申报状态；候选仍需匹配对应后台税种 ID，后续通过残保金专用验证逻辑判断是否成功。
- 不再复用 `filed` 作为残保金内部覆盖状态，避免报告中继续出现“已申报/未申报”语义。

选择原因：
- 个税残保金只检查后台字段 `snzzzgrs_cbj`、`snzzzggzze_cbj` 是否返回。
- 汇算清缴残保金需要进税局查 A000000/A105050 并与后台字段对比，但同样不依赖“已申报/未申报”覆盖维度。
- 减少无效覆盖缺口，避免运营误以为还需要寻找“未申报残保金”样本。

影响：
- 覆盖目标总数减少，残保金只按“个税残保金是否验证”“汇算清缴残保金是否验证”统计。
- 历史批次已生成的覆盖文件不会自动变化，需要重新生成覆盖状态或重新跑批次后生效。

## 2026-06-01：残保金子类型优先使用后台任务日志判定

状态：已采纳

背景：
税号 `91460000MAE0TMR45K` 的后台任务日志中，“残保金任务返回结果”写明“数据库未查询到返回数据，调用汇算清缴取数接口查询”。这说明该任务实际走的是汇算清缴残保金路径，但批量验证此前只按 `taxTypeId=26` 默认归为个税残保金，导致验证路径错误。

选择：
- 在 `--cbj-mode auto` 下，优先读取后台任务日志类型“残保金任务返回结果”。
- 日志内容包含“数据库未查询到返回数据”“调用汇算清缴取数接口”或“汇算清缴取数接口”时，判定为汇算清缴残保金。
- 日志判定优先级高于 `taxTypeId=26` 的默认个税残保金判断。
- 如果任务日志不可读或没有明确 marker，继续使用原有 `taxTypeId`、覆盖目标和文本关键字兜底。

选择原因：
- `taxTypeId=26` 只能说明进入残保金任务链路，不能稳定区分个税残保金和汇算清缴残保金。
- 后台日志记录了实际执行器选择，是当前更接近真实业务路径的信号。
- 个税残保金和汇算清缴残保金验证方式不同，误分类会直接导致验证结果失真。

影响：
- 批量验证会在残保金任务进入验证前多读取一次后台任务日志。
- `91460000MAE0TMR45K / 2075110899720157073` 这类先查数据库、再调用汇算清缴接口的任务会走年度企业所得税表取数比对路径。

后续：
- 如果后台日志文案调整，需要补充新的 marker。
- 如果后台后续提供结构化残保金子类型字段，应优先替换文本 marker 判断。

## 2026-06-01：后台补齐只尝试一个候选任务

状态：已采纳

背景：
此前后台覆盖补齐支持同一个覆盖缺口最多尝试 3 个候选任务。真实批量运行中，这会显著拉长税局登录和申报表查询时间；当外部税局登录态、地区页面或数字账户不可用时，多候选重试往往重复消耗时间，但不能稳定提高成功率。

选择：
- 每个覆盖缺口只保留并尝试第一个匹配候选任务。
- `--coverage-supplement-max-candidates` 参数暂时保留兼容旧命令，但内部固定为 1。
- 补齐规划器 `CoverageSupplementPlanner` 也强制最多返回 1 个候选，避免其他入口绕过批量脚本重新启用多候选重试。

选择原因：
- 优先缩短批量链路耗时和减少重复登录税局的外部风险。
- 后台补齐的目标是找到一个代表样本，不是穷举所有可疑任务。
- 单候选失败时结果页仍能展示失败步骤和原因，运营可以据此人工处理或重新跑指定任务。

影响：
- 覆盖补齐不再自动尝试第二、第三个候选；如果第一个候选因税局登录或页面问题失败，该缺口会保留为未覆盖。
- 历史批次已有的多候选尝试记录不变，新批次只会产生一个候选尝试。

## 2026-06-02：消费税未申报入口使用直达 URL 并切换新税局页

状态：已采纳

背景：山东消费税未申报任务进入税局时，税局首页点击“填写申报表”会打开新的消费税申报标签页。原逻辑仍停留在旧的 `loginb/` 首页上查找左侧表单菜单，导致误报“找不到消费税及附加税费申报表”。同时消费税左侧菜单存在父级“消费税及附加税费申报表”和子级“消费税及附加税费申报表主表”，原逻辑可能把父级激活误判为主表已激活。

选择：
- 消费税未申报优先直达 `/sbzx/view/lzsfjssb/#/declare/xfssb?jyjkId=30`。
- 如果税局仍通过首页点击打开新标签页，自动在同一浏览器上下文中切换到消费税申报页。
- 消费税主表菜单选择必须匹配“消费税及附加税费申报表 + 主表”，避免父级菜单误判。
- 字段比对只纳入接口有非空值的字段；接口空字符串视为未返回，按全局规则忽略。

原因：
- 直达 URL 比从首页逐级点击更稳定，且已在真实山东税局消费税页面验证。
- 切换新标签页可以兜住税局页面行为变化。
- 父级菜单和子级表单名称相近，必须区分菜单选择信号和正文标题信号。

影响：
- 山东消费税未申报任务可以稳定进入两张表：消费税及附加税费申报表、消费税附加税费计算表。
- 接口空值字段不再产生 `api_missing`，结果更符合“接口未返回则忽略”的业务规则。

验证：
- `taskId=2076264459216848195` 真实税局验证通过，两张消费税表均 100%。

## 2026-06-01：新批次默认重新发起取数，旧 taskId 复用改为显式选项

状态：已采纳

背景：
税号 `91370203334145023C` 重新验证时，已申报/未申报状态问题并不是后台状态判断错误，而是批量取数阶段复用了旧 taskId，导致后续验证基于旧任务结果。运营重新发起验证时，默认预期是产生当次新取数任务。

选择：
- 新批次中，如果税号当前 state 没有 `verifyTaskId`，默认强制提交新的易代账取数任务。
- 只有传入 `--reuse-collected-task` 时，才允许在易代账已显示已取数的情况下复用后台已有任务。
- 后台 taskId 解析在新提交取数后只接受提交时间附近的新任务，避免命中历史成功任务。

选择原因：
- “重新发起验证”在业务语义上应绑定本次取数，而不是最近一次历史任务。
- 状态判断和字段比对必须基于当前批次任务，否则会把旧数据误认为当前数据问题。
- 保留显式复用选项，便于运营在确实需要节省取数时间时手动选择。

影响：
- 新批次默认会比复用旧任务多一次取数提交，但结果可追溯性更强。
- 历史任务复用不再是默认行为，旧命令如果依赖复用，需要增加 `--reuse-collected-task`。
- 如果新任务提交后后台短时间没有生成 taskId，流程会等待或给出取数未完成/需人工处理原因，而不会自动拿旧任务兜底。

## 2026-06-01：青岛税号进税局必须覆盖旧省份跳转参数

状态：已采纳

背景：
山东税号中青岛地区需要走 `qingdao` 电子税局域名。实际任务 cookie 中可能同时存在 `province=shandong`、旧 `forceRedirectEtaxProvinces=hebei` 或空 `tgtUrl`，导致 tpass 初始化参数被旧值覆盖，进税局路径不稳定。

选择：
- 根据税号行政区划把青岛税号的税局省份修正为 `qingdao`。
- 构造 tpass 登录 URL 时，在合并后台 cookie/localStorage 后再次显式写入 `province`、`tgtUrl`、`forceRedirectEtaxProvinces`。
- 如果后台没有可用 `tgtUrl`，使用目标省份登录入口作为兜底。

选择原因：
- 后台 taskInfo 中的旧字段优先级不能高于项目根据税号和目标省份计算出的最终跳转参数。
- 青岛属于独立电子税局入口，不能沿用山东普通入口或其他历史省份值。
- 明确覆盖关键字段可以避免同一批次中前一个省份污染后一个省份的登录跳转。

影响：
- 青岛税号会稳定打开青岛 tpass/电子税局入口。
- 如果青岛 tpass 本身没有有效登录 token，仍会停在统一登录页并需要人工处理；该决策只修复省份和跳转参数错误，不绕过税局登录认证。

## 2026-06-01：一个税号可对应多个取数 taskId

状态：已采纳

背景：
部分税号一次发起取数后，后台会生成多个成功取数 taskId。例如税号 `91370102MA7D3P0D2P` 曾同时对应 `2075110435864560097` 和 `2075110435864560096`。此前解析器只选择一个 taskId，会漏验另一部分取数结果，导致覆盖和差异展示不完整。

选择：
- 后台 taskId 解析器在同一提交窗口内返回全部成功取数 taskId，而不是只取最新一条。
- state 中继续保留 `collect.verifyTaskId` 作为第一个 taskId，兼容旧逻辑。
- 新增 `collect.verifyTaskIds`、`collect.resolvedTasks` 保存全部任务。
- 批量验证为额外 taskId 生成同税号内部子项，逐个调用 `main.py --task-id`。
- 汇总页、CSV 和覆盖分析读取全部 taskId 的验证结果。

选择原因：
- `main.py --task-id` 仍是唯一真实验证入口，避免新增第二套验证流程。
- 保留单 taskId 字段可以兼容旧批次、运营台和已有报告逻辑。
- 用内部子项表示额外 taskId，能让每个 taskId 都有独立日志、报告和失败原因，便于排查。

影响：
- 同一个税号可能在批量结果中出现多行或显示多个 taskId。
- 同一批次 taskId 去重仍然生效，避免不同税号或子项重复验证同一个 taskId。
- 如果后台返回多个成功任务，批量耗时会增加，但不会漏验。
## 2026-06-03：网页字段提取采用“专用解析器 + 滚动重试 + 覆盖率门槛”

状态：已采纳

背景：
真实验证中出现“网页缺失”但页面实际有值的情况。排查发现，一般纳税人附表一初次只提取到可见区域，未覆盖纵向/横向滚动后的表格内容；小规模主表和附表二则是通用 DOM 下标无法稳定处理合并单元格、栏次列、税率列和减征比例列。旧的零值空值等价规则还会让大面积网页未提取被误判为通过。

选择：
- 对表格虚拟滚动风险高的附表，在初次网页提取覆盖率低时自动滚动页面和内部滚动容器，再对缺失字段重试提取。
- 对小规模增值税主表、附列资料（一）、附列资料（二）使用税表专用文本解析器，不再依赖通用 DOM 下标猜列。
- 对关键表单设置更高的网页提取覆盖率门槛；低覆盖即使没有字段差异，也作为质量问题输出。
- 保留零值空值等价规则，但让覆盖率门槛兜住“全为空却通过”的假通过。

选择原因：
- 真实税局页面的 DOM 结构受省份、组件、滚动容器、合并单元格影响，通用下标算法不适合承担复杂申报表的主解析职责。
- 税表专用文本解析器直接围绕表单业务结构定位行列，能减少页面结构细节变化带来的误读。
- 覆盖率门槛能把解析失败和真实字段差异区分开，避免运营看到“通过”但实际没有取到足够网页证据。

影响：
- 一般附表一等存在滚动表格的页面会多一次滚动重试，耗时略有增加。
- 后续新增税种时，如果表格结构复杂，应优先新增专用解析器，并配置合适的覆盖率门槛。
- 报告中低覆盖会更严格地标记为质量风险，有利于尽早发现解析退化。

验证：
- `2076614026604697199` 真实回归成功；一般附表一原 3 个网页缺失字段已提取并匹配。
- `2076614417445323010` 真实回归成功；小规模主表、附表一、附表二均无网页缺失，主表栏次错读消失。
## 2026-06-04：税局首页兜底点击必须排除查询/进度类入口

状态：已采纳

背景：
山东税局未申报直达 URL 失败后会回到税局首页。快速登录回退使这条首页兜底路径更频繁触发，`2076981254899665895` 暴露出“办税”宽关键词可能误点“办税进度及结果信息查询”的问题。

选择：
- 首页兜底只允许在申报相关区域或目标税种卡片内点击“填写申报表/继续申报/办理”等动作。
- 明确排除办税进度及结果信息查询、申报查询、税费缴纳、发票业务、社保费业务、税务数字账户、我的待办、通知公告等非申报入口。
- 禁止恢复全页兜底扫描任意“填写申报表/办理”按钮；找不到安全入口时应失败并输出可处理原因。

原因：
- 误进查询进度页会污染浏览器状态，也会误导人工认为系统在执行错误业务。
- 对验证流程来说，早失败比进入错误页面继续验证更安全。

影响：
- 部分未知首页结构可能需要补充省份/税种入口规则后才能自动进入。
- 失败率可能短期上升为“找不到入口”，但错误页面点击概率下降。

## 2026-06-09: classify query-row misses and undeclared-entry failures separately

Status: adopted.

Decision:
- Filed declaration-query pages must be refreshed with the target tax period before selecting a row. For Vue-backed `/szzh/zhcx/sbxx/sbxxcx`, update `skssqq/skssqz`, clear declaration-date filters, reset page number, and invoke the page search handler.
- If a filed declaration row is still not found after a period-aware query, classify the supplement attempt as `source_state_conflict` unless later evidence proves a selector bug.
- `cit_a_main` may use a keyword-only row fallback only when exactly one candidate row matches; multiple matches must fail rather than selecting an arbitrary row.
- Undeclared home pages that show only a target title or hot-service entry but never open the target form should be reported as `target_entry_unavailable`.
- Expired task-cookie/login messages (`getTaskCookie`, `登录连接状态已失效`, `重新发起任务`) are login/session blockers and should not be treated as field-comparison failures.

Reason:
- Backend task success and tax-bureau page availability are different signals. Coverage should only be marked when the current run produces a valid report for the target tax type/status.
- Misclassifying login/session and source-state mismatches as field failures makes the workbench harder to operate and hides the actual next action.

Follow-up:
- Shorten repeated undeclared home-entry retries after a target action/title click fails to open an expected page.
- Treat `tpass/code` authorization-code pages as auth failures during login detection instead of "main page" success.
