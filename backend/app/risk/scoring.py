"""Orchestration du ciblage (T20) : règles → décision → IA → score → priorité → table `scores`.

Usage : python -m app.risk.scoring   (depuis backend/, recalcule tout et affiche un résumé)

Le score ne mesure pas la culpabilité : il mesure la probabilité qu'un contrôle soit utile.
Priorité = probabilité × montant en jeu estimé. L'humain décide toujours.
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import delete, text
from sqlalchemy.engine import Engine

from .. import config, db
from . import evaluation, explain, model
from .features import ANNEES, Contexte, charger_contexte
from .rules import FAMILLES, POIDS_FORCE, REGLES, evaluer_toutes

log = logging.getLogger("rasd.scoring")

CATEGORIES = {
    "rouge": "Contrôle recommandé",
    "orange": "Demande de justification",
    "gris": "Données insuffisantes",
    "vert": "Cohérent",
}
ORDRE_CATEGORIES = {"rouge": 0, "orange": 1, "gris": 2, "vert": 3}


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    return str(o)


def _propre(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, (np.floating,)):
        return _propre(float(v))
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def indices_entreprise(ctx: Contexte, res: dict[str, pd.DataFrame], eid: int) -> list[dict]:
    out = []
    for r in REGLES:
        row = res[r.code].loc[eid].to_dict()
        dec = bool(row["declenchee"])
        out.append({
            "code": r.code, "niveau": r.niveau, "libelle": r.libelle, "formule": r.formule, "condition": r.condition,
            "valeur": _propre(row["valeur"]), "seuil": _propre(row["seuil"]), "declenchee": dec,
            "force": r.niveau, "montant_en_jeu": round(float(row["montant"]), 2) if dec else 0.0,
            "annee": int(row["annee"]), "annees": [int(y) for y in row["annees"]],
            "phrase": r.phrase(row, ctx, eid) if dec else None,
        })
    return out


def decider(indices: list[dict], insuffisant: bool, seuil_a: float = 20_000.0) -> tuple[str, str]:
    dec = [i for i in indices if i["declenchee"]]
    a_forts = [i for i in dec if i["niveau"] == "A" and i["montant_en_jeu"] > seuil_a]
    n_b = sum(1 for i in dec if i["niveau"] == "B") + sum(1 for i in dec if i["niveau"] == "A" and i not in a_forts)
    n_c = sum(1 for i in dec if i["niveau"] == "C")
    if a_forts:
        codes = ", ".join(i["code"] for i in a_forts)
        return "rouge", f"Indice de niveau A ({codes}) avec plus de {int(seuil_a):,} DT en jeu".replace(",", " ")
    if n_b >= 2:
        return "rouge", "Au moins deux indices de niveau B concordants"
    if n_b >= 1 and n_c >= 2:
        return "rouge", "Un indice de niveau B et deux signaux de contexte"
    if insuffisant:
        return "gris", "Déclarations annuelles manquantes : données insuffisantes pour conclure"
    if n_b >= 1:
        return "orange", "Un indice de niveau B : demander des justifications"
    if n_c >= 2:
        return "orange", "Deux signaux de contexte : demander des justifications"
    return "vert", "Aucun faisceau d'indices : déclarations cohérentes"


def force_indices(indices: list[dict]) -> tuple[float, dict[str, float]]:
    """1 − Π(1 − poids) sur les indices déclenchés ; poids log pour répartir la contribution."""
    prod, poids = 1.0, {}
    for i in indices:
        if i["declenchee"]:
            w = POIDS_FORCE[i["niveau"]]
            prod *= 1 - w
            poids[i["code"]] = -math.log(1 - w)
    return 1 - prod, poids


def montant_en_jeu(indices: list[dict]) -> float:
    fam: dict[str, float] = {}
    for i in indices:
        f = FAMILLES.get(i["code"])
        if i["declenchee"] and f:
            fam[f] = max(fam.get(f, 0.0), i["montant_en_jeu"])
    return float(sum(fam.values()))


def retards_depot(ctx: Contexte) -> tuple[pd.Series, pd.Series]:
    """Nombre de mois de TVA déposés en retard (après le 28 du mois suivant) ou non déposés, par entreprise."""
    t = ctx.tva
    ny = t.annee + (t.mois == 12)
    nm = t.mois % 12 + 1
    limite = pd.to_datetime(pd.DataFrame({"year": ny, "month": nm, "day": 28}))
    depot = pd.to_datetime(t.date_depot)
    retard = (depot > limite) | depot.isna()
    return retard.groupby(t.entreprise_id).sum(), t.groupby("entreprise_id").size()


def criteres_facilitation(ctx: Contexte, eid: int, indices: list[dict], score: float, insuffisant: bool,
                          retards: pd.Series, n_mois: pd.Series, redressees: set) -> dict:
    ent = ctx.ent.loc[eid]
    n_tva = int(n_mois.get(eid, 0))
    n_ret = int(retards.get(eid, 0))
    redresse = eid in redressees
    anciennete = (pd.Timestamp(f"{ANNEES[-1]}-12-31") - ent.date_creation).days / 365.25
    a = ctx.annuel.loc[eid]
    importe = a.imports_total.sum() > 0
    exporte = ent.statut_export != "local"
    ca = float(a.ca_decl.iloc[-1]) if len(a) else 0.0
    crit = [
        {"libelle": f"Aucun indice sur {len(ANNEES)} ans (A, B ou C)", "ok": not any(i["declenchee"] for i in indices)},
        {"libelle": "Déclarations annuelles complètes", "ok": not insuffisant},
        {"libelle": f"TVA déposée dans les délais ({n_tva - n_ret}/{n_tva} mois)", "ok": n_tva >= 24 and n_ret <= 1},
        {"libelle": "Score de risque très faible (< 10/100)", "ok": score < 10},
        {"libelle": f"Ancienneté d'au moins 5 ans ({anciennete:.0f} ans)".replace(".", ","), "ok": anciennete >= 5},
        {"libelle": "Aucun redressement antérieur", "ok": not redresse},
        {"libelle": "Activité significative (CA ≥ 500 000 DT)", "ok": ca >= 500_000},
    ]
    eligible = all(c["ok"] for c in crit)
    return {
        "criteres": crit, "eligible": eligible,
        "candidat_oea": bool(eligible and (importe or exporte) and not bool(ent.statut_oea)),
        "candidat_remboursement_rapide": bool(eligible and exporte),
        "deja_oea": bool(ent.statut_oea),
    }


def calculer(engine: Engine | None = None, avec_evaluation: bool = True) -> dict:
    t0 = time.perf_counter()
    engine = engine or db.get_engine()
    ctx = charger_contexte(engine)
    res = evaluer_toutes(ctx)
    ids = ctx.actives()
    insuff = explain.donnees_insuffisantes(ctx)
    seuil_a = float(ctx.parametres.get("seuil_montant_alerte_A", 20_000.0))

    lignes: dict[int, dict] = {}
    for eid in ids:
        ind = indices_entreprise(ctx, res, eid)
        cat, raison = decider(ind, bool(insuff[eid]), seuil_a)
        s_regles, poids = force_indices(ind)
        lignes[eid] = {"indices": ind, "categorie": cat, "raison_categorie": raison, "s_regles": s_regles,
                       "poids_regles": poids, "montant": montant_en_jeu(ind)}

    X = model.construire_features(ctx, res)
    with engine.connect() as conn:
        resultats = pd.read_sql(text("SELECT * FROM resultats_controle"), conn)
    y = model.etiquettes(ctx, resultats)
    m = model.entrainer(X, y)
    p = m["proba"]
    anom = model.anomalies(X, ctx.ent.secteur_groupe.reindex(X.index))
    sv = model.valeurs_shap(m["modele_base"], X)
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"calibre": m["modele_calibre"], "base": m["modele_base"], "features": list(X.columns)},
                config.MODELS_DIR / "modele_ciblage.joblib")

    s_reg = pd.Series({e: lignes[e]["s_regles"] for e in ids})
    score = 100 * (explain.POIDS_SCORE["proba"] * p + explain.POIDS_SCORE["regles"] * s_reg + explain.POIDS_SCORE["anomalie"] * anom)
    montant = pd.Series({e: lignes[e]["montant"] for e in ids})
    priorite = p * montant
    categories = pd.Series({e: ORDRE_CATEGORIES[lignes[e]["categorie"]] for e in ids})
    # rang d'affichage : la catégorie décidée par les règles d'abord, puis la priorité à l'intérieur de chaque catégorie
    ordre = pd.DataFrame({"cat": categories, "priorite": priorite, "score": score}).sort_values(
        ["cat", "priorite", "score"], ascending=[True, False, False])
    rang = pd.Series(np.arange(1, len(ordre) + 1), index=ordre.index)
    moyennes = {"score": float(score.mean()), "proba": float(p.mean()), "regles": float(s_reg.mean()), "anomalie": float(anom.mean())}

    maintenant = datetime.now().isoformat(timespec="seconds")
    retards, n_mois = retards_depot(ctx)
    redressees = set(ctx.tables["controles_historiques"].query("redressement == True").entreprise_id)
    rows = []
    for eid in ids:
        L = lignes[eid]
        casc = explain.cascade(float(score[eid]), moyennes, float(p[eid]), sv.loc[eid], L["s_regles"], L["poids_regles"],
                               float(anom[eid]))
        fac = (criteres_facilitation(ctx, eid, L["indices"], float(score[eid]), bool(insuff[eid]), retards, n_mois, redressees)
               if L["categorie"] == "vert" else None)
        dec = [i for i in L["indices"] if i["declenchee"]]
        dec_tri = sorted(dec, key=lambda i: ("ABC".index(i["niveau"]), -i["montant_en_jeu"]))
        details = {
            "indices": L["indices"],
            "raison_categorie": L["raison_categorie"],
            "neutralisations": explain.neutralisations(ctx, eid),
            "cascade": casc,
            "features": {k: _propre(v) for k, v in X.loc[eid].drop("secteur").to_dict().items()},
            "facilitation": fac,
            "probabilite": float(p[eid]), "anomalie": float(anom[eid]), "force_indices": L["s_regles"],
        }
        rows.append({
            "entreprise_id": int(eid), "score": round(float(score[eid]), 1), "categorie": L["categorie"],
            "probabilite": round(float(p[eid]), 4), "score_anomalie": round(float(anom[eid]), 4),
            "force_indices": round(L["s_regles"], 4), "montant_en_jeu": round(L["montant"], 2),
            "priorite": round(float(priorite[eid]), 2), "rang": int(rang[eid]),
            "regles_declenchees": json.dumps([i["code"] for i in dec_tri]),
            "premiere_raison": dec_tri[0]["phrase"] if dec_tri else L["raison_categorie"],
            "details": json.dumps(details, ensure_ascii=False, default=_json_default),
            "facilitation": bool(fac and (fac["candidat_oea"] or fac["candidat_remboursement_rapide"])),
            "score_regles": round(100 * L["s_regles"], 1), "calcule_le": maintenant,
        })
    scores_df = pd.DataFrame(rows)
    with engine.begin() as conn:
        conn.execute(delete(db.scores))
        scores_df.to_sql("scores", conn, if_exists="append", index=False)

    resume = {"entreprises": len(ids), "categories": scores_df.categorie.value_counts().to_dict(),
              "modele": m["metriques"], "duree_s": round(time.perf_counter() - t0, 1)}
    metr = {"modele": m["metriques"], "calcule_le": maintenant,
            "alertes_mensuelles": evaluation.alertes_mensuelles(ctx, res, scores_df),
            "moyennes": moyennes}
    if avec_evaluation:
        perf = evaluation.evaluer(ctx, scores_df, X, y, m["metriques"])
        metr["performance"] = perf
        resume["performance_top100"] = perf.get("resume") if perf else None
    with engine.begin() as conn:
        conn.execute(delete(db.metriques))
        for cle, val in metr.items():
            conn.execute(db.metriques.insert().values(cle=cle, valeur=json.dumps(val, ensure_ascii=False, default=_json_default),
                                                      calcule_le=maintenant))
    resume["duree_s"] = round(time.perf_counter() - t0, 1)
    log.info("Scores calculés : %s", json.dumps(resume, ensure_ascii=False, default=_json_default))
    return resume


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    print(json.dumps(calculer(), ensure_ascii=False, indent=1, default=_json_default))
