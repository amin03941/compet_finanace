"""Couche IA (section 6.4) : au-dessus des règles, pas à la place.

- Features : valeurs continues des indicateurs + contexte (secteur, ancienneté, taille, graphe).
- Modèle supervisé LightGBM sur les contrôles passés (redressement oui/non), calibration isotonique.
- Isolation Forest par secteur pour les signaux faibles hors étiquettes.
- SHAP par entreprise.
"""
from __future__ import annotations

import logging
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
import shap
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import IsolationForest
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import RobustScaler

from .features import ANNEES, FIN_PERIODE, Contexte

log = logging.getLogger("rasd.model")
warnings.filterwarnings("ignore", category=UserWarning)
# compatibilité LightGBM 4.5 / scikit-learn 1.6 (avertissement sans effet sur les résultats)
warnings.filterwarnings("ignore", message=".*__sklearn_tags__.*", category=FutureWarning)

SEED = 42
# Environ 10 % des contrôles de fraudeurs ne donnent pas de redressement (étiquettes imparfaites) :
# aucune probabilité calibrée ne peut honnêtement dépasser ~90 %. On borne donc la sortie.
PROBA_MIN, PROBA_MAX = 0.01, 0.90

LIBELLES_FEATURES = {
    "exces_tej": "Paiements clients (TEJ) au-delà du CA",
    "exces_factures": "Factures El Fatoora au-delà du CA",
    "exces_tva_import": "TVA déduite au-delà de la TVA payée à l'import",
    "exces_export": "Exportations déclarées au-delà de la douane",
    "exces_banque": "Encaissements au-delà du CA TTC",
    "mois_non_deposes": "Mois de TVA non déposés",
    "marge_z36": "Marge sur 36 mois vs secteur (écarts-types)",
    "annees_marge_basse": "Années de marge anormalement basse",
    "decl_sous_evaluees": "Déclarations sous-évaluées",
    "ratio_prix_min": "Prix déclaré ÷ prix de référence",
    "dans_cycle": "Présence dans un circuit de factures",
    "fractionnement": "Déclarations fractionnées (7 jours)",
    "reventes_equipement": "Reventes d'équipements exonérés",
    "mois_credit_max": "Mois en crédit de TVA",
    "remboursements_ca": "Remboursements de TVA ÷ CA (hors exportateurs)",
    "liens_risque": "Liens avec des sociétés radiées, redressées ou défaillantes",
    "societe_recente": "Société récente à gros volumes",
    "productivite_exces": "CA par employé au-delà du 99e centile",
    "imports_sans_personnel": "Importations sans personnel",
    "ratio_import_brut": "Importations ÷ CA local (écart brut)",
    "variation_stock_ca": "Variation de stock ÷ CA",
    "part_equipement": "Part des équipements dans les importations",
    "part_regimes_suspensifs": "Part des régimes suspensifs",
    "log_ca": "Taille (CA)",
    "log_effectif": "Effectif",
    "anciennete": "Ancienneté (années)",
    "annuelles_manquantes": "Déclarations annuelles manquantes",
    "degre_reseau": "Nombre de partenaires (factures)",
    "exportatrice": "Statut exportateur",
    "secteur": "Secteur d'activité",
}

# Contraintes monotones : un excès plus grand ne peut jamais DIMINUER le risque (robustesse, explicabilité)
MONOTONES = {"exces_tej": 1, "exces_factures": 1, "exces_tva_import": 1, "exces_export": 1, "exces_banque": 1,
             "mois_non_deposes": 1, "marge_z36": -1, "annees_marge_basse": 1, "decl_sous_evaluees": 1, "ratio_prix_min": -1,
             "dans_cycle": 1, "fractionnement": 1, "reventes_equipement": 1, "remboursements_ca": 1, "liens_risque": 1,
             "societe_recente": 1, "productivite_exces": 1, "imports_sans_personnel": 1}

# Détection d'anomalies sur des indicateurs NEUTRALISÉS et unilatéraux (seul l'excès compte) : un écart brut
# expliqué (stock, équipements, régimes suspensifs, exportations) ne rend pas une entreprise atypique.
FEATURES_ANOMALIE = ["exces_tej", "exces_factures", "exces_tva_import", "exces_export", "exces_banque", "marge_basse",
                     "remboursements_ca", "productivite_exces", "mois_non_deposes", "sous_evaluation"]


def _exces(num: pd.Series, den: pd.Series, seuil: float = 1.0, hi: float = 10.0) -> pd.Series:
    r = (num / den.where(den > 0)).where(~((den <= 0) & (num > 0)), hi)
    return (r - seuil).clip(lower=0, upper=hi).fillna(0)


def construire_features(ctx: Contexte, res: dict[str, pd.DataFrame]) -> pd.DataFrame:
    ids = ctx.actives()
    a = ctx.annuel[ctx.annuel.active_annee]
    g = a.groupby(level="entreprise_id")
    X = pd.DataFrame(index=ids)
    mx = lambda s: s.groupby(level=0).max().reindex(ids).fillna(0)  # noqa: E731
    X["exces_tej"] = mx(_exces(a.tej_recu, a.ca_decl))
    X["exces_factures"] = mx(_exces(a.factures_emises, a.ca_decl))
    paye = np.maximum(a.tva_import_payee, a.tva_import_payee_decalee)
    X["exces_tva_import"] = mx(_exces(a.tva_deductible_import, paye))
    biens = a.secteur.map(lambda s: bool(ctx.secteur_info(s).get("ventes_biens", True)))
    X["exces_export"] = mx(_exces(a.ca_export_tva, a.exports_douane).where(biens, 0))
    X["exces_banque"] = mx(_exces(a.encaissements, a.ca_ttc, 1.2))
    X["mois_non_deposes"] = res["A5"].valeur.reindex(ids).fillna(0)
    # marge cumulée sur 36 mois glissants (neutralise les décalages de période), en écarts-types du secteur
    ok = a.marge_implicite.notna()
    ca36 = a.ca_decl.where(ok).groupby(level=0).sum()
    cout36 = a.cout_net.where(ok).groupby(level=0).sum()
    marge36 = (ca36 / cout36.where(cout36 > 0) - 1).reindex(ids)
    sect = ctx.ent.secteur_groupe.reindex(ids)
    sd = sect.map(lambda s: float(ctx.secteurs.loc[s, "marge_sd"]) if s in ctx.secteurs.index else 0.1)
    med = sect.map(ctx.marge_mediane_secteur)
    X["marge_z36"] = ((marge36 - med) / sd).clip(-30, 30).fillna(0)
    seuil = a.get("seuil_b1", pd.Series(0.0, index=a.index))
    X["annees_marge_basse"] = (a.marge_implicite < seuil).groupby(level=0).sum().reindex(ids).fillna(0)
    b2 = getattr(ctx, "_b2_lignes", pd.DataFrame(columns=["entreprise_id", "numero_declaration", "ratio_ref"]))
    X["decl_sous_evaluees"] = b2.groupby("entreprise_id").numero_declaration.nunique().reindex(ids).fillna(0)
    X["ratio_prix_min"] = b2.groupby("entreprise_id").ratio_ref.median().reindex(ids).fillna(1.0)
    X["dans_cycle"] = res["B3"].declenchee.reindex(ids).astype(float)
    X["fractionnement"] = res["C1"].valeur.reindex(ids).fillna(0)
    X["reventes_equipement"] = res["C2"].valeur.reindex(ids).fillna(0)
    X["mois_credit_max"] = g.mois_credit.max().reindex(ids).fillna(0)
    exportatrice = ctx.ent.statut_export.reindex(ids) != "local"
    remb = (g.remboursements.sum() / g.ca_decl.sum().where(g.ca_decl.sum() > 0)).reindex(ids)
    X["remboursements_ca"] = remb.where(~exportatrice, 0).clip(0, 5).fillna(0)
    c4 = res["C4"]
    X["liens_risque"] = c4.details.map(lambda d: 1.0 if d.get("lie") else 0.0).reindex(ids).fillna(0)
    X["societe_recente"] = c4.details.map(lambda d: 1.0 if d.get("jeune") else 0.0).reindex(ids).fillna(0)
    c5 = res["C5"]
    X["productivite_exces"] = ((c5.valeur / c5.seuil) - 1).clip(0, 20).reindex(ids).fillna(0)
    X["imports_sans_personnel"] = c5.details.map(lambda d: 1.0 if d.get("imports_sans_personnel") else 0.0).reindex(ids).fillna(0)
    X["ratio_import_brut"] = mx((a.imports_total / a.ca_local_tva.where(a.ca_local_tva > 0)).clip(upper=20)).clip(0, 20)
    X["variation_stock_ca"] = mx((a.delta_stock.abs() / a.ca_decl.where(a.ca_decl > 0)).clip(0, 10))
    tot_imp = g.imports_total.sum().reindex(ids)
    X["part_equipement"] = (g.imports_equipement.sum().reindex(ids) / tot_imp.where(tot_imp > 0)).fillna(0)
    X["part_regimes_suspensifs"] = (g.imports_at.sum().reindex(ids) / tot_imp.where(tot_imp > 0)).fillna(0)
    X["log_ca"] = np.log1p(a.xs(ANNEES[-1], level="annee").ca_decl.reindex(ids).fillna(0))
    X["log_effectif"] = np.log1p(ctx.ent.effectif.reindex(ids))
    X["anciennete"] = ((pd.Timestamp(FIN_PERIODE) - ctx.ent.date_creation).dt.days / 365.25).reindex(ids)
    X["annuelles_manquantes"] = (a.active_annee_complete & ~a.annuelle_presente).groupby(level=0).sum().reindex(ids).fillna(0)
    f = ctx.factures
    deg = pd.concat([f.groupby("emetteur_id").client_id.nunique(), f.groupby("client_id").emetteur_id.nunique()], axis=1).sum(axis=1)
    X["degre_reseau"] = deg.reindex(ids).fillna(0)
    X["exportatrice"] = ctx.ent.statut_export.reindex(ids).map({"local": 0, "partiellement exportatrice": 1,
                                                                 "totalement exportatrice": 2}).fillna(0)
    X["secteur"] = pd.Categorical(sect)
    return X


def etiquettes(ctx: Contexte, resultats: pd.DataFrame | None = None) -> pd.Series:
    """Dernier contrôle connu par entreprise : redressement (1) ou non (0). Étiquettes imparfaites."""
    c = ctx.tables["controles_historiques"].sort_values("date_controle")
    y = c.groupby("entreprise_id").redressement.last().astype(int)
    if resultats is not None and len(resultats):  # boucle d'apprentissage : résultats saisis par les agents
        r = resultats.sort_values("saisi_le").groupby("entreprise_id").redressement.last().astype(int)
        y = pd.concat([y[~y.index.isin(r.index)], r])
    return y[y.index.isin(ctx.actives())]


def _lgbm(colonnes: list[str]) -> lgb.LGBMClassifier:
    return lgb.LGBMClassifier(n_estimators=250, learning_rate=0.04, num_leaves=12, min_child_samples=12, subsample=0.8,
                              subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=SEED, verbose=-1,
                              monotone_constraints=[MONOTONES.get(c, 0) for c in colonnes],
                              monotone_constraints_method="advanced")


def entrainer(X: pd.DataFrame, y: pd.Series) -> dict:
    """Retourne probabilités calibrées (hors échantillon pour les entreprises étiquetées), modèle et métriques."""
    Xl, yl = X.loc[y.index], y.values
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    calib = CalibratedClassifierCV(_lgbm(list(X.columns)), method="isotonic", cv=5)
    oof = cross_val_predict(calib, Xl, yl, cv=cv, method="predict_proba")[:, 1]
    calib.fit(Xl, yl)
    p = pd.Series(calib.predict_proba(X)[:, 1], index=X.index)
    p.loc[y.index] = oof  # score hors échantillon pour les entreprises déjà contrôlées
    base = _lgbm(list(X.columns)).fit(Xl, yl)
    metriques = {"n_etiquettes": int(len(yl)), "taux_redressement": float(yl.mean()),
                 "auc_validation_croisee": float(roc_auc_score(yl, oof)), "brier_validation_croisee": float(brier_score_loss(yl, oof))}
    log.info("Modèle : %s", metriques)
    return {"proba": p.clip(PROBA_MIN, PROBA_MAX), "modele_calibre": calib, "modele_base": base, "metriques": metriques}


def anomalies(X: pd.DataFrame, secteurs: pd.Series, min_taille: int = 40) -> pd.Series:
    """Isolation Forest par secteur ; score = rang percentile de l'anomalie dans le secteur (0 à 1)."""
    Z = X.assign(marge_basse=(-X.marge_z36).clip(lower=0), sous_evaluation=(1 - X.ratio_prix_min).clip(lower=0))
    Z = Z[FEATURES_ANOMALIE].astype(float).fillna(0)
    out = pd.Series(0.5, index=X.index)
    petits = []
    for sect, idx in secteurs.groupby(secteurs).groups.items():
        if len(idx) < min_taille:
            petits.extend(idx)
            continue
        out.loc[idx] = _if_score(Z.loc[idx])
    if petits:
        out.loc[petits] = _if_score(Z.loc[petits]) if len(petits) >= 10 else 0.5
    # atypicité : 0 pour la moitié la plus typique du secteur, puis linéaire jusqu'à 1
    return (2 * out - 1).clip(0, 1)


def _if_score(Z: pd.DataFrame) -> pd.Series:
    Zs = RobustScaler().fit_transform(Z)
    Zs = np.clip(np.nan_to_num(Zs), -50, 50)
    iso = IsolationForest(n_estimators=200, random_state=SEED, contamination="auto").fit(Zs)
    s = -iso.score_samples(Zs)
    return pd.Series(s, index=Z.index).rank(pct=True)


def valeurs_shap(modele_base: lgb.LGBMClassifier, X: pd.DataFrame) -> pd.DataFrame:
    expl = shap.TreeExplainer(modele_base)
    sv = expl.shap_values(X)
    if isinstance(sv, list):  # anciennes versions : [classe 0, classe 1]
        sv = sv[1]
    sv = np.asarray(sv)
    if sv.ndim == 3:
        sv = sv[:, :, 1]
    return pd.DataFrame(sv, index=X.index, columns=X.columns)
