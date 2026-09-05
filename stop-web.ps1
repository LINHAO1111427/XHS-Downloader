[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$pidFile = Join-Path $PSScriptRoot ".install\web-server.pid"

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Output "No managed XHS-Downloader Web process is recorded."
    exit 0
}

$processId = [int](Get-Content -Raw -LiteralPath $pidFile)
$process = Get-Process -Id $processId -ErrorAction SilentlyContinue
if ($process) {
    Stop-Process -Id $processId
    [void]$process.WaitForExit(10000)
}
Remove-Item -LiteralPath $pidFile -Force
Write-Output "XHS-Downloader Web stopped."
