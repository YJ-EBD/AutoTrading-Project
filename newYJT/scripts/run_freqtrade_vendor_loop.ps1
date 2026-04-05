$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
$python = Resolve-Path (Join-Path $root "runtime\freqtrade_venv\Scripts\python.exe")
$config = Resolve-Path (Join-Path $root "runtime\freqtrade\config.binance_usdtm.freqai.json")
$strategyPath = Resolve-Path (Join-Path $root "runtime\freqtrade\user_data\strategies")
$userDataDir = Resolve-Path (Join-Path $root "runtime\freqtrade\user_data")
$configJson = Get-Content $config -Raw | ConvertFrom-Json
$dbName = if ($configJson.dry_run) { "tradesv3.dryrun.sqlite" } else { "tradesv3.sqlite" }
$dbPath = Join-Path $root ("runtime\freqtrade\" + $dbName)
$dbUrl = "sqlite:///" + (($dbPath -replace "\\", "/"))
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONLEGACYWINDOWSSTDIO = "utf-8"
$env:NO_COLOR = "1"
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

while ($true) {
    try {
        & $python -X utf8 -m freqtrade download-data `
            --no-color `
            --user-data-dir $userDataDir `
            --config $config `
            --trading-mode futures `
            --timeframes 3m 15m 1h `
            --timerange 20250101-

        & $python -X utf8 -m freqtrade backtesting `
            --no-color `
            --user-data-dir $userDataDir `
            --config $config `
            --strategy DynamicStakeFreqaiStrategy `
            --strategy-path $strategyPath `
            --freqaimodel MLDLHybridClassifier `
            --timerange 20260101- `
            --breakdown month

        & $python -X utf8 -m freqtrade trade `
            --no-color `
            --user-data-dir $userDataDir `
            --config $config `
            --strategy DynamicStakeFreqaiStrategy `
            --strategy-path $strategyPath `
            --freqaimodel MLDLHybridClassifier `
            --db-url $dbUrl
    } catch {
        Write-Warning $_.Exception.Message
    }
    Start-Sleep -Seconds 30
}
