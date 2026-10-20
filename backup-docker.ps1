[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$compose = Join-Path $PSScriptRoot "deploy\compose.personal.yml"
$backupRoot = Join-Path $PSScriptRoot "Backups"
$stamp = "docker-" + (Get-Date -Format "yyyyMMdd-HHmmss")
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
& docker compose -f $compose stop app
if ($LASTEXITCODE -ne 0) { throw "Stop failed; no snapshot taken." }
try {
    & docker compose -f $compose run --rm --no-deps -v "${backupRoot}:/backups" app python server_admin.py backup --data-root /data --destination "/backups/$stamp"
    if ($LASTEXITCODE -ne 0) { throw "Backup or verification failed." }
    Write-Output "Verified backup: $(Join-Path $backupRoot $stamp)"
}
finally {
    & docker compose -f $compose up -d --wait --wait-timeout 120 app
    if ($LASTEXITCODE -ne 0) { throw "Application restart failed; check docker compose logs." }
}
