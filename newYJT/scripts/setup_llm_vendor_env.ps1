$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $root "runtime\\llm_venv"
$python = Join-Path $venv "Scripts\\python.exe"
$pip = Join-Path $venv "Scripts\\pip.exe"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not (Test-Path $venv)) {
    python -m venv $venv
}

Set-Location $root
& $python -m pip install --upgrade pip setuptools wheel
& $pip install -r vendor\binance-anthropic-trading-bot\requirements.txt
& $pip install "httpx<0.28"
