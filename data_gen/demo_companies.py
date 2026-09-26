"""Entreprises vitrines de la démo (section 5.4) : valeurs FIXES, codées à la main.

Toutes les entreprises, personnes et adresses sont fictives. Les montants annuels sont
reproduits exactement dans la base (les tests de la phase 1 le vérifient).
"""
from __future__ import annotations

from datetime import date

# Clés utilisées par le générateur pour chaque année :
#   imports      : Σ base TVA (valeur CIF + droits) des importations à revendre, mise à la consommation
#   ca_decl      : chiffre d'affaires déclaré (local, HT)          ca_reel : chiffre d'affaires réel (vérité terrain)
#   ca_export    : exportations (déclarées = constatées en douane pour les honnêtes)
#   delta_stock  : variation de stock déclarée                     achats_locaux : achats locaux déclarés
#   tva_deduite_import : TVA déductible à l'import déclarée (None = TVA réellement payée)
#   tej          : Σ montants bruts des certificats de retenue émis par les clients (None = aléatoire cohérent)
#   fatoora      : Σ HT des factures électroniques émises (None = aléatoire cohérent)
#   imports_at   : intrants en admission temporaire          equipements : machines importées (codes 2017-419)

SAHEL = {
    "cle": "sahel",
    "raison_sociale": "Sahel Électro SARL",
    "forme": "SARL", "gouvernorat": "Sousse", "delegation": "Sousse Jawhara",
    "secteur": "telephonie", "nat_code": "46.52",
    "date_creation": date(2019, 3, 14), "effectif": 4, "capital": 50_000,
    "categorie": "fraudeur", "schemas": ["F1", "F3"],
    "stock_initial": 300_000,
    "produit_principal": "85171300",
    "gerant": ("Hichem", "Ben Salah"),
    "annees": {
        2023: {"imports": 2_400_000, "ca_decl": 700_000, "ca_reel": 2_760_000, "delta_stock": 100_000, "achats_locaux": 0,
               "tva_deduite_import": None, "tej": 950_000, "fatoora": 450_000},
        2024: {"imports": 2_700_000, "ca_decl": 750_000, "ca_reel": 3_060_000, "delta_stock": 150_000, "achats_locaux": 0,
               "tva_deduite_import": 538_000, "tej": 1_080_000, "fatoora": 480_000},
        2025: {"imports": 3_000_000, "ca_decl": 800_000, "ca_reel": 3_360_000, "delta_stock": 200_000, "achats_locaux": 0,
               "tva_deduite_import": 610_000, "tej": 1_200_000, "fatoora": 520_000},
    },
    "remboursements": True,
    # Société liée : même gérant, radiée après redressement
    "societe_liee": {"raison_sociale": "Sahel Mobile SARL", "date_creation": date(2016, 5, 2),
                     "date_radiation": date(2024, 3, 31), "annee_controlee": 2023, "date_controle": date(2023, 11, 20),
                     "montant_redresse": 184_000.0, "motif": "minoration_ca"},
}

CAP_BON = {
    "cle": "cap_bon",
    "raison_sociale": "Cap Bon Distribution SARL",
    "forme": "SARL", "gouvernorat": "Nabeul", "delegation": "Nabeul",
    "secteur": "telephonie", "nat_code": "46.52",
    "date_creation": date(2014, 9, 1), "effectif": 9, "capital": 120_000,
    "categorie": "honnete_ecart_explique", "piege": "stock",
    "explication": "Nouvel entrepôt ouvert fin 2025 : 2 300 000 DT de marchandises en stock au 31/12/2025.",
    "stock_initial": 110_000,
    "produit_principal": "85171300",
    "annees": {
        2023: {"imports": 610_000, "ca_decl": 760_000, "ca_reel": 760_000, "delta_stock": 5_000, "achats_locaux": 28_333.333},
        2024: {"imports": 640_000, "ca_decl": 790_000, "ca_reel": 790_000, "delta_stock": 5_000, "achats_locaux": 23_333.333},
        2025: {"imports": 3_000_000, "ca_decl": 800_000, "ca_reel": 800_000, "delta_stock": 2_300_000, "achats_locaux": 0,
               "tej": 780_000, "fatoora": 700_000},
    },
}

DJERBA = {
    "cle": "djerba",
    "raison_sociale": "Djerba Industries SA",
    "forme": "SA", "gouvernorat": "Médenine", "delegation": "Djerba Houmt Souk",
    "secteur": "plasturgie", "nat_code": "22.22",
    "date_creation": date(2011, 4, 18), "effectif": 38, "capital": 900_000,
    "categorie": "honnete_ecart_explique", "piege": "equipement",
    "explication": "Nouvelle ligne de production : 3 000 000 DT de machines importées (codes de l'annexe 2017-419), non revendues.",
    "stock_initial": 90_000,
    "annees": {
        2023: {"imports": 470_000, "ca_decl": 740_000, "ca_reel": 740_000, "delta_stock": 0, "achats_locaux": 58_571.429},
        2024: {"imports": 490_000, "ca_decl": 770_000, "ca_reel": 770_000, "delta_stock": 0, "achats_locaux": 60_000},
        2025: {"imports": 480_000, "ca_decl": 800_000, "ca_reel": 800_000, "delta_stock": 0, "achats_locaux": 91_428.571,
               "equipements": 3_000_000},
    },
}

NOUR = {
    "cle": "nour",
    "raison_sociale": "Nour Textile SA",
    "forme": "SA", "gouvernorat": "Monastir", "delegation": "Ksar Hellal",
    "secteur": "textile_export", "nat_code": "14.14",
    "date_creation": date(2006, 2, 10), "effectif": 180, "capital": 2_000_000,
    "categorie": "honnete", "statut_export": "totalement exportatrice",
    "stock_initial": 400_000,
    "annees": {
        2023: {"imports": 0, "imports_at": 3_000_000, "ca_decl": 0, "ca_export": 6_200_000, "ca_reel": 6_200_000,
               "delta_stock": 0, "achats_locaux": 1_000_000},
        2024: {"imports": 0, "imports_at": 3_150_000, "ca_decl": 0, "ca_export": 6_500_000, "ca_reel": 6_500_000,
               "delta_stock": 0, "achats_locaux": 1_043_548.387},
        2025: {"imports": 0, "imports_at": 3_300_000, "ca_decl": 0, "ca_export": 6_800_000, "ca_reel": 6_800_000,
               "delta_stock": 0, "achats_locaux": 1_087_096.774},
    },
    "remboursements": True,
}

MEDINA = {
    "cle": "medina",
    "raison_sociale": "Médina Trade SUARL",
    "forme": "SUARL", "gouvernorat": "Tunis", "delegation": "Médina",
    "secteur": "electromenager", "nat_code": "46.43",
    "date_creation": date(2020, 6, 22), "effectif": 1, "capital": 10_000,
    "categorie": "fraudeur", "schemas": ["F2"],
    "stock_initial": 60_000,
    "produit_principal": "85287200",
    "sous_evaluation": {"code_sh": "85287200", "pays": "Chine", "ratio": 0.45, "nb_declarations": {2024: 6, 2025: 14}},
    "annees": {
        2023: {"imports": 520_000, "ca_decl": 640_000, "ca_reel": 640_000, "delta_stock": 0, "achats_locaux": 4_590.164},
        2024: {"imports": 560_000, "ca_decl": 780_000, "ca_reel": 780_000, "delta_stock": 0, "achats_locaux": 79_344.262},
        2025: {"imports": 600_000, "ca_decl": 900_000, "ca_reel": 900_000, "delta_stock": 0, "achats_locaux": 137_704.918},
    },
}

# Carrousel : Carthage Négoce -> Atlas Services -> Yasmine Distribution -> Carthage Négoce (6 mois de 2025)
CARROUSEL = {
    "membres": [
        {"cle": "carthage", "raison_sociale": "Carthage Négoce SARL", "forme": "SARL", "gouvernorat": "Tunis",
         "delegation": "Bab Bhar", "secteur": "informatique", "nat_code": "46.51", "date_creation": date(2021, 1, 12),
         "effectif": 3, "capital": 30_000, "ca_annuel": 1_100_000},
        {"cle": "atlas", "raison_sociale": "Atlas Services SUARL", "forme": "SUARL", "gouvernorat": "Ariana",
         "delegation": "La Soukra", "secteur": "informatique", "nat_code": "46.51", "date_creation": date(2024, 10, 3),
         "effectif": 1, "capital": 5_000, "ca_annuel": 150_000, "maillon_manquant": True},
        {"cle": "yasmine", "raison_sociale": "Yasmine Distribution SARL", "forme": "SARL", "gouvernorat": "Ariana",
         "delegation": "La Soukra", "secteur": "telephonie", "nat_code": "46.52", "date_creation": date(2022, 7, 19),
         "effectif": 2, "capital": 20_000, "ca_annuel": 900_000},
    ],
    "annee": 2025, "mois": [3, 4, 5, 6, 7, 8],
    "montant_mensuel": 420_000,  # HT par arête du cycle
}

DEMO_SIMPLES = [SAHEL, CAP_BON, DJERBA, NOUR, MEDINA]
