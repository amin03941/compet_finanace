"""Générateur du pré-dossier de contrôle (T3). Étapes : collecte -> calcul -> articles -> rédaction.

Le dossier est propre à l'administration compétente : fiscal (DGI), douanier (Douane) ou conjoint (deux parties
distinctes, chacune avec ses indices, ses montants, ses articles, ses pièces et sa lettre, plus une fiche de
transmission). Le type est déduit des indices déclenchés (rules.type_dossier).

Le LLM (sortie JSON structurée via Ollama `format`, validée par Pydantic, 1 relance) ne fait que
RÉDIGER la synthèse et la lettre à partir des montants de calc.py. Si Ollama est indisponible ou
échoue deux fois, un modèle de rédaction déterministe prend le relais : le dossier est toujours produit.
"""
from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterator
from datetime import date, datetime

from pydantic import BaseModel, Field, ValidationError

from .. import config, db, fmt, llm
from ..rag.index import get_index, strip_header
from ..risk.features import Contexte
from ..risk.rules import ADMINISTRATION, PARTIES_DOSSIER, REGLES_PAR_CODE, TYPES_DOSSIER, parties_indice, preuve_douaniere, \
    type_dossier
from ..risk.scoring import CATEGORIES
from . import calc
from .articles import CDPF, MOTIF_ORANGE, articles_applicables
from .journal import journaliser

log = logging.getLogger("rasd.dossier")

DELAI_REPONSE_JOURS = 30

AVERTISSEMENTS = [
    "Document d'aide à la décision : l'agent reste seul décisionnaire.",
    "Les montants sont des estimations indicatives, à confirmer par la procédure contradictoire.",
    "Aucune sanction automatique : l'entreprise peut présenter ses explications et justificatifs.",
    "Le score mesure la probabilité qu'un contrôle soit utile, pas la culpabilité.",
    "Prototype — données entièrement fictives. Aucune donnée réelle d'entreprise ou de personne.",
]

TITRES = {"fiscal": "Pré-dossier de contrôle fiscal", "douanier": "Pré-dossier de contrôle douanier",
          "conjoint": "Pré-dossier conjoint DGI – Douane"}
SERVICE_DOUANE = "Service du contrôle a posteriori"
PARTIES = {
    "dgi": {"administration": "DGI", "nom": "Direction générale des impôts", "code": "code des droits et procédures fiscaux",
            "redacteur": "rédacteur au service de contrôle fiscal de la Direction générale des impôts"},
    "douane": {"administration": "Douane", "nom": "Direction générale des douanes", "code": "code des douanes",
               "redacteur": "rédacteur au service du contrôle a posteriori de la Direction générale des douanes"},
}

# pièces à demander : pièce -> indices qui la justifient (None = toujours, pour cette administration)
DOCUMENTS = {
    "dgi": {
        "Grand livre et balance générale de l'exercice": None,
        "Inventaire des stocks au 31/12 (quantités et valorisation)": None,
        "Factures de vente de l'exercice et journal des ventes": None,
        "Liste nominative des clients et fournisseurs avec les montants (article 16 du CDPF)": None,
        "Relevés bancaires de tous les comptes de l'exercice": None,
        "Justificatifs de la TVA déduite (factures d'achat, quittances de douane)": {"A3", "C3", "B3"},
        "Titres d'exportation et preuves de sortie des marchandises": {"A4"},
        "Déclarations de TVA manquantes et état des encaissements de la période": {"A5"},
    },
    "douane": {  # pas de grand livre : la douane contrôle la valeur et l'origine des marchandises
        "Factures commerciales des fournisseurs étrangers": None,
        "Preuves de paiement au fournisseur étranger (ordres de virement, relevés)": None,
        "Contrat ou bon de commande": None,
        "Liste de prix (catalogue) du fournisseur": None,
        "Documents de transport (connaissement, lettre de transport)": None,
        "Certificat d'origine des marchandises": None,
        "Liste des déclarations en douane de la période avec les expéditions correspondantes": {"C1"},
        "Registre des immobilisations et justificatifs d'affectation des équipements exonérés": {"C2"},
    },
}

# fiches de transmission : pièces transmises selon l'indice
PIECES_DOUANE_VERS_DGI = {
    "A3": "Déclarations d'importation et quittances de TVA à l'import de l'exercice",
    "A4": "Déclarations d'exportation (titres de sortie) de l'exercice",
    "B1": "Déclarations d'importation mises à la consommation (valeurs, régimes, équipements)",
    "B2": "Déclarations d'importation sous-évaluées et référentiel de prix utilisé",
    "C1": "Liste des déclarations en douane fractionnées",
    "C2": "Déclarations d'importation d'équipements en exonération",
}
PIECES_DGI_VERS_DOUANE = {
    "A1": "Attestations de retenue à la source (TEJ) établies par les clients",
    "A2": "Factures électroniques émises (El Fatoora)",
    "A5": "État des déclarations de TVA non déposées",
    "B3": "Factures du circuit (El Fatoora)",
    "B4": "Encaissements bancaires agrégés",
    "C2": "Déclarations de TVA (ventes des équipements exonérés)",
    "C3": "Déclarations de TVA en crédit et demandes de remboursement",
}
MENTION_TRANSMISSION = "Transmission soumise au secret professionnel fiscal (article 15 du CDPF)."


class Lettre(BaseModel):
    objet: str = Field(min_length=10, max_length=300)
    corps: str = Field(min_length=200, max_length=4000)


class Redaction(BaseModel):
    synthese: list[str] = Field(min_length=3, max_length=6)
    lettre: Lettre


SCHEMA = {
    "type": "object",
    "properties": {
        "synthese": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 5},
        "lettre": {"type": "object", "properties": {"objet": {"type": "string"}, "corps": {"type": "string"}},
                   "required": ["objet", "corps"]},
    },
    "required": ["synthese", "lettre"],
}

SYSTEME = """Tu es {redacteur}. Tu rédiges en français administratif, sobre et précis.
Règles impératives :
- Tu ne calcules RIEN : tu reprends uniquement les montants fournis, exactement tels qu'ils sont écrits (ex. « 526 400 DT »).
- Tu ne cites que les articles de la liste fournie, sous la forme « article N du {code} ».
- Tu parles d'« indices » et d'« écarts à justifier », jamais de fraude avérée ni de culpabilité.
- La lettre est une DEMANDE DE JUSTIFICATION (procédure contradictoire), pas une notification de redressement : l'entreprise
  peut présenter ses explications et justificatifs dans le délai indiqué.
Réponds uniquement en JSON."""


def _documents(codes: set[str], partie: str) -> list[str]:
    return [d for d, c in DOCUMENTS[partie].items() if c is None or codes & c]


def _de_la_partie(partie: str, calc_res: dict, indices: list[dict], articles: list[dict]) -> tuple[list, list, list]:
    return ([l for l in calc_res["lignes"] if l.get("partie", "dgi") == partie],
            [i for i in indices if partie in i.get("parties", ["dgi"])],
            [a for a in articles if a.get("partie", "dgi") == partie])


def _prompt(entete: dict, calc_res: dict, indices: list[dict], articles: list[dict], documents: list[str],
            partie: str = "dgi") -> str:
    lignes, indices, articles = _de_la_partie(partie, calc_res, indices, articles)
    total = calc_res.get("total_douane" if partie == "douane" else "total_dgi", calc_res["total_estime"])
    donnees = {
        "administration_emettrice": PARTIES[partie]["nom"],
        "entreprise": {k: entete[k] for k in ("raison_sociale", "matricule_fiscal", "adresse", "secteur")},
        "periode": entete["periode"],
        "categorie": entete["categorie_libelle"],
        "montants": {l["libelle"]: l["montant_affiche"] for l in lignes},
        "total_en_jeu_pour_cette_administration": fmt.dt(total),
        "indices": [{"code": i["code"], "force": i["niveau"], "constat": i["phrase"]} for i in indices],
        "articles_autorises": [{"reference": f"{a['article']} ({a['document'][:60]})", "objet": a["motif"]} for a in articles],
        "pieces_a_demander": documents,
        "delai_de_reponse": f"{DELAI_REPONSE_JOURS} jours à compter de la réception de la lettre",
    }
    return (
        "Données du dossier (JSON) :\n" + json.dumps(donnees, ensure_ascii=False, indent=1) + "\n\n"
        "Rédige :\n"
        "1. « synthese » : exactement 5 phrases courtes (une par ligne) : qui, quels indices croisés, quel écart principal chiffré, "
        "quel montant estimé en jeu, quelle suite proposée (demande de justification ou vérification).\n"
        "2. « lettre » : « objet » (une ligne) et « corps » : lettre de demande de justification adressée au représentant légal "
        "de l'entreprise, qui expose les écarts constatés avec leurs montants, rappelle le fondement (articles autorisés), liste "
        "les pièces à fournir, fixe le délai de réponse, rappelle que l'entreprise peut présenter ses observations, et se termine "
        "par une formule de politesse administrative. Pas de signature nominative (le champ agent est ajouté ensuite)."
    )


def _chiffres_non_autorises(texte: str, autorises: set[str]) -> list[str]:
    """Montants de 4 chiffres ou plus présents dans la rédaction mais absents des calculs."""
    trouves = re.findall(r"\d{1,3}(?:[\s  ]\d{3})+(?:,\d+)?|\d{4,}", texte)
    out = []
    for t in trouves:
        norm = re.sub(r"[\s  ]", " ", t).split(",")[0]
        if norm.replace(" ", "").isdigit() and int(norm.replace(" ", "")) in (2023, 2024, 2025, 2026):
            continue
        if norm not in autorises and norm not in out:
            out.append(norm)
    return out


_NUM_ARTICLE = r"\d+(?:\s*(?:bis|ter|quater))?"
# « articles 16, 17 et 40 » / « articles 89 à 105 » : une liste. Au singulier, une liste seulement si elle se termine
# par « et N » ou « à N » (« l'article 37, 81 et 383 »), pour ne pas lire « article 16, 30 jours » comme deux articles.
_CITATION_ARTICLE = re.compile(
    rf"\barticles\s+({_NUM_ARTICLE}(?:\s*(?:,|et|à|-|–)\s*{_NUM_ARTICLE})*)"
    rf"|\barticle\s+({_NUM_ARTICLE}(?:(?:\s*,\s*{_NUM_ARTICLE})*\s*(?:et|à|-|–)\s*{_NUM_ARTICLE})?)", re.I)


def _norm_numero(n: str) -> str:
    return re.sub(r"\s+", " ", n.strip().lower())


def numeros_cites(texte: str) -> set[str]:
    out = set()
    for m in _CITATION_ARTICLE.finditer(texte):
        out.update(_norm_numero(n) for n in re.findall(_NUM_ARTICLE, m.group(1) or m.group(2), re.I))
    return out


def _articles_non_autorises(texte: str, articles: list[dict], documents: list[str]) -> list[str]:
    """Numéros d'articles cités dans la rédaction mais absents de la liste finale des articles du dossier.
    Les pièces à demander sont un texte fixe du code (elles peuvent rappeler l'article 16 ou 17) : leurs renvois sont admis."""
    autorises = {n for a in articles for n in re.findall(_NUM_ARTICLE, str(a.get("article") or ""), re.I)[:1]}
    autorises = {_norm_numero(n) for n in autorises} | numeros_cites(" ".join(documents))
    return sorted(numeros_cites(texte) - autorises, key=lambda n: (len(n), n))


def rediger_llm(prompt: str, partie: str = "dgi") -> tuple[Redaction, str]:
    systeme = SYSTEME.format(redacteur=PARTIES[partie]["redacteur"], code=PARTIES[partie]["code"])
    messages = [{"role": "system", "content": systeme}, {"role": "user", "content": prompt}]
    derniere_erreur = None
    for tentative in range(2):  # 1 relance en cas d'échec de validation
        if derniere_erreur:
            messages.append({"role": "user", "content": f"Ta réponse était invalide ({derniere_erreur}). Recommence en JSON valide."})
        brut = llm.chat(messages, fmt=SCHEMA, timeout=90, options={"num_predict": 1400})
        try:
            return Redaction.model_validate(json.loads(brut)), f"llm:{config.LLM_MODEL}" + (" (relance)" if tentative else "")
        except (json.JSONDecodeError, ValidationError) as exc:
            derniere_erreur = str(exc)[:300]
            messages.append({"role": "assistant", "content": brut[:2000]})
            log.warning("Rédaction invalide (tentative %d) : %s", tentative + 1, derniere_erreur)
    raise ValueError(f"Rédaction invalide après relance : {derniere_erreur}")


def rediger_secours(entete: dict, calc_res: dict, indices: list[dict], articles: list[dict], documents: list[str],
                    partie: str = "dgi") -> Redaction:
    """Rédaction déterministe (Ollama indisponible) : même structure, mêmes montants, propre à l'administration."""
    lignes, indices, articles = _de_la_partie(partie, calc_res, indices, articles)
    principal = indices[0]["phrase"] if indices else "Aucun indice déclenché."
    codes = ", ".join(i["code"] for i in indices) or "aucun"
    total = fmt.dt(calc_res.get("total_douane" if partie == "douane" else "total_dgi", calc_res["total_estime"]))
    refs = ", ".join(f"{a['article']} ({(a.get('document') or '').split(',')[0]})" for a in articles[:4])
    synthese = [
        f"{entete['raison_sociale']} ({entete['secteur']}, {entete['gouvernorat']}) : période examinée {entete['periode']}.",
        f"Faisceau d'indices issus de sources indépendantes : {codes}.",
        f"Constat principal : {principal}",
        f"Montant estimé en jeu : {total} (estimation indicative).",
        "Suite proposée : " + ("ouverture d'une vérification, après demande de justification." if entete["categorie"] == "rouge"
                               else "demande de justification adressée à l'entreprise."),
    ]
    ecarts = "\n".join(f"- {l['libelle']} : {l['montant_affiche']}" for l in lignes if not l.get("indicatif"))
    objet = "Demande de justification de la valeur déclarée en douane" if partie == "douane" else "Demande de justification"
    pieces = "\n".join(f"- {d}" for d in documents)
    corps = (
        "Madame, Monsieur le représentant légal,\n\n"
        f"L'examen des informations dont dispose la {PARTIES[partie]['nom']} au titre de l'exercice {entete['periode']} fait apparaître "
        "des écarts entre vos déclarations et des données transmises par des tiers, que nous vous invitons à justifier :\n"
        f"{ecarts}\n\n"
        f"En application des textes en vigueur{f' ({refs})' if refs else ''}, nous vous prions de bien vouloir nous communiquer les pièces suivantes :\n"
        f"{pieces}\n\n"
        f"Votre réponse, accompagnée des justificatifs, est attendue dans un délai de {DELAI_REPONSE_JOURS} jours à compter de la "
        "réception de la présente. Vous pouvez également présenter toutes observations utiles dans le cadre de la procédure "
        "contradictoire ; la présente demande ne préjuge pas des suites qui y seront données.\n\n"
        "Veuillez agréer, Madame, Monsieur, l'expression de nos salutations distinguées."
    )
    return Redaction(synthese=synthese, lettre=Lettre(objet=f"{objet} — exercice {entete['periode']}", corps=corps))


def generer_flux(ctx: Contexte, eid: int, agent: str = "agent.demo", utiliser_llm: bool = True) -> Iterator[dict]:
    """Événements d'avancement (pour l'animation) puis le dossier enregistré."""
    t0 = time.perf_counter()
    etapes = []

    def etape(nom: str, libelle: str):
        etapes.append({"etape": nom, "libelle": libelle, "t": round(time.perf_counter() - t0, 2)})
        return {"type": "etape", "etape": nom, "libelle": libelle}

    yield etape("collecte", "Collecte des données…")
    sc = db.read_sql("SELECT * FROM scores WHERE entreprise_id = :e", {"e": eid})
    if sc.empty:
        yield {"type": "erreur", "message": "Entreprise non scorée"}
        return
    s = sc.iloc[0]
    details = json.loads(s.details)
    e = ctx.ent.loc[eid]
    adresse = db.read_sql("SELECT adresse FROM adresses WHERE id = :a", {"a": int(e.adresse_id)})
    indices = [i for i in details["indices"] if i["declenchee"]]
    indices.sort(key=lambda i: ("ABC".index(i["niveau"]), -i["montant_en_jeu"]))
    codes = {i["code"] for i in indices}

    yield etape("calcul", "Calcul des écarts…")
    type_ = type_dossier(codes) or "fiscal"
    parties = PARTIES_DOSSIER[type_]
    for i in indices:
        i["administration"] = ADMINISTRATION.get(i["code"], "neutre")
        i["parties"] = parties_indice(i["code"], type_)
    calc_res = calc.calculer(ctx, eid, details["indices"], date.today())
    entete = {
        "raison_sociale": e.raison_sociale, "matricule_fiscal": e.matricule_fiscal, "forme_juridique": e.forme_juridique,
        "adresse": adresse.adresse.iloc[0] if len(adresse) else None, "gouvernorat": e.gouvernorat,
        "secteur": ctx.secteur_info(e.secteur_groupe).get("libelle"), "periode": str(calc_res["annee"]),
        "score": float(s.score), "categorie": s.categorie, "categorie_libelle": CATEGORIES[s.categorie],
        "montant_en_jeu": float(s.montant_en_jeu), "agent": agent, "statut": "brouillon",
        "date": fmt.date_fr(date.today()), "entreprise_id": int(eid),
        "type_dossier": type_, "type_libelle": TYPES_DOSSIER[type_], "titre": TITRES[type_], "parties": parties,
        "preuve_douaniere": preuve_douaniere(codes),
        "destinataires": [_destinataire(p, e) for p in parties],
    }

    yield etape("articles", "Recherche des articles applicables…")
    articles = articles_applicables(codes, s.categorie, parties, penalites=calc_res["penalites_indicatives"] > 0)
    documents = {p: _documents(codes, p) for p in parties}
    notes = {"dgi": MOTIF_ORANGE + " Les articles 40 et 17 ne sont donc pas cités."} if "dgi" in parties and s.categorie != "rouge" else {}

    yield etape("redaction", "Rédaction…")
    lettres, sources, erreurs, synthese = {}, {}, {}, None
    for p in parties:
        red, source, erreur = rediger(entete, calc_res, indices, articles, documents[p], utiliser_llm, partie=p)
        lettres[p] = _lettre(red, p, e, [a["id"] for a in articles if a["partie"] == p], source, erreur)
        sources[p], erreurs[p] = source, erreur
        synthese = synthese or red.synthese
    if type_ == "conjoint":
        synthese = _synthese_conjointe(entete, calc_res, indices)
    source = next(iter(sources.values()))
    duree = round(time.perf_counter() - t0, 2)
    contenu = {
        "entete": entete, "synthese": synthese, "ecarts": calc_res,
        "indices": [{k: i[k] for k in ("code", "niveau", "libelle", "phrase", "montant_en_jeu", "annee", "annees", "administration",
                                       "parties")} for i in indices],
        "articles": articles, "articles_ecartes": [], "articles_modifies": False, "notes_articles": notes, "documents": documents,
        "lettres": lettres, "transmissions": _transmissions(type_, codes, entete, agent),
        "avertissements": AVERTISSEMENTS,
        "generation": {"source": source, "sources": sources, "erreur": "; ".join(x for x in erreurs.values() if x) or None,
                       "duree_s": duree, "etapes": etapes,
                       "modele": config.LLM_MODEL if any(x.startswith("llm") for x in sources.values()) else None},
    }
    maintenant = datetime.now().isoformat(timespec="seconds")
    with db.get_engine().begin() as conn:
        res = conn.execute(db.dossiers.insert().values(entreprise_id=int(eid), statut="brouillon", agent=agent,
                                                       contenu=json.dumps(contenu, ensure_ascii=False),
                                                       modele_llm=contenu["generation"]["modele"], duree_generation_s=duree,
                                                       cree_le=maintenant, modifie_le=maintenant))
        did = int(res.inserted_primary_key[0])
    contenu["entete"]["reference"] = f"RASD-{date.today().year}-{did:06d}"
    with db.get_engine().begin() as conn:
        conn.execute(db.dossiers.update().where(db.dossiers.c.id == did).values(contenu=json.dumps(contenu, ensure_ascii=False)))
    journaliser(did, "generation", agent, motif=f"Dossier {TYPES_DOSSIER[type_].lower()} ; rédaction : "
                                                + ", ".join(f"{PARTIES[p]['administration']} {v}" for p, v in sources.items()))
    yield {"type": "dossier", "dossier": lire(did)}


def _destinataire(partie: str, e) -> dict:
    service = (e.bureau_controle if partie == "dgi" else SERVICE_DOUANE)
    return {"partie": partie, "administration": PARTIES[partie]["administration"], "nom": PARTIES[partie]["nom"], "service": service}


def _lettre(red: Redaction, partie: str, e, articles_ids: list[str], source: str, erreur: str | None) -> dict:
    return {"objet": red.lettre.objet, "corps": red.lettre.corps, "delai_jours": DELAI_REPONSE_JOURS, "partie": partie,
            "emetteur": PARTIES[partie]["nom"], "destinataire": f"Le représentant légal de {e.raison_sociale}",
            "articles_ids": articles_ids, "source": source, "erreur": erreur}


def _synthese_conjointe(entete: dict, calc_res: dict, indices: list[dict]) -> list[str]:
    codes = {p: ", ".join(i["code"] for i in indices if p in i["parties"] and i["administration"] != "neutre") or "—"
             for p in ("dgi", "douane")}
    return [
        f"{entete['raison_sociale']} ({entete['secteur']}, {entete['gouvernorat']}) : période examinée {entete['periode']} ; "
        "dossier conjoint DGI – Douane.",
        f"Partie DGI : indices {codes['dgi']} ; impôts en jeu {fmt.dt(calc_res['total_dgi'])}.",
        f"Partie Douane : indices {codes['douane']} ; droits et taxes en jeu {fmt.dt(calc_res['total_douane'])}.",
        f"Montant total estimé : {fmt.dt(calc_res['total_estime'])} (estimation indicative).",
        "Suite proposée : une demande de justification par administration, et transmission des éléments utiles entre la DGI et la Douane.",
    ]


def _base_legale(article: int) -> dict:
    """Base légale de la transmission, avec l'extrait exact de l'index (article 16 : Douane -> DGI ; 15 : DGI -> Douane)."""
    rid = CDPF.format(article)
    rec = get_index().get(rid)
    texte = strip_header(rec.get("content", "")) if rec else ""
    if article == 15 and "Est également exclu" in texte:  # paragraphe sur la communication aux autorités et organismes publics
        texte = texte[texte.index("Est également exclu"):]
    return {"article": f"Article {article}", "document": "Code des droits et procédures fiscaux", "record_id": rid, "extrait": texte}


def _transmissions(type_: str, codes: set[str], entete: dict, agent: str) -> list[dict]:
    """Fiches de transmission entre administrations (dossier conjoint, ou fiscal fondé sur une preuve douanière)."""
    fiches = []
    commun = {"entreprise": {"raison_sociale": entete["raison_sociale"], "matricule_fiscal": entete["matricule_fiscal"]},
              "date": entete["date"], "agent": agent, "mention": MENTION_TRANSMISSION}
    dgi = next((d for d in entete["destinataires"] if d["partie"] == "dgi"), None)
    service_dgi = dgi["service"] if dgi else "Centre de contrôle des impôts"
    if type_ in ("fiscal", "conjoint") and (entete["preuve_douaniere"] or type_ == "conjoint"):
        c = sorted(x for x in codes if ADMINISTRATION.get(x) in ("dgi_preuve_douane", "douane", "deux"))
        fiches.append({"sens": "douane_vers_dgi", "emetteur": f"Douane — {SERVICE_DOUANE}", "destinataire": f"DGI — {service_dgi}",
                       "indices": [{"code": x, "libelle": REGLES_PAR_CODE[x].libelle} for x in c],
                       "pieces": [PIECES_DOUANE_VERS_DGI[x] for x in c if x in PIECES_DOUANE_VERS_DGI],
                       "base_legale": _base_legale(16), **commun})
    if type_ == "conjoint":
        c = sorted(x for x in codes if ADMINISTRATION.get(x) in ("dgi", "dgi_preuve_douane", "deux"))
        pieces = ["Déclarations de TVA et chiffre d'affaires déclaré de l'exercice"] + \
                 [PIECES_DGI_VERS_DOUANE[x] for x in c if x in PIECES_DGI_VERS_DOUANE]
        fiches.append({"sens": "dgi_vers_douane", "emetteur": f"DGI — {service_dgi}", "destinataire": f"Douane — {SERVICE_DOUANE}",
                       "indices": [{"code": x, "libelle": REGLES_PAR_CODE[x].libelle} for x in c], "pieces": pieces,
                       "base_legale": _base_legale(15), **commun})
    return fiches


def rediger(entete: dict, calc_res: dict, indices: list[dict], articles: list[dict], documents: list[str],
            utiliser_llm: bool = True, partie: str = "dgi") -> tuple[Redaction, str, str | None]:
    """Synthèse et lettre d'UNE administration, à partir de la liste FINALE de ses articles. Montants et articles cités
    sont contrôlés : au moindre écart, la rédaction du LLM est écartée au profit du modèle déterministe."""
    source, erreur = "modele_de_secours", None
    try:
        if not utiliser_llm:
            raise llm.LLMUnavailable("rédaction LLM désactivée")
        red, source = rediger_llm(_prompt(entete, calc_res, indices, articles, documents, partie), partie)
    except (llm.LLMUnavailable, ValueError) as exc:
        erreur = str(exc)
        log.warning("Rédaction de secours : %s", exc)
        red = rediger_secours(entete, calc_res, indices, articles, documents, partie)
    texte = " ".join(red.synthese) + " " + red.lettre.corps
    douteux = _chiffres_non_autorises(texte, calc.montants_autorises(calc_res))
    hors_liste = _articles_non_autorises(texte, [a for a in articles if a.get("partie", "dgi") == partie], documents)
    if (douteux or hors_liste) and source != "modele_de_secours":  # un montant ou un article inventé : rédaction écartée
        log.warning("Rédaction du LLM écartée (montants %s, articles %s) -> modèle de secours", douteux, hors_liste)
        red = rediger_secours(entete, calc_res, indices, articles, documents, partie)
        motifs = ([f"montants non vérifiés écartés : {', '.join(douteux)}"] if douteux else []) + \
                 ([f"articles hors liste écartés : {', '.join(hors_liste)}"] if hors_liste else [])
        source, erreur = "modele_de_secours", " ; ".join(motifs)
    return red, source, erreur


def generer(ctx: Contexte, eid: int, agent: str = "agent.demo", utiliser_llm: bool = True) -> dict:
    out = None
    for ev in generer_flux(ctx, eid, agent, utiliser_llm):
        if ev["type"] == "dossier":
            out = ev["dossier"]
        elif ev["type"] == "erreur":
            raise ValueError(ev["message"])
    return out


def lire(did: int) -> dict | None:
    df = db.read_sql("SELECT * FROM dossiers WHERE id = :d", {"d": did})
    if df.empty:
        return None
    r = df.iloc[0]
    contenu = normaliser(json.loads(r.contenu))
    return {"id": int(r.id), "entreprise_id": int(r.entreprise_id), "statut": r.statut, "agent": r.agent,
            "contenu": contenu, "cree_le": r.cree_le, "modifie_le": r.modifie_le, "valide_le": r.valide_le,
            "etat_articles": etat_articles(contenu)}


def normaliser(c: dict) -> dict:
    """Valeurs par défaut pour les dossiers générés avant l'édition des articles et la séparation DGI / Douane."""
    e = c["entete"]
    e.setdefault("type_dossier", "fiscal")
    e.setdefault("type_libelle", TYPES_DOSSIER[e["type_dossier"]])
    e.setdefault("titre", TITRES[e["type_dossier"]])
    e.setdefault("parties", PARTIES_DOSSIER[e["type_dossier"]])
    e.setdefault("preuve_douaniere", False)
    e.setdefault("destinataires", [{"partie": p, "administration": PARTIES[p]["administration"], "nom": PARTIES[p]["nom"],
                                    "service": PARTIES[p]["nom"]} for p in e["parties"]])
    for a in c.get("articles", []) + c.get("articles_ecartes", []):
        a.setdefault("origine", "systeme")
        a.setdefault("suggestion", a["origine"] == "systeme" and not a.get("recherche_directe", True))
        a.setdefault("partie", e["parties"][0])
    for i in c.get("indices", []):
        i.setdefault("administration", ADMINISTRATION.get(i["code"], "neutre"))
        i.setdefault("parties", parties_indice(i["code"], e["type_dossier"]))
    for l in c["ecarts"].get("lignes", []):
        l.setdefault("partie", e["parties"][0])
    c.setdefault("articles_ecartes", [])
    c.setdefault("articles_modifies", False)
    c.setdefault("notes_articles", {})
    c.setdefault("transmissions", [])
    if isinstance(c.get("documents"), list):
        c["documents"] = {e["parties"][0]: c["documents"]}
    if "lettres" not in c:
        ancienne = c.pop("lettre")
        ancienne.setdefault("articles_ids", [a["id"] for a in c.get("articles", [])])
        ancienne.setdefault("partie", e["parties"][0])
        c["lettres"] = {e["parties"][0]: ancienne}
    return c


def etat_articles(c: dict) -> dict:
    """Cohérence entre la liste finale des articles de chaque administration et sa lettre (affichée au-dessus de la lettre)."""
    par = {}
    for p, lettre in c["lettres"].items():
        arts = [a for a in c["articles"] if a.get("partie") == p]
        par[p] = {"lettre_a_regenerer": sorted(a["id"] for a in arts) != sorted(lettre.get("articles_ids") or []),
                  "articles_hors_liste": _articles_non_autorises(lettre["corps"], arts, c["documents"].get(p, []))}
    return {"par_partie": par, "lettre_a_regenerer": any(x["lettre_a_regenerer"] for x in par.values()),
            "articles_hors_liste_lettre": sorted({n for x in par.values() for n in x["articles_hors_liste"]}, key=lambda n: (len(n), n))}


def modifier(did: int, maj: dict, agent: str) -> dict | None:
    d = lire(did)
    if d is None:
        return None
    c = d["contenu"]
    if d["statut"] == "valide" and maj.get("statut") != "brouillon":
        raise PermissionError("Dossier validé : repasser en brouillon pour le modifier")
    if maj.get("synthese") is not None:
        c["synthese"] = maj["synthese"]
    for p, docs in (maj.get("documents") or {}).items():
        if p in c["documents"]:
            c["documents"][p] = docs
    for p, lettre in (maj.get("lettres") or {}).items():
        if p in c["lettres"]:
            c["lettres"][p].update({k: v for k, v in lettre.items() if k in ("objet", "corps")})
    if maj.get("agent"):
        c["entete"]["agent"] = maj["agent"]
    statut = maj.get("statut") or d["statut"]
    c["entete"]["statut"] = statut
    if statut != d["statut"]:
        journaliser(did, "validation" if statut == "valide" else "retour_brouillon", agent)
    maintenant = datetime.now().isoformat(timespec="seconds")
    valeurs = {"contenu": json.dumps(c, ensure_ascii=False), "modifie_le": maintenant, "statut": statut,
               "agent": maj.get("agent") or d["agent"]}
    if statut == "valide" and d["statut"] != "valide":
        valeurs["valide_le"] = maintenant
    with db.get_engine().begin() as conn:
        conn.execute(db.dossiers.update().where(db.dossiers.c.id == did).values(**valeurs))
    return lire(did)


def lister(entreprise_id: int | None = None) -> list[dict]:
    q = "SELECT d.id, d.entreprise_id, d.statut, d.agent, d.cree_le, d.modifie_le, e.raison_sociale FROM dossiers d " \
        "JOIN entreprises e ON e.id = d.entreprise_id"
    params = {}
    if entreprise_id:
        q += " WHERE d.entreprise_id = :e"
        params["e"] = entreprise_id
    return db.read_sql(q + " ORDER BY d.id DESC", params).to_dict("records")
