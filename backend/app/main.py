"""RASD 360 — API FastAPI (routes et CORS)."""
from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
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
        from .rag.retriever import get_retriever

        get_retriever()  # index BM25
        if llm.prechauffer():
            log.info("Modèle %s chargé en mémoire GPU", config.LLM_MODEL)
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
                tri: str = "priorite", page: int = Query(1, ge=1), taille: int = Query(50, ge=1, le=500),
                type: str | None = None, nat: str | None = None) -> dict:  # noqa: A002 - noms des paramètres de requête
    _exiger_base()
    if nat and services.nat.niveau(nat) is None:
        raise HTTPException(422, "Code NAT invalide : section (G), division (46), groupe (46.5) ou classe (46.52)")
    return services.liste(categorie, secteur, gouvernorat, regle, q, montant_min, tri, page, taille, type, nat)


@app.get("/api/entreprises.csv", response_class=PlainTextResponse)
def entreprises_csv(categorie: str | None = None, secteur: str | None = None, gouvernorat: str | None = None,
                    regle: str | None = None, q: str | None = None, montant_min: float | None = None, tri: str = "priorite",
                    type: str | None = None, nat: str | None = None):  # noqa: A002
    _exiger_base()
    contenu = services.liste_csv(categorie=categorie, secteur=secteur, gouvernorat=gouvernorat, regle=regle, q=q,
                                 montant_min=montant_min, tri=tri, type_=type, nat_=nat)
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


# ============================================================================ dossier de contrôle (T3)
class DemandeDossier(BaseModel):
    agent: str = "agent.demo"
    stream: bool = False


@app.post("/api/entreprises/{eid}/dossier")
def generer_dossier(eid: int, req: DemandeDossier | None = None):
    from .dossier import generator

    _exiger_base()
    req = req or DemandeDossier()
    ctx = services.contexte()
    if eid not in ctx.ent.index:
        raise HTTPException(404, "Entreprise inconnue")

    def evenements():
        for ev in generator.generer_flux(ctx, eid, req.agent):
            if ev["type"] == "dossier":
                services.audit("generation_dossier", f"dossier:{ev['dossier']['id']}", req.agent,
                               {"entreprise_id": eid, "source": ev["dossier"]["contenu"]["generation"]["source"]})
            yield ev

    if req.stream:
        return StreamingResponse((json.dumps(ev, ensure_ascii=False) + "\n" for ev in evenements()),
                                 media_type="application/x-ndjson")
    for ev in evenements():
        if ev["type"] == "dossier":
            return ev["dossier"]
        if ev["type"] == "erreur":
            raise HTTPException(422, ev["message"])
    raise HTTPException(500, "Génération interrompue")


@app.get("/api/dossiers")
def lister_dossiers(entreprise_id: int | None = None) -> list[dict]:
    from .dossier import generator

    return generator.lister(entreprise_id)


@app.get("/api/dossiers/{did}")
def lire_dossier(did: int, x_agent: str | None = Header(None)) -> dict:
    from .dossier import generator

    d = generator.lire(did)
    if d is None:
        raise HTTPException(404, "Dossier introuvable")
    services.audit("consultation_dossier", f"dossier:{did}", x_agent or "agent.demo")
    return d


class MajDossier(BaseModel):
    synthese: list[str] | None = None
    documents: dict[str, list[str]] | None = None  # par administration : {"dgi": [...], "douane": [...]}
    lettres: dict[str, dict] | None = None  # par administration : {"dgi": {"objet", "corps"}, ...}
    agent: str | None = None
    statut: Literal["brouillon", "valide"] | None = None


@app.put("/api/dossiers/{did}")
def modifier_dossier(did: int, maj: MajDossier) -> dict:
    from .dossier import generator

    agent = maj.agent or "agent.demo"
    try:
        d = generator.modifier(did, maj.model_dump(exclude_none=True), agent)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    if d is None:
        raise HTTPException(404, "Dossier introuvable")
    services.audit("validation_dossier" if maj.statut == "valide" else "modification_dossier", f"dossier:{did}", agent)
    return d


@app.get("/api/dossiers/{did}/pdf")
def pdf_dossier(did: int, x_agent: str | None = Header(None)):
    from fastapi.responses import Response

    from .dossier import export, generator

    d = generator.lire(did)
    if d is None:
        raise HTTPException(404, "Dossier introuvable")
    contenu = export.pdf(d)
    services.audit("export_pdf", f"dossier:{did}", x_agent or "agent.demo")
    nom = f"RASD360_{d['contenu']['entete'].get('reference', did)}.pdf"
    return Response(contenu, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nom}"'})


class ActionArticle(BaseModel):
    record_id: str = Field(..., min_length=1)
    motif: str = ""  # contrôlé côté métier (10 caractères au moins), pour un message d'erreur explicite
    agent: str = "agent.demo"
    partie: Literal["dgi", "douane"] | None = None  # ajout : administration concernée (dossier conjoint)


class DemandeLettre(BaseModel):
    agent: str = "agent.demo"


def _editer(did: int, fn, *args) -> dict:
    from .dossier.edition import ErreurEdition

    try:
        return fn(did, *args)
    except ErreurEdition as exc:
        raise HTTPException(422, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/dossiers/{did}/articles/recherche")
def rechercher_article(did: int, q: str = Query(..., min_length=2, max_length=200)) -> list[dict]:
    from .dossier import edition

    return _editer(did, edition.rechercher, q)


@app.post("/api/dossiers/{did}/articles")
def ajouter_article(did: int, req: ActionArticle) -> dict:
    from .dossier import edition

    d = _editer(did, edition.ajouter, req.record_id, req.motif, req.agent, req.partie)
    services.audit("ajout_article", f"dossier:{did}", req.agent, {"record_id": req.record_id, "motif": req.motif})
    return d


@app.post("/api/dossiers/{did}/articles/retrait")
def retirer_article(did: int, req: ActionArticle) -> dict:
    from .dossier import edition

    d = _editer(did, edition.retirer, req.record_id, req.motif, req.agent)
    services.audit("retrait_article", f"dossier:{did}", req.agent, {"record_id": req.record_id, "motif": req.motif})
    return d


@app.post("/api/dossiers/{did}/articles/retablissement")
def retablir_article(did: int, req: ActionArticle) -> dict:
    from .dossier import edition

    d = _editer(did, edition.retablir, req.record_id, req.motif, req.agent)
    services.audit("retablissement_article", f"dossier:{did}", req.agent, {"record_id": req.record_id, "motif": req.motif})
    return d


@app.post("/api/dossiers/{did}/lettre/regeneration")
def regenerer_lettre(did: int, req: DemandeLettre | None = None) -> dict:
    from .dossier import edition

    req = req or DemandeLettre()
    d = _editer(did, edition.regenerer_lettre, req.agent)
    services.audit("regeneration_lettre", f"dossier:{did}", req.agent)
    return d


@app.get("/api/dossiers/{did}/historique")
def historique_dossier(did: int) -> list[dict]:
    from .dossier import generator, journal

    d = generator.lire(did)
    if d is None:
        raise HTTPException(404, "Dossier introuvable")
    return journal.historique(did, depuis=d["cree_le"])


# ============================================================================ assistant réglementaire (T9)
class ChatRequete(BaseModel):
    question: str = Field(..., min_length=2, max_length=2000)
    mode: Literal["contribuable", "agent"] = "contribuable"
    langue: Literal["fr", "ar", "tn"] = "fr"
    historique: list[dict] = Field(default_factory=list)
    stream: bool = True


@app.post("/api/chat")
def chat(req: ChatRequete):
    from .chat import assistant

    if _startup["index_error"]:
        raise HTTPException(503, "Index RAG indisponible")
    if not req.stream:
        return assistant.repondre(req.question, req.mode, req.langue, req.historique)

    def flux():
        try:
            for ev in assistant.repondre_flux(req.question, req.mode, req.langue, req.historique):
                yield json.dumps(ev, ensure_ascii=False) + "\n"
        except Exception as exc:  # noqa: BLE001
            log.exception("Erreur de l'assistant")
            yield json.dumps({"type": "erreur", "message": f"Erreur interne : {exc}"}, ensure_ascii=False) + "\n"

    return StreamingResponse(flux(), media_type="application/x-ndjson")


@app.get("/api/chat/exemples")
def chat_exemples() -> list[dict]:
    from .chat.assistant import EXEMPLES

    return EXEMPLES


@app.get("/api/rag/record/{rid}")
def rag_record(rid: str) -> dict:
    from .rag.index import strip_header

    r = get_index().get(rid)
    if r is None:
        raise HTTPException(404, "Record introuvable dans l'index")
    return {"id": r["id"], "source_id": r["source_id"], "document": r.get("source_title"), "section": r.get("section"),
            "article": r.get("article_number") or r.get("article_label"), "page": r.get("pdf_page"), "page_fin": r.get("pdf_page_end"),
            "locator": r.get("locator"), "chunk_type": r.get("chunk_type"), "texte": strip_header(r.get("content", ""))}


@app.get("/api/rag/sources")
def rag_sources() -> dict:
    rag = get_index()
    titres = rag.source_titles()
    notes = {"code_douanes_2016": "Édition 2016", "cdpf_2024": "Mis à jour au 1er janvier 2024"}
    return {"sources": [{"source_id": k, "titre": titres.get(k, k), "records": v, "note": notes.get(k)} for k, v in rag.sources.items()],
            "non_couverts": ["Code de la TVA", "Code de l'IRPP et de l'IS"], "mis_a_jour": rag.manifest.get("updated_utc")}


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
