"""Historique d'un dossier : ajout seulement (la table est protégée par des triggers SQLite)."""
from __future__ import annotations

from datetime import datetime

from .. import db

LIBELLES_ACTIONS = {
    "generation": "Dossier généré",
    "ajout_article": "Article ajouté",
    "retrait_article": "Article écarté",
    "retablissement_article": "Article rétabli",
    "regeneration_lettre": "Lettre régénérée",
    "validation": "Dossier validé",
    "retour_brouillon": "Repassé en brouillon",
}


def journaliser(dossier_id: int, action: str, agent: str, motif: str | None = None, record_id: str | None = None,
                article: str | None = None) -> str:
    horodatage = datetime.now().isoformat(timespec="seconds")
    with db.get_engine().begin() as conn:
        conn.execute(db.journal_dossier.insert().values(dossier_id=int(dossier_id), record_id=record_id, article=article,
                                                         action=action, motif=motif, agent=agent, horodatage=horodatage))
    return horodatage


def historique(dossier_id: int, depuis: str | None = None) -> list[dict]:
    """Entrées du dossier, les plus récentes d'abord. `depuis` (date de création du dossier) écarte les entrées
    d'un ancien dossier supprimé dont l'identifiant aurait été réattribué."""
    q = "SELECT * FROM journal_dossier WHERE dossier_id = :d"
    params: dict = {"d": int(dossier_id)}
    if depuis:
        q += " AND horodatage >= :depuis"
        params["depuis"] = depuis
    lignes = db.read_sql(q + " ORDER BY id DESC", params).to_dict("records")
    for l in lignes:
        l["libelle"] = LIBELLES_ACTIONS.get(l["action"], l["action"])
    return lignes
