# ARCHITECTURE.md

## 总体架构

项目分为五层：

1. 入口层：`main.py`、批量脚本、运营台。
2. 任务编排层：易代账取数、后台 taskId 查询、覆盖分析、串行验证。
3. 外部系统层：易代账、畅捷通后台、任务执行日志、电子税局、EtaxPlugin。
4. 比对能力层：API 读取、Excel 映射、网页/PDF 提取、归一化、比较。
5. 报告与运营层：单 taskId 报告、批量汇总、覆盖矩阵、问题处理清单。

## 入口层

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
  -> 后台查询取数 taskId
  -> 按 taskId 串行调用 main.py 验证
  -> 汇总 batch_summary.html / CSV / coverage_status.json
```

### `scripts/ops_console.py`

本地运营工作台，默认地址 `http://127.0.0.1:8765/`。

职责：

- 生成并启动批量命令。
- 临时传递易代账账号密码到子进程环境变量，不落盘。
- 展示环境检查、当前任务、税号进度、问题处理、覆盖检查、最近批次。
- 提供继续验证、重试取数、跳过、导出问题清单等操作。

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

- `task_query.py`：调用 `getTaskListInternal` 查询任务列表，支持按时间、税号、所属期、税种、任务状态查询。
- `task_execution_log.py`：调用 `tTaskExecutionLog/getPageListByTaskId` 查询任务执行日志。

增值税申报状态规则：

```text
logType = 成功保存数据-是否是当期
lsn = sz_zzs
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
- 税局登录状态识别。
- tpass fallback。
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
