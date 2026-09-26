"""Référentiel de simulation : secteurs (nomenclature NAT 2009), produits, prix simulés,
géographie, codes d'équipement (annexe du décret 2017-419).

Tout est fictif ou générique (géographie publique, codes tarifaires). Les marges
médianes sectorielles forment un « référentiel sectoriel simulé » stocké dans `parametres`.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_ASSETS = ROOT / "data" / "rag_index" / "data_assets"
NAT_FILE = DATA_ASSETS / "nomenclature_activites_nat2009.csv"
EQUIP_FILE = DATA_ASSETS / "equipements_codes_tarifaires_2017_419.csv"

TAUX_TVA = 0.19          # paramètre `taux_tva_normal` (à vérifier dans le code de la TVA)
TAUX_IS = 0.15           # paramètre `taux_is` (à vérifier)
TAUX_AVANCE_IMPORT = 0.10
TAUX_RETENUE = 0.015
SEUIL_FRACTIONNEMENT = 3000.0  # valeur CIF sous laquelle une déclaration échappe au contrôle (hypothèse)


@dataclass(frozen=True)
class Produit:
    code_sh: str
    designation: str
    unite: str
    prix: float                    # prix unitaire CIF de référence (DT), origine de base
    origines: tuple[tuple[str, float, float], ...]  # (pays, poids, multiplicateur de prix)
    taux_droits: float
    kg_par_unite: float


@dataclass(frozen=True)
class Secteur:
    cle: str
    nat_codes: tuple[str, ...]
    type: str                      # negoce | industrie | services
    marge_mediane: float           # marge sur coût d'achat consommé : CA = coût × (1 + marge)
    marge_sd: float
    poids: float                   # part des entreprises
    p_importateur: float
    part_import: float             # part des achats importés chez un importateur
    mois_stock: float              # stock moyen en mois de coût des ventes
    part_b2b: tuple[float, float]  # part des ventes locales à des entreprises (factures + TEJ)
    ca_par_employe: float
    salaire_moyen: float
    ratio_autres_charges: float
    produits: tuple[Produit, ...] = ()
    prefixes_equipement: tuple[str, ...] = ()
    produits_export: tuple[Produit, ...] = ()
    statut_export: str = "local"   # statut par défaut
    habituellement_crediteur: bool = False
    b1_applicable: bool = True
    ratio_achats_services: float = 0.25  # services : achats / CA


def _p(code, des, unite, prix, origines, droits, kg):
    return Produit(code, des, unite, prix, tuple(origines), droits, kg)


CN, TR, IT, FR, DE, ES = "Chine", "Turquie", "Italie", "France", "Allemagne", "Espagne"
VN, KR, IN, SA, NL, PT = "Viet Nam", "Corée du Sud", "Inde", "Arabie saoudite", "Pays-Bas", "Portugal"
CI, GH, BR, UA, DZ, EG, MY = "Côte d'Ivoire", "Ghana", "Brésil", "Ukraine", "Algérie", "Égypte", "Malaisie"

SECTEURS: dict[str, Secteur] = {s.cle: s for s in [
    Secteur("telephonie", ("46.52", "47.42"), "negoce", 0.20, 0.04, 0.07, 0.80, 0.95, 2.0, (0.35, 0.65), 450_000, 14_000, 0.05,
            (_p("85171300", "Téléphones intelligents (smartphones)", "u", 650, [(CN, .7, .95), (VN, .2, 1.0), (KR, .1, 1.25)], 0.0, 0.3),
             _p("85176200", "Routeurs et appareils de transmission de données", "u", 180, [(CN, .8, 1.0), (VN, .2, 1.05)], 0.0, 0.6),
             _p("85183000", "Écouteurs et casques d'écoute", "u", 25, [(CN, .9, 1.0), (VN, .1, 1.1)], 0.0, 0.1))),
    Secteur("electromenager", ("46.43", "47.54"), "negoce", 0.22, 0.045, 0.07, 0.75, 0.85, 2.5, (0.30, 0.60), 400_000, 13_000, 0.06,
            (_p("85287200", "Téléviseurs couleur à écran plat", "u", 900, [(CN, .5, .9), (TR, .35, 1.0), (KR, .15, 1.3)], 0.20, 12),
             _p("84182100", "Réfrigérateurs ménagers à compression", "u", 1100, [(TR, .5, 1.0), (CN, .3, .9), (IT, .2, 1.25)], 0.20, 55),
             _p("84501100", "Machines à laver le linge entièrement automatiques", "u", 950, [(TR, .5, 1.0), (CN, .3, .9), (IT, .2, 1.2)], 0.20, 65))),
    Secteur("informatique", ("46.51",), "negoce", 0.18, 0.04, 0.05, 0.75, 0.85, 2.0, (0.45, 0.75), 420_000, 16_000, 0.06,
            (_p("84713000", "Ordinateurs portables", "u", 1500, [(CN, .75, .95), (MY, .25, 1.05)], 0.0, 2.2),
             _p("84716000", "Claviers et souris d'ordinateur", "u", 25, [(CN, 1.0, 1.0)], 0.0, 0.5),
             _p("85285200", "Moniteurs pour machines de traitement de l'information", "u", 350, [(CN, .7, .95), (KR, .3, 1.15)], 0.0, 4.5))),
    Secteur("pieces_auto", ("45.31",), "negoce", 0.25, 0.05, 0.06, 0.75, 0.80, 3.0, (0.40, 0.70), 380_000, 13_000, 0.06,
            (_p("40111000", "Pneumatiques neufs pour voitures de tourisme", "u", 220, [(CN, .4, .85), (TR, .3, 1.0), (IT, .3, 1.25)], 0.30, 9),
             _p("87083000", "Freins et servofreins et leurs parties", "u", 120, [(TR, .4, 1.0), (DE, .3, 1.3), (CN, .3, .85)], 0.20, 4),
             _p("87089900", "Autres parties et accessoires de véhicules", "u", 80, [(TR, .5, 1.0), (CN, .3, .85), (ES, .2, 1.2)], 0.20, 3))),
    Secteur("pharma_para", ("46.46",), "negoce", 0.22, 0.04, 0.04, 0.75, 0.70, 2.0, (0.50, 0.80), 500_000, 17_000, 0.06,
            (_p("33049900", "Produits de beauté et de soin de la peau", "u", 18, [(FR, .5, 1.1), (IT, .3, 1.05), (TR, .2, .85)], 0.20, 0.25),
             _p("34011100", "Savons de toilette", "u", 3, [(TR, .6, 1.0), (ES, .4, 1.1)], 0.20, 0.12))),
    Secteur("materiaux", ("46.73",), "negoce", 0.15, 0.035, 0.06, 0.75, 0.60, 2.5, (0.50, 0.80), 550_000, 12_000, 0.05,
            (_p("69072100", "Carreaux céramiques (le m²)", "m2", 28, [(ES, .4, 1.1), (IT, .3, 1.2), (TR, .3, .9)], 0.30, 20),
             _p("72142000", "Barres en fer ou en acier (le kg)", "kg", 3.2, [(TR, .5, 1.0), (UA, .3, .95), (DZ, .2, .97)], 0.0, 1),
             _p("44071100", "Bois de conifères sciés (le m³)", "m3", 1200, [(PT, .5, 1.0), (ES, .5, 1.05)], 0.0, 500))),
    Secteur("distribution_alimentaire", ("46.39", "47.11"), "negoce", 0.08, 0.02, 0.08, 0.70, 0.55, 1.2, (0.40, 0.75), 700_000, 11_000, 0.03,
            (_p("04069000", "Fromages (le kg)", "kg", 22, [(FR, .4, 1.05), (NL, .4, 1.0), (DE, .2, 1.0)], 0.36, 1),
             _p("09012100", "Café torréfié (le kg)", "kg", 30, [(IT, .6, 1.1), (BR, .4, .9)], 0.36, 1),
             _p("17019900", "Sucre blanc (le kg)", "kg", 2.3, [(BR, .5, .95), (EG, .3, 1.0), (DZ, .2, 1.02)], 0.0, 1))),
    Secteur("carburants", ("46.71",), "negoce", 0.05, 0.012, 0.03, 0.55, 0.25, 0.8, (0.50, 0.85), 1_200_000, 12_000, 0.02,
            (_p("27101981", "Huiles lubrifiantes pour moteurs (le litre)", "l", 6, [(IT, .4, 1.05), (FR, .3, 1.1), (ES, .3, 1.0)], 0.20, 0.9),)),
    Secteur("textile_negoce", ("46.41",), "negoce", 0.24, 0.05, 0.04, 0.75, 0.80, 3.0, (0.40, 0.70), 400_000, 12_000, 0.06,
            (_p("52085200", "Tissus de coton imprimés (le mètre)", "m", 9, [(TR, .4, 1.0), (CN, .4, .85), (IT, .2, 1.3)], 0.20, 0.2),
             _p("55151100", "Tissus de fibres synthétiques (le mètre)", "m", 7, [(TR, .5, 1.0), (CN, .5, .85)], 0.20, 0.2))),
    Secteur("agroalimentaire", ("10.82", "10.71"), "industrie", 0.45, 0.08, 0.06, 0.65, 0.50, 1.5, (0.40, 0.75), 250_000, 11_000, 0.10,
            (_p("18010000", "Fèves de cacao (le kg)", "kg", 12, [(CI, .6, 1.0), (GH, .4, 1.02)], 0.0, 1),
             _p("17019900", "Sucre blanc (le kg)", "kg", 2.3, [(BR, .5, .95), (EG, .3, 1.0), (DZ, .2, 1.02)], 0.0, 1)),
            ("8438", "8422", "8419")),
    Secteur("plasturgie", ("22.22",), "industrie", 0.40, 0.07, 0.05, 0.65, 0.70, 2.0, (0.60, 0.85), 280_000, 12_000, 0.10,
            (_p("39011000", "Polyéthylène en granulés (le kg)", "kg", 4.2, [(SA, .6, 1.0), (KR, .2, 1.05), (ES, .2, 1.1)], 0.0, 1),
             _p("39021000", "Polypropylène en granulés (le kg)", "kg", 4.0, [(SA, .6, 1.0), (KR, .4, 1.05)], 0.0, 1)),
            ("8477", "8479")),
    Secteur("textile_export", ("14.14",), "industrie", 0.55, 0.10, 0.06, 0.85, 0.90, 1.5, (0.0, 0.0), 60_000, 9_000, 0.08,
            (_p("52085200", "Tissus de coton imprimés (le mètre)", "m", 9, [(IT, .5, 1.1), (TR, .5, 1.0)], 0.0, 0.2),
             _p("96071100", "Fermetures à glissière", "u", 0.8, [(TR, .5, 1.0), (CN, .5, .85)], 0.0, 0.02)),
            ("8452", "8445"),
            (_p("62034200", "Pantalons en coton pour hommes", "u", 45, [], 0.0, 0.5),
             _p("62046200", "Pantalons en coton pour femmes", "u", 40, [], 0.0, 0.45)),
            statut_export="totalement exportatrice", habituellement_crediteur=True),
    Secteur("cablage_auto", ("29.31",), "industrie", 0.50, 0.08, 0.04, 0.90, 0.90, 1.5, (0.0, 0.0), 90_000, 10_000, 0.08,
            (_p("74081100", "Fils de cuivre affiné (le kg)", "kg", 38, [(DE, .5, 1.05), (IT, .5, 1.0)], 0.0, 1),
             _p("85369010", "Connecteurs électriques", "u", 1.2, [(DE, .6, 1.1), (CN, .4, .85)], 0.0, 0.01)),
            ("8479", "8465"),
            (_p("85443000", "Jeux de fils pour véhicules", "u", 95, [], 0.0, 1.2),),
            statut_export="totalement exportatrice", habituellement_crediteur=True),
    Secteur("mecanique", ("25.62",), "industrie", 0.45, 0.08, 0.04, 0.60, 0.40, 2.0, (0.60, 0.85), 180_000, 13_000, 0.10,
            (_p("72142000", "Barres en fer ou en acier (le kg)", "kg", 3.2, [(TR, .5, 1.0), (UA, .5, .95)], 0.0, 1),),
            ("8465", "8479", "8428")),
    Secteur("btp", ("41.20",), "industrie", 0.25, 0.06, 0.07, 0.20, 0.15, 1.0, (0.40, 0.80), 150_000, 10_000, 0.08,
            (_p("72142000", "Barres en fer ou en acier (le kg)", "kg", 3.2, [(TR, .5, 1.0), (UA, .5, .95)], 0.0, 1),),
            ("8429", "8474", "8428")),
    Secteur("transport", ("49.41",), "services", 1.20, 0.25, 0.05, 0.10, 0.20, 0.3, (0.60, 0.90), 160_000, 12_000, 0.25,
            b1_applicable=False, ratio_achats_services=0.35, prefixes_equipement=("8427", "8428")),
    Secteur("hotellerie", ("55.10",), "services", 1.50, 0.30, 0.04, 0.05, 0.20, 0.3, (0.10, 0.30), 70_000, 9_000, 0.25,
            b1_applicable=False, ratio_achats_services=0.30),
    Secteur("conseil", ("70.22",), "services", 3.00, 0.60, 0.05, 0.0, 0.0, 0.0, (0.70, 0.95), 120_000, 22_000, 0.20,
            b1_applicable=False, ratio_achats_services=0.10),
    Secteur("services_informatiques", ("62.01",), "services", 3.00, 0.60, 0.04, 0.05, 0.10, 0.0, (0.60, 0.90), 110_000, 24_000, 0.15,
            b1_applicable=False, ratio_achats_services=0.10),
]}

# Secteurs d'où proviennent les pièges « faible marge »
SECTEURS_FAIBLE_MARGE = ("distribution_alimentaire", "carburants")

GOUVERNORATS: dict[str, tuple[float, tuple[str, ...]]] = {
    "Tunis": (0.14, ("Bab Bhar", "La Marsa", "El Menzah", "Le Bardo", "Médina")),
    "Ariana": (0.07, ("Ariana Ville", "La Soukra", "Raoued", "Ettadhamen")),
    "Ben Arous": (0.08, ("Ben Arous", "Mégrine", "Radès", "Hammam Lif")),
    "Manouba": (0.03, ("Manouba", "Den Den", "Oued Ellil")),
    "Nabeul": (0.07, ("Nabeul", "Hammamet", "Korba", "Grombalia")),
    "Zaghouan": (0.01, ("Zaghouan", "El Fahs")),
    "Bizerte": (0.04, ("Bizerte Nord", "Menzel Bourguiba", "Mateur")),
    "Béja": (0.01, ("Béja Nord", "Medjez El Bab")),
    "Jendouba": (0.01, ("Jendouba", "Tabarka")),
    "Le Kef": (0.01, ("Le Kef Est", "Dahmani")),
    "Siliana": (0.01, ("Siliana Nord", "Makthar")),
    "Sousse": (0.09, ("Sousse Médina", "Sousse Jawhara", "Hammam Sousse", "Msaken", "Kalâa Kebira")),
    "Monastir": (0.07, ("Monastir", "Ksar Hellal", "Moknine", "Jemmal")),
    "Mahdia": (0.03, ("Mahdia", "El Jem", "Ksour Essef")),
    "Sfax": (0.11, ("Sfax Ville", "Sfax Sud", "Sakiet Ezzit", "Thyna")),
    "Kairouan": (0.02, ("Kairouan Nord", "Haffouz")),
    "Kasserine": (0.01, ("Kasserine Nord", "Sbeïtla")),
    "Sidi Bouzid": (0.01, ("Sidi Bouzid Ouest", "Regueb")),
    "Gabès": (0.02, ("Gabès Ville", "El Hamma")),
    "Médenine": (0.03, ("Médenine Nord", "Djerba Houmt Souk", "Djerba Midoun", "Zarzis")),
    "Tataouine": (0.005, ("Tataouine Nord",)),
    "Gafsa": (0.01, ("Gafsa Nord", "Métlaoui")),
    "Tozeur": (0.005, ("Tozeur", "Nefta")),
    "Kébili": (0.005, ("Kébili Nord", "Douz")),
}

BUREAUX_DOUANE = {
    "Tunis": "Bureau de Radès Port", "Ben Arous": "Bureau de Radès Port", "Ariana": "Bureau de Tunis-Carthage Aéroport",
    "Manouba": "Bureau de Radès Port", "Nabeul": "Bureau de Radès Port", "Bizerte": "Bureau de Bizerte Port",
    "Sousse": "Bureau de Sousse Port", "Monastir": "Bureau de Sousse Port", "Mahdia": "Bureau de Sousse Port",
    "Sfax": "Bureau de Sfax Port", "Gabès": "Bureau de Gabès Port", "Médenine": "Bureau de Zarzis Port",
}
BUREAU_DOUANE_DEFAUT = "Bureau de Radès Port"

FORMES = (("SARL", 0.50), ("SUARL", 0.25), ("SA", 0.12), ("Personne physique", 0.13))

PRENOMS = ("Ahmed", "Mohamed", "Sami", "Karim", "Nizar", "Walid", "Hichem", "Mourad", "Anis", "Riadh", "Slim", "Fares",
           "Amel", "Leila", "Sonia", "Imen", "Rim", "Nadia", "Salma", "Ines", "Hela", "Mariem", "Olfa", "Sarra",
           "Yassine", "Bilel", "Chokri", "Lotfi", "Mehdi", "Aymen", "Houda", "Asma", "Khaled", "Tarek", "Nabil", "Wafa")
NOMS = ("Ben Ali", "Trabelsi", "Gharbi", "Jlassi", "Hammami", "Ayari", "Mejri", "Dridi", "Sassi", "Khelifi", "Chaabane",
        "Bouazizi", "Jebali", "Mansouri", "Ferchichi", "Karray", "Zouari", "Ellouze", "Masmoudi", "Rekik", "Belhadj",
        "Ben Salah", "Ben Amor", "Hamdi", "Nasri", "Toumi", "Oueslati", "Saidi", "Brahmi", "Kchaou", "Abid", "Mzoughi")

PREFIXES_NOMS = ("Sahel", "Carthage", "Atlas", "Yasmine", "Médina", "Oasis", "Jasmin", "Zitouna", "Hannibal", "Tanit",
                 "Elissa", "Phénix", "Golfe", "Horizon", "Étoile", "Olivier", "Palmier", "Andalous", "Nour", "Amal",
                 "Salam", "Rim", "Kerkennah", "Cap", "Soleil", "Méditerranée", "Dunes", "Ksar", "Alyssa", "Byrsa",
                 "Numidia", "Thapsus", "Hadrumète", "Utique", "Dougga", "Kairouane", "Sabra", "Mahdia Côte", "Delta",
                 "Orion", "Sirius", "Lotus", "Cèdre", "Corail", "Ambre", "Opale", "Saphir", "Aurore", "Zénith", "Ibis")
SUFFIXES_NOMS = {
    "telephonie": ("Mobile", "Télécom Distribution", "Phone Center", "Électro", "Connect"),
    "electromenager": ("Électroménager", "Home Équipement", "Froid et Confort", "Électro Maison"),
    "informatique": ("Informatique", "Digital Distribution", "Micro Systèmes", "Data Store"),
    "pieces_auto": ("Auto Pièces", "Pneus et Services", "Moteur Distribution", "Auto Import"),
    "pharma_para": ("Para Distribution", "Beauté Santé", "Cosmétique Import"),
    "materiaux": ("Matériaux", "Céramique Import", "Bois et Acier", "Construction Distribution"),
    "distribution_alimentaire": ("Distribution", "Alimentation Générale", "Agro Négoce", "Épicerie en Gros"),
    "carburants": ("Lubrifiants", "Énergie Distribution", "Carburants Services"),
    "textile_negoce": ("Tissus", "Textile Négoce", "Mercerie en Gros"),
    "agroalimentaire": ("Agro Industries", "Confiserie", "Biscuiterie", "Délices Industriels"),
    "plasturgie": ("Plast", "Emballages", "Polymères Industries"),
    "textile_export": ("Textile", "Confection", "Jeans Manufacturing", "Mode Export"),
    "cablage_auto": ("Câblage", "Wiring Systems", "Faisceaux Électriques"),
    "mecanique": ("Mécanique", "Usinage de Précision", "Métal Industries"),
    "btp": ("Bâtiment", "Construction", "Travaux Généraux"),
    "transport": ("Transport", "Logistique", "Fret Express"),
    "hotellerie": ("Hôtel", "Résidence", "Tourisme"),
    "conseil": ("Conseil", "Gestion et Stratégie", "Audit et Conseil"),
    "services_informatiques": ("Software", "Solutions Numériques", "IT Services"),
}
RUES = ("rue de la Liberté", "avenue Habib Bourguiba", "rue des Oliviers", "zone industrielle", "rue Ibn Khaldoun",
        "avenue de la République", "rue de Palestine", "route de Sfax", "rue du Jasmin", "avenue Farhat Hached",
        "rue de Marseille", "cité El Khadra", "rue Ali Belhouane", "route de la Plage", "avenue de l'Environnement")


@lru_cache(maxsize=1)
def nomenclature_nat() -> dict[str, str]:
    """class_code -> libellé, lu dans l'actif de l'index (encodage utf-8)."""
    with NAT_FILE.open(encoding="utf-8", newline="") as fh:
        return {r["class_code"]: r["class_title"] for r in csv.DictReader(fh)}


def _digits(code: str) -> str:
    return re.sub(r"\D", "", code or "")


@lru_cache(maxsize=1)
def codes_equipement() -> dict[str, str]:
    """Codes tarifaires précis (>= 6 chiffres) de l'annexe 2017-419 -> désignation.

    Les positions « EX » à 4 chiffres couvrent un chapitre entier (ex. 8517 inclut les
    téléphones) : elles sont ignorées pour ne pas classer à tort des marchandises.
    """
    out: dict[str, str] = {}
    with EQUIP_FILE.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            d = _digits(r["tariff_code"])
            if len(d) >= 6:
                out.setdefault(d[:8], (r.get("designation") or "").strip())
    return out


def est_equipement(code_sh: str) -> bool:
    code = _digits(code_sh)
    return any(code.startswith(c) for c in codes_equipement())


@lru_cache(maxsize=None)
def machines_pour(prefixes: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """Codes d'équipement (8 chiffres) de l'annexe correspondant aux préfixes d'un secteur."""
    out = []
    for code, des in sorted(codes_equipement().items()):
        if len(code) == 8 and code.startswith(prefixes):
            out.append((code, des[:120] or "Machine ou équipement industriel"))
    return tuple(out)


def verifier_referentiel() -> None:
    """Garde-fou : aucun produit à revendre ne doit être classé comme équipement."""
    nat = nomenclature_nat()
    for s in SECTEURS.values():
        for code in s.nat_codes:
            assert code in nat, f"Code NAT inconnu : {code}"
        for p in s.produits + s.produits_export:
            assert not est_equipement(p.code_sh), f"{p.code_sh} est un code d'équipement"
        if s.prefixes_equipement:
            assert machines_pour(s.prefixes_equipement), f"Aucune machine pour {s.cle}"
