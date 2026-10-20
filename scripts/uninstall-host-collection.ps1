$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$stateDirectory = Join-Path $projectRoot '.install\host-discovery'
$taskName = 'XHS-Host-Discovery'
$daemon = Join-Path $PSScriptRoot 'host_collection_daemon.py'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task -and ($task.Actions.Arguments -join ' ') -like ('*' + (Join-Path $PSScriptRoot 'run_host_collection.py') + '*')) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
$statusPath = Join-Path $stateDirectory 'daemon-status.json'
if (Test-Path -LiteralPath $statusPath) {
    $status = Get-Content -Raw -Encoding UTF8 -LiteralPath $statusPath | ConvertFrom-Json
    $daemonPid = [int]$status.pid
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $daemonPid" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -like ('*' + $daemon + '*')) { Stop-Process -Id $daemonPid }
}
$backup = Join-Path $stateDirectory 'startup-before.json'
if (Test-Path -LiteralPath $backup) {
    $previous = Get-Content -Raw -Encoding UTF8 -LiteralPath $backup | ConvertFrom-Json
    $property = (Get-ItemProperty -LiteralPath $previous.key).PSObject.Properties[$taskName]
    if ($property -and $property.Value.Contains($daemon)) {
        if ($null -eq $previous.value) { Remove-ItemProperty -LiteralPath $previous.key -Name $taskName }
        else { Set-ItemProperty -LiteralPath $previous.key -Name $taskName -Value $previous.value }
    }
}
Write-Output 'Host collection scheduling removed. Saved observations and source files are preserved.'
