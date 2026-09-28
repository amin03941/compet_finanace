"""Phase 4 (suite) : l'agent ajoute, retire ou rétablit des articles ; historique en ajout seulement ; lettre cohérente."""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("RASD_WARMUP", "0")

from app import config, db  # noqa: E402
from app.dossier.generator import Lettre, Redaction, _articles_non_autorises  # noqa: E402

BASE = config.DB_PATH.exists() and db.db_status().get("scores", 0) > 0
pytestmark = pytest.mark.skipif(not BASE, reason="base de démonstration absente")

ART = "cdpf_2024__code_des_droits_et_procedures_fiscaux_article_{}"
AGENT = "pytest"
MOTIF = "Motif de test suffisamment long"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.rag import embedder
    from app.rag.index import get_index

    embedder.initialize(get_index())
    with TestClient(app) as c:
        yield c
    with db.get_engine().begin() as conn:  # nettoyage (l'historique, lui, est en ajout seulement)
        conn.execute(db.dossiers.delete().where(db.dossiers.c.agent == AGENT))
        conn.execute(db.journal_audit.delete().where(db.journal_audit.c.agent == AGENT))


@pytest.fixture()
def dossier(client):
    from app.dossier.generator import generer
    from app.risk.features import charger_contexte

    eid = int(db.read_sql("SELECT id FROM entreprises WHERE raison_sociale = 'Sahel Électro SARL'").id.iloc[0])
    return generer(charger_contexte(), eid, AGENT, utiliser_llm=False)


def test_retrait_sans_motif_refuse(client, dossier):
    did = dossier["id"]
    for motif in ("", "   ", "court"):
        r = client.post(f"/api/dossiers/{did}/articles/retrait", json={"record_id": ART.format(81), "motif": motif, "agent": AGENT})
        assert r.status_code == 422 and "Motif obligatoire" in r.json()["detail"]
    assert ART.format(81) in {a["id"] for a in client.get(f"/api/dossiers/{did}").json()["contenu"]["articles"]}


def test_ajout_d_un_id_absent_de_l_index_refuse(client, dossier):
    r = client.post(f"/api/dossiers/{dossier['id']}/articles", json={"record_id": "article_invente_999", "motif": MOTIF, "agent": AGENT})
    assert r.status_code == 422 and "index" in r.json()["detail"]


def test_retrait_ajout_retablissement_et_historique(client, dossier):
    did = dossier["id"]
    # recherche par numéro : uniquement des records existants de l'index
    res = client.get(f"/api/dossiers/{did}/articles/recherche", params={"q": "article 38 du code des droits et procédures fiscaux"}).json()
    assert res and res[0]["id"] == ART.format(38) and not res[0]["deja_present"]

    r = client.post(f"/api/dossiers/{did}/articles/retrait", json={"record_id": ART.format(81), "motif": MOTIF, "agent": AGENT}).json()
    assert ART.format(81) not in {a["id"] for a in r["contenu"]["articles"]}
    ecarte = next(a for a in r["contenu"]["articles_ecartes"] if a["id"] == ART.format(81))
    assert ecarte["retrait"]["motif"] == MOTIF and ecarte["retrait"]["agent"] == AGENT and ecarte["retrait"]["le"]

    r = client.post(f"/api/dossiers/{did}/articles", json={"record_id": ART.format(38), "motif": MOTIF, "agent": AGENT}).json()
    ajoute = next(a for a in r["contenu"]["articles"] if a["id"] == ART.format(38))
    assert ajoute["origine"] == "agent" and len(ajoute["extrait"]) > 50 and r["contenu"]["articles_modifies"]
    assert client.post(f"/api/dossiers/{did}/articles", json={"record_id": ART.format(38), "motif": MOTIF, "agent": AGENT}).status_code == 422

    r = client.post(f"/api/dossiers/{did}/articles/retablissement", json={"record_id": ART.format(81), "motif": MOTIF, "agent": AGENT}).json()
    assert ART.format(81) in {a["id"] for a in r["contenu"]["articles"]} and not r["contenu"]["articles_ecartes"]

    h = client.get(f"/api/dossiers/{did}/historique").json()
    assert [l["action"] for l in h] == ["retablissement_article", "ajout_article", "retrait_article", "generation"]
    for l in h[:3]:
        assert l["dossier_id"] == did and l["record_id"] and l["motif"] == MOTIF and l["agent"] == AGENT and l["horodatage"]


def test_historique_en_ajout_seulement(client, dossier):
    from sqlalchemy.exc import DatabaseError

    with pytest.raises(DatabaseError, match="ajout seulement"):
        with db.get_engine().begin() as conn:
            conn.execute(db.journal_dossier.update().where(db.journal_dossier.c.dossier_id == dossier["id"]).values(motif="x"))
    with pytest.raises(DatabaseError, match="ajout seulement"):
        with db.get_engine().begin() as conn:
            conn.execute(db.journal_dossier.delete().where(db.journal_dossier.c.dossier_id == dossier["id"]))


def test_lettre_verifiee_avec_la_liste_finale(client, dossier, monkeypatch):
    from app.dossier import generator

    did = dossier["id"]
    c = dossier["contenu"]
    assert _articles_non_autorises("En application de l'article 81 du code.", c["articles"], c["documents"]["dgi"]) == []
    # l'agent retire l'article 81 : la lettre qui le cite n'est plus cohérente avec la liste finale
    r = client.post(f"/api/dossiers/{did}/articles/retrait", json={"record_id": ART.format(81), "motif": MOTIF, "agent": AGENT}).json()
    assert r["etat_articles"]["lettre_a_regenerer"]
    assert _articles_non_autorises("En application de l'article 81 du code.", r["contenu"]["articles"],
                                   r["contenu"]["documents"]["dgi"]) == ["81"]
    # une rédaction du LLM qui cite un article hors de la liste finale est écartée au profit du modèle de secours
    corps = "Madame, Monsieur, en application des articles 16 et 81 du code, " + "nous vous demandons vos justificatifs. " * 8
    monkeypatch.setattr(generator, "rediger_llm", lambda prompt, partie="dgi": (
        Redaction(synthese=["a", "b", "c"], lettre=Lettre(objet="Demande de justification", corps=corps)), "llm:test"))
    fc = r["contenu"]
    red, source, erreur = generator.rediger(fc["entete"], fc["ecarts"], fc["indices"], fc["articles"], fc["documents"]["dgi"], True,
                                            partie="dgi")
    assert source == "modele_de_secours" and "articles hors liste" in erreur and "81" in erreur
    # régénération : lettre rédigée avec la liste finale, plus d'alerte
    r = client.post(f"/api/dossiers/{did}/lettre/regeneration", json={"agent": AGENT}).json()
    assert not r["etat_articles"]["lettre_a_regenerer"] and r["etat_articles"]["articles_hors_liste_lettre"] == []
    assert sorted(r["contenu"]["lettres"]["dgi"]["articles_ids"]) == sorted(a["id"] for a in r["contenu"]["articles"])
    assert client.get(f"/api/dossiers/{did}/historique").json()[0]["action"] == "regeneration_lettre"


def test_recherche_par_numero_dans_le_code_nomme(client, dossier):
    res = client.get(f"/api/dossiers/{dossier['id']}/articles/recherche", params={"q": "article 35 du code des douanes"}).json()
    assert res[0]["source_id"] == "code_douanes_2016" and res[0]["article"] == "Article 35" and res[0]["par_numero"]
    assert "raisons de douter" in " ".join(res[0]["extrait"].split())


def test_lecture_des_citations_d_articles():
    from app.dossier.generator import numeros_cites

    assert numeros_cites("Selon l'article 37, 81 et 383 du code") == {"37", "81", "383"}
    assert numeros_cites("en application des articles 16, 17 et 40 bis") == {"16", "17", "40 bis"}
    assert numeros_cites("sanctions des articles 89 à 105") == {"89", "105"}
    assert numeros_cites("au titre de l'article 16, 30 jours après réception") == {"16"}


def test_dossier_valide_non_modifiable(client, dossier):
    did = dossier["id"]
    assert client.put(f"/api/dossiers/{did}", json={"statut": "valide", "agent": AGENT}).status_code == 200
    corps = {"record_id": ART.format(81), "motif": MOTIF, "agent": AGENT}
    assert client.post(f"/api/dossiers/{did}/articles/retrait", json=corps).status_code == 409
    assert client.post(f"/api/dossiers/{did}/articles", json={**corps, "record_id": ART.format(38)}).status_code == 409
    assert client.post(f"/api/dossiers/{did}/lettre/regeneration", json={"agent": AGENT}).status_code == 409
    contenu = json.loads(db.read_sql("SELECT contenu FROM dossiers WHERE id = :d", {"d": did}).contenu.iloc[0])
    assert ART.format(81) in {a["id"] for a in contenu["articles"]}
    assert client.get(f"/api/dossiers/{did}/historique").json()[0]["action"] == "validation"


def test_pdf_liste_finale_et_mention(client, dossier):
    from app.dossier import export, generator

    did = dossier["id"]
    client.post(f"/api/dossiers/{did}/articles/retrait", json={"record_id": ART.format(81), "motif": MOTIF, "agent": AGENT})
    d = generator.lire(did)
    textes = []
    monkey = export._p

    def espion(texte, *a, **k):
        textes.append(texte)
        return monkey(texte, *a, **k)

    export._p = espion
    try:
        assert export.pdf(d).startswith(b"%PDF")
    finally:
        export._p = monkey
    assert "Liste des articles modifiée par l'agent (voir historique)." in textes
    assert not any(t.startswith("Article 81 —") for t in textes)
