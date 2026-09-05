[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Link
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$inputText = ($Link -join " ").Trim()

if (-not $inputText) {
    throw "Please provide a Xiaohongshu note or share link."
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$main = Join-Path $PSScriptRoot "main.py"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The installed Python environment is missing: $python"
}

Push-Location $PSScriptRoot
try {
    & $python $main --url $inputText
    $exitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

exit $exitCode
