param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [switch]$InstallPlaywright
)

$ErrorActionPreference = "Stop"

Set-Location $ProjectRoot

$python = Get-Command python -ErrorAction Stop
Write-Host "Using Python: $($python.Source)"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Write-Host "Upgrading pip..."
& $venvPython -m pip install --upgrade pip

Write-Host "Installing project dependencies..."
& $venvPython -m pip install -r requirements.txt

if ($InstallPlaywright) {
    Write-Host "Installing Playwright and Chromium..."
    & $venvPython -m pip install playwright
    & $venvPython -m playwright install chromium
}

Write-Host "Environment is ready: $ProjectRoot"
