"""RASD 360 — API FastAPI (routes et CORS)."""
from __future__ import annotations

import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import config, db, llm, services
from .rag import embedder
from .rag.index import IndexIntegrityError, get_index

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("rasd")

_startup: dict = {"index_error": None}
_taches: dict = {"reset": {"etat": "inactif"}, "reentrainement": {"etat": "inactif"}}


def _warmup_embedder() -> None:
    try:
        embedder.initialize(get_index())
    except Exception as exc:  # noqa: BLE001
        log.exception("Échec de l'initialisation des embeddings")
        embedder.state().status = "error"
        embedder.state().error = str(exc)
        embedder.state().ready_event.set()


def _scores_presents() -> bool:
    st = db.db_status()
    return st.get("status") == "ok" and st.get("scores", 0) > 0


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        rag = get_index()  # contrôle obligatoire ntotal == lignes de métadonnées
        log.info("Contrôle de l'index OK : ntotal = %d", rag.ntotal)
        if config.WARMUP_EMBEDDINGS:
            threading.Thread(target=_warmup_embedder, name="embedder-warmup", daemon=True).start()
    except IndexIntegrityError as exc:
        _startup["index_error"] = str(exc)
        log.error("INDEX RAG INVALIDE : %s", exc)
    db.create_schema(db.get_engine())  # tables applicatives manquantes (sans rien effacer)
    if db.db_status().get("status") == "ok" and not _scores_presents():
        log.info("Scores absents : calcul initial (règles, modèle, évaluation)…")
        from .risk import scoring
        scoring.calculer()
    yield


app = FastAPI(title="RASD 360 — Radar fiscal et douanier", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


def _exiger_base() -> None:
    if not _scores_presents():
        raise HTTPException(503, "Base de démonstration absente : lancer scripts\\reset_demo.ps1")


# ============================================================================ santé
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


# ============================================================================ ciblage (T20)
@app.get("/api/stats")
def stats() -> dict:
    _exiger_base()
    return services.statistiques()


@app.get("/api/referentiels")
def referentiels() -> dict:
    _exiger_base()
    return services.referentiels()


@app.get("/api/entreprises")
def entreprises(categorie: str | None = None, secteur: str | None = None, gouvernorat: str | None = None,
                regle: str | None = None, q: str | None = None, montant_min: float | None = None,
                tri: str = "priorite", page: int = Query(1, ge=1), taille: int = Query(50, ge=1, le=500)) -> dict:
    _exiger_base()
    return services.liste(categorie, secteur, gouvernorat, regle, q, montant_min, tri, page, taille)


@app.get("/api/entreprises.csv", response_class=PlainTextResponse)
def entreprises_csv(categorie: str | None = None, secteur: str | None = None, gouvernorat: str | None = None,
                    regle: str | None = None, q: str | None = None, montant_min: float | None = None, tri: str = "priorite"):
    _exiger_base()
    contenu = services.liste_csv(categorie=categorie, secteur=secteur, gouvernorat=gouvernorat, regle=regle, q=q,
                                 montant_min=montant_min, tri=tri)
    return PlainTextResponse("﻿" + contenu, media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="rasd360_ciblage.csv"'})


@app.get("/api/entreprises/{eid}")
def entreprise(eid: int, x_agent: str | None = Header(None)) -> dict:
    _exiger_base()
    f = services.fiche(eid)
    if f is None:
        raise HTTPException(404, "Entreprise inconnue")
    services.audit("consultation_fiche", f"entreprise:{eid}", x_agent or "agent.demo")
    return f


@app.get("/api/entreprises/{eid}/preuves/{regle}")
def preuves(eid: int, regle: str) -> dict:
    _exiger_base()
    p = services.preuves(eid, regle)
    if p is None:
        raise HTTPException(404, "Règle inconnue")
    return p


class ResultatControle(BaseModel):
    redressement: bool
    montant: float = Field(0.0, ge=0)
    commentaire: str = ""
    agent: str = "agent.demo"


@app.post("/api/entreprises/{eid}/resultat-controle")
def resultat_controle(eid: int, r: ResultatControle) -> dict:
    _exiger_base()
    out = services.enregistrer_resultat(eid, r.redressement, r.montant, r.commentaire, r.agent)
    services.audit("resultat_controle", f"entreprise:{eid}", r.agent, r.model_dump())
    return out


@app.get("/api/facilitation")
def facilitation() -> dict:
    _exiger_base()
    return services.facilitation()


@app.get("/api/performance")
def performance() -> dict:
    _exiger_base()
    return services.performance()


@app.get("/api/audit")
def audit(limite: int = Query(100, ge=1, le=1000)) -> list[dict]:
    return services.journal(limite)


# ============================================================================ administration
def _tache(nom: str, fn) -> None:
    _taches[nom] = {"etat": "en_cours", "debut": time.time()}
    try:
        resume = fn()
        services.invalider_caches()
        _taches[nom] = {"etat": "termine", "duree_s": round(time.time() - _taches[nom]["debut"], 1), "resume": resume}
    except Exception as exc:  # noqa: BLE001
        log.exception("Échec de la tâche %s", nom)
        _taches[nom] = {"etat": "erreur", "message": str(exc)}


def _reset() -> dict:
    import sys

    sys.path.insert(0, str(config.ROOT_DIR))
    from data_gen.generate import generer

    from .risk import scoring

    db.get_engine().dispose()
    stats = generer()
    return {"generation": stats, "scores": scoring.calculer()}


def _reentrainer() -> dict:
    from .risk import scoring

    return scoring.calculer()


@app.post("/api/admin/reset-demo", status_code=202)
def reset_demo(bg: BackgroundTasks) -> dict:
    if _taches["reset"].get("etat") == "en_cours":
        return {"etat": "en_cours"}
    bg.add_task(_tache, "reset", _reset)
    return {"etat": "lance", "message": "Régénération de la base (seed 42) et recalcul des scores en cours"}


@app.post("/api/admin/reentrainer", status_code=202)
def reentrainer(bg: BackgroundTasks) -> dict:
    _exiger_base()
    if _taches["reentrainement"].get("etat") == "en_cours":
        return {"etat": "en_cours"}
    bg.add_task(_tache, "reentrainement", _reentrainer)
    services.audit("reentrainement", "modele", "agent.demo")
    return {"etat": "lance", "message": "Ré-entraînement avec les résultats de contrôle saisis"}


@app.get("/api/admin/taches")
def taches() -> dict:
    return _taches
