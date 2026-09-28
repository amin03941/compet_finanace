"""Phase 5 : pré-dossiers séparés selon l'administration compétente (DGI, Douane ou conjoint) et affichage cohérent
avec la décision des règles (couleurs, facilitation, tri du ciblage)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("RASD_WARMUP", "0")

from app import config, db  # noqa: E402

BASE = config.DB_PATH.exists() and db.db_status().get("scores", 0) > 0
pytestmark = pytest.mark.skipif(not BASE, reason="base de démonstration absente")

AGENT = "pytest-admin"
CDPF = "cdpf_2024__code_des_droits_et_procedures_fiscaux_article_{}"
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


def _eid(nom: str) -> int:
    return int(db.read_sql("SELECT id FROM entreprises WHERE raison_sociale = :n", {"n": nom}).id.iloc[0])


@pytest.fixture(scope="module")
def dossiers():
    """Dossiers générés sans LLM (rédaction déterministe) : Médina (douanier orange), Cap Cosmétique (douanier rouge),
    Sahel Électro (fiscal rouge), Delta Carburants (fiscal orange), Sahel Mobile (conjoint rouge)."""
    from app.dossier.generator import generer
    from app.rag import embedder
    from app.rag.index import get_index
    from app.risk.features import charger_contexte

    embedder.initialize(get_index())
    ctx = charger_contexte()
    noms = {"medina": "Médina Trade SUARL", "cap": "Cap Cosmétique Import SARL", "sahel": "Sahel Électro SARL",
            "delta": "Delta Carburants Services SARL", "mobile": "Sahel Mobile SA"}
    out = {k: generer(ctx, _eid(n), AGENT, utiliser_llm=False) for k, n in noms.items()}
    yield out
    with db.get_engine().begin() as conn:
        conn.execute(db.dossiers.delete().where(db.dossiers.c.agent == AGENT))


def _ids(d, partie=None):
    return {a["id"] for a in d["contenu"]["articles"] if partie is None or a["partie"] == partie}


# ------------------------------------------------------------------ classement des règles et type de dossier
def test_classement_des_regles_et_type():
    from app.risk.rules import REGLES, type_dossier

    attendu = {"A1": "dgi", "A2": "dgi", "A5": "dgi", "B3": "dgi", "B4": "dgi", "C3": "dgi", "A3": "dgi_preuve_douane",
               "A4": "dgi_preuve_douane", "B1": "dgi_preuve_douane", "B2": "douane", "C1": "douane", "C2": "deux",
               "C4": "neutre", "C5": "neutre"}
    assert {r.code: r.administration for r in REGLES} == attendu
    assert type_dossier({"B2", "C5"}) == "douanier"
    assert type_dossier({"A3", "B1", "C4"}) == "fiscal"
    assert type_dossier({"B2", "A1"}) == "conjoint"
    assert type_dossier({"C2"}) == "conjoint"
    assert type_dossier(set()) is None


# ------------------------------------------------------------------ séparation DGI / Douane
def test_medina_dossier_douanier(dossiers):
    c = dossiers["medina"]["contenu"]
    e = c["entete"]
    assert e["type_dossier"] == "douanier" and e["titre"] == "Pré-dossier de contrôle douanier"
    assert [d["administration"] for d in e["destinataires"]] == ["Douane"]
    assert all(a["source_id"] != "cdpf_2024" for a in c["articles"])  # aucun article du CDPF
    assert not any("IS" in h or "Pénalités" in h for h in c["ecarts"]["hypotheses"])
    assert not any("Grand livre" in d for docs in c["documents"].values() for d in docs)
    assert c["ecarts"]["total_douane"] > 0 and c["ecarts"]["total_dgi"] == 0
    cles = {l["cle"] for l in c["ecarts"]["lignes"]}
    assert "total_douane" in cles and "total_dgi" not in cles and "is_indicatif" not in cles
    # écart de valeur, droits et TVA à l'import : le total douane retombe sur le montant de l'indice B2
    b2 = next(i for i in c["indices"] if i["code"] == "B2")
    assert c["ecarts"]["total_douane"] == pytest.approx(b2["montant_en_jeu"], rel=1e-6)
    assert list(c["lettres"]) == ["douane"] and not c["transmissions"]


def test_douanier_orange_sans_383_rouge_avec_383(dossiers):
    from app.dossier.articles import DOUANE_23, DOUANE_35, DOUANE_383

    assert dossiers["medina"]["contenu"]["entete"]["categorie"] == "orange"
    assert _ids(dossiers["medina"]) >= {DOUANE_23, DOUANE_35} and DOUANE_383 not in _ids(dossiers["medina"])
    assert dossiers["cap"]["contenu"]["entete"]["categorie"] == "rouge"
    assert {DOUANE_23, DOUANE_35, DOUANE_383} <= _ids(dossiers["cap"])


def test_sahel_electro_fiscal_avec_preuve_douaniere(dossiers):
    c = dossiers["sahel"]["contenu"]
    assert c["entete"]["type_dossier"] == "fiscal" and c["entete"]["preuve_douaniere"]
    assert {"A3", "B1"} <= {i["code"] for i in c["indices"]}
    t = c["transmissions"]
    assert [x["sens"] for x in t] == ["douane_vers_dgi"]
    assert t[0]["base_legale"]["record_id"] == CDPF.format(16) and "services de l'Etat" in t[0]["base_legale"]["extrait"]
    assert t[0]["mention"] == "Transmission soumise au secret professionnel fiscal (article 15 du CDPF)."
    assert {x["code"] for x in t[0]["indices"]} == {"A3", "B1"} and t[0]["pieces"]


def test_dossier_conjoint_deux_parties_et_transmissions(dossiers):
    d = dossiers["mobile"]
    c = d["contenu"]
    assert c["entete"]["type_dossier"] == "conjoint" and c["entete"]["titre"] == "Pré-dossier conjoint DGI – Douane"
    assert c["entete"]["parties"] == ["dgi", "douane"] and set(c["lettres"]) == {"dgi", "douane"}
    assert _ids(d, "dgi") and _ids(d, "douane")
    assert all(a["source_id"] != "cdpf_2024" for a in c["articles"] if a["partie"] == "douane")
    assert c["documents"]["dgi"] and c["documents"]["douane"]
    assert c["ecarts"]["total_dgi"] > 0 and c["ecarts"]["total_douane"] > 0
    sens = {t["sens"]: t for t in c["transmissions"]}
    assert set(sens) == {"douane_vers_dgi", "dgi_vers_douane"}
    art15 = sens["dgi_vers_douane"]["base_legale"]
    assert art15["record_id"] == CDPF.format(15) and art15["extrait"].startswith("Est également exclu")
    assert "autorités et organismes publics" in art15["extrait"]
    # chaque lettre est contrôlée avec les articles de SA partie
    assert d["etat_articles"]["articles_hors_liste_lettre"] == []


def test_dossier_orange_sans_articles_40_et_17(dossiers):
    for cle in ("delta", "medina"):
        c = dossiers[cle]["contenu"]
        assert c["entete"]["categorie"] == "orange"
        assert CDPF.format(40) not in _ids(dossiers[cle]) and CDPF.format(17) not in _ids(dossiers[cle])
    assert {CDPF.format(37), CDPF.format(16)} <= _ids(dossiers["delta"])
    assert "aucune vérification n'est encore ouverte" in dossiers["delta"]["contenu"]["notes_articles"]["dgi"]
    assert {CDPF.format(40), CDPF.format(17), CDPF.format(47)} <= _ids(dossiers["sahel"])


def test_article_81_seulement_si_penalites(dossiers):
    from app.dossier.articles import articles_applicables

    for d in dossiers.values():
        penalites = d["contenu"]["ecarts"]["penalites_indicatives"] > 0
        assert (CDPF.format(81) in _ids(d)) == penalites
    assert CDPF.format(81) not in {a["id"] for a in articles_applicables({"A1"}, "rouge", ["dgi"], penalites=False)}


def test_articles_douaniers_issus_de_la_loi_2008_34():
    from app.dossier.articles import DOUANE_23, DOUANE_35, DOUANE_383
    from app.rag.index import get_index

    for rid, num in ((DOUANE_23, "23"), (DOUANE_35, "35"), (DOUANE_383, "383")):
        rec = get_index().get(rid)
        assert rec["source_id"] == "code_douanes_2016"
        assert rec["section"].startswith("Loi n° 2008-34") and rec["section"].endswith(f"Article {num}")
    assert "Valeur en douane" in get_index().get(DOUANE_35)["section"] or "raisons de douter" in " ".join(
        get_index().get(DOUANE_35)["content"].split())


def test_pdf_conjoint_titre_parties_et_fiches(dossiers):
    from app.dossier import export

    textes = []
    origine = export._p

    def espion(texte, *a, **k):
        textes.append(str(texte))
        return origine(texte, *a, **k)

    export._p = espion
    try:
        assert export.pdf(dossiers["mobile"]).startswith(b"%PDF")
    finally:
        export._p = origine
    assert "Pré-dossier conjoint DGI – Douane" in textes
    assert any(t.startswith("Partie DGI") for t in textes) and any(t.startswith("Partie Douane") for t in textes)
    assert "Fiche de transmission — Douane → DGI" in textes and "Fiche de transmission — DGI → Douane" in textes


# ------------------------------------------------------------------ affichage cohérent avec la décision des règles
def _sources_frontend() -> str:
    fichiers = [f for d in ("app", "components", "lib") for f in (FRONTEND / d).rglob("*.ts*")]
    return "\n".join(f.read_text(encoding="utf-8") for f in fichiers)


def test_couleurs_de_la_categorie_et_aucun_seuil_sur_le_score():
    src = _sources_frontend()
    assert "couleurScore" not in src
    assert not re.search(r"score\s*>=?\s*\d", src)  # aucun seuil de couleur sur le score
    elements = (FRONTEND / "components/risque/elements.tsx").read_text(encoding="utf-8")
    for composant in ("JaugeScore", "PastilleScore"):
        corps = elements[elements.index(f"export function {composant}"):]
        corps = corps[:corps.index("\n}\n")]
        assert "categorie" in corps and "CATEGORIES[categorie]" in corps
    # chaque ligne de la liste et de la fiche transmet la catégorie décidée par les règles : la couleur en découle
    from app import services

    s = services.scores()
    lignes = services.liste(taille=500)["resultats"]
    assert all(r["categorie"] == s.set_index("id").categorie[r["id"]] for r in lignes)


def test_aucune_entreprise_grise_en_facilitation():
    from app import services

    f = services.facilitation()["entreprises"]
    assert f and {e["categorie"] for e in f} == {"vert"}


def test_tri_par_defaut_categorie_puis_priorite():
    from app import services

    ordre = {"rouge": 0, "orange": 1, "gris": 2, "vert": 3}
    lignes = []
    for page in range(1, 6):
        lignes += services.liste(page=page, taille=500)["resultats"]
    assert len(lignes) == len(services.scores())
    cats = [ordre[r["categorie"]] for r in lignes]
    assert cats == sorted(cats)  # aucune rouge derrière une orange, une grise ou une verte
    for c in ordre.values():  # priorité décroissante à l'intérieur de chaque catégorie
        p = [r["priorite"] for r in lignes if ordre[r["categorie"]] == c]
        assert p == sorted(p, reverse=True)
    assert [r["rang"] for r in lignes] == list(range(1, len(lignes) + 1))
    assert all(r["categorie"] == "rouge" for r in services.statistiques()["top5"])


def test_type_de_dossier_dans_la_liste_et_la_fiche():
    from app import services

    douaniers = services.liste(type_="douanier", taille=500)["resultats"]
    assert douaniers and all(r["type_dossier"] == "douanier" for r in douaniers)
    assert services.fiche(_eid("Médina Trade SUARL"))["score"]["type_dossier"] == "douanier"
    par_admin = {x["type"]: x for x in services.statistiques()["alertes_par_administration"]}
    assert set(par_admin) == {"fiscal", "douanier", "conjoint"}
    s = services.scores()
    alertes = s[s.categorie.isin(["rouge", "orange"])]
    assert sum(x["rouges"] + x["oranges"] for x in par_admin.values()) == len(alertes)
    assert json.dumps(par_admin)  # sérialisable pour l'API
