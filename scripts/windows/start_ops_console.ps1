param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8765,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
} else {
    $python = "python"
}

$argsList = @(
    "scripts\ops_console.py",
    "--host",
    $HostName,
    "--port",
    "$Port"
)

if (-not $NoOpen) {
    $argsList += "--open"
}

& $python @argsList
