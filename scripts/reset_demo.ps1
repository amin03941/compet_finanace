# RASD 360 — remet la démo à zéro : régénère la base fictive (seed 42), recalcule scores et métriques.
# Si l'API tourne, la régénération passe par elle (la base SQLite est ouverte) ; sinon elle est lancée directement.
$ErrorActionPreference = "Stop"
$Racine = Split-Path -Parent $PSScriptRoot
$Debut = Get-Date
$Api = "http://127.0.0.1:8000"

$ApiActive = $false
try { Invoke-RestMethod "$Api/api/admin/taches" -TimeoutSec 3 | Out-Null; $ApiActive = $true } catch { }

if ($ApiActive) {
    Write-Host "API détectée : régénération via $Api/api/admin/reset-demo" -ForegroundColor Cyan
    Invoke-RestMethod -Method Post "$Api/api/admin/reset-demo" | Out-Null
    do {
        Start-Sleep -Seconds 3
        $Etat = (Invoke-RestMethod "$Api/api/admin/taches").reset
        Write-Host ("  … {0} ({1:N0} s)" -f $Etat.etat, ((Get-Date) - $Debut).TotalSeconds)
    } while ($Etat.etat -eq "en_cours")
    if ($Etat.etat -ne "termine") { throw "Échec de la régénération : $($Etat.message)" }
} else {
    $Py = Join-Path $Racine "backend\.venv\Scripts\python.exe"
    if (-not (Test-Path $Py)) { throw "Environnement Python absent : lancer d'abord scripts\setup.ps1" }
    $env:PYTHONPATH = "$Racine;$Racine\backend"
    $env:PYTHONIOENCODING = "utf-8"
    Push-Location (Join-Path $Racine "backend")
    Write-Host "==> Génération de la base fictive (seed 42)" -ForegroundColor Cyan
    & $Py -m data_gen.generate | Out-Null
    Write-Host "==> Règles, modèle, scores et métriques" -ForegroundColor Cyan
    & $Py -m app.risk.scoring | Out-Null
    Pop-Location
}
$Duree = [int]((Get-Date) - $Debut).TotalSeconds
Write-Host "Démo remise à zéro en $Duree s : 2 000 entreprises fictives, scores et métriques recalculés." -ForegroundColor Green
