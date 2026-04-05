$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Resolve-Path (Join-Path $root "runtime\freqtrade_venv\Scripts\python.exe")
$userDataDir = Join-Path $root "runtime\freqtrade\user_data"

Set-Location $root
New-Item -ItemType Directory -Force -Path `
    runtime\freqtrade,`
    runtime\freqtrade\user_data,`
    runtime\freqtrade\user_data\data,`
    runtime\freqtrade\user_data\strategies,`
    runtime\freqtrade\user_data\backtest_results,`
    runtime\llm,`
    runtime\logs | Out-Null

Copy-Item vendor\freqtrade\freqtrade\templates\FreqaiExampleHybridStrategy.py runtime\freqtrade\user_data\strategies\FreqaiExampleHybridStrategy.py -Force
Copy-Item strategies\DynamicStakeFreqaiStrategy.py runtime\freqtrade\user_data\strategies\DynamicStakeFreqaiStrategy.py -Force
& $python -X utf8 scripts\render_runtime_configs.py | Out-Null
& $python -X utf8 -m freqtrade create-userdir --userdir $userDataDir | Out-Null
