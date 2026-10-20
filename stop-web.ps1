[CmdletBinding()]
param(
    [int]$Port = 5557
)

$ErrorActionPreference = "Stop"
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot ".install\docker-mode.json")) {
    & docker compose -f (Join-Path $PSScriptRoot "deploy\compose.personal.yml") stop app
    if ($LASTEXITCODE -ne 0) { throw "Docker application stop failed." }
    Write-Output "XHS-Downloader Docker stopped. Persistent data retained."
    exit 0
}
$pidFile = Join-Path $PSScriptRoot ".install\web-server.pid"

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output "No managed XHS-Downloader Web process is recorded."
    exit 0
}

$recordContent = Get-Content -Raw -LiteralPath $pidFile
try {
    $record = $recordContent | ConvertFrom-Json
    if ($record.PSObject.Properties.Name -contains "ProcessId") {
        $recordedProcessId = [int]$record.ProcessId
        $parentProcessId = [int]$record.ParentProcessId
        $Port = [int]$record.Port
    }
    else {
        $recordedProcessId = [int]$record
        $parentProcessId = 0
    }
}
catch {
    throw "Invalid web server process record: $pidFile"
}

$processIds = @($recordedProcessId, $parentProcessId)
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($listener) {
    $processIds += [int]$listener.OwningProcess
}

$stopped = 0
foreach ($processId in $processIds | Where-Object { $_ -gt 0 } | Select-Object -Unique) {
    $details = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    if (-not $details -or $details.CommandLine -notlike "*web_app.py*") {
        continue
    }
    Stop-Process -Id $processId -Force
    $stopped += 1
}
Remove-Item -LiteralPath $pidFile -Force
Write-Output "XHS-Downloader Web stopped ($stopped processes)."
