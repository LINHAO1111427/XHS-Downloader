[CmdletBinding()]
param(
    [int]$Port = 5557,
    [string]$BindHost = "127.0.0.1",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$browserHost = if ($BindHost -in @("0.0.0.0", "::")) { "127.0.0.1" } else { $BindHost }
$url = "http://${browserHost}:$Port"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$app = Join-Path $PSScriptRoot "web_app.py"
$installDir = Join-Path $PSScriptRoot ".install"
$pidFile = Join-Path $installDir "web-server.pid"
$stdout = Join-Path $installDir "web-server.stdout.log"
$stderr = Join-Path $installDir "web-server.stderr.log"
$dataRoot = Join-Path $PSScriptRoot "Volume"
$tempRoot = Join-Path $dataRoot "Temp"

if ([System.IO.Path]::GetPathRoot($dataRoot) -ieq "C:\") {
    throw "Local data directory must not be on drive C: $dataRoot"
}

New-Item -ItemType Directory -Force -Path $dataRoot, $tempRoot | Out-Null
$env:XHS_LOCAL_DATA_ROOT = $dataRoot
$env:XHS_AI_CONFIG_PATH = Join-Path $dataRoot "ai_config.json"
$env:XHS_AUTH_DB_PATH = Join-Path $dataRoot "users.db"
$env:XHS_KNOWLEDGE_DB_PATH = Join-Path $dataRoot "knowledge.db"
$env:XHS_VIRAL_DB_PATH = Join-Path $dataRoot "viral_notes.db"
$env:XHS_FEISHU_CORPUS_PATH = Join-Path $PSScriptRoot "output\feishu_export\entries.json"
$env:TEMP = $tempRoot
$env:TMP = $tempRoot

New-Item -ItemType Directory -Force -Path $installDir | Out-Null

function Test-WebService {
    try {
        $response = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 1
        return [bool]$response.ok -and $response.authentication -eq "session"
    }
    catch {
        return $false
    }
}

function Get-ListenerProcessId {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) {
        return [int]$listener.OwningProcess
    }
    return $null
}

if (-not (Test-WebService)) {
    if (Get-ListenerProcessId) {
        throw "Port $Port is occupied by a different or outdated service. Run .\stop-web.ps1 -Port $Port first."
    }
    $startParameters = @{
        FilePath = $python
        ArgumentList = @($app, "--host", $BindHost, "--port", $Port)
        WorkingDirectory = $PSScriptRoot
        WindowStyle = "Hidden"
        RedirectStandardOutput = $stdout
        RedirectStandardError = $stderr
        PassThru = $true
    }
    $process = Start-Process @startParameters
    @{
        ProcessId = $process.Id
        Port = $Port
    } | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding ascii

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
    $listenerProcessId = Get-ListenerProcessId
    @{
        ProcessId = $listenerProcessId
        ParentProcessId = $process.Id
        Port = $Port
    } | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding ascii
}

if (-not $NoBrowser) {
    Start-Process $url
}
Write-Output "XHS-Downloader Web is running at $url"
