"""Évaluation (section 6.5) sur la vérité terrain, SANS jamais l'utiliser pour entraîner.

Hasard vs écart brut naïf vs règles seules vs règles + IA : précision sur les N premiers
contrôles, rappel, montant détecté, fausses alertes sur les pièges, détection par schéma.
Aucun chiffre n'est écrit à la main : tout est recalculé à chaque lancement.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .. import config
from .features import Contexte

log = logging.getLogger("rasd.evaluation")

TOP_N = (50, 100, 200)
LIBELLES_SCHEMAS = {
    "F1": "Minoration du chiffre d'affaires", "F2": "Sous-évaluation en douane", "F3": "TVA déductible gonflée",
    "F4": "Fausses factures / société écran", "F5": "Carrousel de TVA", "F6": "Fractionnement",
    "F7": "Détournement d'avantages fiscaux", "F8": "Fausses exportations",
}
METHODES = {
    "hasard": "Sélection au hasard",
    "ecart_brut": "Écart brut (importations ÷ CA, sans neutralisation)",
    "regles": "Règles seules",
    "regles_ia": "Règles + IA (RASD 360)",
}


def charger_verite_terrain() -> pd.DataFrame | None:
    if not config.GROUND_TRUTH_PATH.exists():
        return None
    gt = pd.read_csv(config.GROUND_TRUTH_PATH, keep_default_na=False)
    return gt.set_index("entreprise_id")


def _stats_top(ordre: pd.Index, gt: pd.DataFrame, n: int) -> dict:
    top = gt.loc[ordre[:n]]
    fraude = top.categorie == "fraudeur"
    n_fraudeurs = int((gt.categorie == "fraudeur").sum())
    n_pieges = int((gt.categorie == "honnete_ecart_explique").sum())
    pieges = int((top.categorie == "honnete_ecart_explique").sum())
    return {"n": n, "precision": float(fraude.mean()), "rappel": float(fraude.sum() / n_fraudeurs),
            "montant_detecte": float(top.loc[fraude, "montant_elude_reel"].sum()),
            "pieges_dans_top": pieges, "taux_fausses_alertes_pieges": float(pieges / n_pieges) if n_pieges else 0.0}


def evaluer(ctx: Contexte, scores: pd.DataFrame, X: pd.DataFrame, y: pd.Series, metr_modele: dict) -> dict | None:
    gt = charger_verite_terrain()
    if gt is None:
        log.warning("ground_truth.csv absent : évaluation ignorée")
        return None
    s = scores.set_index("entreprise_id")
    gt = gt.loc[s.index]
    est_fraude = (gt.categorie == "fraudeur").astype(int)
    total_montant = float(gt.loc[est_fraude == 1, "montant_elude_reel"].sum())
    n, n_fraud = len(gt), int(est_fraude.sum())
    ordres = {
        "ecart_brut": X["ratio_import_brut"].reindex(s.index).sort_values(ascending=False, kind="mergesort").index,
        "regles": s.sort_values(["force_indices", "montant_en_jeu"], ascending=False, kind="mergesort").index,
        "regles_ia": s.sort_values(["priorite", "score"], ascending=False, kind="mergesort").index,
    }
    methodes = {}
    for cle, lib in METHODES.items():
        lignes = []
        for k in TOP_N:
            if cle == "hasard":  # espérance mathématique d'une sélection aléatoire
                n_pieges = int((gt.categorie == "honnete_ecart_explique").sum())
                lignes.append({"n": k, "precision": n_fraud / n, "rappel": k / n, "montant_detecte": total_montant * k / n,
                               "pieges_dans_top": round(n_pieges * k / n, 1), "taux_fausses_alertes_pieges": k / n})
            else:
                lignes.append(_stats_top(ordres[cle], gt, k))
        methodes[cle] = {"libelle": lib, "top": lignes}
    # alertes par catégorie (décision de l'outil) vs règle naïve « importations > CA »
    alerte = s.categorie.isin(["rouge", "orange"])
    pieges = gt.categorie == "honnete_ecart_explique"
    naif = X["ratio_import_brut"].reindex(s.index) > 1.0
    categories = pd.crosstab(gt.categorie, s.categorie).reindex(columns=["rouge", "orange", "gris", "vert"], fill_value=0)
    fausses_alertes = {
        "outil": float(alerte[pieges].mean()),
        "outil_rouge": float((s.categorie == "rouge")[pieges].mean()),
        "naif": float(naif[pieges].mean()),
        "honnetes_outil": float(alerte[gt.categorie == "honnete"].mean()),
        "honnetes_naif": float(naif[gt.categorie == "honnete"].mean()),
    }
    # détection par schéma de fraude
    schemas = []
    top200 = set(ordres["regles_ia"][:200])
    top200_r = set(ordres["regles"][:200])
    for code, lib in LIBELLES_SCHEMAS.items():
        ids = gt.index[(gt.categorie == "fraudeur") & gt.schemas.str.split(";").map(lambda l: code in l)]
        if not len(ids):
            continue
        schemas.append({"code": code, "libelle": lib, "n": int(len(ids)),
                        "rouge": float((s.loc[ids, "categorie"] == "rouge").mean()),
                        "alerte": float(s.loc[ids, "categorie"].isin(["rouge", "orange"]).mean()),
                        "top200_regles_ia": float(np.mean([i in top200 for i in ids])),
                        "top200_regles": float(np.mean([i in top200_r for i in ids]))})
    # qualité du modèle
    auc = {
        "probabilite_ia": float(roc_auc_score(est_fraude, s.probabilite)),
        "force_indices": float(roc_auc_score(est_fraude, s.force_indices)),
        "score_final": float(roc_auc_score(est_fraude, s.score)),
        "anomalie": float(roc_auc_score(est_fraude, s.score_anomalie)),
    }
    hist = ctx.tables["controles_historiques"]
    hist = hist[hist.entreprise_id.isin(s.index)]
    taux_hist = hist.groupby("origine_selection").redressement.mean().to_dict()
    top100 = methodes["regles_ia"]["top"][1]
    m_regles, m_ia = methodes["regles"]["top"][1]["montant_detecte"], top100["montant_detecte"]
    # signaux faibles : l'Isolation Forest repère-t-il des fraudeurs qu'aucun indice ne signale ?
    sans_alerte = ~s.categorie.isin(["rouge", "orange"])
    atyp = s.score_anomalie > 0.5
    fr_sa, ho_sa = sans_alerte & (est_fraude == 1), sans_alerte & (est_fraude == 0)
    signaux_faibles = {"fraudeurs_sans_alerte": int(fr_sa.sum()), "dont_atypiques": int((fr_sa & atyp).sum()),
                       "non_fraudeurs_sans_alerte": int(ho_sa.sum()), "dont_atypiques_non_fraudeurs": int((ho_sa & atyp).sum())}
    resume = {
        "montant_top100_regles": m_regles,
        "montant_top100_regles_ia": m_ia,
        "gain_montant_ia_pct": (m_ia / m_regles - 1) if m_regles else None,
        "precision_top100_regles_ia": top100["precision"],
        "precision_hasard": n_fraud / n,
        "gain_vs_hasard": top100["precision"] / (n_fraud / n) if n_fraud else None,
        "taux_redressement_historique": float(hist.redressement.mean()) if len(hist) else None,
        "fausses_alertes_pieges_outil": fausses_alertes["outil"],
        "fausses_alertes_pieges_naif": fausses_alertes["naif"],
    }
    return {
        "resume": resume, "methodes": methodes, "categories": {k: {c: int(v) for c, v in r.items()} for k, r in categories.iterrows()},
        "fausses_alertes": fausses_alertes, "schemas": schemas, "auc": auc, "modele": metr_modele,
        "signaux_faibles": signaux_faibles,
        "historique": {"n_controles": int(len(hist)), "taux_par_origine": {k: float(v) for k, v in taux_hist.items()}},
        "population": {"entreprises": n, "fraudeurs": n_fraud, "pieges": int(pieges.sum()),
                       "honnetes": int((gt.categorie == "honnete").sum()), "montant_elude_total": total_montant},
    }


def alertes_mensuelles(ctx: Contexte, res: dict, scores: pd.DataFrame) -> list[dict]:
    """Nombre d'entreprises présentant au moins un signal mensuel (défaut de dépôt, TVA import déduite en trop,
    factures > CA du mois, déclaration sous-évaluée, facture de circuit), et parmi elles les alertes rouges."""
    m = ctx.mensuel.copy()
    paye = ctx.douane[ctx.douane.flux == "import"].groupby(["entreprise_id", "annee", "mois"]).tva_import.sum()
    m = m.merge(paye.rename("tva_payee").reset_index(), on=["entreprise_id", "annee", "mois"], how="left").fillna({"tva_payee": 0})
    m = m.sort_values(["entreprise_id", "annee", "mois"])
    m["tva_payee_prec"] = m.groupby("entreprise_id").tva_payee.shift(1).fillna(0)
    fac = ctx.factures.assign(mois=ctx.factures.date.dt.month).groupby(["emetteur_id", "annee", "mois"]).montant_ht.sum()
    m = m.merge(fac.rename("factures").reset_index().rename(columns={"emetteur_id": "entreprise_id"}),
                on=["entreprise_id", "annee", "mois"], how="left").fillna({"factures": 0})
    sig = ((~m.deposee.astype(bool)) & ((m.total_encaissements > 10_000) | (m.imports_mois > 0)))
    sig |= m.tva_deductible_import > (m.tva_payee + m.tva_payee_prec) * 1.02 + 2_000
    sig |= (m.factures > 1.05 * m.ca_local_ht + 5_000) & m.deposee.astype(bool)
    m["signal"] = sig
    b2 = getattr(ctx, "_b2_lignes", None)
    if b2 is not None and len(b2):
        k = b2.assign(mois=b2.date.dt.month)[["entreprise_id", "annee", "mois"]].drop_duplicates()
        m = m.merge(k.assign(b2=True), on=["entreprise_id", "annee", "mois"], how="left")
        m["signal"] |= m.b2.eq(True)
    rouges = set(scores.loc[scores.categorie == "rouge", "entreprise_id"])
    m["rouge"] = m.entreprise_id.isin(rouges)
    g = m[m.signal].groupby(["annee", "mois"])
    out = []
    for (y, mo), grp in g:
        out.append({"periode": f"{y}-{mo:02d}", "entreprises": int(grp.entreprise_id.nunique()),
                    "dont_rouges": int(grp.loc[grp.rouge, "entreprise_id"].nunique())})
    return out
