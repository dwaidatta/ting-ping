$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

$venvPath = Join-Path $PSScriptRoot ".venv"
$activateScript = Join-Path $venvPath "Scripts\Activate.ps1"

if (-not (Test-Path $activateScript)) {
    Write-Error "Virtual environment not found at '$venvPath'. Create it with: python -m venv .venv"
}

& $activateScript
python run.py