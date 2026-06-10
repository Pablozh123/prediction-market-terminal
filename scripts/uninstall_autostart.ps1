# Removes the Scheduled Tasks registered by scripts/install_autostart.ps1.

foreach ($name in "MarketIntelTerminal", "MarketIntelCopyDaemon", "MarketIntelAlertScanner") {
    try {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction Stop
        Write-Output "removed $name"
    } catch {
        Write-Output "$name not registered"
    }
}
