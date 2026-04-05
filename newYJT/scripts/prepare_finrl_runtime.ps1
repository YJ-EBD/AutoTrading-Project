$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Resolve-Path (Join-Path $root "runtime\finrl_venv\Scripts\python.exe")
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"

Set-Location $root
& $python (Join-Path $root "scripts\prepare_finrl_data.py")
