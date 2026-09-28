"""Articles applicables (section 7.2), propres à chaque administration.

- Partie DGI : articles du code des droits et procédures fiscaux (CDPF), figés par identifiant de record.
- Partie Douane : articles du code des douanes (loi n° 2008-34), figés par identifiant de record ; aucun article du CDPF.
- Quelques entrées restent des recherches dans l'index (« suggestion automatique, à vérifier »).

Chaque article cité correspond à un record réellement présent dans l'index, avec l'extrait exact affiché.
Aucun article n'est écrit « de mémoire ».
"""
from __future__ import annotations

from ..rag.index import get_index, strip_header
from ..rag.retriever import get_retriever

CDPF = "cdpf_2024__code_des_droits_et_procedures_fiscaux_article_{}"
# Code des douanes, loi n° 2008-34 du 2 juin 2008 (plusieurs textes ont un « Article 35 » : on retient celui de la
# section « Valeur en douane des marchandises »)
DOUANE_23, DOUANE_35, DOUANE_383 = "a61ad2a80721_00057", "c608f05f9996_00086", "673500401284_00685"

TOUTES = ("rouge", "orange", "gris")
ROUGE = ("rouge",)

# (partie, record figé, motif, indices concernés ou None pour tous, catégories)
FIGES = [
    ("dgi", CDPF.format(37), "Vérification préliminaire des déclarations sur pièces.", None, TOUTES),
    ("dgi", CDPF.format(16),
     "Droit de communication : demander la liste nominative des clients et fournisseurs (réponse sous trente jours).", None, TOUTES),
    ("dgi", CDPF.format(40), "Vérification approfondie de la situation fiscale : déroulement et durée maximale.", None, ROUGE),
    ("dgi", CDPF.format(17), "Communication des numéros de comptes bancaires par les banques, sur demande écrite de l'administration.",
     None, ROUGE),
    ("dgi", CDPF.format(47), "Taxation d'office en cas de désaccord ou de défaut de déclaration.", None, ROUGE),
    ("dgi", CDPF.format(89), "Sanction du défaut de dépôt de déclaration dans les délais.", {"A5"}, ROUGE),
    ("dgi", CDPF.format(94), "Sanctions pénales : ventes sans facture, factures minorées ou fictives.", {"A1", "B3"}, ROUGE),
    ("douane", DOUANE_23, "La valeur en douane est la valeur transactionnelle : le prix effectivement payé ou à payer.", None, TOUTES),
    ("douane", DOUANE_35, "Doute sur la valeur transactionnelle : la douane peut demander des justificatifs complémentaires ; "
                          "à défaut, la valeur déclarée peut être écartée.", None, TOUTES),
    ("douane", DOUANE_383, "Paragraphe 2 : fausse déclaration dans l'espèce, la valeur ou l'origine avec droits éludés : "
                           "confiscation et amende de 200 à 3 000 DT.", None, ROUGE),
]
PENALITES = ("dgi", CDPF.format(81), "Pénalités de retard : 1,25 % par mois ou fraction de mois.")

# Suggestions par recherche dans l'index (partie, requête, motif, indices concernés)
SUGGESTIONS = [
    ("dgi", "Quelles conditions pour que le chiffre d'affaires à l'exportation soit exonéré et justifié ?",
     "Justification des exportations.", {"A4"}),
    ("douane", "Fractionnement des déclarations en douane et des envois pour rester sous les seuils de contrôle",
     "Fractionnement des déclarations en douane.", {"C1"}),
    ("douane", "Équipements importés bénéficiant de l'exonération des droits de douane et de la réduction du taux de la TVA à 6 % "
               "nécessaires aux investissements",
     "Avantages fiscaux sur les équipements : conditions et retrait.", {"C2"}),
]

MOTIF_ORANGE = "Un dossier orange est une demande de justification : aucune vérification n'est encore ouverte."

_CACHE: dict[str, object] = {}  # requêtes fixes sur un index en lecture seule : résultat mémorisé


def articles_applicables(codes: set[str], categorie: str = "orange", parties: list[str] | None = None,
                         penalites: bool = False, max_par_partie: int = 8) -> list[dict]:
    """Liste des articles d'un dossier : par partie (DGI, Douane), selon la catégorie et les indices déclenchés.
    L'article 81 n'est cité que si des pénalités de retard sont réellement calculées."""
    parties = parties or ["dgi"]
    rag = get_index()
    out: list[dict] = []
    vus: set[str] = set()
    for partie in parties:
        n = 0
        entrees = [e for e in FIGES if e[0] == partie]
        if partie == "dgi" and penalites:
            entrees.append((*PENALITES, None, TOUTES))
        for _, rid, motif, concernes, categories in entrees:
            if categorie not in categories or (concernes is not None and not (codes & concernes)) or rid in vus:
                continue
            rec = rag.get(rid)
            if rec is None:  # record figé introuvable : on ne cite rien plutôt que d'inventer
                continue
            vus.add(rid)
            out.append(article_depuis_record(rec, motif, origine="systeme", partie=partie,
                                             indices=sorted(codes & concernes) if concernes else []))
            n += 1
        for partie_s, requete, motif, concernes in SUGGESTIONS:
            if partie_s != partie or not (codes & concernes) or n >= max_par_partie:
                continue
            if requete not in _CACHE:
                _CACHE[requete] = get_retriever().rechercher(requete, top_k=3)
            rech = _CACHE[requete]
            if not rech.resultats or rech.abstention:
                continue
            res = rech.resultats[0]
            rec = res.record
            if rec["id"] in vus or rag.get(rec["id"]) is None:
                continue
            if partie == "douane" and rec["source_id"] == "cdpf_2024":  # jamais de CDPF dans la partie douane
                continue
            vus.add(rec["id"])
            a = article_depuis_record(rec, motif, origine="systeme", partie=partie, indices=sorted(codes & concernes))
            a.update({"recherche_directe": False, "suggestion": True})
            out.append(a)
            n += 1
    return out


def article_depuis_record(rec: dict, motif: str, origine: str, partie: str = "dgi", indices: list[str] | None = None) -> dict:
    """Entrée « article » d'un dossier, construite uniquement à partir d'un record existant de l'index."""
    return {
        "id": rec["id"], "document": rec.get("source_title"), "source_id": rec["source_id"],
        "article": rec.get("article_number") or rec.get("article_label") or (rec.get("section") or "").split(" > ")[-1],
        "section": rec.get("section"), "page": rec.get("pdf_page"), "locator": rec.get("locator"), "motif": motif,
        "extrait": strip_header(rec.get("content", "")), "recherche_directe": True, "suggestion": False,
        "indices": indices or [], "origine": origine, "partie": partie,
        "edition": "Code des douanes, édition 2016" if rec["source_id"] == "code_douanes_2016" else None,
    }
