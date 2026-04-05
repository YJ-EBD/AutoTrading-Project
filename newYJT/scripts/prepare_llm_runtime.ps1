$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runtimeDir = Join-Path $root "runtime\\llm"
$logsDir = Join-Path $root "runtime\\logs"
$python = Resolve-Path (Join-Path $root "runtime\\freqtrade_venv\\Scripts\\python.exe")

Set-Location $root
New-Item -ItemType Directory -Force -Path $runtimeDir, $logsDir | Out-Null
& $python -X utf8 scripts\render_runtime_configs.py | Out-Null
