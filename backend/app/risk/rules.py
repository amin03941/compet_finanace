"""Catalogue des indicateurs (section 6.2). Chaque règle retourne, par entreprise :
valeur, seuil, déclenchée, force (A/B/C), montant en jeu, phrase explicative, et
fournit ses preuves (lignes sources) à la demande.

Niveau A : contradiction arithmétique avec des données de tiers (quasi-preuve).
Niveau B : anomalie économique forte, après neutralisation des explications légitimes.
Niveau C : signaux de contexte (ne suffisent jamais seuls).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd

from .. import fmt
from .features import ANNEES, FIN_PERIODE, Contexte

COLONNES = ["valeur", "seuil", "declenchee", "montant", "annee", "annees", "details"]

# Famille de montant : les règles d'une même famille estiment le même enjeu (on garde le maximum)
# (A5 et B3 : TVA non reversée sur des ventes = même enjeu que les ventes omises, pas de double comptage)
FAMILLES = {"A1": "ventes_omises", "A2": "ventes_omises", "B1": "ventes_omises", "B4": "ventes_omises",
            "A5": "ventes_omises", "B3": "ventes_omises", "A3": "tva_import", "A4": "exportations",
            "B2": "douane", "C2": "avantages"}


def _vide(ids) -> pd.DataFrame:
    df = pd.DataFrame(index=pd.Index(ids, name="entreprise_id"))
    df["valeur"] = np.nan
    df["seuil"] = np.nan
    df["declenchee"] = False
    df["montant"] = 0.0
    df["annee"] = ANNEES[-1]
    df["annees"] = [[] for _ in range(len(df))]
    df["details"] = [{} for _ in range(len(df))]
    return df


def _par_annee(ctx: Contexte, valeur: pd.Series, declenche: pd.Series, montant: pd.Series, seuil: float,
               details_cols: list[str]) -> pd.DataFrame:
    """Réduit un indicateur annuel à une ligne par entreprise (année focale = dernière année déclenchée)."""
    a = ctx.annuel
    df = pd.DataFrame({"valeur": valeur, "declenche": declenche.fillna(False), "montant": montant.fillna(0)})
    for c in details_cols:
        df[c] = a[c]
    df = df[a.active_annee]
    out = _vide(ctx.ent.index)
    if df.empty:
        return out
    trig = df[df.declenche]
    annees = trig.reset_index().groupby("entreprise_id").annee.apply(list)
    last_trig = trig.reset_index().groupby("entreprise_id").annee.max()
    last_any = df.dropna(subset=["valeur"]).reset_index().groupby("entreprise_id").annee.max()
    focus = last_trig.combine_first(last_any).astype(int)
    rows = df.loc[list(zip(focus.index, focus.values))]
    rows.index = rows.index.get_level_values(0)
    out.loc[rows.index, "valeur"] = rows.valeur
    out.loc[rows.index, "annee"] = focus
    out["seuil"] = seuil
    out.loc[annees.index, "declenchee"] = True
    ann = annees.to_dict()
    out["annees"] = [list(ann.get(i, [])) for i in out.index]
    out.loc[annees.index, "montant"] = rows.loc[annees.index, "montant"].clip(lower=0)
    det = rows[details_cols].to_dict("index")
    out["details"] = [det.get(i, {}) for i in out.index]
    return out


@dataclass
class Regle:
    code: str
    niveau: str
    libelle: str
    formule: str
    condition: str

    def evaluer(self, ctx: Contexte) -> pd.DataFrame:  # pragma: no cover - interface
        raise NotImplementedError

    def phrase(self, r: dict, ctx: Contexte, eid: int) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def preuves(self, ctx: Contexte, eid: int) -> dict:  # pragma: no cover - interface
        raise NotImplementedError

    def as_dict(self) -> dict:
        return {"code": self.code, "niveau": self.niveau, "libelle": self.libelle, "formule": self.formule,
                "condition": self.condition, "famille": FAMILLES.get(self.code)}


def _preuves_df(df: pd.DataFrame, colonnes: dict[str, str], source: str, limite: int = 200) -> dict:
    df = df.head(limite).copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%d/%m/%Y")
    lignes = df[list(colonnes)].rename(columns=colonnes).replace({np.nan: None}).to_dict("records")
    return {"source": source, "colonnes": list(colonnes.values()), "lignes": lignes, "total": int(len(df))}


# ============================================================================ Niveau A
class A1(Regle):
    def __init__(self):
        super().__init__("A1", "A", "Paiements attestés par les clients supérieurs au chiffre d'affaires",
                         "Σ montants bruts des certificats de retenue à la source (TEJ) reçus sur l'année ÷ CA déclaré",
                         "ratio > 1,05")

    def evaluer(self, ctx):
        a = ctx.annuel
        ratio = np.where(a.ca_decl > 0, a.tej_recu / a.ca_decl.where(a.ca_decl > 0, 1), np.where(a.tej_recu > 0, np.inf, np.nan))
        ratio = pd.Series(ratio, index=a.index)
        dec = (ratio > 1.05) & (a.tej_recu - a.ca_decl > 5_000)
        return _par_annee(ctx, ratio, dec, (a.tej_recu - a.ca_decl) * ctx.taux_tva, 1.05, ["tej_recu", "ca_decl"])

    def phrase(self, r, ctx, eid):
        d = r["details"]
        return (f"Ses clients attestent l'avoir payée {fmt.dt(d.get('tej_recu'))} en {r['annee']} (certificats de retenue TEJ), "
                f"mais elle déclare {fmt.dt(d.get('ca_decl'))} de chiffre d'affaires.")

    def preuves(self, ctx, eid):
        t = ctx.tej[ctx.tej.beneficiaire_id == eid].merge(
            ctx.ent[["raison_sociale"]], left_on="payeur_id", right_index=True, how="left").sort_values("date", ascending=False)
        return _preuves_df(t, {"id": "Certificat n°", "date": "Date", "raison_sociale": "Client payeur",
                               "montant_brut": "Montant brut (DT)", "montant_retenu": "Retenue (DT)"},
                           "Plateforme TEJ — certificats de retenue à la source émis par les clients")


class A2(Regle):
    def __init__(self):
        super().__init__("A2", "A", "Factures électroniques émises supérieures au chiffre d'affaires",
                         "Σ montants HT des factures El Fatoora émises ÷ CA déclaré (mensuel et annuel)", "ratio > 1,05 sur l'année")

    def evaluer(self, ctx):
        a = ctx.annuel
        ratio = pd.Series(np.where(a.ca_decl > 0, a.factures_emises / a.ca_decl.where(a.ca_decl > 0, 1),
                                   np.where(a.factures_emises > 0, np.inf, np.nan)), index=a.index)
        dec = (ratio > 1.05) & (a.factures_emises - a.ca_decl > 5_000)
        return _par_annee(ctx, ratio, dec, (a.factures_emises - a.ca_decl) * ctx.taux_tva, 1.05, ["factures_emises", "ca_decl"])

    def phrase(self, r, ctx, eid):
        d = r["details"]
        return f"Elle a facturé {fmt.dt(d.get('factures_emises'))} via El Fatoora en {r['annee']} mais déclaré {fmt.dt(d.get('ca_decl'))}."

    def preuves(self, ctx, eid):
        f = ctx.factures[ctx.factures.emetteur_id == eid].merge(
            ctx.ent[["raison_sociale"]], left_on="client_id", right_index=True, how="left").sort_values("date", ascending=False)
        return _preuves_df(f, {"id": "Facture n°", "date": "Date", "raison_sociale": "Client", "montant_ht": "Montant HT (DT)",
                               "tva": "TVA (DT)"}, "El Fatoora — factures électroniques émises")


class A3(Regle):
    def __init__(self):
        super().__init__("A3", "A", "TVA déduite à l'import supérieure à la TVA payée à la douane",
                         "Σ TVA déductible import (déclarations de TVA) − Σ TVA import payée (douane), décalage d'un mois toléré",
                         "écart > 2 % et > 5 000 DT")

    def evaluer(self, ctx):
        a = ctx.annuel
        paye = np.maximum(a.tva_import_payee, a.tva_import_payee_decalee)
        ecart = a.tva_deductible_import - paye
        ratio = pd.Series(np.where(paye > 0, a.tva_deductible_import / paye.where(paye > 0, 1),
                                   np.where(a.tva_deductible_import > 0, np.inf, np.nan)), index=a.index)
        dec = (ecart > 0.02 * paye) & (ecart > 5_000)
        a = a.assign(tva_payee_retenue=paye)
        ctx.annuel["tva_payee_retenue"] = paye
        return _par_annee(ctx, ratio, dec, ecart, 1.02, ["tva_deductible_import", "tva_payee_retenue"])

    def phrase(self, r, ctx, eid):
        d = r["details"]
        return (f"Elle a déduit {fmt.dt(d.get('tva_deductible_import'))} de TVA à l'import en {r['annee']} "
                f"pour {fmt.dt(d.get('tva_payee_retenue'))} payés à la douane.")

    def preuves(self, ctx, eid):
        d = ctx.douane[(ctx.douane.entreprise_id == eid) & (ctx.douane.flux == "import") & (ctx.douane.tva_import > 0)]
        d = d.sort_values("date", ascending=False)
        return _preuves_df(d, {"numero_declaration": "Déclaration", "date": "Date", "designation": "Marchandise",
                               "base_tva": "Base TVA (DT)", "tva_import": "TVA payée (DT)"},
                           "Douane — TVA acquittée à l'importation (à comparer aux déclarations mensuelles de TVA)")


class A4(Regle):
    def __init__(self):
        super().__init__("A4", "A", "Exportations déclarées au fisc supérieures aux exportations constatées en douane",
                         "CA export déclaré en TVA ÷ Σ exportations en douane", "ratio > 1,10")

    def evaluer(self, ctx):
        a = ctx.annuel
        biens = a.secteur.map(lambda s: bool(ctx.secteur_info(s).get("ventes_biens", True)))
        ratio = pd.Series(np.where(a.exports_douane > 0, a.ca_export_tva / a.exports_douane.where(a.exports_douane > 0, 1),
                                   np.where(a.ca_export_tva > 0, np.inf, np.nan)), index=a.index)
        ratio = ratio.where(biens)
        dec = (ratio > 1.10) & (a.ca_export_tva - a.exports_douane > 10_000) & biens
        return _par_annee(ctx, ratio, dec, (a.ca_export_tva - a.exports_douane) * ctx.taux_tva, 1.10,
                          ["ca_export_tva", "exports_douane"])

    def phrase(self, r, ctx, eid):
        d = r["details"]
        return (f"Exportations déclarées au fisc en {r['annee']} : {fmt.dt(d.get('ca_export_tva'))} ; "
                f"constatées en douane : {fmt.dt(d.get('exports_douane'))}.")

    def preuves(self, ctx, eid):
        d = ctx.douane[(ctx.douane.entreprise_id == eid) & (ctx.douane.flux == "export")].sort_values("date", ascending=False)
        return _preuves_df(d, {"numero_declaration": "Déclaration", "date": "Date", "regime": "Régime", "designation": "Marchandise",
                               "valeur_cif_dt": "Valeur (DT)"}, "Douane — déclarations d'exportation")


class A5(Regle):
    def __init__(self):
        super().__init__("A5", "A", "Défaut de déclaration de TVA malgré une activité",
                         "Mois sans déclaration de TVA déposée alors que des importations ou des encaissements ont lieu",
                         "au moins 3 mois manquants")

    def evaluer(self, ctx):
        m = ctx.mensuel
        manquants = m[(~m.deposee.astype(bool)) & ((m.total_encaissements > 10_000) | (m.imports_mois > 0))]
        out = _vide(ctx.ent.index)
        out["seuil"] = 3
        g = manquants.groupby("entreprise_id")
        n = g.size()
        out.loc[n.index, "valeur"] = n
        out["valeur"] = out.valeur.fillna(0)
        trig = n[n >= 3].index
        out.loc[trig, "declenchee"] = True
        enc = g.total_encaissements.sum()
        imp = g.imports_mois.sum()
        out.loc[trig, "montant"] = (enc.loc[trig] / 1.2 * ctx.taux_tva / (1 + ctx.taux_tva))
        for eid in trig:
            mm = manquants[manquants.entreprise_id == eid]
            out.at[eid, "annee"] = int(mm.annee.max())
            out.at[eid, "annees"] = sorted(mm.annee.unique().tolist())
            out.at[eid, "details"] = {"mois": [fmt.mois_fr(y, mo) for y, mo in zip(mm.annee, mm.mois)],
                                      "encaissements": float(enc[eid]), "imports": float(imp[eid])}
        return out

    def phrase(self, r, ctx, eid):
        d = r["details"]
        mois = d.get("mois", [])
        periode = f"de {mois[0]} à {mois[-1]}" if len(mois) > 1 else (mois[0] if mois else "")
        return (f"Aucune déclaration de TVA pendant {int(r['valeur'])} mois ({periode}), alors que "
                f"{fmt.dt(d.get('encaissements'))} ont été encaissés et {fmt.dt(d.get('imports'))} d'importations sont passées.")

    def preuves(self, ctx, eid):
        m = ctx.mensuel[(ctx.mensuel.entreprise_id == eid) & (~ctx.mensuel.deposee.astype(bool))].copy()
        m["periode"] = [fmt.mois_fr(y, mo) for y, mo in zip(m.annee, m.mois)]
        m["statut"] = "non déposée"
        return _preuves_df(m, {"periode": "Mois", "statut": "Déclaration de TVA", "total_encaissements": "Encaissements (DT)",
                               "imports_mois": "Importations (DT)"}, "Déclarations mensuelles de TVA et relevés bancaires agrégés")


# ============================================================================ Niveau B
class B1(Regle):
    def __init__(self):
        super().__init__("B1", "B", "Marge implicite impossible",
                         "coût des ventes net = importations à revendre (hors équipements et régimes suspensifs) + achats locaux − Δstock ; "
                         "marge = CA ÷ coût − 1, comparée à la distribution du secteur", "marge < 5e centile du secteur (ou négative) sur au moins 2 ans")

    def evaluer(self, ctx):
        a = ctx.annuel
        p5 = a.secteur.map(ctx.marge_p5)
        seuil = np.maximum(p5.fillna(0), 0.0)
        dec_annee = a.marge_implicite < seuil
        med = a.secteur.map(lambda s: ctx.marge_mediane_secteur(s))
        ca_recon = a.cout_net * (1 + med)
        ecart = (ca_recon - a.ca_decl).clip(lower=0)
        ctx.annuel["ca_reconstitue"] = ca_recon
        ctx.annuel["marge_mediane_ref"] = med
        ctx.annuel["seuil_b1"] = seuil
        res = _par_annee(ctx, a.marge_implicite, dec_annee, ecart * ctx.taux_tva, 0.0,
                         ["marge_implicite", "cout_net", "ca_decl", "ca_reconstitue", "marge_mediane_ref", "seuil_b1",
                          "imports_revente", "achats_locaux", "delta_stock"])
        # persistance : au moins 2 années
        n = res.annees.map(len)
        res.loc[n < 2, "declenchee"] = False
        res.loc[n < 2, "montant"] = 0.0
        res["seuil"] = [d.get("seuil_b1", 0.0) if d else 0.0 for d in res.details]
        return res

    def phrase(self, r, ctx, eid):
        d = r["details"]
        n = len(r["annees"])
        return (f"Marge implicite de {fmt.pct(d.get('marge_implicite'))} en {r['annee']} (coût des ventes net {fmt.dt(d.get('cout_net'))}, "
                f"CA {fmt.dt(d.get('ca_decl'))}) alors que la médiane du secteur est de {fmt.pct(d.get('marge_mediane_ref'))} "
                f"— {n} année{'s' if n > 1 else ''} sur {len(ANNEES)}.")

    def preuves(self, ctx, eid):
        a = ctx.annuel.loc[eid].reset_index()
        a = a[a.annuelle_presente]
        return _preuves_df(a, {"annee": "Année", "imports_revente": "Importations à revendre (DT)", "achats_locaux": "Achats locaux (DT)",
                               "delta_stock": "Variation de stock (DT)", "cout_net": "Coût des ventes net (DT)",
                               "ca_decl": "CA déclaré (DT)", "marge_implicite": "Marge implicite"},
                           "Douane (importations) + déclarations annuelles (achats, stocks) + déclarations de TVA (CA)")


class B2(Regle):
    def __init__(self):
        super().__init__("B2", "B", "Sous-évaluation en douane",
                         "valeur unitaire déclarée vs prix de référence (même code SH et même origine)",
                         "< 10e centile et < 70 % de la médiane, sur au moins 3 déclarations")

    def _lignes(self, ctx) -> pd.DataFrame:
        d = ctx.douane
        d = d[(d.flux == "import") & (d.regime == "mise à la consommation") & (~d.est_equipement.astype(bool)) & (d.quantite > 0)]
        d = d.merge(ctx.tables["prix_reference"], on=["code_sh", "pays_origine"], how="inner")
        d["pu"] = d.valeur_cif_dt / d.quantite
        d["ratio_ref"] = d.pu / d.prix_unitaire_median
        return d[(d.pu < d.p10) & (d.ratio_ref < 0.70)]

    def evaluer(self, ctx):
        s = self._lignes(ctx)
        s = s.assign(ecart=(s.prix_unitaire_median * s.quantite - s.valeur_cif_dt).clip(lower=0))
        s = s.assign(enjeu=s.ecart * (s.taux_droits + ctx.taux_tva * (1 + s.taux_droits)))
        ctx._b2_lignes = s
        out = _vide(ctx.ent.index)
        out["seuil"] = 0.70
        g = s.groupby("entreprise_id")
        n_decl = g.numero_declaration.nunique()
        trig = n_decl[n_decl >= 3].index
        out.loc[trig, "declenchee"] = True
        for eid in trig:
            e = s[s.entreprise_id == eid]
            focus = int(e.annee.max())
            ef = e[e.annee == focus]
            top = ef.groupby(["designation", "pays_origine"]).size().idxmax()
            out.at[eid, "valeur"] = float(ef.ratio_ref.median())
            out.at[eid, "annee"] = focus
            out.at[eid, "annees"] = sorted(e.annee.unique().tolist())
            out.at[eid, "montant"] = float(ef.enjeu.sum())
            out.at[eid, "details"] = {"n_declarations": int(ef.numero_declaration.nunique()), "n_total": int(n_decl[eid]),
                                      "designation": top[0], "pays": top[1],
                                      "prix_ref": float(ef.prix_unitaire_median.median()), "ecart_valeur": float(ef.ecart.sum())}
        return out

    def phrase(self, r, ctx, eid):
        d = r["details"]
        return (f"{d.get('n_declarations')} déclarations en {r['annee']} ({d.get('designation')}, origine {d.get('pays')}) "
                f"à {fmt.pct(r['valeur'], 0)} du prix de référence médian ({fmt.dt(d.get('prix_ref'), 2)} l'unité).")

    def preuves(self, ctx, eid):
        s = self._lignes(ctx)
        s = s[s.entreprise_id == eid].sort_values("date", ascending=False)
        return _preuves_df(s, {"numero_declaration": "Déclaration", "date": "Date", "designation": "Marchandise",
                               "pays_origine": "Origine", "quantite": "Quantité", "pu": "Prix unitaire déclaré (DT)",
                               "prix_unitaire_median": "Prix de référence médian (DT)", "ratio_ref": "Ratio"},
                           "Douane — déclarations d'importation comparées au référentiel de prix")


class B3(Regle):
    def __init__(self):
        super().__init__("B3", "B", "Carrousel de TVA",
                         "cycles de longueur 3 ou 4 dans le graphe des factures El Fatoora (NetworkX simple_cycles)",
                         "cycle détecté avec un maillon sans reversement de TVA")

    def graphe(self, ctx) -> nx.DiGraph:
        f = ctx.factures.groupby(["emetteur_id", "client_id"]).montant_ht.sum().reset_index()
        f = f[f.montant_ht >= 50_000]
        g = nx.DiGraph()
        g.add_weighted_edges_from(f[["emetteur_id", "client_id", "montant_ht"]].itertuples(index=False, name=None))
        return g

    def maillons_suspects(self, ctx) -> set[int]:
        m = ctx.mensuel
        non_dep = m[~m.deposee.astype(bool)].groupby("entreprise_id").size()
        a = ctx.annuel
        sous = a[(a.factures_emises > 100_000) & (a.ca_decl < 0.5 * a.factures_emises)].index.get_level_values(0)
        return set(non_dep[non_dep >= 2].index) | set(sous)

    def evaluer(self, ctx):
        out = _vide(ctx.ent.index)
        out["seuil"] = 1
        g = self.graphe(ctx)
        cycles: dict[frozenset, list[int]] = {}
        for s in self.maillons_suspects(ctx):
            if s not in g:
                continue
            ego = nx.ego_graph(g, s, radius=3)
            for c in nx.simple_cycles(ego, length_bound=4):
                if len(c) >= 3 and s in c:
                    cycles.setdefault(frozenset(c), c)
        ctx._b3_cycles = list(cycles.values())
        f = ctx.factures
        for c in cycles.values():
            aretes = list(zip(c, c[1:] + c[:1]))
            fac = pd.concat([f[(f.emetteur_id == u) & (f.client_id == v)] for u, v in aretes])
            total = float(fac.montant_ht.sum())
            suspects = [x for x in c if x in self.maillons_suspects(ctx)]
            for eid in c:
                recu = float(fac[fac.client_id == eid].montant_ht.sum())
                emis = float(fac[fac.emetteur_id == eid].montant_ht.sum())
                montant = (emis if eid in suspects else recu) * ctx.taux_tva
                if montant > out.at[eid, "montant"]:
                    out.at[eid, "declenchee"] = True
                    out.at[eid, "valeur"] = len(c)
                    out.at[eid, "montant"] = montant
                    out.at[eid, "annee"] = int(fac.date.dt.year.max())
                    out.at[eid, "annees"] = sorted(fac.date.dt.year.unique().tolist())
                    out.at[eid, "details"] = {"cycle": [int(x) for x in c], "noms": [ctx.ent.at[x, "raison_sociale"] for x in c],
                                              "suspects": [ctx.ent.at[x, "raison_sociale"] for x in suspects],
                                              "total": total, "n_mois": int(fac.date.dt.to_period("M").nunique())}
        return out

    def phrase(self, r, ctx, eid):
        d = r["details"]
        noms = d.get("noms", [])
        circuit = " → ".join(noms + noms[:1])
        maillon = ", ".join(d.get("suspects", [])) or "un maillon"
        return (f"Circuit fermé de factures {circuit} ({d.get('n_mois')} mois, {fmt.dt(d.get('total'))} HT) ; "
                f"{maillon} ne reverse pas la TVA.")

    def preuves(self, ctx, eid):
        cycles = [c for c in getattr(ctx, "_b3_cycles", []) if eid in c]
        if not cycles:
            self.evaluer(ctx)
            cycles = [c for c in ctx._b3_cycles if eid in c]
        f = ctx.factures
        lignes = []
        for c in cycles:
            for u, v in zip(c, c[1:] + c[:1]):
                lignes.append(f[(f.emetteur_id == u) & (f.client_id == v)])
        df = pd.concat(lignes) if lignes else f.head(0)
        df = df.merge(ctx.ent[["raison_sociale"]].rename(columns={"raison_sociale": "emetteur"}), left_on="emetteur_id", right_index=True)
        df = df.merge(ctx.ent[["raison_sociale"]].rename(columns={"raison_sociale": "client"}), left_on="client_id", right_index=True)
        return _preuves_df(df.sort_values("date"), {"id": "Facture n°", "date": "Date", "emetteur": "Émetteur", "client": "Client",
                                                    "montant_ht": "Montant HT (DT)", "tva": "TVA (DT)"},
                           "El Fatoora — factures formant un circuit fermé")


class B4(Regle):
    def __init__(self):
        super().__init__("B4", "B", "Encaissements bancaires très supérieurs au chiffre d'affaires",
                         "Σ encaissements bancaires ÷ CA TTC déclaré", "ratio > 1,5")

    def evaluer(self, ctx):
        a = ctx.annuel
        ratio = pd.Series(np.where(a.ca_ttc > 0, a.encaissements / a.ca_ttc.where(a.ca_ttc > 0, 1),
                                   np.where(a.encaissements > 0, np.inf, np.nan)), index=a.index)
        dec = (ratio > 1.5) & (a.encaissements > 50_000)
        exces_ttc = (a.encaissements / 1.2 - a.ca_ttc).clip(lower=0)
        return _par_annee(ctx, ratio, dec, exces_ttc * ctx.taux_tva / (1 + ctx.taux_tva), 1.5, ["encaissements", "ca_ttc"])

    def phrase(self, r, ctx, eid):
        d = r["details"]
        v = r["valeur"]
        fois = fmt.ratio(v) if not math.isinf(v) else "infiniment"
        return (f"Ses encaissements bancaires ({fmt.dt(d.get('encaissements'))}) représentent {fois} fois son chiffre "
                f"d'affaires TTC déclaré ({fmt.dt(d.get('ca_ttc'))}) en {r['annee']}.")

    def preuves(self, ctx, eid):
        m = ctx.mensuel[ctx.mensuel.entreprise_id == eid].copy()
        m["periode"] = [fmt.mois_fr(y, mo) for y, mo in zip(m.annee, m.mois)]
        m["ca_ttc"] = m.ca_local_ht * (1 + ctx.taux_tva) + m.ca_export_ht
        return _preuves_df(m.sort_values(["annee", "mois"], ascending=False),
                           {"periode": "Mois", "total_encaissements": "Encaissements (DT)", "ca_ttc": "CA TTC déclaré (DT)"},
                           "Encaissements bancaires agrégés et déclarations mensuelles de TVA")


# ============================================================================ Niveau C
class C1(Regle):
    def __init__(self, seuil_dt: float = 3000.0):
        super().__init__("C1", "C", "Fractionnement des déclarations en douane",
                         "déclarations de faible valeur (< seuil de contrôle) sur 7 jours glissants, même fournisseur",
                         "au moins 5 déclarations en 7 jours")
        self.seuil_dt = seuil_dt

    def _petites(self, ctx) -> pd.DataFrame:
        d = ctx.douane[ctx.douane.flux == "import"]
        dec = d.groupby(["entreprise_id", "numero_declaration", "fournisseur_etranger"]).agg(
            date=("date", "min"), valeur=("valeur_cif_dt", "sum")).reset_index()
        return dec[dec.valeur < self.seuil_dt].sort_values(["entreprise_id", "fournisseur_etranger", "date"])

    def evaluer(self, ctx):
        seuil = float(ctx.parametres.get("seuil_fractionnement_dt", self.seuil_dt))
        self.seuil_dt = seuil
        p = self._petites(ctx)
        out = _vide(ctx.ent.index)
        out["seuil"] = 5
        out["valeur"] = 0.0
        for (eid, four), grp in p.groupby(["entreprise_id", "fournisseur_etranger"]):
            if len(grp) < 5:
                continue
            dates = grp.date.values
            j, best, best_i = 0, 0, 0
            for i in range(len(dates)):
                while dates[i] - dates[j] > np.timedelta64(6, "D"):
                    j += 1
                if i - j + 1 > best:
                    best, best_i = i - j + 1, i
            if best > out.at[eid, "valeur"]:
                out.at[eid, "valeur"] = best
                out.at[eid, "annee"] = int(pd.Timestamp(dates[best_i]).year)
                out.at[eid, "details"] = {"fournisseur": four, "date_fin": fmt.date_fr(pd.Timestamp(dates[best_i]).date())}
        trig = out.valeur >= 5
        out.loc[trig, "declenchee"] = True
        out["annees"] = [[int(y)] if d else [] for d, y in zip(out.declenchee, out.annee)]
        return out

    def phrase(self, r, ctx, eid):
        d = r["details"]
        return (f"{int(r['valeur'])} déclarations en douane de moins de {fmt.dt(self.seuil_dt)} en 7 jours auprès du même "
                f"fournisseur ({d.get('fournisseur')}), jusqu'au {d.get('date_fin')}.")

    def preuves(self, ctx, eid):
        p = self._petites(ctx)
        p = p[p.entreprise_id == eid].sort_values("date", ascending=False)
        return _preuves_df(p, {"numero_declaration": "Déclaration", "date": "Date", "fournisseur_etranger": "Fournisseur",
                               "valeur": "Valeur CIF (DT)"}, "Douane — déclarations de faible valeur")


class C2(Regle):
    def __init__(self):
        super().__init__("C2", "C", "Détournement d'avantage fiscal",
                         "équipements importés en exonération (annexe 2017-419) puis facturés à des tiers sous le même code SH",
                         "au moins une revente constatée")

    def _reventes(self, ctx) -> pd.DataFrame:
        d = ctx.douane
        eq = d[(d.flux == "import") & d.est_equipement.astype(bool) & (d.tva_import == 0)]
        eq = eq.groupby(["entreprise_id", "code_sh"]).agg(valeur_importee=("valeur_cif_dt", "sum")).reset_index()
        f = ctx.factures.dropna(subset=["code_sh_principal"])
        return f.merge(eq, left_on=["emetteur_id", "code_sh_principal"], right_on=["entreprise_id", "code_sh"], how="inner")

    def evaluer(self, ctx):
        r = self._reventes(ctx)
        out = _vide(ctx.ent.index)
        out["seuil"] = 1
        out["valeur"] = 0.0
        for eid, grp in r.groupby("emetteur_id"):
            vendu = float(grp.montant_ht.sum())
            importe = float(grp.drop_duplicates("code_sh").valeur_importee.sum())
            out.at[eid, "declenchee"] = True
            out.at[eid, "valeur"] = len(grp)
            out.at[eid, "montant"] = min(vendu, importe) * ctx.taux_tva
            out.at[eid, "annee"] = int(grp.annee.max())
            out.at[eid, "annees"] = sorted(grp.annee.unique().tolist())
            out.at[eid, "details"] = {"vendu": vendu, "importe": importe}
        return out

    def phrase(self, r, ctx, eid):
        d = r["details"]
        return (f"Machines importées en exonération ({fmt.dt(d.get('importe'))}, codes de l'annexe du décret 2017-419) puis revendues : "
                f"{int(r['valeur'])} facture(s) El Fatoora sur ces mêmes codes pour {fmt.dt(d.get('vendu'))}.")

    def preuves(self, ctx, eid):
        r = self._reventes(ctx)
        r = r[r.emetteur_id == eid].merge(ctx.ent[["raison_sociale"]], left_on="client_id", right_index=True)
        return _preuves_df(r, {"id": "Facture n°", "date": "Date", "raison_sociale": "Acheteur", "code_sh_principal": "Code SH",
                               "montant_ht": "Montant HT (DT)", "valeur_importee": "Valeur importée exonérée (DT)"},
                           "El Fatoora (factures) croisées avec la douane (équipements exonérés)")


class C3(Regle):
    def __init__(self):
        super().__init__("C3", "C", "Crédit de TVA structurel",
                         "mois en crédit de TVA sur l'année, avec demandes de remboursement",
                         "crédit ≥ 10 mois sur 12 avec remboursement, secteur habituellement débiteur")

    def evaluer(self, ctx):
        a = ctx.annuel
        crediteur = a.secteur.map(lambda s: bool(ctx.secteur_info(s).get("habituellement_crediteur", False)))
        exportateur = ctx.ent.statut_export.reindex(a.index.get_level_values(0)).values != "local"
        dec = (a.mois_credit >= 10) & (a.remboursements > 0) & (~crediteur) & (~exportateur)
        return _par_annee(ctx, a.mois_credit, dec, pd.Series(0.0, index=a.index), 10, ["mois_credit", "remboursements", "mois_declares"])

    def phrase(self, r, ctx, eid):
        d = r["details"]
        return (f"Crédit de TVA {int(r['valeur'])} mois sur {int(d.get('mois_declares', 12))} en {r['annee']}, avec "
                f"{fmt.dt(d.get('remboursements'))} de remboursements demandés, alors que son secteur est habituellement débiteur.")

    def preuves(self, ctx, eid):
        m = ctx.mensuel[ctx.mensuel.entreprise_id == eid].copy()
        m["periode"] = [fmt.mois_fr(y, mo) for y, mo in zip(m.annee, m.mois)]
        return _preuves_df(m.sort_values(["annee", "mois"], ascending=False),
                           {"periode": "Mois", "tva_collectee": "TVA collectée (DT)", "tva_deductible_import": "TVA déductible import (DT)",
                            "tva_deductible_local": "TVA déductible locale (DT)", "credit_reporte": "Crédit reporté (DT)",
                            "remboursement_demande": "Remboursement demandé (DT)"}, "Déclarations mensuelles de TVA")


class C4(Regle):
    def __init__(self):
        super().__init__("C4", "C", "Réseau à risque",
                         "gérant, associé ou adresse partagés avec une entreprise radiée, redressée ou défaillante "
                         "(TVA non déposée) ; société récente à gros volumes",
                         "lien détecté, ou création depuis moins de 18 mois avec plus de 500 000 DT de flux")

    def liens(self, ctx) -> pd.DataFrame:
        roles = ctx.tables["roles"]
        ent = ctx.ent
        redressees = set(ctx.tables["controles_historiques"].query("redressement == True").entreprise_id)
        m = ctx.mensuel
        non_dep = m[~m.deposee.astype(bool)].groupby("entreprise_id").size()
        defaillantes = set(non_dep[non_dep >= 3].index)
        risque = set(ent.index[ent.statut == "radiée"]) | redressees | defaillantes
        paires = roles.merge(roles, on="personne_id", suffixes=("", "_lie"))
        paires = paires[paires.entreprise_id != paires.entreprise_id_lie]
        paires = paires[paires.entreprise_id_lie.isin(risque)].assign(type_lien="dirigeant commun")
        adr = ent[["adresse_id"]].reset_index()
        pa = adr.merge(adr, on="adresse_id", suffixes=("", "_lie"))
        pa = pa[(pa.id != pa.id_lie) & pa.id_lie.isin(risque)].rename(columns={"id": "entreprise_id", "id_lie": "entreprise_id_lie"})
        pa = pa.assign(type_lien="adresse commune")
        out = pd.concat([paires[["entreprise_id", "entreprise_id_lie", "type_lien"]], pa[["entreprise_id", "entreprise_id_lie", "type_lien"]]])
        out = out.drop_duplicates(["entreprise_id", "entreprise_id_lie"])
        out["raison_sociale_lie"] = out.entreprise_id_lie.map(ent.raison_sociale)
        out["statut_lie"] = out.entreprise_id_lie.map(ent.statut)
        out["redressee"] = out.entreprise_id_lie.isin(redressees)
        out["defaillante"] = out.entreprise_id_lie.isin(defaillantes)
        out["date_radiation"] = out.entreprise_id_lie.map(ent.date_radiation)
        return out

    def evaluer(self, ctx):
        out = _vide(ctx.ent.index)
        out["seuil"] = 1
        out["valeur"] = 0.0
        liens = self.liens(ctx)
        for eid, grp in liens.groupby("entreprise_id"):
            out.at[eid, "declenchee"] = True
            out.at[eid, "valeur"] = len(grp)
            r = grp.sort_values(["redressee", "statut_lie"], ascending=[False, True]).iloc[0]
            out.at[eid, "details"] = {"lie": r.raison_sociale_lie, "type_lien": r.type_lien, "statut_lie": r.statut_lie,
                                      "redressee": bool(r.redressee), "defaillante": bool(r.defaillante),
                                      "annee_radiation": int(r.date_radiation.year) if pd.notna(r.date_radiation) else None}
        # sociétés récentes à gros volumes
        a = ctx.annuel.xs(ANNEES[-1], level="annee")
        age_mois = (pd.Timestamp(FIN_PERIODE) - ctx.ent.date_creation).dt.days / 30.44
        volume = np.maximum(a.encaissements, a.factures_emises).reindex(ctx.ent.index).fillna(0)
        jeunes = ctx.ent.index[(age_mois < 18) & (volume > 500_000)]
        for eid in jeunes:
            out.at[eid, "declenchee"] = True
            out.at[eid, "valeur"] = out.at[eid, "valeur"] + 1
            det = dict(out.at[eid, "details"])
            det.update({"jeune": True, "age_mois": int(age_mois[eid]), "volume": float(volume[eid])})
            out.at[eid, "details"] = det
        out["annees"] = [[ANNEES[-1]] if d else [] for d in out.declenchee]
        return out

    def phrase(self, r, ctx, eid):
        d = r["details"]
        parts = []
        if d.get("lie"):
            etat = "radiée" if d.get("statut_lie") == "radiée" else "active"
            suite = f"{etat}{' en ' + str(d['annee_radiation']) if d.get('annee_radiation') else ''}"
            if d.get("redressee"):
                suite += " après un redressement" if etat == "radiée" else ", ayant fait l'objet d'un redressement"
            elif d.get("defaillante"):
                suite += ", qui ne dépose plus ses déclarations de TVA"
            lien = "Son dirigeant est aussi lié à" if d.get("type_lien") == "dirigeant commun" else "Elle partage son adresse avec"
            parts.append(f"{lien} {d['lie']}, {suite}.")
        if d.get("jeune"):
            parts.append(f"Société créée il y a {d['age_mois']} mois avec déjà {fmt.dt(d['volume'])} de flux en {ANNEES[-1]}.")
        return " ".join(parts)

    def preuves(self, ctx, eid):
        liens = self.liens(ctx)
        liens = liens[liens.entreprise_id == eid].copy()
        liens["statut_lie"] = liens.statut_lie.str.capitalize()
        liens["redressee"] = liens.redressee.map({True: "oui", False: "non"})
        liens["defaillante"] = liens.defaillante.map({True: "oui", False: "non"})
        return _preuves_df(liens, {"raison_sociale_lie": "Entreprise liée", "type_lien": "Nature du lien", "statut_lie": "Statut",
                                   "redressee": "Redressement antérieur", "defaillante": "TVA non déposée",
                                   "date_radiation": "Date de radiation"},
                           "Registre des entreprises (dirigeants, adresses) et historique des contrôles")


class C5(Regle):
    def __init__(self):
        super().__init__("C5", "C", "Productivité anormale",
                         "CA par employé comparé au 99e centile du secteur ; importations fortes sans personnel",
                         "CA par employé > P99 du secteur, ou plus de 500 000 DT d'importations avec 0 ou 1 employé")

    def evaluer(self, ctx):
        out = _vide(ctx.ent.index)
        a = ctx.annuel.xs(ANNEES[-1], level="annee").reindex(ctx.ent.index)
        eff = ctx.ent.effectif
        cpe = ctx.ca_par_employe.reindex(ctx.ent.index)
        p99 = ctx.ent.secteur_groupe.map(ctx.cpe_p99)
        imp = a.imports_total.fillna(0)
        dec_cpe = cpe > p99
        dec_imp = (imp > 500_000) & (eff <= 1)
        out["valeur"] = cpe
        out["seuil"] = p99
        out["declenchee"] = (dec_cpe | dec_imp).fillna(False)
        out["annees"] = [[ANNEES[-1]] if d else [] for d in out.declenchee]
        out["details"] = [{"effectif": int(eff[i]), "imports": float(imp[i]), "ca_par_employe": float(cpe[i]) if pd.notna(cpe[i]) else None,
                           "p99": float(p99[i]) if pd.notna(p99[i]) else None, "imports_sans_personnel": bool(dec_imp[i])}
                          for i in out.index]
        return out

    def phrase(self, r, ctx, eid):
        d = r["details"]
        if d.get("imports_sans_personnel"):
            return f"{d['effectif']} salarié déclaré pour {fmt.dt(d['imports'])} d'importations en {ANNEES[-1]}."
        return (f"{fmt.dt(d.get('ca_par_employe'))} de chiffre d'affaires par employé en {ANNEES[-1]}, au-delà du 99e centile "
                f"du secteur ({fmt.dt(d.get('p99'))}).")

    def preuves(self, ctx, eid):
        e = ctx.ent.loc[[eid]].reset_index()
        a = ctx.annuel.loc[eid].reset_index()
        a["effectif"] = int(e.effectif.iloc[0])
        return _preuves_df(a, {"annee": "Année", "ca_decl": "CA déclaré (DT)", "imports_total": "Importations (DT)", "effectif": "Effectif"},
                           "Registre des entreprises (effectif) et déclarations")


REGLES: list[Regle] = [A1(), A2(), A3(), A4(), A5(), B1(), B2(), B3(), B4(), C1(), C2(), C3(), C4(), C5()]
REGLES_PAR_CODE = {r.code: r for r in REGLES}
POIDS_FORCE = {"A": 0.40, "B": 0.25, "C": 0.10}


def evaluer_toutes(ctx: Contexte) -> dict[str, pd.DataFrame]:
    return {r.code: r.evaluer(ctx) for r in REGLES}
