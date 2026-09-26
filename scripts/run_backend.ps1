# RASD 360 — démarre l'API FastAPI sur http://localhost:8000
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Root "backend")
$env:PYTHONPATH = "$Root;$Root\backend"
& ".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
