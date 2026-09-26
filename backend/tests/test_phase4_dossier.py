"""Phase 4 : dossier de contrôle T3 (calc.py déterministe, articles vérifiés, rédaction, PDF)."""
from __future__ import annotations

import json
import os
from datetime import date

import pytest

os.environ.setdefault("RASD_WARMUP", "0")

from app import config, db, llm  # noqa: E402
from app.dossier.calc import _mois_de_retard, calculer, montants_autorises  # noqa: E402
from app.dossier.generator import _chiffres_non_autorises  # noqa: E402

BASE = config.DB_PATH.exists() and db.db_status().get("scores", 0) > 0
OLLAMA = llm.ollama_status().get("status") == "ok"
pytestmark = pytest.mark.skipif(not BASE, reason="base de démonstration absente")

ART = "cdpf_2024__code_des_droits_et_procedures_fiscaux_article_{}"


@pytest.fixture(scope="module")
def ctx():
    from app.rag import embedder
    from app.rag.index import get_index
    from app.risk.features import charger_contexte

    embedder.initialize(get_index())
    return charger_contexte()


@pytest.fixture(scope="module")
def sahel():
    eid = int(db.read_sql("SELECT id FROM entreprises WHERE raison_sociale = 'Sahel Électro SARL'").id.iloc[0])
    det = json.loads(db.read_sql("SELECT details FROM scores WHERE entreprise_id = :e", {"e": eid}).details.iloc[0])
    return eid, det["indices"]


def test_calcul_de_reference_sahel(ctx, sahel):
    eid, indices = sahel
    c = calculer(ctx, eid, indices, date(2026, 9, 26))
    v = {l["cle"]: l["montant"] for l in c["lignes"]}
    assert v["cout_ventes"] == pytest.approx(2_800_000)
    assert v["ca_reconstitue"] == pytest.approx(3_360_000)
    assert v["ecart_ca"] == pytest.approx(2_560_000)
    assert v["tva_ventes_omises"] == pytest.approx(486_400)
    assert v["tva_deduite_trop"] == pytest.approx(40_000)
    assert c["total_tva"] == pytest.approx(526_400)
    assert v["is_indicatif"] == pytest.approx(2_560_000 * 0.20 * 0.15)
    assert c["mention"] == "Estimation indicative, à confirmer par la procédure contradictoire."
    assert any(l.get("a_verifier") for l in c["lignes"])  # taux de TVA et d'IS marqués « à vérifier »
    assert all("formule" in l and l["formule"] for l in c["lignes"])


def test_penalites_mois_ou_fraction_de_mois():
    assert _mois_de_retard(date(2025, 2, 28), date(2025, 2, 28)) == 0
    assert _mois_de_retard(date(2025, 2, 28), date(2025, 3, 1)) == 1
    assert _mois_de_retard(date(2025, 2, 28), date(2025, 4, 28)) == 2
    assert _mois_de_retard(date(2025, 2, 28), date(2025, 4, 29)) == 3


def test_articles_16_17_81_retrouves_avec_extrait(ctx):
    from app.dossier.articles import articles_applicables
    from app.rag.index import get_index

    arts = articles_applicables({"A1", "A3", "B1", "B4", "C3", "C4"})
    ids = {a["id"] for a in arts}
    assert {ART.format(16), ART.format(17), ART.format(81)} <= ids
    for a in arts:
        assert get_index().get(a["id"]) is not None and len(a["extrait"]) > 50
    a81 = next(a for a in arts if a["id"] == ART.format(81))
    assert "1,25%" in a81["extrait"]


def test_montants_inventes_detectes(ctx, sahel):
    eid, indices = sahel
    autorises = montants_autorises(calculer(ctx, eid, indices, date(2026, 9, 26)))
    assert _chiffres_non_autorises("Le total est de 526 400 DT pour l'exercice 2025.", autorises) == []
    assert _chiffres_non_autorises("Le total est de 612 000 DT.", autorises) == ["612 000"]


def test_dossier_sans_llm_et_pdf(ctx, sahel):
    from app.dossier.export import pdf
    from app.dossier.generator import generer

    eid, _ = sahel
    d = generer(ctx, eid, "pytest", utiliser_llm=False)
    c = d["contenu"]
    assert c["generation"]["source"] == "modele_de_secours"
    assert c["ecarts"]["total_tva"] == pytest.approx(526_400)
    assert "526 400 DT" in c["lettre"]["corps"] or "526 400" in c["lettre"]["corps"].replace(" ", " ")
    assert {ART.format(16), ART.format(17), ART.format(81)} <= {a["id"] for a in c["articles"]}
    assert c["entete"]["statut"] == "brouillon" and len(c["synthese"]) == 5
    assert any("article 16" in doc.lower() for doc in c["documents"])
    assert pdf(d).startswith(b"%PDF")


@pytest.mark.skipif(not OLLAMA, reason="Ollama indisponible")
def test_dossier_redige_par_le_llm(ctx, sahel):
    from app.dossier.generator import generer

    llm.prechauffer()
    eid, _ = sahel
    d = generer(ctx, eid, "pytest")
    c = d["contenu"]
    texte = (" ".join(c["synthese"]) + c["lettre"]["corps"]).replace(" ", " ").replace(" ", " ")
    if c["generation"]["source"].startswith("llm"):
        assert "526 400" in texte
    assert c["generation"]["duree_s"] < 45


def test_api_dossier_validation_et_pdf(ctx, sahel):
    from fastapi.testclient import TestClient

    from app.dossier.generator import generer
    from app.main import app

    eid, _ = sahel
    d = generer(ctx, eid, "pytest", utiliser_llm=False)
    with TestClient(app) as c:
        r = c.put(f"/api/dossiers/{d['id']}", json={"synthese": ["Ligne modifiée par l'agent"] * 5, "agent": "pytest"}).json()
        assert r["contenu"]["synthese"][0] == "Ligne modifiée par l'agent"
        r = c.put(f"/api/dossiers/{d['id']}", json={"statut": "valide", "agent": "pytest"}).json()
        assert r["statut"] == "valide" and r["valide_le"]
        assert c.put(f"/api/dossiers/{d['id']}", json={"synthese": ["x"] * 5}).status_code == 409
        p = c.get(f"/api/dossiers/{d['id']}/pdf")
        assert p.status_code == 200 and p.content.startswith(b"%PDF")
        journal = c.get("/api/audit").json()
        assert any(j["action"] == "validation_dossier" for j in journal)
    with db.get_engine().begin() as conn:  # nettoyage
        conn.execute(db.dossiers.delete().where(db.dossiers.c.agent == "pytest"))
        conn.execute(db.journal_audit.delete().where(db.journal_audit.c.agent == "pytest"))
