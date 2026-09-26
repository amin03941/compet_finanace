"""Configuration centrale de RASD 360 : chemins, modèles, seuils et paramètres.

Toutes les valeurs peuvent être surchargées par variables d'environnement
(ou par un fichier `.env` à la racine du projet, voir `.env.example`).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Chargeur .env minimal (évite une dépendance) : CLE=valeur, commentaires ignorés."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT_DIR / ".env")


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


# --- Chemins -----------------------------------------------------------------
DATA_DIR = Path(_env("RASD_DATA_DIR", str(ROOT_DIR / "data")))
RAG_INDEX_DIR = Path(_env("RASD_RAG_INDEX_DIR", str(DATA_DIR / "rag_index")))
DB_PATH = Path(_env("RASD_DB_PATH", str(DATA_DIR / "rasd.db")))
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.csv"
MODELS_DIR = DATA_DIR / "models"
EXPORTS_DIR = DATA_DIR / "exports"
AUDIT_LOG_PATH = DATA_DIR / "audit.log"

FAISS_INDEX_FILE = RAG_INDEX_DIR / "faiss_unified.index"
METADATA_FILE = RAG_INDEX_DIR / "metadata_unified.jsonl"
MANIFEST_FILE = RAG_INDEX_DIR / "index_manifest.json"
EMBEDDING_CONFIG_FILE = RAG_INDEX_DIR / "embedding_config.json"
NAT_NOMENCLATURE_FILE = RAG_INDEX_DIR / "data_assets" / "nomenclature_activites_nat2009.csv"
EQUIPEMENTS_FILE = RAG_INDEX_DIR / "data_assets" / "equipements_codes_tarifaires_2017_419.csv"

# --- Embeddings (section 4.4) ------------------------------------------------
EMBED_MODEL_ST = _env("RASD_EMBED_MODEL", "BAAI/bge-m3")
EMBED_MODEL_OLLAMA = _env("RASD_EMBED_MODEL_OLLAMA", "bge-m3:latest")
# "sentence_transformers" (recommandé, CPU) ou "ollama" ; bascule automatique si le test échoue
EMBED_BACKEND = _env("RASD_EMBED_BACKEND", "sentence_transformers")
EMBED_DEVICE = _env("RASD_EMBED_DEVICE", "cpu")
EMBED_COMPAT_SAMPLES = 20
# Chargement du modèle d'embeddings au démarrage de l'API (désactivable pour les tests)
WARMUP_EMBEDDINGS = _env("RASD_WARMUP", "1") == "1"
EMBED_COMPAT_MIN_COSINE = 0.98

# --- LLM local (section 9) ---------------------------------------------------
OLLAMA_URL = _env("RASD_OLLAMA_URL", "http://127.0.0.1:11434")  # 127.0.0.1 : sous Windows, « localhost » tente IPv6 d'abord (+2 s)
LLM_MODEL = _env("RASD_LLM_MODEL", "qwen3:8b")
LLM_MODEL_QUALITY = _env("RASD_LLM_MODEL_QUALITY", "qwen3.5:9b")
LLM_TEMPERATURE = float(_env("RASD_LLM_TEMPERATURE", "0.2"))
LLM_NUM_CTX = int(_env("RASD_LLM_NUM_CTX", "8192"))
LLM_TIMEOUT_S = float(_env("RASD_LLM_TIMEOUT_S", "120"))

# --- Retriever (section 4.5) ------------------------------------------------
RETRIEVER_DENSE_K = 50
RETRIEVER_TOP_K = 8
RETRIEVER_RRF_K = 60
# Seuil d'abstention sur la similarité cosinus du meilleur résultat dense.
# Calibré sur backend/tests/rag_questions.json (voir scripts/calibrate_retriever.py)
RETRIEVER_ABSTAIN_THRESHOLD = float(_env("RASD_ABSTAIN_THRESHOLD", "0.48"))

# --- Données fictives --------------------------------------------------------
SEED = 42
YEARS = (2023, 2024, 2025)
N_ENTREPRISES = int(_env("RASD_N_ENTREPRISES", "2000"))

# --- Paramètres légaux (table `parametres`) ----------------------------------
# a_verifier = True : valeur absente de l'index RAG (code TVA / IS non indexés)
PARAMETRES_DEFAUT = [
    # (cle, valeur, source, a_verifier)
    ("taux_tva_normal", 0.19, "Code de la TVA (non indexé) — à vérifier", True),
    ("taux_is", 0.15, "Code de l'IRPP et de l'IS (non indexé) — à vérifier", True),
    ("taux_avance_impot_import", 0.10, "Hypothèse de simulation — à vérifier", True),
    ("taux_retenue_source", 0.015, "Hypothèse de simulation (taux TEJ) — à vérifier", True),
    ("taux_penalite_retard_mensuel", 0.0125, "CDPF 2024, article 81 (texte indexé)", False),
    ("seuil_montant_alerte_A", 20000.0, "Paramètre RASD 360 (section 6.3)", False),
    ("seuil_fractionnement_dt", 3000.0, "Hypothèse de simulation (seuil de contrôle) — à vérifier", True),
]
