"""Générateur de la base fictive RASD 360 (seed fixe 42, montants en DT, 2023-2025, mensuel).

Usage : python -m data_gen.generate   (depuis la racine, PYTHONPATH incluant backend/)

Principe : pour chaque entreprise on simule d'abord l'activité RÉELLE (cohérente
comptablement), puis ce qu'elle DÉCLARE (identique pour les honnêtes, falsifié selon
les schémas de fraude). Les données de tiers (douane, TEJ, El Fatoora, banque) reflètent
la réalité, ce qui crée les contradictions que le moteur de risque doit trouver.
"""
from __future__ import annotations

import calendar
import csv
import json
import logging
import math
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app import config, db  # noqa: E402

from . import demo_companies as demo  # noqa: E402
from . import reference as ref  # noqa: E402
from . import scenarios as sc  # noqa: E402

log = logging.getLogger("rasd.datagen")

YEARS = list(config.YEARS)
T = 12 * len(YEARS)
TVA = ref.TAUX_TVA


def t_index(y: int, m: int) -> int:
    return (y - YEARS[0]) * 12 + (m - 1)


def ym(t: int) -> tuple[int, int]:
    return YEARS[0] + t // 12, t % 12 + 1


def r3(x: float) -> float:
    return float(round(x, 3))


def fin_de_mois(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


@dataclass
class Ent:
    id: int
    raison_sociale: str
    forme: str
    gouvernorat: str
    delegation: str
    secteur: ref.Secteur
    nat_code: str
    date_creation: date
    effectif: int
    capital: float
    categorie: str = "honnete"
    schemas: list[str] = field(default_factory=list)
    piege: str | None = None
    explication: str | None = None
    demo: str | None = None
    statut: str = "active"
    date_radiation: date | None = None
    regime: str = "réel"
    statut_export: str = "local"
    importateur: bool = False
    statut_oea: bool = False
    adresse_id: int = 0
    lag_tva: int = 0
    facteur_banque: float = 1.1
    part_b2b: float = 0.5
    agent_retenue: bool = False
    ticket: float = 80_000
    produits_poids: np.ndarray | None = None
    params: dict = field(default_factory=dict)
    plan: dict = field(default_factory=dict)  # année -> dict des montants annuels
    # séries mensuelles (36 mois)
    actif: np.ndarray | None = None
    ca_local_reel: np.ndarray | None = None
    ca_export_reel: np.ndarray | None = None
    ca_local_decl: np.ndarray | None = None
    ca_export_decl: np.ndarray | None = None
    achats_locaux: np.ndarray | None = None
    charges_taxables: np.ndarray | None = None
    tva_import_payee: np.ndarray | None = None
    exports_douane: np.ndarray | None = None
    factures_recues_fictives: np.ndarray | None = None
    ventes_carrousel: np.ndarray | None = None
    achats_carrousel: np.ndarray | None = None
    mois_non_deposes: set = field(default_factory=set)
    annuelles_absentes: set = field(default_factory=set)
    montant_elude: float = 0.0

    def __post_init__(self):
        z = lambda: np.zeros(T)  # noqa: E731
        self.ca_local_reel, self.ca_export_reel = z(), z()
        self.ca_local_decl, self.ca_export_decl = z(), z()
        self.achats_locaux, self.charges_taxables = z(), z()
        self.tva_import_payee, self.exports_douane = z(), z()
        self.factures_recues_fictives, self.ventes_carrousel, self.achats_carrousel = z(), z(), z()
        self.actif = np.array([self._actif_mois(t) for t in range(T)])

    def _actif_mois(self, t: int) -> bool:
        y, m = ym(t)
        debut = date(y, m, 1)
        if debut < date(self.date_creation.year, self.date_creation.month, 1):
            return False
        if self.date_radiation and debut > self.date_radiation:
            return False
        return True

    def refresh_actif(self) -> None:
        self.actif = np.array([self._actif_mois(t) for t in range(T)])

    def frac_annee(self, y: int) -> float:
        k = t_index(y, 1)
        return float(self.actif[k:k + 12].mean())


class Generateur:
    def __init__(self, n: int = config.N_ENTREPRISES, seed: int = config.SEED):
        self.n = n
        self.rng = np.random.default_rng(seed)
        self.rnd = random.Random(seed)
        self.ents: list[Ent] = []
        self.by_demo: dict[str, Ent] = {}
        self.personnes: list[dict] = []
        self.roles: list[dict] = []
        self.adresses: list[dict] = []
        self.douane: list[dict] = []
        self.tva: list[dict] = []
        self.annuelles: list[dict] = []
        self.tej: list[dict] = []
        self.factures: list[dict] = []
        self.banque: list[dict] = []
        self.controles: list[dict] = []
        self.noms_utilises: set[str] = set()
        self.matricules: set[str] = set()
        self.seq_decl = 0
        self.equip_importes: dict[int, list[tuple[int, str, float]]] = {}  # F7 : (t, code, valeur)
        self.carrousels: list[list[Ent]] = []
        self.ecrans: list[Ent] = []

    # ------------------------------------------------------------------ identité
    def _matricule(self) -> str:
        while True:
            mf = f"{self.rnd.randint(1000000, 1999999)}{self.rnd.choice('ABCDEFGHJKLMNPQRSTVWXYZ')}/" \
                 f"{self.rnd.choice('ABPN')}/{self.rnd.choice('MPCN')}/000"
            if mf not in self.matricules:
                self.matricules.add(mf)
                return mf

    def _nom(self, secteur: str, forme: str) -> str:
        for _ in range(200):
            if forme == "Personne physique":
                nom = f"Ets {self.rnd.choice(ref.PRENOMS)} {self.rnd.choice(ref.NOMS)} — {self.rnd.choice(ref.SUFFIXES_NOMS[secteur])}"
            else:
                nom = f"{self.rnd.choice(ref.PREFIXES_NOMS)} {self.rnd.choice(ref.SUFFIXES_NOMS[secteur])} {forme}"
            if nom not in self.noms_utilises:
                self.noms_utilises.add(nom)
                return nom
        raise RuntimeError("Impossible de générer un nom unique")

    def _adresse(self, gouvernorat: str, delegation: str) -> int:
        aid = len(self.adresses) + 1
        self.adresses.append({"id": aid, "adresse": f"{self.rnd.randint(1, 180)}, {self.rnd.choice(ref.RUES)}, {delegation}",
                              "gouvernorat": gouvernorat})
        return aid

    def _personne(self, prenom: str | None = None, nom: str | None = None) -> int:
        pid = len(self.personnes) + 1
        self.personnes.append({"id": pid, "prenom": prenom or self.rnd.choice(ref.PRENOMS), "nom": nom or self.rnd.choice(ref.NOMS)})
        return pid

    def _gouvernorat(self) -> tuple[str, str]:
        noms = list(ref.GOUVERNORATS)
        poids = np.array([ref.GOUVERNORATS[g][0] for g in noms])
        g = noms[self.rng.choice(len(noms), p=poids / poids.sum())]
        return g, self.rnd.choice(ref.GOUVERNORATS[g][1])

    def _nouvelle_ent(self, secteur_cle: str, **kw) -> Ent:
        s = ref.SECTEURS[secteur_cle]
        forme = kw.pop("forme", None) or self._choix_forme()
        gouv, deleg = kw.pop("gouvernorat", None), kw.pop("delegation", None)
        if not gouv:
            gouv, deleg = self._gouvernorat()
        e = Ent(
            id=len(self.ents) + 1,
            raison_sociale=kw.pop("raison_sociale", None) or self._nom(secteur_cle, forme),
            forme=forme, gouvernorat=gouv, delegation=deleg, secteur=s,
            nat_code=kw.pop("nat_code", None) or self.rnd.choice(s.nat_codes),
            date_creation=kw.pop("date_creation", None) or self._date_creation(),
            effectif=kw.pop("effectif", 0), capital=kw.pop("capital", 0.0), **kw,
        )
        self.noms_utilises.add(e.raison_sociale)
        if s.statut_export != "local":
            e.statut_export = s.statut_export
        e.adresse_id = self._adresse(gouv, deleg)
        e.lag_tva = int(self.rng.random() < 0.4)
        e.facteur_banque = float(self.rng.uniform(1.02, 1.18))
        lo, hi = s.part_b2b
        e.part_b2b = float(self.rng.uniform(lo, hi))
        e.agent_retenue = forme in ("SA", "SARL") and self.rng.random() < 0.75
        e.ticket = float(self.rng.uniform(90_000, 260_000))
        if s.produits:
            e.produits_poids = self.rng.dirichlet(np.ones(len(s.produits)) * 2)
        self.ents.append(e)
        return e

    def _choix_forme(self) -> str:
        formes, poids = zip(*ref.FORMES)
        return self.rnd.choices(formes, weights=poids)[0]

    def _date_creation(self) -> date:
        u = self.rng.random()
        if u < 0.06:  # jeunes sociétés créées pendant la période
            return date(2023, 1, 1) + timedelta(days=int(self.rng.integers(0, 900)))
        return date(1995, 1, 1) + timedelta(days=int(self.rng.integers(0, 10200)))

    # ------------------------------------------------------------------ profils cachés
    def _tirer_profils(self) -> list[tuple[str, str, str | None]]:
        """Liste (categorie, secteur, piege_ou_schema) pour les entreprises aléatoires."""
        n_demo = len(demo.DEMO_SIMPLES) + len(demo.CARROUSEL["membres"])
        n = self.n - n_demo
        n_fraude = round(self.n * sc.PART_FRAUDEUR) - 5  # 5 fraudeurs vitrines (Sahel, Médina, carrousel)
        n_piege = round(self.n * sc.PART_PIEGE) - 2       # 2 pièges vitrines (Cap Bon, Djerba)
        n_honnete = n - n_fraude - n_piege
        profils: list[tuple[str, str, str | None]] = []

        secteurs = list(ref.SECTEURS)
        poids = np.array([ref.SECTEURS[s].poids for s in secteurs])
        for _ in range(n_honnete):
            profils.append(("honnete", secteurs[self.rng.choice(len(secteurs), p=poids / poids.sum())], None))

        pieges = list(sc.PIEGES)
        pp = np.array([sc.PIEGES[p]["poids"] for p in pieges])
        for _ in range(n_piege):
            p = pieges[self.rng.choice(len(pieges), p=pp / pp.sum())]
            cand = sc.PIEGES[p]["secteurs"] or secteurs
            profils.append(("honnete_ecart_explique", self.rnd.choice(cand), p))

        # carrousels aléatoires : 4 anneaux de 3 ou 4 membres
        tailles = [3, 4, 3, 4]
        n_f5 = sum(tailles)
        fr = [f for f in sc.FRAUDES if f != "F5"]
        fp = np.array([sc.FRAUDES[f]["poids"] for f in fr])
        for _ in range(n_fraude - n_f5):
            f = fr[self.rng.choice(len(fr), p=fp / fp.sum())]
            profils.append(("fraudeur", self.rnd.choice(sc.FRAUDES[f]["secteurs"]), f))
        for taille in tailles:
            for _ in range(taille):
                profils.append(("fraudeur", self.rnd.choice(sc.FRAUDES["F5"]["secteurs"]), "F5"))
        self._tailles_anneaux = tailles
        self.rnd.shuffle(profils)
        return profils

    # ------------------------------------------------------------------ construction
    def _caracteriser(self, e: Ent) -> None:
        s = e.secteur
        # taille (CA réel annuel de base) : PME ; les grandes entreprises relèvent de la DGE
        mediane = {"negoce": 1_300_000, "industrie": 2_300_000, "services": 650_000}[s.type]
        ca0 = float(np.clip(self.rng.lognormal(math.log(mediane), 0.85), 60_000, 25_000_000))
        if e.categorie == "fraudeur":
            ca0 = float(np.clip(ca0, 250_000, 1_500_000))
        e.params["ca0"] = ca0
        e.params["croissance"] = float(self.rng.normal(0.05, 0.07))
        # statut export
        if s.statut_export == "totalement exportatrice":
            e.statut_export = "totalement exportatrice"
        elif e.piege == "export" or "F8" in e.schemas:
            e.statut_export = "partiellement exportatrice"
        elif s.cle in ("agroalimentaire", "plasturgie", "mecanique", "services_informatiques") and self.rng.random() < 0.28:
            e.statut_export = "partiellement exportatrice"
        elif s.cle == "textile_negoce" and self.rng.random() < 0.10:
            e.statut_export = "partiellement exportatrice"
        # importateur
        force_import = e.piege in ("stock", "periode", "faible_marge", "export", "admission_temporaire") or any(
            f in e.schemas for f in ("F1", "F2", "F3", "F6"))
        e.importateur = force_import or e.statut_export == "totalement exportatrice" or self.rng.random() < s.p_importateur * 0.8
        if s.type == "services" and not force_import:
            e.importateur = self.rng.random() < s.p_importateur
        # régime fiscal
        if e.forme == "Personne physique" and not e.importateur and ca0 < 250_000 and e.categorie == "honnete" and self.rng.random() < 0.5:
            e.regime = "forfaitaire"
        # effectif
        e.effectif = int(max(1, round(ca0 / s.ca_par_employe * self.rng.lognormal(0, 0.35))))
        if e.forme == "Personne physique":
            e.effectif = min(e.effectif, 12)
        e.capital = float(round({"SA": max(100_000, ca0 * 0.15), "SARL": max(10_000, ca0 * 0.05),
                                 "SUARL": max(5_000, ca0 * 0.03), "Personne physique": 0}[e.forme], -3))
        e.statut_oea = bool(e.categorie == "honnete" and ca0 > 6_000_000 and self.rng.random() < 0.25)

    # ------------------------------------------------------------------ plans annuels
    def _plan_aleatoire(self, e: Ent) -> None:
        s, rng = e.secteur, self.rng
        ca0, g = e.params["ca0"], e.params["croissance"]
        med, sd = s.marge_mediane, s.marge_sd
        m_c = float(np.clip(rng.normal(med, sd), max(0.01, med - 2.2 * sd), med + 2.5 * sd))
        if e.piege == "faible_marge":
            m_c = float(np.clip(rng.normal(med, sd * 0.7), max(0.01, med - 1.2 * sd), med + 1.5 * sd))
        part_export = {"local": 0.0, "totalement exportatrice": float(rng.uniform(0.96, 1.0)),
                       "partiellement exportatrice": float(rng.uniform(0.2, 0.55))}[e.statut_export]
        if e.piege == "export":
            part_export = float(rng.uniform(0.70, 0.90))
        part_import = 0.0
        if e.importateur:
            part_import = min(0.97, s.part_import * float(rng.uniform(0.8, 1.08)))
            if e.piege in ("faible_marge", "admission_temporaire"):
                part_import = float(rng.uniform(0.88, 0.97))
            if s.type == "services":
                part_import = float(rng.uniform(0.05, 0.25))
        stock = 0.0
        annee_piege = int(rng.choice([2024, 2025])) if e.piege in ("stock", "equipement") else int(rng.choice([2023, 2024]))
        e.params["annee_piege"] = annee_piege
        report_periode = 0.0
        for k, y in enumerate(YEARS):
            f = e.frac_annee(y)
            ca = ca0 * (1 + g) ** k * float(rng.lognormal(0, 0.05)) * f
            if report_periode:  # piège période : ventes de l'année suivante
                ca += report_periode * (1 + m_c)
            m_y = m_c + float(rng.normal(0, sd * 0.2)) if s.type != "services" else m_c
            if s.type == "services":
                achats = ca * s.ratio_achats_services * float(rng.uniform(0.7, 1.3))
                s_debut = s_fin = 0.0
                cout = achats
            else:
                cout = ca / (1 + m_y)
                s_debut = stock if k else cout * s.mois_stock / 12 * float(rng.uniform(0.8, 1.2))
                s_fin = cout * s.mois_stock / 12 * float(rng.uniform(0.85, 1.15)) if f > 0 else s_debut
                if report_periode:
                    report_periode = 0.0
                achats = cout + s_fin - s_debut
            extra = 0.0
            if e.piege == "stock" and y == annee_piege:
                extra = ca * float(rng.uniform(1.5, 3.0))
            if e.piege == "periode" and y == annee_piege:
                extra = ca * float(rng.uniform(0.6, 1.2))
                report_periode = extra
            s_fin += extra
            achats += extra
            stock = s_fin
            imports = achats * part_import if e.importateur else 0.0
            if extra and e.importateur:
                imports = (achats - extra) * part_import + extra
            locaux = max(0.0, achats - imports)
            if achats < 0:  # déstockage marqué : pas d'achats, le stock absorbe
                imports, locaux = 0.0, 0.0
                stock = s_fin = s_debut - cout
            equip = 0.0
            if s.prefixes_equipement and s.type != "services":
                if e.piege == "equipement" and y == annee_piege:
                    equip = ca * float(rng.uniform(2.0, 4.0))
                elif rng.random() < 0.22:
                    equip = ca * float(rng.uniform(0.03, 0.15))
            at = e.statut_export == "totalement exportatrice"
            e.plan[y] = {
                "ca_reel": ca, "part_export": part_export, "marge": m_y,
                "imports": 0.0 if at else imports, "imports_at": imports if at else 0.0,
                "achats_locaux": locaux, "stock_debut": s_debut, "stock_fin": s_fin, "equipements": equip,
                "extra_fin_annee": extra, "charges_taxables": ca * s.ratio_autres_charges * 0.6,
            }
        if e.piege == "donnees_manquantes":
            k = int(rng.integers(1, 3))
            e.annuelles_absentes = set(self.rnd.sample(YEARS[1:], k)) | ({2025} if k == 1 and rng.random() < 0.5 else set())

    def _plan_demo(self, spec: dict, e: Ent) -> None:
        stock = float(spec["stock_initial"])
        for y, a in spec["annees"].items():
            s_debut, s_fin = stock, stock + a.get("delta_stock", 0)
            stock = s_fin
            ca_reel = a["ca_reel"]
            ca_export = a.get("ca_export", 0.0)
            e.plan[y] = {
                "ca_reel": ca_reel, "part_export": (ca_export / ca_reel) if ca_reel else 0.0,
                "marge": e.secteur.marge_mediane, "imports": float(a.get("imports", 0)),
                "imports_at": float(a.get("imports_at", 0)), "achats_locaux": float(a.get("achats_locaux", 0)),
                "stock_debut": s_debut, "stock_fin": s_fin, "equipements": float(a.get("equipements", 0)),
                "extra_fin_annee": 0.0, "charges_taxables": ca_reel * e.secteur.ratio_autres_charges * 0.6,
                "ca_decl": float(a["ca_decl"]), "ca_export_decl": float(ca_export),
                "tva_deduite_import": a.get("tva_deduite_import"), "tej": a.get("tej"), "fatoora": a.get("fatoora"),
                "exact": True,
            }

    def _construire_demos(self) -> None:
        for spec in demo.DEMO_SIMPLES:
            kw = {k: spec[k] for k in ("raison_sociale", "forme", "gouvernorat", "delegation", "nat_code",
                                       "date_creation", "effectif", "capital")}
            e = self._nouvelle_ent(spec["secteur"], categorie=spec["categorie"], **kw)
            e.demo = spec["cle"]
            e.schemas = list(spec.get("schemas", []))
            e.piege = spec.get("piege")
            e.explication = spec.get("explication")
            e.importateur = any(a.get("imports") or a.get("imports_at") for a in spec["annees"].values())
            e.statut_export = spec.get("statut_export", "local")
            e.lag_tva = 0
            e.params["produit_principal"] = spec.get("produit_principal")
            e.params["remboursements"] = spec.get("remboursements", False)
            if spec["cle"] == "sahel":
                e.facteur_banque = 1.08
            self._plan_demo(spec, e)
            self.by_demo[spec["cle"]] = e
        # membres du carrousel vitrine
        car = demo.CARROUSEL
        anneau = []
        for mbr in car["membres"]:
            kw = {k: mbr[k] for k in ("raison_sociale", "forme", "gouvernorat", "delegation", "nat_code",
                                      "date_creation", "effectif", "capital")}
            e = self._nouvelle_ent(mbr["secteur"], categorie="fraudeur", **kw)
            e.demo = mbr["cle"]
            e.schemas = ["F5"]
            e.importateur = not mbr.get("maillon_manquant")
            e.params["ca0"] = mbr["ca_annuel"]
            e.params["croissance"] = 0.04
            e.params["maillon_manquant"] = bool(mbr.get("maillon_manquant"))
            self._plan_aleatoire(e)
            self.by_demo[mbr["cle"]] = e
            anneau.append(e)
        self.carrousels.append(anneau)
        self._anneau_demo = anneau

    # ------------------------------------------------------------------ fraudes (structure)
    def _appliquer_structure_fraudes(self) -> None:
        rng = self.rng
        # anneaux aléatoires de carrousel
        f5 = [e for e in self.ents if "F5" in e.schemas and e.demo is None]
        i = 0
        for taille in self._tailles_anneaux:
            anneau = f5[i:i + taille]
            i += taille
            if len(anneau) < 3:
                continue
            maillon = anneau[1]
            maillon.params["maillon_manquant"] = True
            maillon.date_creation = date(2024, int(rng.integers(1, 10)), int(rng.integers(1, 28)))
            maillon.effectif = int(rng.integers(0, 2))
            maillon.importateur = False
            maillon.refresh_actif()
            self._plan_aleatoire(maillon)
            self.carrousels.append(anneau)
        # sociétés écran (F4) : jeunes, sans effectif
        for e in self.ents:
            if "F4" in e.schemas:
                e.date_creation = date(2024, 1, 1) + timedelta(days=int(rng.integers(0, 400)))
                e.effectif = int(rng.integers(0, 2))
                e.importateur = False
                e.refresh_actif()
                e.params["ca0"] = float(rng.uniform(80_000, 300_000))
                self._plan_aleatoire(e)
                e.params["mode_ecran"] = "non_depose" if rng.random() < 0.5 else "sous_declare"
                self.ecrans.append(e)
        for e in self.ents:
            if e.categorie != "fraudeur" or e.demo:
                continue
            if "F1" in e.schemas:
                debut = int(rng.choice([2023, 2023, 2024]))
                e.params["f1_ratio"] = {y: float(rng.uniform(0.2, 0.6)) for y in YEARS if y >= debut}
                e.params["f1_variante"] = "tej" if rng.random() < 0.6 else "fatoora"
                if e.params["f1_variante"] == "tej":
                    e.part_b2b = float(rng.uniform(0.55, 0.85))
            if "F2" in e.schemas and e.secteur.produits:
                debut = int(rng.choice([2023, 2024]))
                e.params["f2"] = {"ratio": float(rng.uniform(0.30, 0.65)), "annees": [y for y in YEARS if y >= debut],
                                  "produit": int(rng.integers(0, len(e.secteur.produits)))}
            if "F3" in e.schemas:
                debut = int(rng.choice([2023, 2024]))
                e.params["f3"] = {"variante": "import" if (e.importateur and rng.random() < 0.65) else "locale",
                                  "facteur": {y: float(rng.uniform(1.08, 1.35)) for y in YEARS if y >= debut}}
                e.params["remboursements"] = True
            if "F6" in e.schemas:
                e.params["f6"] = {y: int(rng.integers(3, 7)) for y in YEARS}
            if "F7" in e.schemas and e.secteur.prefixes_equipement:
                e.params["f7"] = True
                for y in self.rnd.sample(YEARS, 2):
                    e.plan[y]["equipements"] = e.plan[y]["ca_reel"] * float(rng.uniform(0.15, 0.4))
            if "F8" in e.schemas:
                debut = int(rng.choice([2023, 2024]))
                e.params["f8"] = {y: float(rng.uniform(1.4, 2.4)) for y in YEARS if y >= debut}
                e.params["remboursements"] = True
        # F3 variante locale : factures d'une société écran
        locaux = [e for e in self.ents if e.params.get("f3", {}).get("variante") == "locale"]
        for k, e in enumerate(locaux):
            if self.ecrans:
                e.params["ecran"] = self.ecrans[k % len(self.ecrans)].id

    # ------------------------------------------------------------------ séries mensuelles
    def _poids_mensuels(self, e: Ent) -> np.ndarray:
        pic = {"electromenager": 7, "telephonie": 12, "hotellerie": 8, "textile_export": 4, "agroalimentaire": 3}.get(
            e.secteur.cle, int(self.rng.integers(1, 13)))
        a = float(self.rng.uniform(0.05, 0.22))
        m = np.arange(1, 13)
        w = 1 + a * np.cos(2 * np.pi * (m - pic) / 12) + self.rng.normal(0, 0.05, 12)
        return np.clip(w, 0.3, None)

    def _repartir(self, total: float, w: np.ndarray, actif: np.ndarray) -> np.ndarray:
        ww = w * actif
        if total <= 0 or ww.sum() <= 0:
            return np.zeros(12)
        v = np.round(total * ww / ww.sum(), 3)
        v[np.nonzero(ww)[0][-1]] += r3(total - v.sum())
        return v

    def _series_mensuelles(self, e: Ent) -> None:
        w = self._poids_mensuels(e)
        for y in YEARS:
            p = e.plan[y]
            k = t_index(y, 1)
            act = e.actif[k:k + 12].astype(float)
            if "ca_decl" in p:  # vitrine : chiffres exacts
                local_reel = p["ca_reel"] - p.get("ca_export_decl", 0.0)
                e.ca_local_reel[k:k + 12] = self._repartir(local_reel, w, act)
                e.ca_export_reel[k:k + 12] = self._repartir(p.get("ca_export_decl", 0.0), w, act)
                e.ca_local_decl[k:k + 12] = self._repartir(p["ca_decl"], w, act)
            else:
                ca_export = p["ca_reel"] * p["part_export"]
                e.ca_local_reel[k:k + 12] = self._repartir(p["ca_reel"] - ca_export, w, act)
                e.ca_export_reel[k:k + 12] = self._repartir(ca_export, w, act)
                ratio = e.params.get("f1_ratio", {}).get(y)
                e.ca_local_decl[k:k + 12] = np.round(e.ca_local_reel[k:k + 12] * ratio, 3) if ratio else e.ca_local_reel[k:k + 12]
            e.achats_locaux[k:k + 12] = self._repartir(p["achats_locaux"], w, act)
            e.charges_taxables[k:k + 12] = self._repartir(p["charges_taxables"], np.ones(12), act)
        e.params["poids"] = w

    # ------------------------------------------------------------------ douane
    def _code_bureau(self, e: Ent) -> tuple[str, str]:
        b = ref.BUREAUX_DOUANE.get(e.gouvernorat, ref.BUREAU_DOUANE_DEFAUT)
        code = {"Bureau de Radès Port": "RDS", "Bureau de Tunis-Carthage Aéroport": "TCA", "Bureau de Bizerte Port": "BIZ",
                "Bureau de Sousse Port": "SOU", "Bureau de Sfax Port": "SFX", "Bureau de Gabès Port": "GAB",
                "Bureau de Zarzis Port": "ZRZ"}[b]
        return b, code

    def _num_decl(self, y: int, code: str) -> str:
        self.seq_decl += 1
        return f"{y}{code}{self.seq_decl:07d}"

    def _fournisseur(self, e: Ent, pays: str) -> str:
        key = f"four_{pays}"
        if key not in e.params:
            iso = {"Chine": "CN", "Turquie": "TR", "Italie": "IT", "France": "FR", "Allemagne": "DE", "Espagne": "ES",
                   "Viet Nam": "VN", "Corée du Sud": "KR", "Inde": "IN", "Arabie saoudite": "SA", "Pays-Bas": "NL",
                   "Portugal": "PT", "Côte d'Ivoire": "CI", "Ghana": "GH", "Brésil": "BR", "Ukraine": "UA",
                   "Algérie": "DZ", "Égypte": "EG", "Malaisie": "MY"}.get(pays, "XX")
            e.params[key] = [f"Exportateur {iso}-{self.rng.integers(100, 9999):04d} (fictif)" for _ in range(int(self.rng.integers(1, 4)))]
        return self.rnd.choice(e.params[key])

    def _circuit(self, suspect: bool = False) -> tuple[str, str | None]:
        u = self.rng.random()
        if suspect:
            circuit = "rouge" if u < 0.25 else ("orange" if u < 0.45 else "vert")
        else:
            circuit = "rouge" if u < 0.08 else ("orange" if u < 0.25 else "vert")
        if circuit == "vert":
            return circuit, None
        if suspect and circuit == "rouge" and self.rng.random() < 0.4:
            return circuit, "infraction"
        return circuit, "conforme"

    def _ligne(self, e: Ent, t: int, jour: int, numero: str, bureau: str, flux: str, regime: str, code_sh: str,
               designation: str, pays: str, fournisseur: str, unite: str, kg_u: float, base: float, prix_u: float,
               taux_droits: float, equip: bool = False, suspect: bool = False) -> dict:
        y, m = ym(t)
        suspensif = regime in ("admission temporaire", "réexportation", "export définitif", "entrepôt") or equip
        if flux == "export":
            cif, droits, base_tva, tva, avance = base, 0.0, 0.0, 0.0, 0.0
        else:
            t_eff = 0.0 if suspensif else taux_droits
            cif = r3(base / (1 + t_eff))
            droits = r3(base - cif) if t_eff else 0.0
            base_tva = r3(cif + droits) if not suspensif else 0.0
            tva = r3(base_tva * TVA) if not suspensif else 0.0
            avance = r3(base_tva * ref.TAUX_AVANCE_IMPORT) if (not suspensif and e.secteur.type == "negoce") else 0.0
        qte = cif / max(prix_u, 1e-6)
        qte = float(max(1, round(qte))) if unite == "u" else float(max(0.1, round(qte, 1)))
        fret_rate, ass_rate = 0.05, 0.005
        fob = r3(cif / (1 + fret_rate + ass_rate)) if flux == "import" else cif
        fret = r3(fob * fret_rate) if flux == "import" else 0.0
        assurance = r3(cif - fob - fret) if flux == "import" else 0.0
        circuit, resultat = self._circuit(suspect)
        return {
            "entreprise_id": e.id, "numero_declaration": numero, "date": date(y, m, jour), "bureau": bureau, "flux": flux,
            "regime": regime, "code_sh": code_sh, "designation": designation, "pays_origine": pays,
            "fournisseur_etranger": fournisseur, "quantite": qte, "unite": unite, "poids_kg": round(qte * kg_u, 1),
            "valeur_fob": fob, "fret": fret, "assurance": assurance, "valeur_cif_dt": cif, "taux_droits": 0.0 if suspensif else taux_droits,
            "droits_douane": droits, "base_tva": base_tva, "tva_import": tva, "avance_impot_import": avance,
            "est_equipement": equip, "circuit": circuit, "resultat_controle": resultat,
        }

    def _decouper(self, total: float, n: int, exact: bool) -> list[float]:
        if n <= 1:
            return [total]
        if exact:  # multiples de 100 DT : TVA à 19 % exacte au millime
            unites = int(round(total / 100))
            parts = self.rng.dirichlet(np.ones(n) * 3) * unites
            ent = [int(p) for p in parts]
            ent[-1] += unites - sum(ent)
            return [float(x * 100) for x in ent if x > 0]
        parts = np.round(self.rng.dirichlet(np.ones(n) * 2) * total, 3)
        parts[-1] = r3(total - parts[:-1].sum())
        return [float(p) for p in parts if p > 0]

    def _produit(self, e: Ent, force: str | None = None) -> ref.Produit:
        prods = e.secteur.produits
        if force:
            for p in prods:
                if p.code_sh == force:
                    return p
        return prods[self.rng.choice(len(prods), p=e.produits_poids)]

    def _origine(self, p: ref.Produit, force: str | None = None) -> tuple[str, float]:
        if force:
            for pays, _, mult in p.origines:
                if pays == force:
                    return pays, mult
        pays, poids, mults = zip(*p.origines)
        i = self.rng.choice(len(pays), p=np.array(poids) / sum(poids))
        return pays[i], mults[i]

    def _douane(self, e: Ent) -> None:
        bureau, code = self._code_bureau(e)
        w = e.params["poids"]
        f2 = e.params.get("f2")
        f6 = e.params.get("f6")
        exact = any(p.get("exact") for p in e.plan.values())
        medina = e.demo == "medina"
        for y in YEARS:
            p = e.plan[y]
            k = t_index(y, 1)
            act = e.actif[k:k + 12].astype(float)
            # --- importations mise à la consommation (et admission temporaire)
            for regime, total in (("mise à la consommation", p["imports"]), ("admission temporaire", p["imports_at"])):
                if total <= 0 or not e.secteur.produits:
                    continue
                if exact:
                    mensuel = self._repartir_exact(total, act)
                else:
                    ww = w.copy()
                    extra = p.get("extra_fin_annee", 0.0)
                    base_part = total - extra if regime == "mise à la consommation" else total
                    n_exp = int(np.clip(round(base_part / e.ticket), 2, 12))
                    if n_exp < 12 and act.sum() > n_exp:
                        garde = np.zeros(12)
                        garde[self.rng.choice(np.nonzero(act)[0], size=n_exp, replace=False)] = 1.0
                        ww = ww * garde
                    mensuel = self._repartir(base_part, ww, act)
                    if extra and regime == "mise à la consommation":
                        mois_extra = [10, 11] if e.piege == "periode" else [9, 10, 11]
                        mensuel[mois_extra] += np.round(extra / len(mois_extra), 3)
                        mensuel[mois_extra[-1]] += r3(extra - round(extra / len(mois_extra), 3) * len(mois_extra))
                for mi in range(12):
                    montant = float(mensuel[mi])
                    if montant <= 0:
                        continue
                    t = k + mi
                    if medina and regime == "mise à la consommation":
                        self._douane_medina(e, t, montant, bureau, code)
                        continue
                    n_decl = int(np.clip(round(montant / e.ticket), 1, 8))
                    for part in self._decouper(montant, n_decl, exact):
                        numero = self._num_decl(y, code)
                        jour = int(self.rng.integers(1, 29))
                        n_lignes = 1 if exact else int(self.rng.choice([1, 2, 3], p=[0.55, 0.3, 0.15]))
                        for base in self._decouper(part, n_lignes, exact):
                            prod = self._produit(e, e.params.get("produit_principal") if exact else None)
                            pays, mult = self._origine(prod)
                            prix = prod.prix * mult * float(self.rng.lognormal(0, 0.10))
                            suspect = False
                            if f2 and y in f2["annees"] and prod.code_sh == e.secteur.produits[f2["produit"]].code_sh \
                                    and regime == "mise à la consommation":
                                prix *= f2["ratio"]
                                e.montant_elude += (base / f2["ratio"] - base) * (1 + TVA) + (base / f2["ratio"] - base) * prod.taux_droits
                                suspect = True
                            self.douane.append(self._ligne(e, t, jour, numero, bureau, "import", regime, prod.code_sh,
                                                           prod.designation, pays, self._fournisseur(e, pays), prod.unite,
                                                           prod.kg_par_unite, base, prix, prod.taux_droits, suspect=suspect))
                # F6 : fractionnement (en plus des déclarations normales)
                if f6 and regime == "mise à la consommation" and y in f6:
                    for _ in range(f6[y]):
                        mi = int(self.rng.integers(0, 12))
                        if not act[mi]:
                            continue
                        t = k + mi
                        prod = self._produit(e)
                        pays, mult = self._origine(prod)
                        four = self._fournisseur(e, pays)
                        j0 = int(self.rng.integers(1, 21))
                        for _ in range(int(self.rng.integers(5, 9))):
                            base = float(self.rng.uniform(1_500, ref.SEUIL_FRACTIONNEMENT * 0.97))
                            prix = prod.prix * mult * 0.6
                            e.montant_elude += base / 0.6 * 0.4 * (TVA + prod.taux_droits)
                            self.douane.append(self._ligne(e, t, min(28, j0 + int(self.rng.integers(0, 7))), self._num_decl(y, code),
                                                           bureau, "import", "mise à la consommation", prod.code_sh,
                                                           prod.designation, pays, four, prod.unite, prod.kg_par_unite,
                                                           r3(base * (1 + prod.taux_droits)), prix, prod.taux_droits, suspect=True))
            # --- équipements (codes de l'annexe 2017-419) : droits et TVA suspendus
            if p["equipements"] > 0:
                machines = ref.machines_pour(e.secteur.prefixes_equipement)
                n = 3 if exact else int(self.rng.integers(1, 4))
                mois = sorted(self.rng.choice(np.nonzero(act)[0], size=min(n, int(act.sum())), replace=False)) if act.sum() else []
                for mi, base in zip(mois, self._decouper(p["equipements"], len(mois), exact)):
                    code_sh, des = machines[int(self.rng.integers(0, len(machines)))]
                    qte_cible = int(self.rng.integers(1, 5))
                    ligne = self._ligne(e, k + int(mi), int(self.rng.integers(1, 29)), self._num_decl(y, code), bureau, "import",
                                        "mise à la consommation", code_sh, des, "Allemagne" if self.rng.random() < 0.5 else "Italie",
                                        self._fournisseur(e, "Allemagne"), "u", 800, base, base / qte_cible, 0.0, equip=True)
                    self.douane.append(ligne)
                    if e.params.get("f7"):
                        self.equip_importes.setdefault(e.id, []).append((k + int(mi), code_sh, base))
            # --- exportations
            for mi in range(12):
                t = k + mi
                v = float(e.ca_export_reel[t])
                if v <= 0 or e.secteur.type == "services":
                    continue
                e.exports_douane[t] = v
                prods = e.secteur.produits_export or e.secteur.produits
                regime = "réexportation" if e.statut_export == "totalement exportatrice" else "export définitif"
                n = int(np.clip(round(v / 400_000), 1, 4))
                for part in self._decouper(v, n, False):
                    prod = prods[int(self.rng.integers(0, len(prods)))]
                    dest = self.rnd.choice(["France", "Italie", "Allemagne", "Espagne", "Libye", "Algérie"])
                    client = f"Client {dest[:2].upper()}-{self.rng.integers(100, 9999):04d} (fictif)"
                    self.douane.append(self._ligne(e, t, int(self.rng.integers(1, 29)), self._num_decl(y, code), bureau, "export",
                                                   regime, prod.code_sh, prod.designation, "Tunisie", client, prod.unite,
                                                   prod.kg_par_unite, r3(part), prod.prix * float(self.rng.lognormal(0, 0.08)), 0.0))

    def _repartir_exact(self, total: float, act: np.ndarray) -> np.ndarray:
        """Répartition en multiples de 100 DT, montants mensuels quasi égaux (vitrines)."""
        idx = np.nonzero(act)[0]
        unites = int(round(total / 100))
        base = unites // len(idx)
        v = np.zeros(12)
        v[idx] = base * 100
        v[idx[-1]] += (unites - base * len(idx)) * 100
        return v

    def _douane_medina(self, e: Ent, t: int, montant: float, bureau: str, code: str) -> None:
        """Médina Trade : téléviseurs déclarés à ~45 % du prix de référence (F2), le reste normal."""
        spec = demo.MEDINA["sous_evaluation"]
        y, m = ym(t)
        n_tv = spec["nb_declarations"].get(y, 0)
        if f"mois_tv_{y}" not in e.params:
            e.params[f"mois_tv_{y}"] = self._mois_tv(n_tv)
        mois_tv = e.params[f"mois_tv_{y}"]
        tv = self._produit(e, spec["code_sh"])
        nb_ce_mois = mois_tv.count(m)
        reste = montant
        for _ in range(nb_ce_mois):
            base_tv = float(round(montant * 0.45 / max(1, nb_ce_mois), -2))
            base_tv = min(base_tv, reste - 100)
            prix = tv.prix * 0.9 * spec["ratio"] * float(self.rng.lognormal(0, 0.03))
            e.montant_elude += (base_tv / spec["ratio"] - base_tv) * (1 + TVA) + (base_tv / spec["ratio"] - base_tv) * tv.taux_droits
            self.douane.append(self._ligne(e, t, int(self.rng.integers(1, 29)), self._num_decl(y, code), bureau, "import",
                                           "mise à la consommation", tv.code_sh, tv.designation, spec["pays"],
                                           self._fournisseur(e, spec["pays"]), tv.unite, tv.kg_par_unite, base_tv, prix,
                                           tv.taux_droits, suspect=True))
            reste -= base_tv
        if reste > 0:
            autres = [p for p in e.secteur.produits if p.code_sh != spec["code_sh"]]
            prod = autres[int(self.rng.integers(0, len(autres)))]
            pays, mult = self._origine(prod)
            self.douane.append(self._ligne(e, t, int(self.rng.integers(1, 29)), self._num_decl(y, code), bureau, "import",
                                           "mise à la consommation", prod.code_sh, prod.designation, pays,
                                           self._fournisseur(e, pays), prod.unite, prod.kg_par_unite, r3(reste),
                                           prod.prix * mult * float(self.rng.lognormal(0, 0.08)), prod.taux_droits))

    def _mois_tv(self, n: int) -> list[int]:
        if n <= 0:
            return []
        mois = list(range(1, 13))
        out = sorted(self.rnd.sample(mois, min(n, 12)))
        while len(out) < n:
            out.append(self.rnd.choice(mois))
        return sorted(out)

    # ------------------------------------------------------------------ factures et TEJ
    def _factures_et_tej(self) -> None:
        rng = self.rng
        actives = [e for e in self.ents if e.statut == "active" or e.date_radiation]
        budgets = np.array([[max(0.0, e.plan[y]["achats_locaux"] + e.plan[y]["charges_taxables"]) for y in YEARS] for e in actives])
        cap_poids = budgets.sum(axis=1)
        cap_poids = cap_poids / cap_poids.sum()
        idx_of = {e.id: i for i, e in enumerate(actives)}
        paires: list[dict] = []
        recu = np.zeros_like(budgets)
        for e in actives:
            if e.regime == "forfaitaire" or "F4" in e.schemas or e.params.get("maillon_manquant"):
                continue
            ventes_b2b = np.array([e.ca_local_reel[t_index(y, 1):t_index(y, 1) + 12].sum() * e.part_b2b for y in YEARS])
            if ventes_b2b.sum() <= 0:
                continue
            k = int(rng.integers(2, 8))
            if e.demo in ("sahel", "cap_bon"):
                k = 8
            clients = set()
            while len(clients) < k:
                j = int(rng.choice(len(actives), p=cap_poids))
                if actives[j].id != e.id and actives[j].regime != "forfaitaire":
                    clients.add(j)
            parts = rng.dirichlet(np.ones(k) * 1.5)
            freq = int(rng.choice([1, 2, 3], p=[0.2, 0.3, 0.5]))
            for j, part in zip(sorted(clients), parts):
                c = actives[j]
                agent = c.agent_retenue or (e.params.get("f1_variante") == "tej") or e.demo in ("sahel", "cap_bon")
                paires.append({"f": e, "c": c, "montants": ventes_b2b * part, "freq": freq,
                               "offset": int(rng.integers(0, freq)), "agent": agent})
                recu[j] += ventes_b2b * part
        # plafonnement : les factures reçues restent inférieures aux achats locaux du client
        facteur = np.where(recu > 0.85 * budgets, 0.85 * budgets / np.maximum(recu, 1e-9), 1.0)
        for pr in paires:
            if pr["f"].demo:
                continue  # les vitrines sont recalées exactement plus bas
            pr["montants"] = pr["montants"] * facteur[idx_of[pr["c"].id]]
        # calage exact des vitrines (TEJ et El Fatoora)
        for e in self.ents:
            if not e.demo or not any(e.plan[y].get("tej") or e.plan[y].get("fatoora") for y in YEARS):
                continue
            prs = [pr for pr in paires if pr["f"] is e]
            for ky, y in enumerate(YEARS):
                cible = e.plan[y].get("tej") or e.plan[y].get("fatoora")
                if not cible:
                    continue
                tot = sum(pr["montants"][ky] for pr in prs) or 1
                for pr in prs:
                    pr["montants"][ky] = pr["montants"][ky] / tot * cible
        fid = 0
        tid = 0
        for pr in paires:
            e, c = pr["f"], pr["c"]
            variante = e.params.get("f1_variante")
            for ky, y in enumerate(YEARS):
                total_reel = float(pr["montants"][ky])
                if total_reel <= 0:
                    continue
                k0 = t_index(y, 1)
                mois = [mi for mi in range(12) if (mi % pr["freq"]) == pr["offset"] and e.actif[k0 + mi] and c.actif[k0 + mi]]
                if not mois:
                    continue
                # montant facturé via El Fatoora
                total_fact = total_reel
                ratio = e.params.get("f1_ratio", {}).get(y)
                if ratio and variante == "tej":
                    b2b_total = e.ca_local_reel[k0:k0 + 12].sum() * e.part_b2b
                    total_fact = total_reel * min(1.0, 0.9 * ratio * e.ca_local_reel[k0:k0 + 12].sum() / max(b2b_total, 1))
                if e.demo and e.plan[y].get("fatoora") and e.plan[y].get("tej"):
                    total_fact = total_reel * e.plan[y]["fatoora"] / e.plan[y]["tej"]
                vals = self._decouper(total_fact, len(mois), False) if len(mois) > 1 else [total_fact]
                for mi, v in zip(mois, vals):
                    fid += 1
                    self.factures.append({"id": fid, "emetteur_id": e.id, "client_id": c.id,
                                          "date": fin_de_mois(y, mi + 1) - timedelta(days=int(self.rng.integers(0, 20))),
                                          "montant_ht": r3(v), "tva": r3(v * TVA),
                                          "code_sh_principal": e.secteur.produits[0].code_sh if (e.secteur.produits and self.rng.random() < 0.3) else None})
                # certificats de retenue à la source (TEJ), trimestriels, émis par le client payeur
                if not pr["agent"]:
                    continue
                paiements = np.zeros(4)
                vals_reels = self._decouper(total_reel, len(mois), False) if len(mois) > 1 else [total_reel]
                for mi, v in zip(mois, vals_reels):
                    paiements[mi // 3] += v
                if e.demo and e.plan[y].get("tej"):
                    paiements = np.round(paiements, 3)
                for q in range(4):
                    if paiements[q] < 1000:
                        continue
                    tid += 1
                    self.tej.append({"id": tid, "payeur_id": c.id, "beneficiaire_id": e.id,
                                     "date": fin_de_mois(y, 3 * q + 3) - timedelta(days=int(self.rng.integers(0, 25))),
                                     "montant_brut": r3(paiements[q]), "taux": ref.TAUX_RETENUE,
                                     "montant_retenu": r3(paiements[q] * ref.TAUX_RETENUE)})
        self._caler_tej_vitrines()
        self._fid, self._tid = fid, tid

    def _caler_tej_vitrines(self) -> None:
        """Corrige les arrondis pour que les totaux annuels des vitrines soient exacts."""
        for e in self.ents:
            if not e.demo:
                continue
            for y in YEARS:
                for cle, table, champ, id_champ in (("tej", self.tej, "montant_brut", "beneficiaire_id"),
                                                     ("fatoora", self.factures, "montant_ht", "emetteur_id")):
                    cible = e.plan[y].get(cle)
                    if not cible:
                        continue
                    lignes = [r for r in table if r[id_champ] == e.id and r["date"].year == y]
                    if not lignes:
                        continue
                    ecart = r3(cible - sum(r[champ] for r in lignes))
                    lignes[-1][champ] = r3(lignes[-1][champ] + ecart)
                    if cle == "tej":
                        lignes[-1]["montant_retenu"] = r3(lignes[-1][champ] * ref.TAUX_RETENUE)
                    else:
                        lignes[-1]["tva"] = r3(lignes[-1][champ] * TVA)

    def _carrousels(self) -> None:
        """F5 : cycle A -> B -> C (-> D) -> A sur 6 mois, un maillon ne reverse pas la TVA."""
        for n_anneau, anneau in enumerate(self.carrousels):
            if anneau is self._anneau_demo:
                annee, mois, montant = demo.CARROUSEL["annee"], demo.CARROUSEL["mois"], float(demo.CARROUSEL["montant_mensuel"])
            else:
                annee = 2025 if n_anneau % 2 else 2024
                debut = int(self.rng.integers(2, 7))
                mois = list(range(debut, debut + 6))
                montant = float(round(self.rng.uniform(100_000, 300_000), -3))
            for e in anneau:
                e.date_creation = min(e.date_creation, date(annee, mois[0], 1) - timedelta(days=60))
                e.refresh_actif()
            for mi in mois:
                t = t_index(annee, mi)
                for a, b in zip(anneau, anneau[1:] + anneau[:1]):
                    v = r3(montant * float(self.rng.uniform(0.97, 1.03))) if anneau is not self._anneau_demo else montant
                    self._fid += 1
                    self.factures.append({"id": self._fid, "emetteur_id": a.id, "client_id": b.id,
                                          "date": date(annee, mi, int(self.rng.integers(5, 26))), "montant_ht": v,
                                          "tva": r3(v * TVA), "code_sh_principal": "85171300"})
                    a.ventes_carrousel[t] += v
                    b.achats_carrousel[t] += v
            for e in anneau:
                if e.params.get("maillon_manquant"):
                    e.mois_non_deposes |= {t_index(annee, mi) for mi in mois}
                    e.montant_elude += sum(e.ventes_carrousel) * TVA
                    e.annuelles_absentes.add(annee)
                else:
                    e.montant_elude += sum(e.achats_carrousel) * TVA * 0.3

    def _societes_ecran(self) -> None:
        """F4 : factures fictives émises vers les sociétés du réseau (F3 variante locale)."""
        clients_par_ecran: dict[int, list[Ent]] = {}
        for e in self.ents:
            if e.params.get("ecran"):
                clients_par_ecran.setdefault(e.params["ecran"], []).append(e)
        by_id = {e.id: e for e in self.ents}
        for ecran in self.ecrans:
            clients = clients_par_ecran.get(ecran.id) or self.rnd.sample([e for e in self.ents if e.categorie == "fraudeur" and e is not ecran], 2)
            for c in clients:
                c.params.setdefault("ecran", ecran.id)
                for t in range(T):
                    if not (ecran.actif[t] and c.actif[t]) or self.rng.random() < 0.35:
                        continue
                    y, m = ym(t)
                    v = r3(float(self.rng.uniform(15_000, 60_000)))
                    self._fid += 1
                    self.factures.append({"id": self._fid, "emetteur_id": ecran.id, "client_id": c.id,
                                          "date": date(y, m, int(self.rng.integers(1, 28))), "montant_ht": v, "tva": r3(v * TVA),
                                          "code_sh_principal": None})
                    ecran.ventes_carrousel[t] += v       # ventes fictives de l'écran
                    c.factures_recues_fictives[t] += v   # TVA déduite à tort par le client
                    c.montant_elude += v * TVA
                    ecran.montant_elude += v * TVA * 0.2
            if ecran.params.get("mode_ecran") == "non_depose":
                actifs = [t for t in range(T) if ecran.actif[t]]
                if actifs:
                    n = min(len(actifs), int(self.rng.integers(4, 9)))
                    ecran.mois_non_deposes |= set(actifs[-n:])
        _ = by_id

    def _detournement_avantages(self) -> None:
        """F7 : équipements importés en exonération, puis revendus à des tiers (factures El Fatoora)."""
        tiers = [e for e in self.ents if e.categorie == "honnete" and e.secteur.type != "services"]
        for eid, lots in self.equip_importes.items():
            e = next(x for x in self.ents if x.id == eid)
            for t, code_sh, valeur in lots:
                t2 = min(T - 1, t + int(self.rng.integers(2, 7)))
                y, m = ym(t2)
                client = self.rnd.choice(tiers)
                v = r3(valeur * float(self.rng.uniform(1.0, 1.3)))
                self._fid += 1
                self.factures.append({"id": self._fid, "emetteur_id": e.id, "client_id": client.id,
                                      "date": date(y, m, int(self.rng.integers(1, 28))), "montant_ht": v, "tva": r3(v * TVA),
                                      "code_sh_principal": code_sh})
                e.ventes_carrousel[t2] += v  # vente déclarée
                e.montant_elude += valeur * (TVA + 0.15)

    # ------------------------------------------------------------------ TVA mensuelle
    def _declarations_tva(self, e: Ent) -> None:
        if e.regime == "forfaitaire":
            return
        credit = 0.0
        f3 = e.params.get("f3")
        f8 = e.params.get("f8")
        remb = e.params.get("remboursements") or e.secteur.habituellement_crediteur
        mois_credit = 0
        for t in range(T):
            if not e.actif[t]:
                continue
            y, m = ym(t)
            p = e.plan[y]
            fictives = e.ventes_carrousel[t] * (0.3 if e.params.get("mode_ecran") == "sous_declare" else 1.0)
            ca_local = r3(e.ca_local_decl[t] + fictives)
            if e.secteur.type == "services":
                ca_export = r3(e.ca_export_reel[t])
            else:
                ca_export = r3(e.exports_douane[t])
            if f8 and y in f8:
                fausses = r3(max(ca_export, e.ca_local_reel[t] * 0.3) * (f8[y] - 1))
                ca_export = r3(ca_export + fausses)
                e.montant_elude += fausses * TVA
            e.ca_export_decl[t] = ca_export
            # TVA import : payée en douane, déduite le mois même ou le suivant
            if e.lag_tva == 0:
                ded_import = e.tva_import_payee[t]
            else:
                ded_import = e.tva_import_payee[t - 1] if t > 0 else 0.0
            if p.get("tva_deduite_import") is not None:
                paye_annee = e.tva_import_payee[t_index(y, 1):t_index(y, 1) + 12].sum()
                ded_import = e.tva_import_payee[t] * p["tva_deduite_import"] / paye_annee if paye_annee else 0.0
                e.montant_elude += ded_import - e.tva_import_payee[t]
            if f3 and f3["variante"] == "import" and y in f3["facteur"]:
                sup = ded_import * (f3["facteur"][y] - 1)
                e.montant_elude += sup
                ded_import += sup
            ded_import = r3(ded_import)
            ded_local = r3((e.achats_locaux[t] + e.charges_taxables[t] + e.achats_carrousel[t] + e.factures_recues_fictives[t]) * TVA)
            ded_immo = 0.0
            collectee = r3(ca_local * TVA)
            net = collectee - ded_import - ded_local - ded_immo - credit
            if net >= 0:
                due, credit = r3(net), 0.0
                mois_credit = 0
            else:
                due, credit = 0.0, r3(-net)
                mois_credit += 1
            demande = 0.0
            if remb and credit > 5_000 and m in (3, 6, 9, 12) and mois_credit >= 3:
                demande, credit = credit, 0.0
            deposee = t not in e.mois_non_deposes
            retard = int(self.rng.integers(0, 12)) if (self.rng.random() < 0.05 and not e.demo) else 0
            ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
            self.tva.append({
                "entreprise_id": e.id, "annee": y, "mois": m,
                "date_depot": (date(ny, nm, 28) + timedelta(days=retard)) if deposee else None, "deposee": deposee,
                "ca_local_ht": ca_local if deposee else 0.0, "ca_export_ht": ca_export if deposee else 0.0,
                "tva_collectee": collectee if deposee else 0.0, "tva_deductible_import": ded_import if deposee else 0.0,
                "tva_deductible_local": ded_local if deposee else 0.0, "tva_deductible_immobilisations": ded_immo if deposee else 0.0,
                "credit_reporte": credit if deposee else 0.0, "tva_due": due if deposee else 0.0,
                "remboursement_demande": demande if deposee else 0.0,
            })

    # ------------------------------------------------------------------ déclarations annuelles
    def _declarations_annuelles(self, e: Ent) -> None:
        s = e.secteur
        lignes_imp = self._imports_par_annee.get(e.id, {})
        for y in YEARS:
            if y in e.annuelles_absentes or e.frac_annee(y) == 0:
                continue
            k = t_index(y, 1)
            p = e.plan[y]
            ca_decl = r3(sum(r["ca_local_ht"] + r["ca_export_ht"] for r in self._tva_par_ent.get(e.id, {}).get(y, []))) \
                if e.regime != "forfaitaire" else r3(e.ca_local_decl[k:k + 12].sum() + e.ca_export_reel[k:k + 12].sum())
            imp = lignes_imp.get(y, {"mc": 0.0, "at": 0.0, "equip": 0.0})
            achats_locaux = r3(e.achats_locaux[k:k + 12].sum() + e.achats_carrousel[k:k + 12].sum())
            if s.type == "negoce":
                achats_m, achats_mat = r3(imp["mc"] + achats_locaux), 0.0
            else:
                achats_m, achats_mat = 0.0, r3(imp["mc"] + imp["at"] + achats_locaux)
            s0, s1 = r3(p["stock_debut"]), r3(p["stock_fin"])
            consommes = r3(s0 + achats_m + achats_mat - s1)
            marge_brute = r3(ca_decl - consommes)
            personnel = r3(e.effectif * s.salaire_moyen * float(self.rng.uniform(0.9, 1.1)) * e.frac_annee(y))
            autres = r3(p["ca_reel"] * s.ratio_autres_charges * float(self.rng.uniform(0.85, 1.15)))
            rc = r3(marge_brute - personnel - autres - imp["equip"] * 0.1)
            rf = r3(rc * float(self.rng.uniform(1.0, 1.04)) if rc > 0 else rc)
            impot = r3(max(ref.TAUX_IS * max(rf, 0.0), 0.002 * ca_decl))
            self.annuelles.append({
                "entreprise_id": e.id, "annee": y, "chiffre_affaires": ca_decl, "achats_marchandises": achats_m,
                "achats_matieres": achats_mat, "stock_initial": s0, "stock_final": s1, "marge_brute": marge_brute,
                "charges_personnel": personnel, "autres_charges": autres, "resultat_comptable": rc, "resultat_fiscal": rf,
                "impot_du": impot, "immobilisations_acquises": r3(imp["equip"]),
            })
            ratio = e.params.get("f1_ratio", {}).get(y)
            if ratio:
                ecart = e.ca_local_reel[k:k + 12].sum() - e.ca_local_decl[k:k + 12].sum()
                e.montant_elude += ecart * TVA + ecart * p["marge"] / (1 + p["marge"]) * ref.TAUX_IS
            if e.demo == "sahel":
                ecart = p["ca_reel"] - p["ca_decl"]
                e.montant_elude += ecart * TVA + ecart * p["marge"] / (1 + p["marge"]) * ref.TAUX_IS

    def _encaissements(self, e: Ent) -> None:
        for t in range(T):
            if not e.actif[t]:
                continue
            y, m = ym(t)
            ttc = (e.ca_local_reel[t] + e.ventes_carrousel[t]) * (1 + TVA) + e.ca_export_reel[t]
            v = ttc * e.facteur_banque * float(self.rng.normal(1.0, 0.03))
            self.banque.append({"entreprise_id": e.id, "annee": y, "mois": m, "total_encaissements": r3(max(v, 0.0))})

    # ------------------------------------------------------------------ réseau
    def _ancres_radiees(self) -> None:
        """Sociétés radiées (hors des 2 000 actives) servant d'ancres au réseau : certaines après redressement."""
        rng = self.rng
        sahel = self.by_demo["sahel"]
        lie = demo.SAHEL["societe_liee"]
        a = self._nouvelle_ent("telephonie", categorie="fraudeur", raison_sociale=lie["raison_sociale"], forme="SARL",
                               gouvernorat="Sousse", delegation="Msaken", nat_code="47.42", date_creation=lie["date_creation"],
                               effectif=2, capital=20_000.0)
        a.schemas, a.statut, a.date_radiation, a.demo = ["F1"], "radiée", lie["date_radiation"], "sahel_mobile"
        a.refresh_actif()
        a.params.update({"ca0": 600_000, "croissance": 0.0, "redresse": lie})
        self._plan_aleatoire(a)
        self._series_mensuelles(a)
        self._ancre_sahel = a
        self.ancres = [a]
        for _ in range(44):
            secteur = self.rnd.choice(["telephonie", "informatique", "conseil", "transport", "materiaux", "electromenager"])
            cat = "fraudeur" if rng.random() < 0.65 else "honnete"
            e = self._nouvelle_ent(secteur, categorie=cat)
            e.statut = "radiée"
            e.date_creation = date(2012, 1, 1) + timedelta(days=int(rng.integers(0, 3000)))
            e.date_radiation = date(2023, 3, 1) + timedelta(days=int(rng.integers(0, 900)))
            e.refresh_actif()
            e.schemas = [self.rnd.choice(["F1", "F3", "F4"])] if cat == "fraudeur" else []
            e.params.update({"ca0": float(rng.uniform(150_000, 900_000)), "croissance": 0.0})
            e.effectif = int(rng.integers(1, 6))
            e.importateur = rng.random() < 0.5
            self._plan_aleatoire(e)
            self._series_mensuelles(e)
            if cat == "fraudeur" or rng.random() < 0.2:
                d = e.date_radiation - timedelta(days=int(rng.integers(90, 400)))
                e.params["redresse"] = {"annee_controlee": d.year - 1 if d.year > 2023 else 2023, "date_controle": d,
                                        "montant_redresse": float(round(rng.uniform(30_000, 250_000), -2)),
                                        "motif": sc.FRAUDES[e.schemas[0]]["motif"] if e.schemas else "regularisation_technique"}
            self.ancres.append(e)
        _ = sahel

    def _reseau_personnes(self) -> None:
        rng = self.rnd
        gerant_de: dict[int, int] = {}
        # vitrine : même gérant pour Sahel Électro et Sahel Mobile (radiée après redressement)
        pr, nm = demo.SAHEL["gerant"]
        pid = self._personne(pr, nm)
        for e in (self.by_demo["sahel"], self._ancre_sahel):
            self.roles.append({"entreprise_id": e.id, "personne_id": pid, "role": "gérant"})
            gerant_de[e.id] = pid
        ancres_redressees = [a for a in self.ancres if a.params.get("redresse")]
        # carrousels : gérant commun et adresse de domiciliation partagée
        for anneau in self.carrousels:
            pid = self._personne()
            dom = anneau[1].adresse_id
            for i, e in enumerate(anneau):
                if i < 2:
                    self.roles.append({"entreprise_id": e.id, "personne_id": pid, "role": "gérant" if i == 0 else "associé"})
                if i >= 1:
                    e.adresse_id = dom
        # sociétés écran : gérant lié à une société radiée redressée, adresse de domiciliation commune
        doms = [self._adresse("Tunis", "Bab Bhar") for _ in range(3)]
        for i, e in enumerate(self.ecrans):
            e.adresse_id = doms[i % len(doms)]
            anc = rng.choice(ancres_redressees)
            pid = gerant_de.get(anc.id) or self._personne()
            gerant_de.setdefault(anc.id, pid)
            if not any(r["entreprise_id"] == anc.id and r["personne_id"] == pid for r in self.roles):
                self.roles.append({"entreprise_id": anc.id, "personne_id": pid, "role": "gérant"})
            self.roles.append({"entreprise_id": e.id, "personne_id": pid, "role": "gérant"})
            gerant_de[e.id] = pid
        # fraudeurs : 55 % liés à une société radiée redressée ; honnêtes : 4 % (bruit réaliste)
        for e in self.ents:
            if e.id in gerant_de:
                continue
            lien = (e.categorie == "fraudeur" and e.statut == "active" and self.rng.random() < 0.55) or \
                   (e.categorie != "fraudeur" and e.statut == "active" and self.rng.random() < 0.04)
            if lien and ancres_redressees and e.demo is None:
                anc = rng.choice(ancres_redressees)
                pid = gerant_de.get(anc.id)
                if pid is None:
                    pid = self._personne()
                    gerant_de[anc.id] = pid
                    self.roles.append({"entreprise_id": anc.id, "personne_id": pid, "role": "gérant"})
            else:
                pid = self._personne()
            self.roles.append({"entreprise_id": e.id, "personne_id": pid, "role": "gérant"})
            gerant_de[e.id] = pid
        # associés et petits groupes d'entreprises honnêtes (même dirigeant)
        honnetes = [e for e in self.ents if e.categorie != "fraudeur" and e.statut == "active" and e.demo is None]
        for e in self.ents:
            if e.forme in ("SARL", "SA") and self.rng.random() < 0.6:
                for _ in range(int(self.rng.integers(1, 3))):
                    if self.rng.random() < 0.08 and honnetes:
                        autre = rng.choice(honnetes)
                        pid = gerant_de.get(autre.id) or self._personne()
                    else:
                        pid = self._personne()
                    self.roles.append({"entreprise_id": e.id, "personne_id": pid, "role": "associé"})

    # ------------------------------------------------------------------ contrôles passés (étiquettes)
    def _controles_historiques(self) -> None:
        rng = self.rng
        cid = 0
        for a in self.ancres:
            r = a.params.get("redresse")
            if r:
                cid += 1
                self.controles.append({"id": cid, "entreprise_id": a.id, "annee_controlee": r["annee_controlee"],
                                       "date_controle": r["date_controle"], "type": "approfondie", "origine_selection": "dénonciation",
                                       "redressement": True, "montant_redresse": r["montant_redresse"], "motif_categorie": r["motif"]})
        pool = [e for e in self.ents if e.statut == "active" and e.date_creation < date(2023, 1, 1) and e.demo is None]
        taille = np.array([max(e.params.get("ca0", 5e5), 1e5) for e in pool]) ** 0.5
        fraude = np.array([e.categorie == "fraudeur" for e in pool])
        piege = np.array([e.categorie == "honnete_ecart_explique" for e in pool])
        choisis: dict[int, str] = {}

        def tirer(n: int, poids: np.ndarray, origine: str) -> None:
            p = poids.copy()
            for i, e in enumerate(pool):
                if e.id in choisis:
                    p[i] = 0
            idx = rng.choice(len(pool), size=n, replace=False, p=p / p.sum())
            for i in idx:
                choisis[pool[i].id] = origine

        tirer(250, np.ones(len(pool)), "aléatoire")
        tirer(250, taille * np.where(fraude, 2.5, 1.0) * np.where(piege, 2.0, 1.0), "liste manuelle")
        tirer(80, np.where(fraude, 9.0, 1.0), "dénonciation")
        by_id = {e.id: e for e in pool}
        for eid, origine in sorted(choisis.items()):
            e = by_id[eid]
            annee = int(rng.choice([2023, 2024]))
            d = date(annee + 1, int(rng.integers(1, 13)), int(rng.integers(1, 28)))
            fraude_active = e.categorie == "fraudeur" and (
                ("F1" in e.schemas and annee in e.params.get("f1_ratio", {})) or
                ("F2" in e.schemas and annee in e.params.get("f2", {}).get("annees", [])) or
                ("F3" in e.schemas and annee in e.params.get("f3", {}).get("facteur", {})) or
                ("F8" in e.schemas and annee in e.params.get("f8", {})) or
                any(f in e.schemas for f in ("F6", "F7")))
            if fraude_active:
                redr = rng.random() < 0.90  # ~10 % de fraudeurs contrôlés passent sans redressement (bruit)
                montant = float(round(e.montant_elude / 3 * rng.uniform(0.6, 1.1), -2)) if redr else 0.0
                motif = sc.FRAUDES[e.schemas[0]]["motif"] if redr else None
            elif e.categorie == "fraudeur":  # fraude pas encore commencée cette année-là
                redr = rng.random() < 0.3
                montant = float(round(rng.uniform(5_000, 40_000), -2)) if redr else 0.0
                motif = "regularisation_technique" if redr else None
            else:
                redr = rng.random() < (0.12 if e.categorie == "honnete" else 0.15)
                montant = float(round(rng.uniform(2_000, 35_000), -2)) if redr else 0.0
                motif = "regularisation_technique" if redr else None
            cid += 1
            self.controles.append({"id": cid, "entreprise_id": eid, "annee_controlee": annee, "date_controle": d,
                                   "type": "approfondie" if rng.random() < 0.35 else "vérification préliminaire",
                                   "origine_selection": origine, "redressement": bool(redr),
                                   "montant_redresse": montant, "motif_categorie": motif})

    # ------------------------------------------------------------------ export
    def finaliser(self) -> dict[str, pd.DataFrame]:
        entreprises = []
        for e in self.ents:
            bureau = "Direction des moyennes entreprises" if e.params.get("ca0", 0) > 8_000_000 else \
                f"Centre régional de contrôle des impôts de {e.gouvernorat}"
            entreprises.append({
                "id": e.id, "matricule_fiscal": self._matricule(), "raison_sociale": e.raison_sociale,
                "forme_juridique": e.forme, "date_creation": e.date_creation, "gouvernorat": e.gouvernorat,
                "delegation": e.delegation, "adresse_id": e.adresse_id, "secteur_nat_code": e.nat_code,
                "secteur_libelle": ref.nomenclature_nat()[e.nat_code], "secteur_groupe": e.secteur.cle,
                "regime_fiscal": e.regime, "statut_export": e.statut_export, "capital": e.capital, "effectif": e.effectif,
                "statut_oea": e.statut_oea, "bureau_controle": bureau, "statut": e.statut, "date_radiation": e.date_radiation,
            })
        douane = pd.DataFrame(self.douane)
        douane.insert(0, "id", np.arange(1, len(douane) + 1))
        prix = self._prix_reference(douane)
        return {
            "entreprises": pd.DataFrame(entreprises), "personnes": pd.DataFrame(self.personnes),
            "roles": pd.DataFrame(self.roles).drop_duplicates(), "adresses": pd.DataFrame(self.adresses),
            "declarations_douane": douane, "declarations_tva": pd.DataFrame(self.tva),
            "declarations_annuelles": pd.DataFrame(self.annuelles), "retenues_source": pd.DataFrame(self.tej),
            "factures_electroniques": pd.DataFrame(self.factures), "encaissements_bancaires": pd.DataFrame(self.banque),
            "controles_historiques": pd.DataFrame(self.controles), "prix_reference": prix,
            "parametres": self._parametres(),
            "secteurs_reference": pd.DataFrame([{
                "secteur_groupe": s.cle, "libelle": ref.LIBELLES_SECTEURS[s.cle], "type": s.type,
                "marge_mediane": s.marge_mediane, "marge_sd": s.marge_sd,
                "habituellement_crediteur": s.habituellement_crediteur, "ventes_biens": s.type != "services",
            } for s in ref.SECTEURS.values()]),
        }

    def _prix_reference(self, douane: pd.DataFrame) -> pd.DataFrame:
        """Référentiel de prix (simule la base de valeur de la douane) : déclarations d'entreprises honnêtes."""
        honnetes = {e.id for e in self.ents if e.categorie != "fraudeur"}
        d = douane[(douane.flux == "import") & (~douane.est_equipement) & (douane.entreprise_id.isin(honnetes))
                   & (douane.quantite > 0)].copy()
        d["pu"] = d.valeur_cif_dt / d.quantite
        g = d.groupby(["code_sh", "pays_origine"])["pu"]
        out = pd.DataFrame({"prix_unitaire_median": g.median(), "p10": g.quantile(0.10), "p90": g.quantile(0.90),
                            "nb_obs": g.size()}).reset_index()
        out = out[out.nb_obs >= 5]
        for c in ("prix_unitaire_median", "p10", "p90"):
            out[c] = out[c].round(3)
        return out

    def _parametres(self) -> pd.DataFrame:
        rows = [{"cle": k, "valeur": v, "source": s, "a_verifier": a} for k, v, s, a in config.PARAMETRES_DEFAUT]
        for s in ref.SECTEURS.values():
            rows.append({"cle": f"marge_mediane.{s.cle}", "valeur": s.marge_mediane,
                         "source": "Référentiel sectoriel simulé (données fictives)", "a_verifier": False})
        return pd.DataFrame(rows)

    def verite_terrain(self) -> pd.DataFrame:
        rows = []
        for e in self.ents:
            rows.append({"entreprise_id": e.id, "categorie": e.categorie, "schemas": ";".join(e.schemas),
                         "explication_legitime": e.explication or (sc.PIEGES[e.piege]["explication"] if e.piege else ""),
                         "montant_elude_reel": round(e.montant_elude, 0) if e.categorie == "fraudeur" else 0.0,
                         "piege": e.piege or "", "statut": e.statut, "vitrine": e.demo or ""})
        return pd.DataFrame(rows)


def _post_douane(gen: Generateur) -> None:
    """Agrège les lignes douane (TVA payée, importations par année) avant la TVA et les annuelles."""
    by = {e.id: e for e in gen.ents}
    imports: dict[int, dict[int, dict]] = {}
    for r in gen.douane:
        e = by[r["entreprise_id"]]
        y, m = r["date"].year, r["date"].month
        t = t_index(y, m)
        if r["flux"] == "import":
            e.tva_import_payee[t] += r["tva_import"]
            d = imports.setdefault(e.id, {}).setdefault(y, {"mc": 0.0, "at": 0.0, "equip": 0.0})
            if r["est_equipement"]:
                d["equip"] += r["valeur_cif_dt"]
            elif r["regime"] == "admission temporaire":
                d["at"] += r["valeur_cif_dt"]
            else:
                d["mc"] += r["base_tva"]
    gen._imports_par_annee = imports


def generer(n: int = config.N_ENTREPRISES, seed: int = config.SEED, db_path: Path | None = None,
            gt_path: Path | None = None) -> dict:
    t0 = time.perf_counter()
    ref.verifier_referentiel()
    gen = Generateur(n, seed)
    # construire() découpé pour insérer l'agrégation douane au bon moment
    profils = gen._tirer_profils()
    for categorie, secteur, tag in profils:
        e = gen._nouvelle_ent(secteur, categorie=categorie)
        if categorie == "honnete_ecart_explique":
            e.piege, e.explication = tag, sc.PIEGES[tag]["explication"]
        elif categorie == "fraudeur":
            e.schemas = [tag]
            second = sc.SECOND_SCHEMA.get(tag)
            if second and gen.rng.random() < sc.PROBA_SECOND_SCHEMA:
                e.schemas.append(gen.rnd.choice(second))
        gen._caracteriser(e)
    gen._construire_demos()
    for e in gen.ents:
        if e.demo is None:
            gen._plan_aleatoire(e)
    gen._appliquer_structure_fraudes()
    for e in gen.ents:
        gen._series_mensuelles(e)
    gen._ancres_radiees()
    for e in gen.ents:
        gen._douane(e)
    _post_douane(gen)
    gen._factures_et_tej()
    gen._carrousels()
    gen._societes_ecran()
    gen._detournement_avantages()
    for e in gen.ents:
        gen._declarations_tva(e)
    gen._tva_par_ent = {}
    for r in gen.tva:
        gen._tva_par_ent.setdefault(r["entreprise_id"], {}).setdefault(r["annee"], []).append(r)
    for e in gen.ents:
        gen._declarations_annuelles(e)
        gen._encaissements(e)
    gen._reseau_personnes()
    gen._controles_historiques()
    tables = gen.finaliser()
    gt = gen.verite_terrain()

    db_path = Path(db_path or config.DB_PATH)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            p.unlink()
    engine = db.make_engine(db_path)
    db.create_schema(engine, drop=True)
    with engine.begin() as conn:
        for name, df in tables.items():
            if len(df):
                df.to_sql(name, conn, if_exists="append", index=False, chunksize=5000, method=None)
    engine.dispose()
    gt_path = Path(gt_path or config.GROUND_TRUTH_PATH)
    gt.to_csv(gt_path, index=False, encoding="utf-8")
    stats = {name: len(df) for name, df in tables.items()}
    stats["duree_s"] = round(time.perf_counter() - t0, 1)
    stats["categories"] = gt[gt.statut == "active"].categorie.value_counts().to_dict()
    log.info("Base générée : %s", json.dumps(stats, ensure_ascii=False, default=str))
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    s = generer()
    print(json.dumps(s, ensure_ascii=False, indent=1, default=str))
