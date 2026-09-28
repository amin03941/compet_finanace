"""Édition de la liste « Articles applicables » par l'agent : ajout, retrait, rétablissement, régénération de la lettre.

Règles : motif obligatoire (10 caractères au moins) ; seuls des records existants de l'index RAG peuvent être ajoutés
(aucune saisie libre de numéro) ; un article retiré n'est jamais effacé (bloc « articles écartés ») ; chaque action est
inscrite dans l'historique du dossier (ajout seulement) ; un dossier validé n'est plus modifiable.
"""
from __future__ import annotations

import json
from datetime import datetime

from .. import db
from ..rag.index import get_index, normalize_article_number, strip_header
from . import generator
from .articles import article_depuis_record
from .journal import journaliser

MOTIF_MIN = 10


class ErreurEdition(ValueError):
    """Demande refusée (motif trop court, article inconnu, déjà présent…)."""


def _motif(motif: str | None) -> str:
    m = (motif or "").strip()
    if len(m) < MOTIF_MIN:
        raise ErreurEdition(f"Motif obligatoire : au moins {MOTIF_MIN} caractères.")
    return m


def _dossier_modifiable(did: int) -> dict:
    d = generator.lire(did)
    if d is None:
        raise LookupError("Dossier introuvable")
    if d["statut"] == "valide":
        raise PermissionError("Dossier validé : repasser en brouillon pour le modifier")
    return d


def _enregistrer(did: int, contenu: dict, action: str, agent: str, motif: str, article: dict) -> dict:
    """Enregistre la liste modifiée, puis inscrit l'action dans l'historique."""
    contenu["articles_modifies"] = True
    with db.get_engine().begin() as conn:
        conn.execute(db.dossiers.update().where(db.dossiers.c.id == did).values(
            contenu=json.dumps(contenu, ensure_ascii=False), modifie_le=datetime.now().isoformat(timespec="seconds")))
    journaliser(did, action, agent, motif, article["id"], article["article"])
    return generator.lire(did)


def _trace(agent: str, motif: str) -> dict:
    return {"agent": agent, "motif": motif, "le": datetime.now().isoformat(timespec="seconds")}


def retirer(did: int, record_id: str, motif: str, agent: str) -> dict:
    m = _motif(motif)
    d = _dossier_modifiable(did)
    c = d["contenu"]
    a = next((x for x in c["articles"] if x["id"] == record_id), None)
    if a is None:
        raise ErreurEdition("Cet article ne figure pas dans la liste du dossier.")
    c["articles"] = [x for x in c["articles"] if x["id"] != record_id]
    a["retrait"] = _trace(agent, m)
    c["articles_ecartes"].append(a)
    return _enregistrer(did, c, "retrait_article", agent, m, a)


def retablir(did: int, record_id: str, motif: str, agent: str) -> dict:
    m = _motif(motif)
    d = _dossier_modifiable(did)
    c = d["contenu"]
    a = next((x for x in c["articles_ecartes"] if x["id"] == record_id), None)
    if a is None:
        raise ErreurEdition("Cet article ne figure pas parmi les articles écartés.")
    c["articles_ecartes"] = [x for x in c["articles_ecartes"] if x["id"] != record_id]
    a.pop("retrait", None)
    a["retablissement"] = _trace(agent, m)
    c["articles"].append(a)
    return _enregistrer(did, c, "retablissement_article", agent, m, a)


def ajouter(did: int, record_id: str, motif: str, agent: str, partie: str | None = None) -> dict:
    m = _motif(motif)
    d = _dossier_modifiable(did)
    rec = get_index().get(record_id)
    if rec is None:  # aucune saisie libre : seul un record existant de l'index est accepté
        raise ErreurEdition("Article inconnu : seuls les textes présents dans l'index peuvent être ajoutés.")
    c = d["contenu"]
    if any(x["id"] == record_id for x in c["articles"]):
        raise ErreurEdition("Cet article figure déjà dans la liste.")
    if any(x["id"] == record_id for x in c["articles_ecartes"]):
        raise ErreurEdition("Cet article a été écarté : utiliser « Rétablir ».")
    parties = c["entete"]["parties"]
    if partie is not None and partie not in parties:
        raise ErreurEdition("Cette administration n'a pas de partie dans ce dossier.")
    if partie is None:  # dossier conjoint : le code d'origine du texte désigne la partie
        partie = parties[0] if len(parties) == 1 else ("douane" if rec["source_id"] == "code_douanes_2016" else "dgi")
    a = article_depuis_record(rec, m, origine="agent", partie=partie)
    a["ajout"] = _trace(agent, m)
    c["articles"].append(a)
    return _enregistrer(did, c, "ajout_article", agent, m, a)


def regenerer_lettre(did: int, agent: str, utiliser_llm: bool = True) -> dict:
    """Nouvelles lettres (une par administration) rédigées avec la liste FINALE de leurs articles.
    La synthèse, éventuellement retouchée par l'agent, est conservée."""
    d = _dossier_modifiable(did)
    c = d["contenu"]
    sources = []
    for partie, lettre in c["lettres"].items():
        red, source, erreur = generator.rediger(c["entete"], c["ecarts"], c["indices"], c["articles"], c["documents"].get(partie, []),
                                                utiliser_llm, partie=partie)
        lettre.update({"objet": red.lettre.objet, "corps": red.lettre.corps, "source": source, "erreur": erreur,
                       "articles_ids": [a["id"] for a in c["articles"] if a.get("partie") == partie],
                       "regeneree_le": datetime.now().isoformat(timespec="seconds")})
        sources.append(f"{generator.PARTIES[partie]['administration']} {source}")
    with db.get_engine().begin() as conn:
        conn.execute(db.dossiers.update().where(db.dossiers.c.id == did).values(
            contenu=json.dumps(c, ensure_ascii=False), modifie_le=datetime.now().isoformat(timespec="seconds")))
    journaliser(did, "regeneration_lettre", agent, f"Liste de {len(c['articles'])} articles ; rédaction : {', '.join(sources)}")
    return generator.lire(did)


def _numero(rec: dict) -> str | None:
    """Numéro d'article d'un record ; certains codes (douanes) ne l'ont que dans le chemin de section."""
    return normalize_article_number(rec.get("article_number") or rec.get("article_label")
                                    or (rec.get("section") or "").split(" > ")[-1])


def rechercher(did: int, q: str, limite: int = 10) -> list[dict]:
    """Recherche d'un article à ajouter : par numéro (« article 94 ») ou par mots-clés, dans l'index RAG uniquement."""
    from ..rag.retriever import ARTICLE_RE, CODES, get_retriever

    d = generator.lire(did)
    if d is None:
        raise LookupError("Dossier introuvable")
    presents = {a["id"] for a in d["contenu"]["articles"]}
    ecartes = {a["id"] for a in d["contenu"]["articles_ecartes"]}
    rag, r = get_index(), get_retriever()
    trouves: list[tuple[dict, float | None]] = []
    m = ARTICLE_RE.search(q)
    if m:  # par numéro : d'abord l'article du code nommé dans la requête (sinon du CDPF), puis ceux des autres codes
        num = normalize_article_number(m.group(0).replace("art.", "article"))
        source = next((sid for motif, sid, _ in CODES if motif.search(q)), None)
        cands = [rec for rec in rag.records if _numero(rec) == num]
        cands.sort(key=lambda rec: (0 if source and rec["source_id"] == source else 1, 0 if rec["source_id"] == "cdpf_2024" else 1))
        trouves += [(rec, None) for rec in cands]
    rech = r.rechercher(q, top_k=limite)
    trouves += [(res.record, res.score_dense) for res in rech.resultats]
    out, vus = [], set()
    for rec, score in trouves:
        if rec["id"] in vus:
            continue
        vus.add(rec["id"])
        a = article_depuis_record(rec, "", origine="agent")
        out.append({"id": rec["id"], "article": a["article"], "document": a["document"], "source_id": a["source_id"],
                    "edition": a["edition"], "locator": a["locator"], "extrait": strip_header(rec.get("content", "")),
                    "pertinence": round(score, 3) if score is not None else None, "par_numero": score is None,
                    "deja_present": rec["id"] in presents, "ecarte": rec["id"] in ecartes})
        if len(out) >= limite:
            break
    return out
