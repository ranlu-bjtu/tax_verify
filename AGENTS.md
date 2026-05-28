# AGENTS.md

本文件是 Codex/AI agent 在本项目中的稳定工作规则。每次进入项目都必须优先阅读。优先级高于一般性建议，但低于用户的最新明确指令。

## 项目概述

本项目是税务取数与申报表验证工具，用于自动发起易代账取数任务，查询后台 taskId，登录电子税局或读取后台结果，并将接口字段与税局页面、PDF、Excel 映射结果进行字段级核对。

主要目标：

- 批量处理税号，自动发起取数并验证。
- 统一真实入口，避免多套生产主线。
- 支持运营人员通过本地工作台使用项目，尽量减少命令行和人工介入。
- 让项目长期上下文沉淀在仓库文件中，不依赖聊天历史。

## 必读项目记忆

每次开始任务前，按顺序阅读：

1. `PROJECT_CONTEXT.md`
2. `ARCHITECTURE.md`
3. `TASKS.md`
4. 任务涉及架构、长期计划或多模块时，阅读并更新 `PLANS.md`
5. 任务涉及已有取舍或新增取舍时，阅读并更新 `DECISIONS.md`

每次完成任务后：

1. 运行相关测试，或说明无法运行的原因。
2. 更新 `CHANGELOG_AI.md`。
3. 如果规则、架构、运行方式、入口命令发生变化，同步更新本文件或相关项目记忆文件。
4. 最终回复说明修改内容、验证方式、残余风险。

## 仓库结构

- `main.py`：推荐统一入口。
- `scripts/compare_tax_forms.py`：当前真实 taskId 比对核心实现，`main.py` 复用其 `run_compare()`。
- `scripts/batch_collect_verify.py`：批量发取数、查询 taskId、串行验证、生成批量汇总。
- `scripts/ops_console.py`：本地运营工作台，包装批量脚本，不新增第二套验证流程。
- `scripts/coverage_check.py`：读取已有批次并生成覆盖矩阵。
- `src/api/`：畅捷通任务结果接口读取。
- `src/chanjet_admin/`：后台任务列表与任务执行日志查询。
- `src/compare/`：字段归一化与比较。
- `src/coverage/`：税种/申报状态覆盖分析与后台补齐框架。
- `src/login/`：Chrome CDP、EtaxPlugin、电子税局登录流程。
- `src/ydz/`：易代账登录、账套查询、取数任务提交。
- `src/cbj/`：残保金验证逻辑。
- `tests/unit/`：单元测试。
- `mappings/`：ID 映射工作簿。
- `output/`、`browser_profile/`、`runtime/`：运行产物、浏览器 profile、工作台状态，不应提交敏感内容。

## 运行入口

真实 taskId 验证：

```powershell
python main.py --task-id <taskId> --log-level INFO
```

只验证接口和映射，不进税局页面：

```powershell
python main.py --task-id <taskId> --skip-browser --log-level INFO
```

批量完整链路：

```powershell
python scripts\batch_collect_verify.py --tax-no-file tax_nos.txt --period 202604 --enterprise 蓝天之爱 --verify --log-level INFO
```

本地运营工作台：

```powershell
python scripts\ops_console.py --open
```

覆盖检查：

```powershell
python scripts\coverage_check.py --run-dir output\batch_runs\<runId>
```

离线 mock 管线：

```powershell
python main.py --dry-run --period 2026Q1 --tax-type VAT_SMALL_SCALE
```

## 浏览器和外部依赖

- 完整验证依赖 Chrome CDP，默认端口 `9222`。
- 完整验证依赖 EtaxPlugin，默认路径 `C:\Users\Administrator\Downloads\EtaxPlugin`。
- 易代账账号密码必须来自环境变量、运营台临时输入或人工登录态，不得写入代码。
- 电子税局可能出现验证码、强制登录、数字账户登录失效、进税局任务锁等外部阻塞。
- 如果返回 `needForceTax=true` 或内部 taskId 为空，应明确说明是外部登录流程阻塞，不要包装成字段比对失败。

## 开发规范

- 保持改动范围尽量小，不顺手重构无关模块。
- 不新增第二套生产流程。真实 taskId 比对逻辑应复用 `scripts/compare_tax_forms.py::run_compare()`，或进一步下沉到 `src/`。
- 新功能优先接入现有 `main.py`、批量脚本或运营台，不绕开主流程。
- 修改功能时同步添加或更新测试。
- 对外接口、后台接口参数、覆盖规则、登录策略、数据结构变更必须写入 `DECISIONS.md`。
- 手工编辑使用补丁方式。
- 当前项目历史文件存在中文编码风险，修改中文业务文案、表单名、按钮名时要保持 UTF-8。
- 不提交浏览器缓存、运行输出、大体积报告、账号、密码、cookie、token、Authorization、access_token、身份证号。

## 验证要求

文档-only 修改可以不跑代码测试，但需说明未跑原因。

小改动至少运行：

```powershell
python -m compileall -q main.py scripts src
```

核心比较逻辑改动至少运行：

```powershell
python tests\unit\test_models.py
python tests\unit\test_normalizer_comparator.py
python tests\unit\test_config_loader.py
python tests\unit\test_mapping_loader.py
```

当前批量、运营台、覆盖补齐相关改动优先运行：

```powershell
python tests\unit\test_batch_handling_info.py
python tests\unit\test_batch_summary_rendering.py
python tests\unit\test_ops_console.py
python tests\unit\test_coverage_framework.py
python tests\unit\test_chanjet_admin_task_query.py
python tests\unit\test_task_execution_log.py
```

涉及真实 taskId 流程时，优先先跑 `--skip-browser`，再跑完整验证。

## 完成标准

一个任务只有在满足以下条件时才算完成：

- 功能实现符合需求。
- 相关测试通过，或明确说明无法运行的外部原因。
- 没有明显破坏现有入口和主流程。
- 文档或项目记忆文件已同步更新。
- 回复中包含修改内容、验证结果、残余风险。
