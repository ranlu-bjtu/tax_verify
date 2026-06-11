param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$ChromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe",
    [string]$PluginPath = "$env:USERPROFILE\Downloads\EtaxPlugin",
    [string]$UserDataDir = "",
    [int]$CdpPort = 9222,
    [switch]$Hidden
)

$ErrorActionPreference = "Stop"

if (-not $UserDataDir) {
    $UserDataDir = Join-Path $ProjectRoot "browser_profile\etax_compare_forms"
}

if (-not (Test-Path $ChromePath)) {
    throw "Chrome path does not exist: $ChromePath"
}

if (-not (Test-Path $PluginPath)) {
    Write-Warning "EtaxPlugin path does not exist: $PluginPath"
}

New-Item -ItemType Directory -Force -Path $UserDataDir | Out-Null

$chromeArgs = @(
    "--load-extension=$PluginPath",
    "--user-data-dir=$UserDataDir",
    "--remote-debugging-port=$CdpPort",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-blink-features=AutomationControlled"
)

$startArgs = @{
    FilePath = $ChromePath
    ArgumentList = $chromeArgs
}

if ($Hidden) {
    $startArgs["WindowStyle"] = "Hidden"
}

Start-Process @startArgs
Write-Host "Chrome CDP started on port $CdpPort"
Write-Host "User data dir: $UserDataDir"
Write-Host "Plugin path: $PluginPath"
