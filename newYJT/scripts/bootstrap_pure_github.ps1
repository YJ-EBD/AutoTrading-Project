$ErrorActionPreference = "Continue"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Start-VendorLoop {
    param(
        [string]$Pattern,
        [string]$ScriptPath,
        [string]$StdoutPath,
        [string]$StderrPath
    )

    $existing = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match "powershell" -and $_.CommandLine -match [regex]::Escape($Pattern)
    }

    if (-not $existing) {
        Start-Process powershell -ArgumentList @(
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            $ScriptPath
        ) -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath | Out-Null
    }
}

while ($true) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\setup_freqtrade_vendor_env.ps1")
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\setup_finrl_vendor_env.ps1")
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\setup_llm_vendor_env.ps1")
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\prepare_freqtrade_runtime.ps1")
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\prepare_finrl_runtime.ps1")
    & powershell -ExecutionPolicy Bypass -File (Join-Path $root "scripts\prepare_llm_runtime.ps1")

    Start-VendorLoop `
        -Pattern "newYJT\\scripts\\run_freqtrade_vendor_loop.ps1" `
        -ScriptPath (Join-Path $root "scripts\run_freqtrade_vendor_loop.ps1") `
        -StdoutPath (Join-Path $root "runtime\logs\freqtrade_loop_stdout.log") `
        -StderrPath (Join-Path $root "runtime\logs\freqtrade_loop_stderr.log")

    Start-VendorLoop `
        -Pattern "newYJT\\scripts\\run_finrl_vendor_loop.ps1" `
        -ScriptPath (Join-Path $root "scripts\run_finrl_vendor_loop.ps1") `
        -StdoutPath (Join-Path $root "runtime\logs\finrl_loop_stdout.log") `
        -StderrPath (Join-Path $root "runtime\logs\finrl_loop_stderr.log")

    Start-VendorLoop `
        -Pattern "newYJT\\scripts\\run_llm_vendor_loop.ps1" `
        -ScriptPath (Join-Path $root "scripts\run_llm_vendor_loop.ps1") `
        -StdoutPath (Join-Path $root "runtime\logs\llm_loop_stdout.log") `
        -StderrPath (Join-Path $root "runtime\logs\llm_loop_stderr.log")

    Start-Sleep -Seconds 30
}
