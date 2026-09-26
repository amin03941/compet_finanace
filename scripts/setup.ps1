# RASD 360 — installation complète (Windows / PowerShell)
# Prérequis : Python 3.11, Node 20+, Ollama (qwen3:8b), index RAG fourni (dossier data\rag_index ou archive -IndexZip)
param([string]$IndexZip = $env:RASD_INDEX_ZIP)
$ErrorActionPreference = "Stop"
$Racine = Split-Path -Parent $PSScriptRoot
Set-Location $Racine
$Debut = Get-Date

Write-Host "==> 1/7 Index RAG (lecture seule)" -ForegroundColor Cyan
$Index = Join-Path $Racine "data\rag_index"
if (-not (Test-Path (Join-Path $Index "faiss_unified.index"))) {
    if (-not $IndexZip -or -not (Test-Path $IndexZip)) {
        throw "Index RAG absent : copiez ses fichiers dans $Index, ou lancez setup.ps1 -IndexZip <chemin de l'archive>"
    }
    New-Item -ItemType Directory -Force $Index | Out-Null
    Expand-Archive -Path $IndexZip -DestinationPath $Index -Force
    Write-Host "    Index dézippé dans $Index"
} else { Write-Host "    Index déjà présent" }

Write-Host "==> 2/7 Environnement Python (backend\.venv)" -ForegroundColor Cyan
$Venv = Join-Path $Racine "backend\.venv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) { py -3.11 -m venv $Venv }
$Py = "$Venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip -q
# PyTorch CPU : les questions sont encodées sur CPU pour laisser les 8 Go de VRAM à Ollama
& $Py -m pip install torch --index-url https://download.pytorch.org/whl/cpu -q
& $Py -m pip install -r backend\requirements.txt -q
$env:PYTHONPATH = "$Racine;$Racine\backend"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "==> 3/7 Modèle d'embeddings BAAI/bge-m3 (cache Hugging Face)" -ForegroundColor Cyan
& $Py -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3', device='cpu')"

Write-Host "==> 4/7 LLM local (Ollama)" -ForegroundColor Cyan
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    $Modeles = (ollama list) -join "`n"
    if ($Modeles -notmatch "qwen3:8b") { ollama pull qwen3:8b }
    Write-Host "    qwen3:8b disponible"
} else { Write-Warning "Ollama absent : l'assistant et la rédaction LLM seront indisponibles (le reste fonctionne)." }

Write-Host "==> 5/7 Base fictive, scores et métriques (seed 42)" -ForegroundColor Cyan
Push-Location backend
& $Py -m data_gen.generate | Out-Null
& $Py -m app.risk.scoring | Out-Null
Write-Host "==> 6/7 Calibration du seuil d'abstention du retriever (20 questions)" -ForegroundColor Cyan
& $Py -m app.rag.calibration | Out-Null
Pop-Location

Write-Host "==> 7/7 Frontend (npm install + build de production)" -ForegroundColor Cyan
Push-Location frontend
npm install --no-fund --no-audit
npm run build
Pop-Location

$Duree = [int]((Get-Date) - $Debut).TotalSeconds
Write-Host "Installation terminée en $Duree s. Lancer scripts\run_backend.ps1 puis scripts\run_frontend.ps1" -ForegroundColor Green
