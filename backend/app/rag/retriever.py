"""Recherche hybride (section 4.5) : dense (bge-m3 + FAISS) + BM25, fusion Reciprocal Rank Fusion,
recherche directe d'article, exclusion des lignes tarifaires, abstention calibrée.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

from .. import config
from . import embedder
from .index import RagIndex, get_index, normalize_article_number, strip_header

log = logging.getLogger("rasd.retriever")

TYPES_TARIFAIRES = {"equipment_tariff_row"}
MOTS_TARIFAIRES = re.compile(r"(équipement|equipement|machine|code tarifaire|position tarifaire|nomenclature|tarif douanier"
                             r"|\bngp\b|\bsh\b|\d{4}\.\d{2}|\b\d{6,8}\b|matériel|materiel)", re.I)
ARTICLE_RE = re.compile(r"\bart(?:icle|\.)?s?\s+(premier|\d+)\s*(bis|ter|quater)?\b", re.I)
CODES = [  # (motif, source_id, unité documentaire prioritaire)
    (re.compile(r"droits et proc[ée]dures fiscaux|\bcdpf\b|proc[ée]dures fiscales", re.I), "cdpf_2024", "CODE DES DROITS ET PROCÉDURES FISCAUX"),
    (re.compile(r"code des douanes|douani", re.I), "code_douanes_2016", None),
    (re.compile(r"enregistrement|timbre", re.I), "code_enregistrement_timbre_2025", None),
    (re.compile(r"op[ée]rateur [ée]conomique agr[ée][ée]|\boea\b", re.I), "decret_oea_2018_612", None),
]
MOTS_VIDES = set("""a au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma mais me même mes moi mon ne nos
notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos votre vous c d j l à m n s t y été
est sont être avoir ai as avons avez ont quel quelle quels quelles comment combien est-ce ce cet cette doit doivent peut
peuvent faut""".split())


# Lexique juridique : langage courant -> termes employés par les codes (expansion de la requête lexicale)
LEXIQUE = [
    (re.compile(r"\bfisc\b|imp[ôo]ts\b|الجباية|الأداءات", re.I), "administration fiscale"),
    (re.compile(r"liste (de |des )?(mes |ses |nos )?(clients|fournisseurs)|الحرفاء|قائمة", re.I),
     "listes nominatives des clients et fournisseurs droit de communication demande écrite"),
    (re.compile(r"relev[ée]s? (de |des )?comptes?|banques?|البنك|كشف", re.I),
     "établissements de crédit relevés des comptes bancaires droit de communication vérification fiscale"),
    (re.compile(r"amende|p[ée]nalit[ée]|retard de paiement|خطية", re.I), "pénalités de retard sanctions fiscales administratives"),
    (re.compile(r"contr[ôo]le fiscal|contr[ôo]leur|v[ée]rification|مراقبة", re.I), "vérification fiscale approfondie préliminaire avis"),
    (re.compile(r"taxation d'office|التوظيف الإجباري", re.I), "taxation d'office"),
    (re.compile(r"recours|contester|contestation|réclamation|اعتراض", re.I), "recours contentieux réclamation tribunal"),
    (re.compile(r"\boea\b|op[ée]rateur [ée]conomique agr[ée]{2}|المتعامل الاقتصادي", re.I), "statut d'opérateur économique agréé conditions d'octroi"),
    (re.compile(r"douane|الديوانة|dédouanement", re.I), "code des douanes déclaration en détail"),
    (re.compile(r"transaction", re.I), "tarif de transaction infractions fiscales pénales"),
    (re.compile(r"d[ée]lai|combien de temps|قداش|مدة", re.I), "délai jours à compter de la notification"),
]


def expansion_lexicale(question: str) -> str | None:
    ajouts = [terme for motif, terme in LEXIQUE if motif.search(question)]
    return " ".join(dict.fromkeys(ajouts)) if ajouts else None


def _normaliser(txt: str) -> str:
    txt = unicodedata.normalize("NFD", txt.lower())
    return "".join(c for c in txt if unicodedata.category(c) != "Mn")


def tokeniser(txt: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", _normaliser(txt)) if t not in MOTS_VIDES and len(t) > 1]


def _charger_calibration() -> float:
    f = config.MODELS_DIR / "retriever_calibration.json"
    if f.exists():
        try:
            return float(json.loads(f.read_text(encoding="utf-8"))["seuil"])
        except (KeyError, ValueError, json.JSONDecodeError):
            pass
    return config.RETRIEVER_ABSTAIN_THRESHOLD


@dataclass
class Resultat:
    position: int
    record: dict
    score_dense: float = 0.0
    score_bm25: float = 0.0
    score_rrf: float = 0.0
    direct: bool = False

    def as_source(self, n: int) -> dict:
        r = self.record
        return {
            "n": n, "id": r["id"], "source_id": r["source_id"], "document": r.get("source_title") or r["source_id"],
            "article": r.get("article_number") or r.get("article_label"), "section": r.get("section"),
            "page": r.get("pdf_page"), "page_fin": r.get("pdf_page_end"), "locator": r.get("locator"),
            "chunk_type": r.get("chunk_type"), "extrait": strip_header(r.get("content", "")),
            "score": round(self.score_dense, 4), "recherche_directe": self.direct,
        }


@dataclass
class Recherche:
    question: str
    resultats: list[Resultat] = field(default_factory=list)
    meilleur_score: float = 0.0
    seuil: float = 0.0
    abstention: bool = False
    tarifaire: bool = False
    article_demande: str | None = None


class Retriever:
    def __init__(self, rag: RagIndex):
        self.rag = rag
        self.bm25 = BM25Okapi([tokeniser(r.get("content", "")) for r in rag.records])
        self.est_tarifaire = np.array([r.get("chunk_type") in TYPES_TARIFAIRES for r in rag.records])
        self.seuil = _charger_calibration()
        log.info("Retriever prêt : %d documents, seuil d'abstention %.3f", len(rag.records), self.seuil)

    # ------------------------------------------------------------ recherche directe d'article
    def articles_directs(self, question: str) -> list[int]:
        m = ARTICLE_RE.search(question)
        if not m:
            return []
        num = normalize_article_number(m.group(0).replace("art.", "article").replace("Art.", "article"))
        source, unite = None, None
        for motif, sid, u in CODES:
            if motif.search(question):
                source, unite = sid, u
                break
        cands = [i for i, r in enumerate(self.rag.records)
                 if normalize_article_number(r.get("article_number") or r.get("article_label")) == num
                 and (source is None or r["source_id"] == source)]
        if not cands:
            return []
        def priorite(i: int) -> tuple:
            r = self.rag.records[i]
            return (0 if (unite and r.get("document_unit") == unite) else 1,
                    0 if r["source_id"] == "cdpf_2024" and r.get("document_unit") == "CODE DES DROITS ET PROCÉDURES FISCAUX" else 1,
                    0 if r["source_id"] == (source or "cdpf_2024") else 1)
        cands.sort(key=priorite)
        return cands[:1]

    # ------------------------------------------------------------ recherche hybride
    def preparer(self, question: str) -> dict[str, np.ndarray]:
        """Pré-encode la question (et son expansion) pendant que le LLM la reformule."""
        textes = [question] + ([question + " " + expansion_lexicale(question)] if expansion_lexicale(question) else [])
        mat = embedder.encode_queries(textes)
        return {t: mat[i:i + 1] for i, t in enumerate(textes)}

    def rechercher(self, question: str, top_k: int = config.RETRIEVER_TOP_K, requetes_sup: list[str] | None = None,
                   inclure_tarifaire: bool | None = None, vecteurs: dict[str, np.ndarray] | None = None) -> Recherche:
        requetes = [question] + [q for q in (requetes_sup or []) if q and q.strip() and q.strip() != question.strip()]
        exp = expansion_lexicale(" ".join(requetes))  # liste BM25 seule, à demi-poids (ne doit pas diluer la fusion)
        tarifaire = bool(MOTS_TARIFAIRES.search(" ".join(requetes))) if inclure_tarifaire is None else inclure_tarifaire
        rrf: dict[int, float] = {}
        dense: dict[int, float] = {}
        bm: dict[int, float] = {}
        k = config.RETRIEVER_RRF_K
        texte_exp = question + " " + exp if exp else None
        a_encoder = [t for t in requetes + ([texte_exp] if texte_exp else []) if t not in (vecteurs or {})]
        vecs = dict(vecteurs or {})
        if a_encoder:  # un seul appel au modèle d'embeddings pour toutes les requêtes
            mat = embedder.encode_queries(a_encoder)
            vecs.update({t: mat[i:i + 1] for i, t in enumerate(a_encoder)})
        for q in requetes:
            vec = vecs[q]
            D, I = self.rag.index.search(vec, config.RETRIEVER_DENSE_K * (1 if tarifaire else 3))
            rang = 0
            for s, i in zip(D[0], I[0]):
                if i < 0 or (not tarifaire and self.est_tarifaire[i]):
                    continue
                dense[i] = max(dense.get(i, 0.0), float(s))
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (k + rang)
                rang += 1
                if rang >= config.RETRIEVER_DENSE_K:
                    break
            scores = self.bm25.get_scores(tokeniser(q))
            if not tarifaire:
                scores = np.where(self.est_tarifaire, -1, scores)
            top = np.argsort(-scores)[: config.RETRIEVER_DENSE_K]
            for rang, i in enumerate(top):
                if scores[i] <= 0:
                    break
                bm[i] = max(bm.get(i, 0.0), float(scores[i]))
                rrf[i] = rrf.get(i, 0.0) + 1.0 / (k + rang)
        if texte_exp:  # expansion lexicale : listes dense et BM25 à demi-poids (aide sans diluer la fusion)
            D, I = self.rag.index.search(vecs[texte_exp], config.RETRIEVER_DENSE_K * (1 if tarifaire else 3))
            rang = 0
            for i in I[0]:
                if i < 0 or (not tarifaire and self.est_tarifaire[i]):
                    continue
                rrf[i] = rrf.get(i, 0.0) + 0.5 / (k + rang)
                rang += 1
                if rang >= config.RETRIEVER_DENSE_K:
                    break
            scores = self.bm25.get_scores(tokeniser(texte_exp))
            if not tarifaire:
                scores = np.where(self.est_tarifaire, -1, scores)
            for rang, i in enumerate(np.argsort(-scores)[: config.RETRIEVER_DENSE_K]):
                if scores[i] <= 0:
                    break
                rrf[i] = rrf.get(i, 0.0) + 0.5 / (k + rang)
        directs = self.articles_directs(" ".join(requetes))
        ordre = sorted(rrf, key=lambda i: -rrf[i])
        ordre = directs + [i for i in ordre if i not in directs]
        res = []
        for i in ordre[:top_k]:
            if i not in dense:  # score dense exact pour l'affichage et l'abstention
                dense[i] = max(float(np.dot(self.rag.vector(i), vecs[q][0])) for q in requetes)
            res.append(Resultat(position=int(i), record=self.rag.records[i], score_dense=dense[i], score_bm25=bm.get(i, 0.0),
                                score_rrf=rrf.get(i, 0.0), direct=i in directs))
        meilleur = max((dense.get(i, 0.0) for i in ordre[:top_k]), default=0.0)
        art = ARTICLE_RE.search(question)
        return Recherche(question=question, resultats=res, meilleur_score=meilleur, seuil=self.seuil,
                         abstention=(meilleur < self.seuil and not directs), tarifaire=tarifaire,
                         article_demande=art.group(0) if art else None)


_lock = threading.Lock()


@lru_cache(maxsize=1)
def _retriever() -> Retriever:
    return Retriever(get_index())


def get_retriever() -> Retriever:
    with _lock:
        return _retriever()
