# PROJECT_CONTEXT.md

## 2026-06-11 addendum: account-set skill treats Playwright as optional

The standalone account-set skill no longer presents Playwright as a default installation requirement. API-only creation paths can run without importing Playwright when Yidaizhang token/password auth and public-manage token/password auth produce usable API contexts. The CLI imports Playwright only when it actually needs browser/CDP fallback, existing Chrome session checks, or manual browser verification.

When Playwright is missing on a browser path, the skill now prints a targeted install hint for the Python `playwright` package and explains that `playwright install chromium` is usually unnecessary because the CLI uses local Chrome CDP.

## 2026-06-11 addendum: Chrome CDP fallback preserves the user's normal browser

Yidaizhang account-set creation no longer assumes that port `9222` is safe to reuse. When the default CDP port is already occupied by a Chrome instance that Playwright rejects because it was not started with automation-compatible flags, the flow now switches to a managed fallback port (`9333`, then `9444`, `9555`, `9666`) and uses a port-suffixed browser profile.

Managed Chrome launches include `--enable-automation` for Playwright 1.60 compatibility and `--disable-blink-features=AutomationControlled` for the existing login-page behavior. The original Chrome process on `9222` is not closed or modified. The standalone `skills/ydz-create-accountset/` package and installed `ydz-create-customer` skill carry the same behavior.

## 2026-06-11 addendum: public-manage backend auth can use API tokens before browser fallback

Yidaizhang account-set backend-source creation now supports a public-manage token provider. The flow can read `TAX_BACKEND_AUTHORIZATION` plus `TAX_BACKEND_TOKEN`/`TAX_BACKEND_ACCESS_TOKEN`, or attempt the normal Chanjet SSO API chain for public-manage (`authorizeByJsonp -> /token`) before falling back to the browser session.

This removes the old hard dependency on an open public-manage page when valid backend tokens are supplied. It does not bypass SSO risk controls: a live account-password attempt for the current backend account returned `MANUAL_VERIFICATION_REQUIRED` / `访问拒绝`, so default auto mode logs the blocker and uses browser fallback. Integration privacy-phone copy/pull uses the same backend provider; integration endpoints still omit the `token` header.

The standalone `skills/ydz-create-accountset/` package and installed `ydz-create-customer` skill carry the same self-contained behavior.

## 2026-06-11 addendum: production YDZ account-set entry recovers through workbench app list

Production Yidaizhang account-set creation can now recover when the browser is authenticated but only shows `ydz.chanjet.com`, `passport.chanjet.com/vm/redirectVM`, or the Chanjet workbench instead of an active `cloud.chanjet.com/.../work.html` tab. The browser fallback opens `workbench.chanjet.com/v2/myapp/list?orgId=<environment org id>`, clicks the primary `易代账` app's `进入应用` control, then waits for the usual `work.html` API token context.

This is not a password-token or verification bypass. If production password auth returns manual verification or access denial, the flow still needs a valid browser login state or the operator to complete the visible challenge. The standalone `skills/ydz-create-accountset/` package carries the same independent recovery logic.

## 2026-06-10 addendum: YDZ account-set supports manual captcha-code tax login

Yidaizhang account-set creation now supports backend-source and manual-source login methods `SDSRDX` and `DLYW-SDSRDX` in addition to `YSHDL` and `DLYW-YSHDL`. For `SDSRDX/DLYW-SDSRDX`, backend `loginJson.cTaxPreparerName` is treated as the phone/login account rather than a privacy number, and `cTaxPreparerPwd` remains the personal user password. For all `DLYW-*` methods, `cSiteLoginName` is the proxy company tax number.

Backend-source task lookup uses task categories `2,3`, no tax-type restriction, and `loginType=YSHDL,DLYW-YSHDL,SDSRDX,DLYW-SDSRDX`. Integration privacy-phone copy/pull runs only for `YSHDL/DLYW-YSHDL`; it is skipped for `SDSRDX/DLYW-SDSRDX`. The workbench manual-accountset form and standalone `skills/ydz-create-accountset/` package carry the same rules.

## 2026-06-10 addendum: YDZ account-set assigned accountant is dynamic

Yidaizhang account-set creation now resolves `accountantEmployeeId` from the logged-in Yidaizhang phone number when possible. The flow queries `trans/easyacctg/employee/getChildEmpListByUserId`, matches login phone to employee `mobile`, and uses row `userId` as the assigned accountant. If unavailable, it falls back to current Yidaizhang `userId`, then the packaged integration/production defaults. The standalone `skills/ydz-create-accountset/` package carries the same independent logic.

## 2026-06-04 更新：真实验证默认插件优先进税局

为降低税局 `/loading` 半登录、数字账户会话未就绪和 tpass 回跳失败概率，真实 taskId 验证默认使用 `--tax-login-strategy plugin_first`。直接打开 tpass URL 仍作为 fallback/调试路径保留，但批量和运营台默认应优先走 EtaxPlugin 的清 cookie、关闭旧页、新开页流程。

同日补齐：登录前会短等待 `window.robotId`，固定机器码取 cookie 失败时会用真实机器码重试一次；青岛 direct fallback 会清理插件同款特殊 cookie；`needForceTax=true` 默认归类为人工确认是否强制进入税局，不自动调用强制进入接口。

## 2026-06-01 更新：残保金覆盖规则

残保金覆盖不再拆分“已申报/未申报”。个税残保金只确认后台字段 `snzzzgrs_cbj`、`snzzzggzze_cbj` 是否取回；汇算清缴残保金通过税局年度企业所得税表与后台字段对比。覆盖矩阵中残保金只展示“已验证”目标。

## 项目背景

本项目的主要目标是建设本地税务运营工作台。工作台统一承载易代账自动登录、批量取数、后台 taskId 查询、电子税局验证、创建客户/账套、进度监控、问题处理和覆盖分析。底层脚本保留为可测试、可复用的执行入口，但新能力应优先接入工作台，而不是形成只靠命令行操作的第二套流程。

取数验证是工作台的核心能力之一：把畅捷通/易代账取数任务返回的接口数据，与电子税局页面、PDF、Excel ID 映射位置中的数据进行字段级对比，帮助发现接口缺字段、网页解析错误、税局页面取错、映射错误和真实数据不一致。

项目已经从单税号脚本演进到批量流程和本地运营工作台。后续重点不是只跑通某一个税号，而是让没有开发经验的运营人员也能批量发起、观察进度、处理卡点、查看差异、确认覆盖缺口。

“自动登录易代账并创建客户/账套”的能力已从项目中抽取为独立 skill：`skills/ydz-create-accountset/`。该 skill 是可复制给其他智能体使用的独立包，必须保持自包含，不依赖本项目的 `src/`、`scripts/`、`output/`、`runtime/` 或浏览器 profile。

## 当前阶段

项目当前处于内测到生产化过渡阶段。

当前重点：

1. 让工作台成为运营人员的主入口，覆盖自动登录、取数验证、建账套和结果处理。
2. 统一真实入口和生产流程，避免双主线维护。
3. 批量发起易代账取数、查询后台 taskId、串行验证。
4. 让结果页面直观展示“哪个税号、哪个税种、哪个表、哪个字段不一致”。
5. 建立税种/已申报/未申报覆盖矩阵，并可用后台成功任务补齐代表样本。
6. 持续提升电子税局登录和页面解析鲁棒性。

## 核心业务概念

- 税号：企业纳税人识别号/统一社会信用代码，是批量任务的输入单位。
- 所属期：取数与验证的税款所属期，常用格式为 `YYYYMM`。
- 易代账取数：在易代账网站选择账套和税种，发起取数任务。
- 后台 taskId：在畅捷通后台任务列表中查询到的取数任务 ID，是当前项目验证入口使用的核心 ID。同一个税号一次取数可能对应多个 taskId，需要逐个验证并在结果页展示。
- 内部 taskId：进电子税局时 `getClientJob` 返回的内部任务 ID，用于获取税局 cookie、打开税局页面。
- 申报状态：当前覆盖目标分为“已申报”和“未申报”。增值税可从任务执行日志 `成功保存数据-是否是当期` 的最新 `logInfo` 判断，不再依赖日志编号 `lsn`。
- CompareTarget：一张待验证申报表的配置，包括税种、API 表、Excel 映射、税局查询关键词和页面解析策略。
- 字段映射：接口字段、Excel 位置、网页/PDF 位置之间的对应关系。
- 原始通过率：按所有字段计算的通过率。
- 有效通过率：排除可接受缺失或无效字段后的通过率，更接近实际问题密度。

## 当前支持税种

项目当前覆盖框架登记的税种：

- 增值税（一般纳税人）
- 增值税（小规模纳税人）
- 企业所得税（A类）
- 文化事业建设费
- 消费税
- 残保金

每个税种都要求尽量覆盖：

- 已申报
- 未申报

消费税当前接入两张表：

- 消费税及附加税费申报表
- 消费税附加税费计算表

后续新增税种时，应同步更新 `src/coverage/registry.py`、映射、验证逻辑、测试和本文件。

## 重要约束

- 工作台是优先入口；新增运营能力应接入 `scripts/ops_console.py` 或其底层服务，而不是只提供孤立脚本。
- 真实验证入口优先使用 `python main.py --task-id <taskId>`。
- 批量验证通过 `scripts/batch_collect_verify.py` 和运营台包装主流程。
- 建账套 skill 必须独立可复制，不能导入项目 `src.*`、`scripts.*` 或依赖项目运行产物；项目内同名能力可以复用业务规则，但不能让 skill 反向依赖项目。
- 完整链路依赖 Chrome CDP、EtaxPlugin、易代账登录态、税局登录态。
- 外部登录阻塞不等同于字段比对失败，报告和运营台必须给出可处理原因。
- 不得在代码、文档、日志中新增明文账号密码、token、cookie。
- 运行输出、浏览器缓存和报告可能含敏感信息，默认不提交。

## 非目标

当前不做：

- 不重写一套新的生产验证流程。
- 不把真实电子税局 E2E 作为默认自动测试。
- 不在项目中固化个人账号密码。
- 不追求一次性重构 `scripts/compare_tax_forms.py`，应逐步下沉稳定模块。

## 已知风险

- 电子税局页面、易代账页面、后台接口字段均可能变化。
- 各省税局登录和数字账户路径并不完全一致。
- 历史文件存在中文编码显示问题，修改时需要避免扩大问题。
- 批量验证可能被税局会话失效、代理、验证码、进税局任务锁影响。
- 部分未申报场景页面与已申报查询页面不同，需要逐税种补齐策略。
