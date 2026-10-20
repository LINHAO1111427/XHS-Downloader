[CmdletBinding()]
param(
    [int]$Port = 5557,
    [string]$BindHost = "127.0.0.1",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot ".install\docker-mode.json")) {
    if ($Port -ne 5557 -or $BindHost -ne "127.0.0.1") { throw "Docker mode uses http://127.0.0.1:5557 (deploy/compose.personal.yml)." }
    & docker compose -f (Join-Path $PSScriptRoot "deploy\compose.personal.yml") up -d --wait --wait-timeout 120 app
    if ($LASTEXITCODE -ne 0) { throw "Docker application startup failed." }
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:5557" }
    Write-Output "XHS-Downloader Docker is running at http://127.0.0.1:5557"
    exit 0
}
$browserHost = if ($BindHost -in @("0.0.0.0", "::")) { "127.0.0.1" } else { $BindHost }
$url = "http://${browserHost}:$Port"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$app = Join-Path $PSScriptRoot "web_app.py"
$expectedWebAppSha256 = (Get-FileHash -LiteralPath $app -Algorithm SHA256).Hash
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
# Gateway resolves the active Codex provider; do not pin an obsolete relay here.
$savedAiConfig = $null
if (Test-Path -LiteralPath $env:XHS_AI_CONFIG_PATH) {
    try { $savedAiConfig = Get-Content -LiteralPath $env:XHS_AI_CONFIG_PATH -Raw | ConvertFrom-Json } catch { $savedAiConfig = $null }
}
if ($savedAiConfig.relay_source -ne "codex" -and -not $env:XHS_CODEX_RELAY_BASE_URL) {
    $env:XHS_CODEX_RELAY_BASE_URL = "http://127.0.0.1:8088/v1"
}
if ($savedAiConfig.relay_source -ne "codex" -and -not $env:XHS_CODEX_RELAY_API_KEY) {
    $env:XHS_CODEX_RELAY_API_KEY = if ($env:SUB2API_API_KEY) { $env:SUB2API_API_KEY } else { $savedAiConfig.api_key }
}
if ($savedAiConfig.relay_source -ne "codex" -and -not $env:XHS_CODEX_RELAY_MODEL) {
    $env:XHS_CODEX_RELAY_MODEL = if ($env:SUB2API_MODEL) { $env:SUB2API_MODEL } elseif ($savedAiConfig.model) { $savedAiConfig.model } else { "gpt-5.6-sol" }
}
$env:XHS_AUTH_DB_PATH = Join-Path $dataRoot "users.db"
$env:XHS_KNOWLEDGE_DB_PATH = Join-Path $dataRoot "knowledge.db"
$env:XHS_VIRAL_DB_PATH = Join-Path $dataRoot "viral_notes.db"
$env:XHS_OPERATION_DB_PATH = Join-Path $dataRoot "xhs_operations.db"
$env:XHS_FEISHU_CORPUS_PATH = Join-Path $PSScriptRoot "output\feishu_export\entries.json"
$env:TEMP = $tempRoot
$env:TMP = $tempRoot
# PowerShell can inherit both PATH and Path from the host; Start-Process
# rejects that duplicate case-insensitive environment key.
$processPath = $env:Path
Remove-Item Env:PATH -ErrorAction SilentlyContinue
[Environment]::SetEnvironmentVariable("Path", $processPath, "Process")

New-Item -ItemType Directory -Force -Path $installDir | Out-Null

function Get-WebService {
    try {
        return Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 1
    }
    catch {
        return $null
    }
}

function Test-WebService {
    $response = Get-WebService
    return [bool]$response.ok `
        -and $response.service -eq "XHS-Downloader Web" `
        -and $response.authentication -eq "session" `
        -and $response.web_app_sha256 -eq $expectedWebAppSha256
}

function Get-ListenerProcessId {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($listener) {
        return [int]$listener.OwningProcess
    }
    return $null
}

$runningService = Get-WebService
$runningServiceMatches = [bool]$runningService.ok `
    -and $runningService.service -eq "XHS-Downloader Web" `
    -and $runningService.authentication -eq "session"
if ($runningServiceMatches -and $runningService.web_app_sha256 -ne $expectedWebAppSha256) {
    Write-Output "Detected an outdated XHS-Downloader Web backend; restarting it now."
    & (Join-Path $PSScriptRoot "stop-web.ps1") -Port $Port
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
