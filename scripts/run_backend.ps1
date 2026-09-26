# RASD 360 — démarre l'API FastAPI sur http://127.0.0.1:8000
$ErrorActionPreference = "Stop"
$Racine = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Racine "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "Environnement Python absent : lancer d'abord scripts\setup.ps1" }
Set-Location (Join-Path $Racine "backend")
$env:PYTHONPATH = "$Racine;$Racine\backend"
$env:PYTHONIOENCODING = "utf-8"
Write-Host "RASD 360 — API sur http://127.0.0.1:8000 (documentation : /docs). Ctrl+C pour arrêter." -ForegroundColor Cyan
& $Py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
