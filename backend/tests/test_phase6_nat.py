"""Phase 6 : filtrage du ciblage par code d'activité NAT 2009 (Section > Division > Groupe > Classe)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("RASD_WARMUP", "0")

from app import config, db, nat  # noqa: E402

BASE = config.DB_PATH.exists() and db.db_status().get("scores", 0) > 0
pytestmark = pytest.mark.skipif(not BASE, reason="base de démonstration absente")


def test_niveaux_et_libelles_officiels():
    assert [nat.niveau(c) for c in ("G", "46", "46.5", "46.52", "4652", "")] == ["section", "division", "groupe", "classe", None, None]
    assert nat.libelle("46.52").startswith("Commerce de gros de composants")
    assert nat.classes_de("46.5") == {"46.51", "46.52"}
    assert "46.52" in nat.classes_de("G") and "10.71" not in nat.classes_de("G")
    assert nat.classes_de("99.99") == set()


def test_toutes_les_entreprises_ont_un_code_nat_connu():
    codes = set(db.read_sql("SELECT DISTINCT secteur_nat_code FROM entreprises").secteur_nat_code)
    assert codes <= set(nat.classes())


@pytest.mark.parametrize("code", ["G", "46", "46.5", "46.52", "C", "10"])
def test_filtre_a_chaque_niveau(code):
    from app import services

    res = services.liste(nat_=code, taille=500)
    attendu = nat.classes_de(code)
    assert res["total"] > 0 and all(r["secteur_nat_code"] in attendu for r in res["resultats"])
    s = services.scores()
    assert res["total"] == int(s.secteur_nat_code.isin(attendu).sum())


def test_arbre_des_referentiels_coherent():
    from app import services

    arbre = services.referentiels()["nat"]
    assert sum(n["entreprises"] for n in arbre) == len(services.scores())
    for section in arbre:  # chaque niveau totalise ses enfants
        assert section["niveau"] == "section"
        assert section["entreprises"] == sum(d["entreprises"] for d in section["enfants"])
        for division in section["enfants"]:
            assert division["entreprises"] == sum(g["entreprises"] for g in division["enfants"])


def test_api_filtre_nat_et_code_invalide():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.get("/api/entreprises", params={"nat": "46.5", "taille": 5}).json()
        assert r["resultats"] and all(x["secteur_nat_code"].startswith("46.5") for x in r["resultats"])
        assert c.get("/api/entreprises", params={"nat": "abc"}).status_code == 422
        csv = c.get("/api/entreprises.csv", params={"nat": "46.52"}).text
        assert "code_nat" in csv.splitlines()[0] and all(";46.52;" in l for l in csv.splitlines()[1:])
