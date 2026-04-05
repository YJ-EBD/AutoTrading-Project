$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match 'powershell|python' -and $_.CommandLine -match [regex]::Escape($root)
} | Select-Object ProcessId, Name, CommandLine

Write-Host "`n--- logs ---"

Get-ChildItem (Join-Path $root "runtime\logs") -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object Name, Length, LastWriteTime
