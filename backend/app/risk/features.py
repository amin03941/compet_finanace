"""Chargement des données et agrégats par entreprise et par année (base du moteur de risque).

Le contexte est construit à partir de DataFrames : les tests unitaires des règles
fabriquent de petits contextes à la main, l'application le charge depuis SQLite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy.engine import Engine

from .. import config, db

ANNEES = list(config.YEARS)
FIN_PERIODE = date(ANNEES[-1], 12, 31)

TABLES = ("entreprises", "declarations_douane", "declarations_tva", "declarations_annuelles", "retenues_source",
          "factures_electroniques", "encaissements_bancaires", "roles", "controles_historiques", "prix_reference",
          "parametres", "secteurs_reference")


def charger_tables(engine: Engine | None = None) -> dict[str, pd.DataFrame]:
    engine = engine or db.get_engine()
    out = {}
    with engine.connect() as conn:
        for t in TABLES:
            out[t] = pd.read_sql_table(t, conn)
    for t, col in (("declarations_douane", "date"), ("retenues_source", "date"), ("factures_electroniques", "date"),
                   ("controles_historiques", "date_controle")):
        out[t][col] = pd.to_datetime(out[t][col])
    for col in ("date_creation", "date_radiation"):
        out["entreprises"][col] = pd.to_datetime(out["entreprises"][col])
    return out


def _idx(ids, annees=ANNEES) -> pd.MultiIndex:
    return pd.MultiIndex.from_product([ids, annees], names=["entreprise_id", "annee"])


@dataclass
class Contexte:
    tables: dict[str, pd.DataFrame]
    parametres: dict[str, float] = field(default_factory=dict)
    secteurs: pd.DataFrame | None = None

    def __post_init__(self):
        t = self.tables
        self.ent = t["entreprises"].set_index("id")
        self.parametres = dict(zip(t["parametres"].cle, t["parametres"].valeur)) if len(t.get("parametres", [])) else {}
        self.secteurs = t["secteurs_reference"].set_index("secteur_groupe") if len(t.get("secteurs_reference", [])) else pd.DataFrame()
        self.taux_tva = float(self.parametres.get("taux_tva_normal", 0.19))
        self._agreger()

    # ---------------------------------------------------------------- agrégats
    def _agreger(self) -> None:
        t, ids = self.tables, self.ent.index
        idx = _idx(ids)
        # --- douane
        d = t["declarations_douane"].copy()
        d["annee"] = d.date.dt.year
        d["mois"] = d.date.dt.month
        imp = d[d.flux == "import"]
        mc = imp[(imp.regime == "mise à la consommation") & (~imp.est_equipement.astype(bool))]
        self.douane = d
        ag = pd.DataFrame(index=idx)
        ag["imports_revente"] = mc.groupby(["entreprise_id", "annee"]).base_tva.sum()
        ag["imports_at"] = imp[imp.regime.isin(["admission temporaire", "entrepôt"])].groupby(["entreprise_id", "annee"]).valeur_cif_dt.sum()
        ag["imports_equipement"] = imp[imp.est_equipement.astype(bool)].groupby(["entreprise_id", "annee"]).valeur_cif_dt.sum()
        ag["imports_total"] = imp.groupby(["entreprise_id", "annee"]).valeur_cif_dt.sum()
        ag["tva_import_payee"] = imp.groupby(["entreprise_id", "annee"]).tva_import.sum()
        ag["exports_douane"] = d[d.flux == "export"].groupby(["entreprise_id", "annee"]).valeur_cif_dt.sum()
        # TVA import payée de décembre (Y-1) à novembre (Y) : tolérance d'un mois de décalage
        tva_m = imp.groupby(["entreprise_id", "annee", "mois"]).tva_import.sum().reset_index()
        tva_m["annee_decalee"] = np.where(tva_m.mois == 12, tva_m.annee + 1, tva_m.annee)
        ag["tva_import_payee_decalee"] = tva_m.groupby(["entreprise_id", "annee_decalee"]).tva_import.sum().rename_axis(
            ["entreprise_id", "annee"])
        # --- TVA mensuelle
        v = t["declarations_tva"].copy()
        # mois en position créditrice : TVA déductible du mois supérieure à la TVA collectée
        v["credit"] = (v.tva_collectee - v.tva_deductible_import - v.tva_deductible_local - v.tva_deductible_immobilisations) < 0
        v["credit"] &= v.deposee.astype(bool)
        v["ca"] = v.ca_local_ht + v.ca_export_ht
        self.tva = v
        g = v.groupby(["entreprise_id", "annee"])
        ag["ca_local_tva"] = g.ca_local_ht.sum()
        ag["ca_export_tva"] = g.ca_export_ht.sum()
        ag["ca_tva"] = g.ca.sum()
        ag["tva_collectee"] = g.tva_collectee.sum()
        ag["tva_deductible_import"] = g.tva_deductible_import.sum()
        ag["tva_deductible_local"] = g.tva_deductible_local.sum()
        ag["mois_credit"] = g.credit.sum()
        ag["remboursements"] = g.remboursement_demande.sum()
        ag["mois_declares"] = g.size()
        ag["mois_non_deposes"] = v[~v.deposee.astype(bool)].groupby(["entreprise_id", "annee"]).size()
        # --- annuelles
        a = t["declarations_annuelles"].set_index(["entreprise_id", "annee"])
        for c in ("chiffre_affaires", "achats_marchandises", "achats_matieres", "stock_initial", "stock_final",
                  "charges_personnel", "resultat_fiscal"):
            ag[c] = a[c]
        ag["annuelle_presente"] = pd.Series(idx.isin(a.index), index=idx)
        # --- tiers
        tej = t["retenues_source"].copy()
        tej["annee"] = tej.date.dt.year
        self.tej = tej
        ag["tej_recu"] = tej.groupby(["beneficiaire_id", "annee"]).montant_brut.sum().rename_axis(["entreprise_id", "annee"])
        f = t["factures_electroniques"].copy()
        f["annee"] = f.date.dt.year
        self.factures = f
        ag["factures_emises"] = f.groupby(["emetteur_id", "annee"]).montant_ht.sum().rename_axis(["entreprise_id", "annee"])
        ag["factures_recues"] = f.groupby(["client_id", "annee"]).montant_ht.sum().rename_axis(["entreprise_id", "annee"])
        b = t["encaissements_bancaires"]
        self.banque = b
        ag["encaissements"] = b.groupby(["entreprise_id", "annee"]).total_encaissements.sum()
        num = [c for c in ag.columns if c != "annuelle_presente"]
        ag[num] = ag[num].astype(float).fillna(0.0)
        # CA de référence : déclarations mensuelles de TVA, à défaut la déclaration annuelle
        ag["ca_decl"] = np.where(ag.mois_declares > 0, ag.ca_tva, ag.chiffre_affaires)
        ag["ca_ttc"] = ag.ca_local_tva * (1 + self.taux_tva) + ag.ca_export_tva
        # activité de l'année
        ent = self.ent
        crea = ent.date_creation.reindex(ag.index.get_level_values(0)).values
        rad = ent.date_radiation.reindex(ag.index.get_level_values(0)).values
        annees = ag.index.get_level_values(1)
        debut = pd.to_datetime([f"{y}-01-01" for y in annees]).values
        fin = pd.to_datetime([f"{y}-12-31" for y in annees]).values
        ag["active_annee_complete"] = (crea <= debut) & (pd.isna(rad) | (rad >= fin))
        ag["active_annee"] = (crea <= fin) & (pd.isna(rad) | (rad >= debut))
        # coût des ventes net (neutralisé : hors équipements et régimes suspensifs)
        achats_decl = ag.achats_marchandises + ag.achats_matieres
        ag["achats_locaux"] = (achats_decl - ag.imports_revente - ag.imports_at).clip(lower=0)
        ag["delta_stock"] = ag.stock_final - ag.stock_initial
        ag["cout_net"] = ag.imports_revente + ag.achats_locaux - ag.delta_stock
        # B1 non applicable : services, régimes suspensifs dominants (admission temporaire), coût non significatif
        type_secteur = ent.secteur_groupe.map(self.secteurs["type"] if len(self.secteurs) else {}).reindex(ag.index.get_level_values(0)).values
        applicable = (ag.annuelle_presente & (type_secteur != "services")
                      & (ag.imports_at <= 0.2 * (ag.imports_revente + ag.achats_locaux + 1))
                      & (ag.cout_net > 0.05 * np.maximum(ag.ca_decl, 1)) & (ag.cout_net > 10_000))
        ag["marge_implicite"] = np.where(applicable, ag.ca_decl / ag.cout_net.where(ag.cout_net > 0, np.nan) - 1, np.nan)
        ag["secteur"] = ent.secteur_groupe.reindex(ag.index.get_level_values(0)).values
        self.annuel = ag
        # séries mensuelles utiles (TVA + banque + importations du mois)
        mens = v.merge(b, on=["entreprise_id", "annee", "mois"], how="left")
        imp_m = imp.groupby(["entreprise_id", "annee", "mois"]).valeur_cif_dt.sum().rename("imports_mois").reset_index()
        mens = mens.merge(imp_m, on=["entreprise_id", "annee", "mois"], how="left")
        mens[["total_encaissements", "imports_mois"]] = mens[["total_encaissements", "imports_mois"]].astype(float).fillna(0.0)
        self.mensuel = mens
        # percentiles sectoriels de marge implicite (toutes entreprises, années complètes)
        base = ag[ag.active_annee_complete & ag.marge_implicite.notna()]
        self.marge_p5 = base.groupby("secteur").marge_implicite.quantile(0.05)
        self.marge_med_obs = base.groupby("secteur").marge_implicite.median()
        self.marge_mad = base.groupby("secteur").marge_implicite.apply(lambda s: (s - s.median()).abs().median() * 1.4826)
        # productivité : CA par employé (P99 sectoriel)
        eff = ent.effectif.clip(lower=1)
        ca_last = ag.xs(ANNEES[-1], level="annee").ca_decl
        self.ca_par_employe = (ca_last / eff.reindex(ca_last.index)).rename("ca_par_employe")
        self.cpe_p99 = pd.concat([self.ca_par_employe, ent.secteur_groupe], axis=1).groupby("secteur_groupe").ca_par_employe.quantile(0.99)

    # ---------------------------------------------------------------- utilitaires
    def marge_mediane_secteur(self, secteur: str) -> float:
        cle = f"marge_mediane.{secteur}"
        if cle in self.parametres:
            return float(self.parametres[cle])
        if self.secteurs is not None and secteur in self.secteurs.index:
            return float(self.secteurs.loc[secteur, "marge_mediane"])
        return float(self.marge_med_obs.get(secteur, 0.2))

    def secteur_info(self, secteur: str) -> dict:
        if self.secteurs is not None and secteur in self.secteurs.index:
            return self.secteurs.loc[secteur].to_dict()
        return {"libelle": secteur, "type": "negoce", "habituellement_crediteur": False, "ventes_biens": True}

    def actives(self) -> pd.Index:
        return self.ent.index[self.ent.statut == "active"]


def charger_contexte(engine: Engine | None = None) -> Contexte:
    return Contexte(charger_tables(engine))
