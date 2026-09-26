"""Explicabilité : explications légitimes vérifiées (neutralisations), cascade du score (SHAP)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import fmt
from .features import ANNEES, Contexte
from .model import LIBELLES_FEATURES

POIDS_SCORE = {"proba": 0.45, "regles": 0.40, "anomalie": 0.15}


def neutralisations(ctx: Contexte, eid: int) -> list[dict]:
    """Bloc « Explications légitimes vérifiées » : ce qui a été neutralisé AVANT tout calcul."""
    a = ctx.annuel.loc[eid]
    a = a[a.active_annee]
    sect = ctx.ent.at[eid, "secteur_groupe"]
    info = ctx.secteur_info(sect)
    out = []
    ds = a.delta_stock[a.annuelle_presente]
    if len(ds) and (ds.abs() > 0.1 * a.ca_decl[a.annuelle_presente].clip(lower=1)).any():
        y = int(ds.abs().idxmax())
        out.append({"cle": "stock", "libelle": "Variation de stock", "statut": "verifie",
                    "detail": f"Variation de stock de {fmt.dt(ds[y])} en {y} intégrée au coût des ventes (achats non encore revendus)."})
    else:
        out.append({"cle": "stock", "libelle": "Variation de stock", "statut": "sans_objet",
                    "detail": "Variations de stock faibles, prises en compte dans le coût des ventes."})
    pres = a[a.annuelle_presente & a.cout_net.gt(0)]
    if len(pres) >= 2:
        m36 = pres.ca_decl.sum() / pres.cout_net.sum() - 1
        out.append({"cle": "periode", "libelle": "Décalage de période", "statut": "verifie",
                    "detail": f"Comparaison glissante sur 12 et 36 mois : marge cumulée sur {len(pres)} ans de {fmt.pct(m36)}."})
    else:
        out.append({"cle": "periode", "libelle": "Décalage de période", "statut": "sans_objet",
                    "detail": "Moins de deux exercices disponibles pour la comparaison glissante."})
    eq = a.imports_equipement.sum()
    out.append({"cle": "equipements", "libelle": "Biens d'équipement", "statut": "verifie" if eq > 0 else "sans_objet",
                "detail": (f"{fmt.dt(eq)} de machines (codes de l'annexe du décret 2017-419) exclus des achats à revendre."
                           if eq > 0 else "Aucune importation de biens d'équipement.")})
    at = a.imports_at.sum()
    out.append({"cle": "regimes_suspensifs", "libelle": "Régimes suspensifs", "statut": "verifie" if at > 0 else "sans_objet",
                "detail": (f"{fmt.dt(at)} importés en admission temporaire exclus (réexportés après transformation)."
                           if at > 0 else "Aucune importation sous régime suspensif.")})
    exp = a.exports_douane.sum()
    out.append({"cle": "exportations", "libelle": "Ventes à l'export", "statut": "verifie" if exp > 0 else "sans_objet",
                "detail": (f"{fmt.dt(exp)} d'exportations constatées en douane intégrés au chiffre d'affaires."
                           if exp > 0 else "Pas d'exportation constatée.")})
    manq = [int(y) for y in a.index if a.at[y, "active_annee_complete"] and not a.at[y, "annuelle_presente"]]
    out.append({"cle": "donnees", "libelle": "Données disponibles", "statut": "manquant" if manq else "verifie",
                "detail": (f"Déclaration(s) annuelle(s) absente(s) : {', '.join(map(str, manq))}. Les règles qui en dépendent ne sont pas évaluées."
                           if manq else f"Déclarations annuelles {ANNEES[0]}–{ANNEES[-1]} disponibles.")})
    out.append({"cle": "secteur", "libelle": "Norme du secteur", "statut": "verifie",
                "detail": f"Comparaison avec la distribution du secteur « {info.get('libelle', sect)} » "
                          f"(marge médiane de référence {fmt.pct(ctx.marge_mediane_secteur(sect))}), pas avec une norme générale."})
    return out


def donnees_insuffisantes(ctx: Contexte) -> pd.Series:
    a = ctx.annuel
    manq = (a.active_annee_complete & ~a.annuelle_presente).groupby(level="entreprise_id").sum()
    return (manq > 0).reindex(ctx.ent.index).fillna(False)


def cascade(score: float, moyennes: dict, p: float, shap_row: pd.Series | None, s_regles: float,
            poids_regles: dict[str, float], anom: float, n_top: int = 6) -> list[dict]:
    """Cascade du score (0-100) : niveau moyen + contributions (IA via SHAP, indices, anomalie). La somme est exacte :
    score = 100 × (0,45 × p + 0,40 × force des indices + 0,15 × anomalie), décomposé autour de la moyenne."""
    etapes = [{"libelle": "Niveau moyen (toutes entreprises)", "valeur": round(moyennes["score"], 1), "type": "base"}]
    # part IA : écart de probabilité calibrée réparti au prorata des valeurs SHAP (même signe) sinon en un bloc
    delta_p = (p - moyennes["proba"]) * 100 * POIDS_SCORE["proba"]
    somme = float(shap_row.sum()) if shap_row is not None else 0.0
    if shap_row is not None and abs(somme) > 1e-6 and np.sign(somme) == np.sign(delta_p):
        contrib = shap_row * (delta_p / somme)
        top = [f for f in contrib.abs().sort_values(ascending=False).index[:n_top] if abs(contrib[f]) >= 0.1]
        for f in top:
            etapes.append({"libelle": LIBELLES_FEATURES.get(f, f), "valeur": round(float(contrib[f]), 1), "type": "ia"})
        reste = float(contrib.sum() - contrib[top].sum()) if top else float(contrib.sum())
        if abs(reste) >= 0.1:
            etapes.append({"libelle": "Autres variables du modèle", "valeur": round(reste, 1), "type": "ia"})
    elif abs(delta_p) >= 0.1:
        etapes.append({"libelle": "Évaluation du modèle (contrôles passés)", "valeur": round(delta_p, 1), "type": "ia"})
    # part des indices : répartie entre les indices déclenchés selon leur force
    delta_r = (s_regles - moyennes["regles"]) * 100 * POIDS_SCORE["regles"]
    tot = sum(poids_regles.values())
    if tot > 0:
        for code, w in sorted(poids_regles.items(), key=lambda kv: -kv[1]):
            etapes.append({"libelle": f"Indice {code}", "valeur": round(delta_r * w / tot, 1), "type": "regle", "code": code})
    elif abs(delta_r) >= 0.1:
        etapes.append({"libelle": "Aucun indice déclenché", "valeur": round(delta_r, 1), "type": "regle"})
    delta_a = (anom - moyennes["anomalie"]) * 100 * POIDS_SCORE["anomalie"]
    if abs(delta_a) >= 0.1:
        etapes.append({"libelle": "Atypicité dans le secteur (Isolation Forest)", "valeur": round(delta_a, 1), "type": "anomalie"})
    ecart = round(score - sum(e["valeur"] for e in etapes), 1)
    if abs(ecart) >= 0.1:  # arrondis : la somme affichée égale le score
        etapes[-1]["valeur"] = round(etapes[-1]["valeur"] + ecart, 1)
    etapes.append({"libelle": "Score final", "valeur": round(score, 1), "type": "total"})
    return etapes
