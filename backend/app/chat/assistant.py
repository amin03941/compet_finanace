"""Assistant réglementaire (T9) : répond en français, en arabe ou en dialecte tunisien, en citant
l'article exact et son texte. Le LLM ne répond qu'à partir des extraits retrouvés.
"""
from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterator

from .. import llm
from ..rag.retriever import Recherche, expansion_lexicale, get_retriever, tokeniser

log = logging.getLogger("rasd.assistant")

N_EXTRAITS_LLM = 8
LONGUEUR_EXTRAIT = 1000
DISCLAIMER = {"fr": "Information, pas un conseil juridique.", "ar": "معلومة وليست استشارة قانونية.",
              "tn": "هذي معلومة موش استشارة قانونية."}
ABSTENTION = {
    "fr": "Je n'ai pas trouvé de texte applicable dans la base.",
    "ar": "لم أجد نصًا منطبقًا في قاعدة النصوص.",
    "tn": "ما لقيتش نص ينطبق على سؤالك في قاعدة النصوص.",
}
LLM_INDISPONIBLE = "Le modèle de langage local (Ollama) ne répond pas : les sources retrouvées sont affichées ci-contre, mais aucune réponse rédigée n'a pu être produite."
SUGGESTIONS_DEFAUT = [
    "Dans quel délai dois-je communiquer la liste de mes clients et fournisseurs à l'administration fiscale ?",
    "Quelle est la durée maximale d'une vérification approfondie ?",
    "Quel est le taux de la pénalité de retard de paiement de l'impôt ?",
]

# Questions d'exemple par mode : Amel (contribuable, gérante de PME) et Sami (agent vérificateur)
EXEMPLES = [
    {"question": "Le fisc me demande la liste de mes clients, je suis obligée ? En combien de temps ?", "langue": "fr",
     "mode": "contribuable", "persona": "Amel, gérante d'une PME"},
    {"question": "الجباية طلبت مني قائمة الحرفاء متاعي، لازم نعطيهالهم؟ وقداش عندي من وقت؟", "langue": "tn",
     "mode": "contribuable", "persona": "Amel, en dialecte"},
    {"question": "J'ai payé mon impôt en retard, combien de pénalités je vais payer ?", "langue": "fr",
     "mode": "contribuable", "persona": "Amel, gérante d'une PME"},
    {"question": "Un contrôleur peut-il venir vérifier ma comptabilité sans me prévenir ?", "langue": "fr",
     "mode": "contribuable", "persona": "Amel, gérante d'une PME"},
    {"question": "Mon entreprise importe et exporte beaucoup : comment obtenir le statut d'opérateur économique agréé ?", "langue": "fr",
     "mode": "contribuable", "persona": "Amel, gérante d'une PME"},
    {"question": "Quelle est la durée maximale d'une vérification approfondie de la situation fiscale ?", "langue": "fr",
     "mode": "agent", "persona": "Sami, vérificateur"},
    {"question": "Les banques doivent-elles présenter les relevés de comptes lors d'une vérification fiscale ?", "langue": "fr",
     "mode": "agent", "persona": "Sami, vérificateur"},
    {"question": "Dans quels cas la taxation d'office est-elle établie ?", "langue": "fr", "mode": "agent", "persona": "Sami, vérificateur"},
    {"question": "Quel est le tarif de transaction pour le non-dépôt d'une déclaration ?", "langue": "fr",
     "mode": "agent", "persona": "Sami, vérificateur"},
    {"question": "ما هي الحالات التي يتم فيها التوظيف الإجباري للضريبة؟", "langue": "ar", "mode": "agent", "persona": "Sami, en arabe"},
]

SYSTEME = """Tu es l'assistant réglementaire de RASD 360, un prototype de l'administration fiscale et douanière tunisienne.
Règles impératives :
1. Réponds UNIQUEMENT à partir des extraits numérotés fournis. N'utilise jamais tes connaissances générales.
2. Chaque affirmation cite sa source entre crochets, par exemple [1] ou [2][3]. Ne cite que les numéros d'extraits fournis.
3. Si les extraits ne permettent pas de répondre, dis-le clairement et n'invente rien. Ne donne JAMAIS un taux, un montant ou un délai qui ne figure pas explicitement dans un extrait.
4. Le Code des douanes de la base est l'édition 2016 : précise-le si tu t'appuies sur lui. Le Code de la TVA et le Code de l'IRPP et de l'IS ne sont pas encore dans la base : si la question porte sur ces impôts (taux de TVA, impôt sur le revenu ou sur les sociétés), dis que ces codes ne sont pas encore couverts.
5. Structure : une réponse courte (1 à 2 phrases), puis une section « Détails » avec les points utiles (conditions, délais, exceptions), chacun cité.
6. N'ajoute pas de liste de sources à la fin : elles sont affichées à côté de ta réponse.
7. Termine par la phrase : « {disclaimer} »"""

MODES = {
    "contribuable": "Public : un contribuable (chef d'entreprise, commerçant). Langage simple, sans jargon, avec des étapes concrètes : que faire, dans quel délai, quels documents. Explique aussi ses droits.",
    "agent": "Public : un agent de l'administration fiscale ou douanière. Réponse technique et précise : articles, alinéas, conditions exactes, exceptions et renvois entre textes.",
}
LANGUES = {
    "fr": "Rédige toute ta réponse en français.",
    "ar": "اكتب إجابتك كاملة باللغة العربية الفصحى. Garde les numéros de sources [n] et les numéros d'articles tels quels. Traduis le titre « Détails » en « التفاصيل ».",
    "tn": "اكتب إجابتك كاملة بالدارجة التونسية بالحروف العربية، بأسلوب بسيط وقريب من الناس. Garde les numéros de sources [n] et les numéros d'articles tels quels. Le titre « Détails » devient « التفاصيل ».",
}

SYSTEME_REFORMULATION = """Tu transformes la question d'un usager (en français, en arabe ou en dialecte tunisien) en UNE question en français juridique, courte et fidèle, pour une recherche dans les codes fiscaux et douaniers tunisiens. Remplace le langage familier par les termes juridiques exacts, n'ajoute AUCUNE notion absente de la question et ne réponds pas.
Exemples :
- « le contrôleur peut débarquer chez moi sans prévenir ? » -> « L'administration fiscale doit-elle adresser un avis préalable avant une vérification fiscale ? »
- « j'ai déclaré en retard, je paie combien d'amende ? » -> « Quelle sanction s'applique en cas de dépôt tardif d'une déclaration fiscale ? »
- « الديوانة حجزتلي السلعة، شنوة نعمل؟ » -> « Quels sont les recours du déclarant en cas de saisie de marchandises par la douane ? »"""

SCHEMA_REFORMULATION = {
    "type": "object",
    "properties": {"reformulation": {"type": "string"}, "sujet_couvert": {"type": "boolean"}},
    "required": ["reformulation", "sujet_couvert"],
}


def reformuler(question: str, historique: list[dict] | None = None) -> str | None:
    """Reformule la question (toute langue) en français juridique pour la recherche ; garde le sens."""
    contexte = ""
    if historique:
        derniers = [f"{m['role']}: {m['content'][:300]}" for m in historique[-4:]]
        contexte = "Échanges précédents (pour résoudre les références) :\n" + "\n".join(derniers) + "\n\n"
    messages = [
        {"role": "system", "content": SYSTEME_REFORMULATION},
        {"role": "user", "content": f"{contexte}Question : {question}\nRéponds en JSON."},
    ]
    messages[-1]["content"] = messages[-1]["content"].replace("Réponds en JSON.", "Réponds par la seule question reformulée.")
    try:
        # décodage déterministe : même question -> même reformulation (démo reproductible)
        brut = llm.chat(messages, timeout=30, options={"num_predict": 70, "stop": ["\n"], "temperature": 0, "seed": 42})
        ref = brut.strip().strip("«»\"' ").removeprefix("Question :").strip()
        return ref or None
    except llm.LLMUnavailable as exc:
        log.warning("Reformulation impossible : %s", exc)
        return None


def extrait_pertinent(texte: str, requete: str, longueur: int = LONGUEUR_EXTRAIT) -> str:
    """Garde le début de l'article et les phrases les plus proches de la requête, dans l'ordre du texte."""
    if len(texte) <= longueur:
        return texte
    phrases = [p for p in re.split(r"(?<=[.;:])\s+|\n+", texte) if p.strip()]
    mots = set(tokeniser(requete))
    scores = [len(mots & set(tokeniser(p))) for p in phrases]
    gardees, total = {0}, len(phrases[0])
    for i in sorted(range(1, len(phrases)), key=lambda i: -scores[i]):
        if scores[i] == 0 or total + len(phrases[i]) > longueur:
            continue
        gardees.add(i)
        total += len(phrases[i])
    morceaux, precedent = [], -1
    for i in sorted(gardees):
        if precedent >= 0 and i != precedent + 1:
            morceaux.append("[…]")
        morceaux.append(phrases[i])
        precedent = i
    if precedent < len(phrases) - 1:
        morceaux.append("[…]")
    return " ".join(morceaux)


def _bloc_extraits(rech: Recherche, requete: str, n: int = N_EXTRAITS_LLM) -> tuple[str, list[dict]]:
    sources = [r.as_source(i + 1) for i, r in enumerate(rech.resultats[:n])]
    blocs = []
    for s in sources:
        titre = f"[{s['n']}] {s['document']}"
        if s["article"]:
            titre += f" — {s['article']}" if str(s["article"]).lower().startswith("article") else f" — Article {s['article']}"
        titre += f" (section : {(s['section'] or '')[-160:]} ; page {s['page']})"
        s["extrait_envoye"] = extrait_pertinent(s["extrait"], requete)
        blocs.append(f"{titre}\n{s['extrait_envoye']}")
    return "\n\n".join(blocs), sources


_NOMBRES = ("un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|douze|quinze|vingt|trente|quarante|cinquante|"
            "soixante|quatre-vingt-dix|cent|mille")
_CHIFFRE_RE = re.compile(rf"\b((?:\d[\d\s.,]*|(?:{_NOMBRES})(?:[\s-](?:{_NOMBRES}))*)\s*(?:%|pour cent|jours?|mois|ans?|années?|"
                         rf"dinars?|DT|millimes?))", re.I)


def verifier_chiffres(texte: str, sources: list[dict]) -> list[str]:
    """Délais, taux et montants de la réponse absents de tous les extraits fournis (à vérifier)."""
    corpus = re.sub(r"\s+", " ", " ".join(s.get("extrait", "") for s in sources).lower()).replace(" %", "%")
    douteux = []
    for m in _CHIFFRE_RE.finditer(texte):
        brut = re.sub(r"\s+", " ", m.group(1).strip().lower()).replace(" %", "%")
        if brut not in corpus and brut not in douteux:
            douteux.append(brut)
    return douteux


SUJETS_NON_COUVERTS = [
    (re.compile(r"\btva\b|taxe sur la valeur ajout[ée]e|الأداء على القيمة المضافة", re.I), "le Code de la TVA"),
    (re.compile(r"\birpp\b|imp[ôo]t sur le revenu|imp[ôo]t sur les soci[ée]t[ée]s|الضريبة على الدخل|الضريبة على الشركات", re.I),
     "le Code de l'IRPP et de l'IS"),
]


def sujets_non_couverts(*textes: str | None) -> list[str]:
    t = " ".join(x for x in textes if x)
    return [nom for motif, nom in SUJETS_NON_COUVERTS if motif.search(t)]


def construire_messages(question: str, rech: Recherche, mode: str, langue: str, reformulation: str | None,
                        historique: list[dict] | None) -> tuple[list[dict], list[dict]]:
    extraits, sources = _bloc_extraits(rech, " ".join(x for x in (question, reformulation, expansion_lexicale(question)) if x))
    systeme = SYSTEME.format(disclaimer=DISCLAIMER.get(langue, DISCLAIMER["fr"])) + "\n" + MODES.get(mode, MODES["contribuable"]) \
        + "\n" + LANGUES.get(langue, LANGUES["fr"])
    messages = [{"role": "system", "content": systeme}]
    for m in (historique or [])[-4:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"][:1500]})
    user = f"Extraits de la base (seules sources autorisées) :\n\n{extraits}\n\nQuestion : {question}"
    if reformulation and reformulation.strip() != question.strip():
        user += f"\n(Reformulation juridique utilisée pour la recherche : {reformulation})"
    manquants = sujets_non_couverts(question, reformulation)
    if manquants:
        user += (f"\n\nATTENTION : cette question relève de {' et de '.join(manquants)}, qui n'est pas encore dans la base. "
                 "Commence ta réponse en le disant clairement. Ne donne un taux que si un extrait le prévoit EXPLICITEMENT pour "
                 "l'objet exact de la question ; un taux prévu pour d'autres biens ou opérations ne s'applique pas. "
                 "Sinon, dis que la base ne permet pas de répondre et qu'il faut consulter ce code.")
    messages.append({"role": "user", "content": user})
    return messages, sources


def verifier_citations(texte: str, n_sources: int) -> tuple[list[int], list[int]]:
    """Chaque citation [n] doit correspondre à un extrait réellement fourni."""
    cites = sorted({int(x) for x in re.findall(r"\[(\d+)\]", texte)})
    valides = [c for c in cites if 1 <= c <= n_sources]
    return valides, [c for c in cites if c not in valides]


def nettoyer_citations(texte: str, n_sources: int) -> str:
    return re.sub(r"\[(\d+)\]", lambda m: m.group(0) if 1 <= int(m.group(1)) <= n_sources else "", texte)


def _suggestions(question: str) -> list[str]:
    schema = {"type": "object", "properties": {"suggestions": {"type": "array", "items": {"type": "string"}}}, "required": ["suggestions"]}
    try:
        brut = llm.chat([
            {"role": "system", "content": "Propose 3 reformulations de la question, en français, dans les domaines couverts : contrôle "
                                          "fiscal, droit de communication, pénalités, taxation d'office, douane, droits d'enregistrement et "
                                          "de timbre, opérateur économique agréé, avantages fiscaux. JSON uniquement."},
            {"role": "user", "content": question}], fmt=schema, timeout=30, options={"num_predict": 200})
        s = [x for x in json.loads(brut).get("suggestions", []) if isinstance(x, str)][:3]
        return s or SUGGESTIONS_DEFAUT
    except (llm.LLMUnavailable, json.JSONDecodeError, AttributeError):
        return SUGGESTIONS_DEFAUT


def repondre_flux(question: str, mode: str = "contribuable", langue: str = "fr", historique: list[dict] | None = None) -> Iterator[dict]:
    """Générateur d'événements : meta, sources, token…, fin (ou erreur). Utilisé en streaming NDJSON."""
    t0 = time.perf_counter()
    langue = langue if langue in LANGUES else "fr"
    retriever = get_retriever()
    with ThreadPoolExecutor(max_workers=1) as pool:  # encodage de la question pendant la reformulation par le LLM
        pre = pool.submit(retriever.preparer, question)
        reformulation = reformuler(question, historique)
        vecteurs = pre.result()
    rech = retriever.rechercher(question, requetes_sup=[reformulation] if reformulation else None, vecteurs=vecteurs)
    manquants = sujets_non_couverts(question, reformulation)
    yield {"type": "meta", "reformulation": reformulation, "abstention": rech.abstention,
           "avertissement": (f"{' et '.join(manquants)} n'est pas encore indexé : réponse limitée aux autres textes."
                             if manquants else None),
           "meilleur_score": round(rech.meilleur_score, 4), "seuil": round(rech.seuil, 4), "recherche_s": round(time.perf_counter() - t0, 2)}
    if rech.abstention:
        yield {"type": "sources", "sources": []}
        texte = f"{ABSTENTION[langue]}\n\n{DISCLAIMER[langue]}"
        yield {"type": "token", "t": texte}
        yield {"type": "fin", "texte": texte, "abstention": True, "suggestions": _suggestions(question), "citations": [],
               "citations_invalides": [], "duree_s": round(time.perf_counter() - t0, 2)}
        return
    messages, sources = construire_messages(question, rech, mode, langue, reformulation, historique)
    yield {"type": "sources", "sources": sources}
    morceaux: list[str] = []
    premier = None
    try:
        for tok in llm.chat_stream(messages):
            if premier is None:
                premier = time.perf_counter() - t0
            morceaux.append(tok)
            yield {"type": "token", "t": tok}
    except llm.LLMUnavailable as exc:
        yield {"type": "erreur", "message": LLM_INDISPONIBLE, "detail": str(exc)}
        return
    texte = "".join(morceaux)
    valides, invalides = verifier_citations(texte, len(sources))
    douteux = verifier_chiffres(texte, sources)
    if invalides:
        log.warning("Citations invalides retirées : %s", invalides)
    yield {"type": "fin", "texte": nettoyer_citations(texte, len(sources)), "abstention": False, "citations": valides,
           "citations_invalides": invalides, "chiffres_non_verifies": douteux,
           "premier_token_s": round(premier or 0, 2), "duree_s": round(time.perf_counter() - t0, 2)}


def repondre(question: str, mode: str = "contribuable", langue: str = "fr", historique: list[dict] | None = None) -> dict:
    """Version non streamée (tests, intégrations)."""
    out: dict = {"question": question, "mode": mode, "langue": langue}
    for ev in repondre_flux(question, mode, langue, historique):
        if ev["type"] == "meta":
            out["meta"] = {k: v for k, v in ev.items() if k != "type"}
        elif ev["type"] == "sources":
            out["sources"] = ev["sources"]
        elif ev["type"] == "fin":
            out.update({k: v for k, v in ev.items() if k != "type"})
        elif ev["type"] == "erreur":
            out["erreur"] = ev["message"]
    return out
