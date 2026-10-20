param([string]$At = '09:10')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
$worker = Join-Path $PSScriptRoot 'run_host_collection.py'
if (!(Test-Path -LiteralPath $python) -or !(Test-Path -LiteralPath $worker)) { throw 'Host collector or Python environment is missing.' }
$stateDirectory = Join-Path $projectRoot '.install\host-discovery'
New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
$taskName = 'XHS-Host-Discovery'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Export-ScheduledTask -TaskName $taskName | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $stateDirectory ('task-before-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.xml'))
}
$arguments = '"' + $worker + '" --state-dir "' + $stateDirectory + '"'
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$settings = New-ScheduledTaskSettingsSet -Hidden -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
try {
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Daily public ranks, logged-in keyword search when available, and resumable linked-product collection into the personal XHS app.' -Force | Out-Null
    Export-ScheduledTask -TaskName $taskName | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $stateDirectory 'task.xml')
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    [pscustomobject]@{Task=$taskName;NextRunTime=$info.NextRunTime.ToString('s');Hidden=$true;StateDirectory=$stateDirectory} | ConvertTo-Json
} catch {
    if ($_.Exception.HResult -ne -2147024891 -and $_.Exception.Message -notmatch 'Access is denied|拒绝访问') { throw }
    $daemon = Join-Path $PSScriptRoot 'host_collection_daemon.py'
    $daemonArguments = '"' + $daemon + '" --state-dir "' + $stateDirectory + '" --at ' + $At
    $runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $previousProperty = (Get-ItemProperty -LiteralPath $runKey).PSObject.Properties[$taskName]
    $previous = if ($previousProperty) { $previousProperty.Value } else { $null }
    $backup = Join-Path $stateDirectory 'startup-before.json'
    if (!(Test-Path -LiteralPath $backup)) { @{key=$runKey;name=$taskName;value=$previous} | ConvertTo-Json | Set-Content -LiteralPath $backup -Encoding UTF8 }
    New-ItemProperty -LiteralPath $runKey -Name $taskName -Value ('"' + $python + '" ' + $daemonArguments) -PropertyType String -Force | Out-Null
    $process = Start-Process -FilePath $python -ArgumentList $daemonArguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
    [pscustomobject]@{Mode='current_user_background';DailyAt=$At;Pid=$process.Id;StartupKey=$runKey;StartupName=$taskName;StateDirectory=$stateDirectory;TaskSchedulerError=$_.Exception.Message} | ConvertTo-Json
}
