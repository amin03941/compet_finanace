# RASD 360 — démarre l'interface sur http://localhost:3000
# Par défaut : build de production (rapide pendant la démo). Option -Dev : serveur de développement.
param([switch]$Dev)
$ErrorActionPreference = "Stop"
$Racine = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $Racine "frontend")
if (-not (Test-Path "node_modules")) { npm install --no-fund --no-audit }
if ($Dev) {
    Write-Host "RASD 360 — interface (développement) sur http://localhost:3000" -ForegroundColor Cyan
    npm run dev
} else {
    if (-not (Test-Path ".next\BUILD_ID")) { npm run build }
    Write-Host "RASD 360 — interface sur http://localhost:3000 (API attendue sur http://127.0.0.1:8000)" -ForegroundColor Cyan
    npm run start
}
