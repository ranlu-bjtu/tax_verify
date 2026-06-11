# 无影云电脑部署说明

本文档用于把当前项目部署到 Windows 系统的无影云电脑。推荐把无影云电脑当作一台长期在线的 Windows 运维工作机使用，不建议把本项目暴露为公网服务。

## 一、推荐目录

路径不要求固定，但建议按下面方式分开项目、浏览器数据和插件：

```text
D:\tax_verify                         项目代码
D:\tax_verify_data\browser_profile    Chrome 登录态目录
D:\tools\EtaxPlugin                   税局插件目录
```

如果仍使用 `C:\Users\Administrator\tax_verify` 也可以。运维页面已经支持填写 Chrome 路径、税局插件路径、浏览器数据目录。

## 二、部署前准备

在无影云电脑中安装：

1. Google Chrome
2. Python 3.11 64 位
3. Git，可选
4. 税局插件 EtaxPlugin

建议关闭代理或 VPN，再运行完整验证。税局、畅捷通、易代账页面对代理比较敏感。

## 三、复制项目

复制项目时不要带运行产物和敏感数据：

```text
不要复制：
- .venv/
- output/
- browser_profile/
- runtime/
- __pycache__/
- .env
- tax_nos*.txt
```

如果用 Git：

```powershell
cd D:\
git clone <你的仓库地址> tax_verify
cd D:\tax_verify
```

如果用压缩包，解压到目标目录即可。

## 四、初始化环境

进入项目根目录后执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\windows\setup_wuying.ps1
```

脚本会创建 `.venv` 并安装 `requirements.txt` 里的依赖。

如需要安装 Playwright 浏览器依赖，可执行：

```powershell
.\scripts\windows\setup_wuying.ps1 -InstallPlaywright
```

## 五、启动 Chrome CDP

根据实际路径启动 Chrome：

```powershell
.\scripts\windows\start_chrome_cdp.ps1 `
  -ChromePath "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  -PluginPath "D:\tools\EtaxPlugin" `
  -UserDataDir "D:\tax_verify_data\browser_profile\etax_compare_forms" `
  -CdpPort 9222
```

第一次建议不要隐藏窗口，方便手工登录易代账、畅捷通后台和处理税局登录状态。

需要检查：

- 易代账可登录
- 畅捷通后台可登录
- 税局插件正常加载
- Chrome CDP 地址 `http://127.0.0.1:9222/json/version` 可访问

## 六、启动运维工作台

```powershell
.\scripts\windows\start_ops_console.ps1
```

默认地址：

```text
http://127.0.0.1:8765/
```

在页面任务参数中填写：

- Chrome 路径
- 税局插件路径
- 浏览器数据目录
- 易代账账号/密码，只有登录态失效时需要填写
- 所属期，例如 `202604`
- 企业，例如 `蓝天之爱`
- 税号清单，每行一个

然后点击“开始任务”。

## 七、验证部署是否成功

先运行基础检查：

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py scripts src
```

已有 taskId 时可先跑接口和映射验证：

```powershell
.\.venv\Scripts\python.exe main.py --task-id <taskId> --skip-browser --log-level INFO
```

完整链路建议从运维页面发起。

## 八、结果位置

批量结果：

```text
output\batch_runs\<runId>\batch_summary.html
```

单 taskId 结果：

```text
output\reports\<taskId>\compare_summary_<taskId>_*.html
```

## 九、日常维护

建议备份：

```text
config/
mappings/
runtime/ops_console/jobs.json
output/batch_runs/需要留档的批次
output/reports/需要留档的任务
浏览器数据目录，例如 D:\tax_verify_data\browser_profile
```

不建议提交或外传：

```text
output/
browser_profile/
runtime/
.env
账号、密码、cookie、token
```

## 十、常见问题

### 页面提示 Chrome 未连接

先确认 Chrome 是用 `--remote-debugging-port=9222` 启动的，并访问：

```text
http://127.0.0.1:9222/json/version
```

### 税局插件路径异常

在运维页面重新填写 `税局插件路径`，或用 `start_chrome_cdp.ps1 -PluginPath` 指定真实路径。

### 易代账登录慢或不填密码

优先在 Chrome 里手工打开易代账并确认登录态。登录态失效时，在运维页面临时填写易代账账号密码。

### 税局登录失效

关闭当前税局页，从运维页面重试；如果出现数字账户登录失效，需要人工重新登录数字账户。

### 批量任务中断

重新打开运维工作台，选择对应批次后使用“继续未完成”。
