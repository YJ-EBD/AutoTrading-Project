$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
$python = Resolve-Path (Join-Path $root "runtime\llm_venv\Scripts\python.exe")
$workdir = Resolve-Path (Join-Path $root "vendor\binance-anthropic-trading-bot")
$runtimeConfig = Resolve-Path (Join-Path $root "runtime\llm\config.json")
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Remove-Item Env:HTTP_PROXY, Env:HTTPS_PROXY, Env:ALL_PROXY -ErrorAction SilentlyContinue

while ($true) {
    $entered = $false
    try {
        Copy-Item $runtimeConfig (Join-Path $workdir "config.json") -Force
        Push-Location $workdir
        $entered = $true
        & $python main.py
        Pop-Location
    } catch {
        if ($entered) {
            Pop-Location
        }
        Write-Warning $_.Exception.Message
    }
    Start-Sleep -Seconds 30
}
