# Starts the paper copy desk on this machine: the control-room API (which
# serves the web frontend and the Copy trade page) and the copy daemon, then
# opens the desk in the browser. Idempotent: whatever already runs is left
# alone. Stop the daemon by creating data\copy_trader.stop (or -StopDaemon);
# stop the API with Ctrl+C in its window or -StopApi.
#
#   powershell -ExecutionPolicy Bypass -File scripts\start_paper_desk.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start_paper_desk.ps1 -NoDaemon
#   powershell -ExecutionPolicy Bypass -File scripts\start_paper_desk.ps1 -StopDaemon
#
# The venv interpreter is used when it exists (.venv\Scripts\python.exe); the
# bare "python" on this machine is the Store stub without the dependencies.

param(
    [int]$Port = 8787,
    [switch]$NoDaemon,
    [switch]$NoBrowser,
    [switch]$StopDaemon,
    [switch]$StopApi
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $Venv) { $python = $Venv } else { $python = (Get-Command python).Source }
$DataDir = Join-Path $ProjectRoot "data"
$StopFile = Join-Path $DataDir "copy_trader.stop"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

function Get-PyProcs([string]$needle) {
    Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*$needle*" }
}

if ($StopDaemon) {
    New-Item -ItemType File -Force -Path $StopFile | Out-Null
    Write-Output "stop file written: $StopFile (the daemon exits on its next loop)"
    return
}
if ($StopApi) {
    $api = Get-PyProcs "api\server.py"
    if ($api) { $api | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Write-Output "API stopped" } else { Write-Output "no API process found" }
    return
}

# --- API + frontend ----------------------------------------------------------
$apiRunning = Get-PyProcs "api\server.py"
if ($apiRunning) {
    Write-Output "API already running (pid $($apiRunning[0].ProcessId))"
} else {
    $env:API_PORT = "$Port"
    Start-Process -FilePath $python -ArgumentList @("api\server.py") -WorkingDirectory $ProjectRoot -WindowStyle Minimized `
        -RedirectStandardOutput (Join-Path $DataDir "api.out.log") -RedirectStandardError (Join-Path $DataDir "api.err.log")
    Write-Output "API starting on http://127.0.0.1:$Port (logs: data\api.out.log / api.err.log)"
}

# --- copy daemon -------------------------------------------------------------
if (-not $NoDaemon) {
    $daemon = Get-PyProcs "run_copy_trader.py"
    if ($daemon) {
        Write-Output "copy daemon already running (pid $($daemon[0].ProcessId))"
    } else {
        if (Test-Path $StopFile) { Remove-Item -LiteralPath $StopFile -Force }
        $args = @(
            "-u", "scripts\run_copy_trader.py",
            "--api-interval", "30",
            "--settlement-interval", "90",
            "--min-copy-notional", "0",
            "--db", (Join-Path $DataDir "copy_trading.sqlite"),
            "--status-file", (Join-Path $DataDir "copy_trader_status.json"),
            "--stop-file", $StopFile
        )
        Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $ProjectRoot -WindowStyle Minimized `
            -RedirectStandardOutput (Join-Path $DataDir "copy_trader.out.log") -RedirectStandardError (Join-Path $DataDir "copy_trader.err.log")
        Write-Output "copy daemon starting (status: data\copy_trader_status.json, logs: data\copy_trader.*.log)"
    }
}

# --- open the desk -----------------------------------------------------------
$url = "http://127.0.0.1:$Port/#copy"
if (-not $NoBrowser) {
    $deadline = (Get-Date).AddSeconds(25)
    $ready = $false
    while ((Get-Date) -lt $deadline -and -not $ready) {
        try { $null = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2; $ready = $true } catch { Start-Sleep -Milliseconds 800 }
    }
    if ($ready) { Start-Process $url } else { Write-Output "API not answering yet - open $url once data\api.err.log is quiet" }
}
Write-Output "desk: $url"
