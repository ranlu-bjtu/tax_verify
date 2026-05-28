# CHANGELOG_AI.md

本文件记录 Codex/AI agent 对项目的改动摘要。每次完成任务后追加或整理记录，保证项目记忆不依赖聊天历史。

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
lsn = sz_zzs
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
