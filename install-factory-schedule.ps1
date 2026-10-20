[CmdletBinding()]
param([switch]$Remove)

$ErrorActionPreference = "Stop"
$taskName = "XHS-Downloader-ContentFactory"
$scriptPath = Join-Path $PSScriptRoot "start-web.ps1"
$arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -File `"$scriptPath`" -NoBrowser"
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
$shortcutPath = Join-Path ([Environment]::GetFolderPath("Startup")) "XHS Content Factory.lnk"
$shortcutShell = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $shortcutPath) {
    $existingShortcut = $shortcutShell.CreateShortcut($shortcutPath)
    if ($existingShortcut.Arguments -ne $arguments) { throw "A different workspace owns the startup shortcut." }
}
if ($existing -and ($existing.Actions.Arguments -notcontains $arguments)) {
    throw "A different workspace already owns the content factory task."
}
if ($Remove) {
    if ($existing) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
    if (Test-Path -LiteralPath $shortcutPath) { Remove-Item -LiteralPath $shortcutPath }
    Write-Output "Content factory startup task removed."
    exit 0
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $PSScriptRoot
$triggers = @(
    (New-ScheduledTaskTrigger -Daily -At "08:55"),
    (New-ScheduledTaskTrigger -AtLogOn -User $identity)
)
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Principal $principal `
        -Settings $settings -Description "Start local XHS content factory at sign-in and daily 08:55; generation plans are managed inside the app." -Force -ErrorAction Stop | Out-Null
}
catch {
    # Current-user Startup works without the Task Scheduler registration privilege.
    $shortcut = $shortcutShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = "Start the local content factory after sign-in; daily plans run inside the app."
    $shortcut.Save()
    $check = $shortcutShell.CreateShortcut($shortcutPath)
    if ($check.Arguments -ne $arguments) { throw "Startup shortcut verification failed." }
    @{ mode = "current_user_startup"; path = $shortcutPath; app_schedule = "09:00 Asia/Shanghai"; task_scheduler_result = "Access denied" } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot "output/account-factory/startup-integration.json") -Encoding UTF8
    Write-Output "Content factory startup shortcut installed and reopened; daily schedule runs inside the app."
    exit 0
}
$saved = Get-ScheduledTask -TaskName $taskName
if ($saved.Actions.Arguments -notcontains $arguments -or $saved.Triggers.Count -ne 2) {
    throw "Content factory startup task verification failed."
}
Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $PSScriptRoot "output/account-factory/WindowsTask.xml") -Encoding UTF8
@{ mode = "scheduled_task"; task_name = $taskName; app_schedule = "09:00 Asia/Shanghai" } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot "output/account-factory/startup-integration.json") -Encoding UTF8
Write-Output "Content factory startup task installed: daily 08:55 and current-user sign-in."
