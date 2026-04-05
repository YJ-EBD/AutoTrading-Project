$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $root "runtime\\freqtrade_venv"
$python = Join-Path $venv "Scripts\\python.exe"
$pip = Join-Path $venv "Scripts\\pip.exe"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONLEGACYWINDOWSSTDIO = "utf-8"

if (-not (Test-Path $venv)) {
    python -m venv $venv
}

Set-Location $root
& $python -m pip install --upgrade pip
& $pip install -r vendor\freqtrade\requirements-freqai.txt
& $pip install -e vendor\freqtrade
& $pip uninstall -y aiodns | Out-Null
