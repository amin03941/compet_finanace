"""Phase 2 : ciblage de bout en bout sur la base de démonstration (seed 42) et API.

Pré-requis : base générée et scores calculés (scripts\\reset_demo.ps1). Sinon les tests sont ignorés.
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("RASD_WARMUP", "0")

from app import config, db  # noqa: E402

pytestmark = pytest.mark.skipif(not config.DB_PATH.exists() or db.db_status().get("scores", 0) == 0,
                                reason="base de démonstration absente")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _score(nom: str) -> dict:
    df = db.read_sql("""SELECT s.* FROM scores s JOIN entreprises e ON e.id = s.entreprise_id
                        WHERE e.raison_sociale = :n""", {"n": nom})
    r = df.iloc[0].to_dict()
    r["regles"] = json.loads(r["regles_declenchees"])
    r["details"] = json.loads(r["details"])
    return r


def _id(nom: str) -> int:
    return int(db.read_sql("SELECT id FROM entreprises WHERE raison_sociale = :n", {"n": nom}).id.iloc[0])


def test_sahel_electro_rouge_en_tete():
    s = _score("Sahel Électro SARL")
    assert s["categorie"] == "rouge"
    assert s["rang"] == 1
    assert 80 <= s["score"] <= 95
    assert s["montant_en_jeu"] == pytest.approx(526_400, abs=1)
    assert {"A1", "A3", "B1"} <= set(s["regles"])
    cascade = s["details"]["cascade"]
    assert cascade[-1]["valeur"] == pytest.approx(s["score"], abs=0.05)
    assert sum(e["valeur"] for e in cascade[:-1]) == pytest.approx(s["score"], abs=0.15)


@pytest.mark.parametrize("nom", ["Cap Bon Distribution SARL", "Djerba Industries SA", "Nour Textile SA"])
def test_pieges_et_exportatrice_coherents_en_vert(nom):
    s = _score(nom)
    assert s["categorie"] == "vert"
    assert s["score"] < 20
    assert s["regles"] == []


def test_meme_ecart_brut_cap_bon_vert_sahel_rouge():
    """Même écart brut (3 M DT importés pour 0,8 M DT de CA) : la neutralisation du stock fait la différence."""
    sahel, cap = _score("Sahel Électro SARL"), _score("Cap Bon Distribution SARL")
    stock = next(n for n in cap["details"]["neutralisations"] if n["cle"] == "stock")
    assert stock["statut"] == "verifie" and "2 300 000" in stock["detail"]
    assert sahel["categorie"] == "rouge" and cap["categorie"] == "vert"


def test_nour_textile_candidate_oea():
    s = _score("Nour Textile SA")
    assert s["facilitation"] and s["details"]["facilitation"]["candidat_oea"]


def test_medina_et_carrousel():
    assert _score("Médina Trade SUARL")["categorie"] in ("rouge", "orange")
    assert "B2" in _score("Médina Trade SUARL")["regles"]
    for nom in ("Carthage Négoce SARL", "Atlas Services SUARL", "Yasmine Distribution SARL"):
        s = _score(nom)
        assert s["categorie"] == "rouge" and "B3" in s["regles"], nom


def test_metriques_calculees_et_ciblage_meilleur_que_le_hasard():
    perf = json.loads(db.read_sql("SELECT valeur FROM metriques WHERE cle = 'performance'").valeur.iloc[0])
    assert set(perf["methodes"]) == {"hasard", "ecart_brut", "regles", "regles_ia"}
    top100 = {m: perf["methodes"][m]["top"][1]["precision"] for m in perf["methodes"]}
    assert top100["regles_ia"] >= 3 * top100["hasard"]
    assert top100["regles_ia"] > top100["ecart_brut"]
    assert perf["fausses_alertes"]["outil"] < perf["fausses_alertes"]["naif"]
    assert len(perf["schemas"]) == 8
    assert 0.5 < perf["modele"]["auc_validation_croisee"] <= 1


# ------------------------------------------------------------------ API
def test_api_stats(client):
    r = client.get("/api/stats").json()
    assert r["kpis"]["entreprises_analysees"] == 2000
    assert r["kpis"]["alertes_rouges"] > 0
    assert r["top5"][0]["raison_sociale"] == "Sahel Électro SARL"
    assert len(r["distribution_scores"]) == 10 and r["evolution_mensuelle"]


def test_api_liste_filtres_et_csv(client):
    r = client.get("/api/entreprises", params={"categorie": "rouge", "taille": 20}).json()
    assert r["total"] > 0 and all(x["categorie"] == "rouge" for x in r["resultats"])
    prio = [x["priorite"] for x in r["resultats"]]
    assert prio == sorted(prio, reverse=True)
    r = client.get("/api/entreprises", params={"q": "sahel électro"}).json()
    assert r["resultats"][0]["raison_sociale"] == "Sahel Électro SARL"
    r = client.get("/api/entreprises", params={"regle": "B3"}).json()
    assert r["total"] >= 3
    csv = client.get("/api/entreprises.csv", params={"categorie": "rouge"})
    assert csv.status_code == 200 and "Sahel Électro SARL" in csv.text


def test_api_fiche_360(client):
    f = client.get(f"/api/entreprises/{_id('Sahel Électro SARL')}").json()
    assert f["score"]["categorie"] == "rouge"
    assert len(f["series"]) == 36
    dernier = f["series"][-1]
    assert dernier["cumul_paiements_tej"] > dernier["cumul_ca_declare"]
    assert len(f["neutralisations"]) == 7
    assert any(n.get("radiee") for n in f["reseau"]["nodes"])
    assert set(f["donnees_brutes"]) >= {"douane", "impots", "tej", "el_fatoora"}
    assert client.get("/api/entreprises/999999").status_code == 404


def test_api_preuves(client):
    sid = _id("Sahel Électro SARL")
    p = client.get(f"/api/entreprises/{sid}/preuves/A1").json()
    assert p["total"] > 0 and "Client payeur" in p["colonnes"]
    p = client.get(f"/api/entreprises/{_id('Carthage Négoce SARL')}/preuves/B3").json()
    assert p["total"] >= 18  # 3 arêtes × 6 mois
    assert client.get(f"/api/entreprises/{sid}/preuves/Z9").status_code == 404


def test_api_facilitation_performance_resultat(client):
    fac = client.get("/api/facilitation").json()
    assert any(e["raison_sociale"] == "Nour Textile SA" for e in fac["entreprises"])
    perf = client.get("/api/performance").json()
    assert perf["performance"]["resume"]["precision_top100_regles_ia"] is not None
    r = client.post(f"/api/entreprises/{_id('Médina Trade SUARL')}/resultat-controle",
                    json={"redressement": True, "montant": 120000, "commentaire": "test automatique", "agent": "pytest"})
    assert r.json()["enregistre"]
    with db.get_engine().begin() as conn:  # nettoyage : ne pas polluer la démo
        conn.execute(db.resultats_controle.delete().where(db.resultats_controle.c.agent == "pytest"))
