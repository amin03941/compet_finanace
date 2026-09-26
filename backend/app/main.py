"""RASD 360 — API FastAPI (routes et CORS)."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, db, llm
from .rag import embedder
from .rag.index import IndexIntegrityError, get_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("rasd")

_startup: dict = {"index_error": None}


def _warmup_embedder() -> None:
    try:
        embedder.initialize(get_index())
    except Exception as exc:  # noqa: BLE001
        log.exception("Échec de l'initialisation des embeddings")
        embedder.state().status = "error"
        embedder.state().error = str(exc)
        embedder.state().ready_event.set()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        rag = get_index()  # contrôle obligatoire ntotal == lignes de métadonnées
        log.info("Contrôle de l'index OK : ntotal = %d", rag.ntotal)
        threading.Thread(target=_warmup_embedder, name="embedder-warmup", daemon=True).start()
    except IndexIntegrityError as exc:
        _startup["index_error"] = str(exc)
        log.error("INDEX RAG INVALIDE : %s", exc)
    yield


app = FastAPI(title="RASD 360 — Radar fiscal et douanier", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    if _startup["index_error"]:
        index_info = {"status": "erreur", "message": _startup["index_error"]}
    else:
        rag = get_index()
        index_info = {
            "status": "ok",
            "ntotal": rag.ntotal,
            "metadata_lignes": len(rag.records),
            "dimension": rag.dimension,
            "modele_embeddings": rag.embedding_config.get("embedding_model", config.EMBED_MODEL_ST),
            "sources": rag.sources,
            "mis_a_jour": rag.manifest.get("updated_utc"),
        }
    emb = embedder.state().as_dict()
    ollama = llm.ollama_status()
    base = db.db_status()
    ok = index_info["status"] == "ok" and emb["status"] == "ready" and base.get("status") == "ok"
    return {
        "status": "ok" if ok else "degrade",
        "index": index_info,
        "embeddings": emb,
        "ollama": ollama,
        "base": base,
        "avertissement": "Prototype — données entièrement fictives",
    }
