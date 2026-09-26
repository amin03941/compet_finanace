"""Catalogue des profils cachés : pièges honnêtes (écart brut expliqué) et schémas de fraude.

Ces profils ne servent QU'À générer les données et la vérité terrain (`ground_truth.csv`).
Ils ne sont jamais lus par le moteur de risque.
"""
from __future__ import annotations

# Répartition cible (section 5.1)
PART_HONNETE = 0.72
PART_PIEGE = 0.17
PART_FRAUDEUR = 0.11

# --- Pièges honnêtes : écart brut réel, mais expliqué ------------------------------
PIEGES: dict[str, dict] = {
    "stock": {
        "poids": 0.18,
        "explication": "Gros achats en fin d'année (nouvel entrepôt) : le stock final augmente fortement.",
        "secteurs": ("telephonie", "electromenager", "informatique", "pieces_auto", "materiaux", "textile_negoce", "pharma_para"),
    },
    "periode": {
        "poids": 0.15,
        "explication": "Décalage de période : marchandises importées en novembre-décembre et vendues l'année suivante.",
        "secteurs": ("telephonie", "electromenager", "informatique", "pieces_auto", "materiaux", "textile_negoce"),
    },
    "equipement": {
        "poids": 0.16,
        "explication": "Importations de machines (codes de l'annexe du décret 2017-419) qui ne sont pas revendues.",
        "secteurs": ("plasturgie", "agroalimentaire", "mecanique", "btp"),
    },
    "admission_temporaire": {
        "poids": 0.13,
        "explication": "Entreprise totalement exportatrice : intrants en admission temporaire puis réexportés.",
        "secteurs": ("textile_export", "cablage_auto"),
    },
    "export": {
        "poids": 0.13,
        "explication": "Ventes à l'export : le chiffre d'affaires local est faible mais les exportations en douane sont élevées.",
        "secteurs": ("plasturgie", "agroalimentaire", "mecanique", "textile_negoce"),
    },
    "donnees_manquantes": {
        "poids": 0.12,
        "explication": "Déclarations annuelles absentes : données insuffisantes, pas un risque élevé.",
        "secteurs": None,  # tous secteurs
    },
    "faible_marge": {
        "poids": 0.13,
        "explication": "Secteur à faible marge (distribution de gros, carburants) : importations proches du chiffre d'affaires.",
        "secteurs": ("distribution_alimentaire", "carburants"),
    },
}

# --- Schémas de fraude (section 5.3) -----------------------------------------------
FRAUDES: dict[str, dict] = {
    "F1": {"poids": 0.30, "libelle": "Minoration du chiffre d'affaires (vente au noir)", "motif": "minoration_ca",
           "secteurs": ("telephonie", "electromenager", "informatique", "pieces_auto", "materiaux", "textile_negoce",
                        "pharma_para", "distribution_alimentaire")},
    "F2": {"poids": 0.15, "libelle": "Sous-évaluation en douane", "motif": "sous_evaluation",
           "secteurs": ("telephonie", "electromenager", "informatique", "pieces_auto", "pharma_para", "textile_negoce")},
    "F3": {"poids": 0.14, "libelle": "TVA déductible gonflée ou fictive", "motif": "tva_deductible",
           "secteurs": ("telephonie", "electromenager", "informatique", "pieces_auto", "materiaux", "distribution_alimentaire",
                        "pharma_para", "btp")},
    "F4": {"poids": 0.05, "libelle": "Fausses factures / société écran", "motif": "fausses_factures",
           "secteurs": ("conseil", "transport", "materiaux")},
    "F5": {"poids": 0.07, "libelle": "Carrousel de TVA", "motif": "carrousel",
           "secteurs": ("telephonie", "informatique", "electromenager")},
    "F6": {"poids": 0.10, "libelle": "Fractionnement des déclarations", "motif": "fractionnement",
           "secteurs": ("telephonie", "electromenager", "informatique", "pieces_auto", "pharma_para")},
    "F7": {"poids": 0.09, "libelle": "Détournement d'avantages fiscaux", "motif": "avantages_fiscaux",
           "secteurs": ("plasturgie", "agroalimentaire", "mecanique", "btp")},
    "F8": {"poids": 0.10, "libelle": "Fausses exportations", "motif": "fausses_exportations",
           "secteurs": ("textile_negoce", "plasturgie", "agroalimentaire", "mecanique")},
}

# Combinaisons de 2 schémas (une entreprise peut en cumuler 2)
SECOND_SCHEMA = {"F1": ("F3",), "F2": ("F6",), "F3": ("F1",), "F6": ("F2",), "F7": ("F1",), "F8": ("F3",)}
PROBA_SECOND_SCHEMA = 0.25

LIBELLES_CATEGORIES = {
    "honnete": "Honnête cohérente",
    "honnete_ecart_explique": "Honnête avec écart brut expliqué (piège)",
    "fraudeur": "Fraudeur",
}
