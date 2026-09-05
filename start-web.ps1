[CmdletBinding()]
param(
    [int]$Port = 5557
)

$ErrorActionPreference = "Stop"
$hostName = "127.0.0.1"
$url = "http://${hostName}:$Port"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$app = Join-Path $PSScriptRoot "web_app.py"
$installDir = Join-Path $PSScriptRoot ".install"
$pidFile = Join-Path $installDir "web-server.pid"
$stdout = Join-Path $installDir "web-server.stdout.log"
$stderr = Join-Path $installDir "web-server.stderr.log"

New-Item -ItemType Directory -Force -Path $installDir | Out-Null

function Test-WebService {
    try {
        $response = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 1
        return [bool]$response.ok
    }
    catch {
        return $false
    }
}

if (-not (Test-WebService)) {
    $startParameters = @{
        FilePath = $python
        ArgumentList = @($app, "--host", $hostName, "--port", $Port)
        WorkingDirectory = $PSScriptRoot
        WindowStyle = "Hidden"
        RedirectStandardOutput = $stdout
        RedirectStandardError = $stderr
        PassThru = $true
    }
    $process = Start-Process @startParameters
    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ascii

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt += 1) {
        Start-Sleep -Milliseconds 500
        if (Test-WebService) {
            $ready = $true
            break
        }
        if ($process.HasExited) {
            break
        }
    }
    if (-not $ready) {
        throw "Web service failed to start. See $stderr"
    }
}

Start-Process $url
Write-Output "XHS-Downloader Web is running at $url"
