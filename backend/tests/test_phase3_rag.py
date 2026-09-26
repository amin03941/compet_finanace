"""Phase 3 : retriever (section 4.5/4.6) et assistant réglementaire T9 (section 8)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("RASD_WARMUP", "0")

from app import llm  # noqa: E402
from app.chat.assistant import extrait_pertinent, nettoyer_citations, verifier_chiffres, verifier_citations  # noqa: E402
from app.rag import embedder  # noqa: E402
from app.rag.index import get_index, normalize_article_number  # noqa: E402
from app.rag.retriever import expansion_lexicale, get_retriever  # noqa: E402

JEU = json.loads((Path(__file__).parent / "rag_questions.json").read_text(encoding="utf-8"))["questions"]
OLLAMA = llm.ollama_status().get("status") == "ok"


@pytest.fixture(scope="module")
def retriever():
    embedder.initialize(get_index())
    return get_retriever()


def _correspond(record: dict, attendu: dict) -> bool:
    if record["source_id"] != attendu["source_id"]:
        return False
    if "article" in attendu and normalize_article_number(record.get("article_number")) != attendu["article"]:
        return False
    if "id_contient" in attendu and attendu["id_contient"] not in record["id"]:
        return False
    if "section_contient" in attendu and attendu["section_contient"] not in (record.get("section") or ""):
        return False
    if attendu.get("article") and record["source_id"] == "cdpf_2024":
        return record.get("document_unit") == "CODE DES DROITS ET PROCÉDURES FISCAUX"
    return True


@pytest.mark.parametrize("q", [q for q in JEU if q.get("acceptation")], ids=lambda q: q["question"][:40])
def test_acceptation_top3(retriever, q):
    """Les 7 tests d'acceptation de la section 4.6 : la source attendue figure dans le top 3."""
    res = retriever.rechercher(q["question"])
    top3 = [r.record for r in res.resultats[:3]]
    assert any(_correspond(r, q["attendu"]) for r in top3), [(r["source_id"], r.get("article_number")) for r in top3]
    assert not res.abstention


def test_abstention_calibree(retriever):
    for q in JEU:
        res = retriever.rechercher(q["question"])
        assert res.abstention == (not q["dans_la_base"]), (q["question"], res.meilleur_score, res.seuil)


def test_recherche_directe_article(retriever):
    res = retriever.rechercher("Que dit l'article 81 du code des droits et procédures fiscaux ?")
    premier = res.resultats[0]
    assert premier.direct
    assert premier.record["id"] == "cdpf_2024__code_des_droits_et_procedures_fiscaux_article_81"


def test_lignes_tarifaires_exclues_par_defaut(retriever):
    res = retriever.rechercher("Quels équipements de l'industrie plastique bénéficient d'avantages fiscaux ?")
    assert res.tarifaire  # la question parle d'équipement : lignes tarifaires autorisées
    res = retriever.rechercher("Quelle est la durée maximale d'une vérification approfondie ?")
    assert not res.tarifaire
    assert all(r.record["chunk_type"] != "equipment_tariff_row" for r in res.resultats)


def test_extraits_sans_entete(retriever):
    res = retriever.rechercher("Quel est le taux de la pénalité de retard de paiement de l'impôt ?")
    src = res.resultats[0].as_source(1)
    assert src["extrait"].startswith("Article 81") and "Document :" not in src["extrait"]
    assert "1,25%" in src["extrait"]


def test_expansion_lexicale():
    assert "listes nominatives" in expansion_lexicale("Le fisc me demande la liste de mes clients")
    assert expansion_lexicale("Quelle est la capitale de l'Australie ?") is None


def test_verification_des_citations():
    valides, invalides = verifier_citations("Oui [1]. Délai de trente jours [3][9].", n_sources=6)
    assert valides == [1, 3] and invalides == [9]
    assert nettoyer_citations("Texte [2] et [8].", 6) == "Texte [2] et ."


def test_extrait_pertinent_garde_la_phrase_utile():
    from app.rag.index import strip_header

    art16 = strip_header(get_index().get("cdpf_2024__code_des_droits_et_procedures_fiscaux_article_16")["content"])
    assert art16.find("trente jours") > 1000  # une simple troncature à 1 000 caractères la perdrait
    ext = extrait_pertinent(art16, "délai liste nominative clients fournisseurs trente jours notification", 1000)
    assert ext.startswith("Article 16") and "trente jours" in ext and len(ext) <= 1100


def test_verification_des_chiffres():
    sources = [{"extrait": "dans un délai ne dépassant pas trente jours à compter de la notification ; pénalité de 1,25% par mois"}]
    assert verifier_chiffres("Le délai est de trente jours et la pénalité de 1,25 % par mois.", sources) == []
    assert verifier_chiffres("Le délai est de neuf jours ouvrés.", sources) == ["neuf jours"]


# ------------------------------------------------------------------ assistant (LLM local)
@pytest.mark.skipif(not OLLAMA, reason="Ollama indisponible")
def test_assistant_question_amel(retriever):
    from app.chat.assistant import repondre

    r = repondre("Le fisc me demande la liste de mes clients, je suis obligée ? En combien de temps ?", "contribuable", "fr")
    assert not r["abstention"] and not r.get("erreur")
    art16 = [s["n"] for s in r["sources"] if s["id"] == "cdpf_2024__code_des_droits_et_procedures_fiscaux_article_16"]
    assert art16, "l'article 16 doit être parmi les sources"
    assert set(art16) & set(r["citations"]), "la réponse doit citer l'article 16"
    assert "trente" in r["texte"].lower() or "30" in r["texte"]
    assert r["citations_invalides"] == [] and r["chiffres_non_verifies"] == []
    assert "Information, pas un conseil juridique" in r["texte"]


@pytest.mark.skipif(not OLLAMA, reason="Ollama indisponible")
def test_assistant_tva_non_couverte(retriever):
    from app.chat.assistant import repondre

    r = repondre("Quel est le taux de TVA applicable aux médicaments ?", "agent", "fr")
    t = r["texte"].lower()
    assert "tva" in t and any(x in t for x in ("pas encore", "non couvert", "ne contient pas", "ne permet pas", "ne permettent pas"))
    assert r["meta"]["avertissement"]
    assert "19" not in t and "7 %" not in t  # aucun taux donné de mémoire


@pytest.mark.skipif(not OLLAMA, reason="Ollama indisponible")
def test_api_chat_streaming(retriever):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        with c.stream("POST", "/api/chat", json={"question": "Quelle est la durée maximale d'une vérification approfondie ?",
                                                  "mode": "agent", "langue": "fr"}) as resp:
            evs = [json.loads(l) for l in resp.iter_lines() if l]
        types = [e["type"] for e in evs]
        assert types[0] == "meta" and types[1] == "sources" and "token" in types and types[-1] == "fin"
        rec = c.get(f"/api/rag/record/{evs[1]['sources'][0]['id']}").json()
        assert rec["texte"] and rec["locator"]
        assert c.get("/api/rag/record/inexistant").status_code == 404
        assert len(c.get("/api/chat/exemples").json()) >= 5
