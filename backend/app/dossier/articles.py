"""Articles applicables (section 7.2) : correspondance indices -> textes, retrouvés dans l'index RAG.

Chaque article cité correspond à un record réellement retrouvé (vérification par `id`), avec
l'extrait exact affiché. Aucun article n'est écrit « de mémoire ».
"""
from __future__ import annotations

from ..rag.index import get_index, strip_header
from ..rag.retriever import get_retriever

# (requête, motif, indices concernés ; None = tous les dossiers)
CORRESPONDANCES = [
    ("article 16 du code des droits et procédures fiscaux",
     "Droit de communication : demander la liste nominative des clients et fournisseurs (réponse sous trente jours).",
     {"A1", "A2", "B3", "C4"}),
    ("article 17 du code des droits et procédures fiscaux",
     "Communication des relevés bancaires, une fois la vérification approfondie ouverte.", {"B4", "A1", "A2", "B1", "A5"}),
    ("article 37 du code des droits et procédures fiscaux", "Vérification préliminaire des déclarations sur pièces.", None),
    ("article 40 du code des droits et procédures fiscaux", "Durée maximale de la vérification approfondie.", {"A1", "A2", "A3", "A4", "A5", "B1", "B3", "B4"}),
    ("article 47 du code des droits et procédures fiscaux", "Taxation d'office en cas de défaut de déclaration ou de comptabilité non probante.",
     {"A5", "B1", "B4"}),
    ("article 81 du code des droits et procédures fiscaux", "Pénalités de retard : 1,25 % par mois ou fraction de mois.", None),
    ("Quel est le tarif de transaction pour le non-dépôt d'une déclaration ?",
     "Sanctions pénales et tarif de transaction (annexe de l'arrêté du 8 janvier 2002).", {"A5"}),
    ("Quelles sanctions pour l'utilisation de factures fictives ou la déduction abusive de TVA ?",
     "Sanctions pénales en matière de factures (articles 89 à 105).", {"A3", "B3", "C2"}),
    ("Quelle valeur en douane retenir et quelles sanctions en cas de fausse déclaration de valeur des marchandises importées ?",
     "Valeur en douane et fausse déclaration (code des douanes, édition 2016).", {"B2", "C1"}),
    ("Équipements importés bénéficiant de l'exonération des droits de douane et de la réduction du taux de la TVA à 6 % "
     "nécessaires aux investissements",
     "Avantages fiscaux sur les équipements : conditions et retrait.", {"C2"}),
    ("Quelles conditions pour que le chiffre d'affaires à l'exportation soit exonéré et justifié ?",
     "Justification des exportations.", {"A4"}),
]


_CACHE: dict[str, object] = {}  # requêtes fixes sur un index en lecture seule : résultat mémorisé


def articles_applicables(codes: set[str], max_articles: int = 7) -> list[dict]:
    r = get_retriever()
    rag = get_index()
    vus, out = set(), []
    for requete, motif, concernes in CORRESPONDANCES:
        if concernes is not None and not (codes & concernes):
            continue
        if requete not in _CACHE:
            _CACHE[requete] = r.rechercher(requete, top_k=3)
        rech = _CACHE[requete]
        if not rech.resultats or rech.abstention:
            continue
        res = rech.resultats[0]
        rec = res.record
        if rec["id"] in vus or rag.get(rec["id"]) is None:  # vérification : le record existe dans l'index
            continue
        vus.add(rec["id"])
        texte = strip_header(rec.get("content", ""))
        out.append({
            "id": rec["id"], "document": rec.get("source_title"), "source_id": rec["source_id"],
            "article": rec.get("article_number") or rec.get("article_label") or (rec.get("section") or "").split(" > ")[-1],
            "section": rec.get("section"), "page": rec.get("pdf_page"), "locator": rec.get("locator"), "motif": motif,
            "extrait": texte, "recherche_directe": res.direct,
            "indices": sorted(codes & concernes) if concernes else [],
            "edition": "Code des douanes, édition 2016" if rec["source_id"] == "code_douanes_2016" else None,
        })
        if len(out) >= max_articles:
            break
    return out


