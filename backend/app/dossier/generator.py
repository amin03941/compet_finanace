"""Générateur du pré-dossier de contrôle (T3). Étapes : collecte -> calcul -> articles -> rédaction.

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
from ..risk.features import Contexte
from ..risk.scoring import CATEGORIES
from . import calc
from .articles import articles_applicables

log = logging.getLogger("rasd.dossier")

DELAI_REPONSE_JOURS = 30

AVERTISSEMENTS = [
    "Document d'aide à la décision : l'agent reste seul décisionnaire.",
    "Les montants sont des estimations indicatives, à confirmer par la procédure contradictoire.",
    "Aucune sanction automatique : l'entreprise peut présenter ses explications et justificatifs.",
    "Le score mesure la probabilité qu'un contrôle soit utile, pas la culpabilité.",
    "Prototype — données entièrement fictives. Aucune donnée réelle d'entreprise ou de personne.",
]

DOCUMENTS = {  # pièce -> indices qui la justifient (None = toujours)
    "Grand livre et balance générale de l'exercice": None,
    "Inventaire des stocks au 31/12 (quantités et valorisation)": {"B1", "A3"},
    "Factures de vente de l'exercice et journal des ventes": {"A1", "A2", "B1", "B4", "B3"},
    "Liste nominative des clients et fournisseurs avec les montants (article 16 du CDPF)": {"A1", "A2", "B3", "C4"},
    "Relevés bancaires de tous les comptes, une fois la vérification approfondie ouverte (article 17 du CDPF)": {"B4", "A1", "A2", "B1", "A5"},
    "Déclarations en douane, factures des fournisseurs étrangers et justificatifs de paiement": {"A3", "B2", "C1"},
    "Justificatifs de la TVA déduite (factures d'achat, quittances de douane)": {"A3", "C3", "B3"},
    "Titres d'exportation et preuves de sortie des marchandises": {"A4"},
    "Registre des immobilisations et justificatifs d'affectation des équipements exonérés": {"C2"},
    "Déclarations de TVA manquantes et état des encaissements de la période": {"A5"},
}


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

SYSTEME = """Tu es rédacteur au service de contrôle fiscal. Tu rédiges en français administratif, sobre et précis.
Règles impératives :
- Tu ne calcules RIEN : tu reprends uniquement les montants fournis, exactement tels qu'ils sont écrits (ex. « 526 400 DT »).
- Tu ne cites que les articles de la liste fournie, sous la forme « article N du code des droits et procédures fiscaux ».
- Tu parles d'« indices » et d'« écarts à justifier », jamais de fraude avérée ni de culpabilité.
- La lettre est une DEMANDE DE JUSTIFICATION (procédure contradictoire), pas une notification de redressement : l'entreprise
  peut présenter ses explications et justificatifs dans le délai indiqué.
Réponds uniquement en JSON."""


def _documents(codes: set[str]) -> list[str]:
    return [d for d, c in DOCUMENTS.items() if c is None or codes & c]


def _prompt(entete: dict, calc_res: dict, indices: list[dict], articles: list[dict], documents: list[str]) -> str:
    donnees = {
        "entreprise": {k: entete[k] for k in ("raison_sociale", "matricule_fiscal", "adresse", "secteur")},
        "periode": entete["periode"],
        "categorie": entete["categorie_libelle"],
        "montants": {l["libelle"]: l["montant_affiche"] for l in calc_res["lignes"]},
        "total_tva_estimee": fmt.dt(calc_res["total_tva"]) if calc_res["total_tva"] else None,
        "total_estime": fmt.dt(calc_res["total_estime"]),
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


def rediger_llm(prompt: str) -> tuple[Redaction, str]:
    messages = [{"role": "system", "content": SYSTEME}, {"role": "user", "content": prompt}]
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


def rediger_secours(entete: dict, calc_res: dict, indices: list[dict], articles: list[dict], documents: list[str]) -> Redaction:
    """Rédaction déterministe (Ollama indisponible) : même structure, mêmes montants."""
    principal = indices[0]["phrase"] if indices else "Aucun indice déclenché."
    codes = ", ".join(i["code"] for i in indices) or "aucun"
    total = fmt.dt(calc_res["total_estime"])
    refs = ", ".join(str(a["article"]) for a in articles[:4])
    synthese = [
        f"{entete['raison_sociale']} ({entete['secteur']}, {entete['gouvernorat']}) : période examinée {entete['periode']}.",
        f"Faisceau d'indices issus de sources indépendantes : {codes}.",
        f"Constat principal : {principal}",
        f"Montant estimé en jeu : {total} (estimation indicative).",
        "Suite proposée : " + ("ouverture d'une vérification, après demande de justification." if entete["categorie"] == "rouge"
                               else "demande de justification adressée à l'entreprise."),
    ]
    ecarts = "\n".join(f"- {l['libelle']} : {l['montant_affiche']}" for l in calc_res["lignes"] if not l.get("indicatif"))
    pieces = "\n".join(f"- {d}" for d in documents)
    corps = (
        "Madame, Monsieur le représentant légal,\n\n"
        f"L'examen des informations dont dispose l'administration au titre de l'exercice {entete['periode']} fait apparaître "
        "des écarts entre vos déclarations et des données transmises par des tiers, que nous vous invitons à justifier :\n"
        f"{ecarts}\n\n"
        f"En application des textes en vigueur ({refs}), nous vous prions de bien vouloir nous communiquer les pièces suivantes :\n"
        f"{pieces}\n\n"
        f"Votre réponse, accompagnée des justificatifs, est attendue dans un délai de {DELAI_REPONSE_JOURS} jours à compter de la "
        "réception de la présente. Vous pouvez également présenter toutes observations utiles dans le cadre de la procédure "
        "contradictoire ; la présente demande ne préjuge pas des suites qui y seront données.\n\n"
        "Veuillez agréer, Madame, Monsieur, l'expression de nos salutations distinguées."
    )
    return Redaction(synthese=synthese, lettre=Lettre(objet=f"Demande de justification — exercice {entete['periode']}", corps=corps))


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
    calc_res = calc.calculer(ctx, eid, details["indices"], date.today())
    entete = {
        "raison_sociale": e.raison_sociale, "matricule_fiscal": e.matricule_fiscal, "forme_juridique": e.forme_juridique,
        "adresse": adresse.adresse.iloc[0] if len(adresse) else None, "gouvernorat": e.gouvernorat,
        "secteur": ctx.secteur_info(e.secteur_groupe).get("libelle"), "periode": str(calc_res["annee"]),
        "score": float(s.score), "categorie": s.categorie, "categorie_libelle": CATEGORIES[s.categorie],
        "montant_en_jeu": float(s.montant_en_jeu), "agent": agent, "statut": "brouillon",
        "date": fmt.date_fr(date.today()), "entreprise_id": int(eid),
    }

    yield etape("articles", "Recherche des articles applicables…")
    articles = articles_applicables(codes)
    documents = _documents(codes)

    yield etape("redaction", "Rédaction…")
    prompt = _prompt(entete, calc_res, indices, articles, documents)
    source, erreur = "modele_de_secours", None
    try:
        if not utiliser_llm:
            raise llm.LLMUnavailable("rédaction LLM désactivée")
        red, source = rediger_llm(prompt)
    except (llm.LLMUnavailable, ValueError) as exc:
        erreur = str(exc)
        log.warning("Rédaction de secours : %s", exc)
        red = rediger_secours(entete, calc_res, indices, articles, documents)
    autorises = calc.montants_autorises(calc_res)
    texte = " ".join(red.synthese) + " " + red.lettre.corps
    douteux = _chiffres_non_autorises(texte, autorises)
    if douteux and source != "modele_de_secours":  # un montant inventé : on ne garde pas la rédaction du LLM
        log.warning("Montants non issus de calc.py dans la rédaction : %s -> modèle de secours", douteux)
        red = rediger_secours(entete, calc_res, indices, articles, documents)
        source, erreur = "modele_de_secours", f"montants non vérifiés écartés : {', '.join(douteux)}"
    duree = round(time.perf_counter() - t0, 2)
    contenu = {
        "entete": entete, "synthese": red.synthese, "ecarts": calc_res,
        "indices": [{k: i[k] for k in ("code", "niveau", "libelle", "phrase", "montant_en_jeu", "annee", "annees")} for i in indices],
        "articles": articles, "documents": documents,
        "lettre": {"objet": red.lettre.objet, "corps": red.lettre.corps, "delai_jours": DELAI_REPONSE_JOURS,
                   "destinataire": f"Le représentant légal de {e.raison_sociale}"},
        "avertissements": AVERTISSEMENTS,
        "generation": {"source": source, "erreur": erreur, "duree_s": duree, "etapes": etapes,
                       "modele": config.LLM_MODEL if source.startswith("llm") else None},
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
    yield {"type": "dossier", "dossier": {"id": did, "statut": "brouillon", "contenu": contenu}}


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
    return {"id": int(r.id), "entreprise_id": int(r.entreprise_id), "statut": r.statut, "agent": r.agent,
            "contenu": json.loads(r.contenu), "cree_le": r.cree_le, "modifie_le": r.modifie_le, "valide_le": r.valide_le}


def modifier(did: int, maj: dict, agent: str) -> dict | None:
    d = lire(did)
    if d is None:
        return None
    c = d["contenu"]
    if d["statut"] == "valide" and maj.get("statut") != "brouillon":
        raise PermissionError("Dossier validé : repasser en brouillon pour le modifier")
    for cle in ("synthese", "documents"):
        if cle in maj and maj[cle] is not None:
            c[cle] = maj[cle]
    if maj.get("lettre"):
        c["lettre"].update({k: v for k, v in maj["lettre"].items() if k in ("objet", "corps")})
    if maj.get("agent"):
        c["entete"]["agent"] = maj["agent"]
    statut = maj.get("statut") or d["statut"]
    c["entete"]["statut"] = statut
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
