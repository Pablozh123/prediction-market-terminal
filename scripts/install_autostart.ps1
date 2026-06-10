# Registers user-logon Scheduled Tasks so the terminal survives reboots:
#   MarketIntelTerminal    - Streamlit app on http://127.0.0.1:8503
#   MarketIntelCopyDaemon  - paper copy-trading daemon (scripts/run_copy_trader.py)
#   MarketIntelAlertScanner- background alert scanner (scripts/run_alert_scanner.py)
# Remove again with scripts/uninstall_autostart.ps1. No admin rights required.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source

$tasks = @(
    @{ Name = "MarketIntelTerminal";     Args = "-m streamlit run prediction_terminal.py --server.address=127.0.0.1 --server.port=8503" },
    @{ Name = "MarketIntelCopyDaemon";   Args = "scripts\run_copy_trader.py" },
    @{ Name = "MarketIntelAlertScanner"; Args = "scripts\run_alert_scanner.py" }
)

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 2) -StartWhenAvailable

foreach ($task in $tasks) {
    $action = New-ScheduledTaskAction -Execute $python -Argument $task.Args -WorkingDirectory $repo
    Register-ScheduledTask -TaskName $task.Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Output "registered $($task.Name)"
}

Write-Output "Done. Start now without reboot: Start-ScheduledTask -TaskName MarketIntelTerminal (etc.)"
