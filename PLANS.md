# PLANS.md

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
