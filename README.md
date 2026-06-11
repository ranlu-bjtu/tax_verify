# 税务运营工作台

本项目的主要目标是提供一个本地运营工作台，集中完成易代账自动登录、取数验证、创建账套、进度监控和问题处理。命令行脚本仍然保留，但应优先作为工作台能力的底层执行入口，而不是另起一套人工流程。

工作台当前覆盖：

- 自动登录易代账和报税后台。
- 批量发起易代账取数，查询后台 taskId。
- 登录电子税局或读取后台结果，完成字段级核对。
- 创建易代账客户/账套并保存税务登录信息。
- 展示当前任务、日志、结果、覆盖情况和需处理问题。

其中“自动登录并创建账套”的能力已抽取为独立 skill：`skills/ydz-create-accountset/`。该 skill 必须能被复制到其他智能体环境独立使用，不依赖本项目的 `src/`、`scripts/` 或运行产物。

## 工作台入口

本地运维工作台：

```powershell
python scripts\ops_console.py --open
```

工作台是推荐入口。下面命令主要用于调试、回归测试或自动化子流程。

## 调试入口

单个 taskId 验证：

```powershell
python main.py --task-id <taskId> --log-level INFO
```

只验证接口和映射，不进入税局页面：

```powershell
python main.py --task-id <taskId> --skip-browser --log-level INFO
```

批量完整链路：

```powershell
python scripts\batch_collect_verify.py --tax-no-file tax_nos.txt --period 202604 --enterprise "蓝天之爱" --verify --targets auto --log-level INFO
```

## 无影云电脑部署

部署到 Windows 系统无影云电脑时，优先阅读：

```text
DEPLOY_WUYING.md
```

配套脚本：

```text
scripts\windows\setup_wuying.ps1
scripts\windows\start_chrome_cdp.ps1
scripts\windows\start_ops_console.ps1
```

## 运行产物

以下目录为本地运行产物，不应提交：

```text
output/
browser_profile/
runtime/
.venv/
```

## 安全要求

不要把易代账账号密码、cookie、token、税局登录态、浏览器缓存提交到仓库。部署时通过运维页面临时输入凭据，或在本机环境变量中配置。
