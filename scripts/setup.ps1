# RASD 360 — installation complète (Windows / PowerShell)
# Prérequis : Python 3.11, Node 20+, Ollama (qwen3:8b), index RAG zippé dans Téléchargements
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> 1/5 Index RAG" -ForegroundColor Cyan
$IndexDir = Join-Path $Root "data\rag_index"
$Zip = Join-Path $env:USERPROFILE "Downloads\rag_index_hackathon_fiscal_douane_v2.zip"
if (-not (Test-Path (Join-Path $IndexDir "faiss_unified.index"))) {
    if (-not (Test-Path $Zip)) { throw "Index introuvable : $Zip" }
    New-Item -ItemType Directory -Force $IndexDir | Out-Null
    Expand-Archive -Path $Zip -DestinationPath $IndexDir -Force
    Write-Host "    Index dézippé dans $IndexDir"
} else { Write-Host "    Index déjà présent" }

Write-Host "==> 2/5 Environnement Python (backend\.venv)" -ForegroundColor Cyan
$Venv = Join-Path $Root "backend\.venv"
if (-not (Test-Path "$Venv\Scripts\python.exe")) { py -3.11 -m venv $Venv }
$Py = "$Venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip -q
# PyTorch CPU : les embeddings des questions tournent sur CPU pour laisser la VRAM à Ollama
& $Py -m pip install torch --index-url https://download.pytorch.org/whl/cpu -q
& $Py -m pip install -r backend\requirements.txt -q

Write-Host "==> 3/5 Modèle d'embeddings BAAI/bge-m3 (cache Hugging Face)" -ForegroundColor Cyan
& $Py -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3', device='cpu')"

Write-Host "==> 4/5 Base fictive + scores (seed 42)" -ForegroundColor Cyan
& $Py -m data_gen.generate
& $Py -m app.risk.scoring

Write-Host "==> 5/5 Frontend (npm install)" -ForegroundColor Cyan
Push-Location (Join-Path $Root "frontend")
npm install --no-fund --no-audit
Pop-Location

Write-Host "Installation terminée. Lancer scripts\run_backend.ps1 puis scripts\run_frontend.ps1" -ForegroundColor Green
