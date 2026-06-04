$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $ProjectRoot "scripts\run_copy_trader.py"
$StopFile = Join-Path $ProjectRoot "data\copy_trader.stop"
$OutLog = Join-Path $ProjectRoot "data\copy_trader.out.log"
$ErrLog = Join-Path $ProjectRoot "data\copy_trader.err.log"

$existing = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
    Where-Object { $_.CommandLine -like "*scripts\run_copy_trader.py*" -or $_.CommandLine -like "*scripts/run_copy_trader.py*" }

if ($existing) {
    exit 0
}

if (Test-Path $StopFile) {
    Remove-Item -LiteralPath $StopFile -Force
}

$python = (Get-Command python).Source
$args = @(
    "-u",
    $Runner,
    "--disable-fast",
    "--api-interval",
    "30",
    "--settlement-interval",
    "180",
    "--db",
    (Join-Path $ProjectRoot "data\copy_trading.sqlite"),
    "--status-file",
    (Join-Path $ProjectRoot "data\copy_trader_status.json"),
    "--stop-file",
    $StopFile
)

Start-Process `
    -FilePath $python `
    -ArgumentList $args `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog
