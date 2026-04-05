$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
$python = Resolve-Path (Join-Path $root "runtime\finrl_venv\Scripts\python.exe")
$workdir = Resolve-Path (Join-Path $root "vendor\FinRL-Trading")
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"

& $python (Join-Path $root "scripts\prepare_finrl_data.py")

while ($true) {
    $entered = $false
    try {
        Push-Location $workdir
        $entered = $true
        & $python src\strategies\run_adaptive_rotation_strategy.py `
            --config src\strategies\AdaptiveRotationConf_v1.2.1.yaml `
            --backtest `
            --start 2023-01-01 `
            --end 2024-12-31
        Pop-Location
    } catch {
        if ($entered) {
            Pop-Location
        }
        Write-Warning $_.Exception.Message
    }
    Start-Sleep -Seconds 21600
}
