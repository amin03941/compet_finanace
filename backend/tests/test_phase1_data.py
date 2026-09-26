"""Phase 1 : base fictive — volumes, identités comptables et entreprises vitrines (section 5)."""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import pytest

from data_gen import reference as ref
from data_gen.generate import generer

TVA = 0.19


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    d = tmp_path_factory.mktemp("gen")
    db_path, gt_path = d / "rasd_test.db", d / "gt.csv"
    stats = generer(db_path=db_path, gt_path=gt_path)
    con = sqlite3.connect(db_path)
    yield {"con": con, "gt": pd.read_csv(gt_path, keep_default_na=False), "stats": stats,
           "q": lambda sql, p=(): pd.read_sql(sql, con, params=p)}
    con.close()


def _id(base, nom: str) -> int:
    return int(base["q"]("SELECT id FROM entreprises WHERE raison_sociale = ?", (nom,)).id.iloc[0])


# --------------------------------------------------------------------------- volumes
def test_volumes_et_repartition(base):
    s, gt = base["stats"], base["gt"]
    actives = gt[gt.statut == "active"]
    assert len(actives) == 2000
    parts = actives.categorie.value_counts(normalize=True)
    assert abs(parts["honnete"] - 0.72) < 0.01
    assert abs(parts["honnete_ecart_explique"] - 0.17) < 0.01
    assert abs(parts["fraudeur"] - 0.11) < 0.01
    assert 45_000 <= s["declarations_douane"] <= 80_000
    assert 65_000 <= s["declarations_tva"] <= 72_000
    assert 5_500 <= s["declarations_annuelles"] <= 6_000
    assert 25_000 <= s["retenues_source"] <= 55_000
    assert 110_000 <= s["factures_electroniques"] <= 200_000
    assert 550 <= s["controles_historiques"] <= 650
    ent = base["q"]("SELECT * FROM entreprises WHERE statut = 'active'")
    imp = base["q"]("SELECT COUNT(DISTINCT entreprise_id) n FROM declarations_douane WHERE flux='import'").n.iloc[0]
    assert 0.50 <= imp / len(ent) <= 0.70
    assert 0.10 <= (ent.statut_export != "local").mean() <= 0.20


def test_schemas_de_fraude_tous_presents(base):
    gt = base["gt"]
    schemas = set(";".join(gt[gt.categorie == "fraudeur"].schemas).split(";"))
    assert {f"F{i}" for i in range(1, 9)} <= schemas
    pieges = set(gt[gt.categorie == "honnete_ecart_explique"].piege)
    assert pieges == {"stock", "periode", "equipement", "admission_temporaire", "export", "donnees_manquantes", "faible_marge"}


def test_verite_terrain_hors_base(base):
    tables = set(base["q"]("SELECT name FROM sqlite_master WHERE type='table'").name)
    assert "ground_truth" not in tables
    assert not any("categorie" in c for c in base["q"]("SELECT * FROM entreprises LIMIT 1").columns)


def test_donnees_fictives(base):
    ent = base["q"]("SELECT matricule_fiscal FROM entreprises")
    assert ent.matricule_fiscal.is_unique
    pers = base["q"]("SELECT * FROM personnes LIMIT 5")
    assert set(pers.columns) == {"id", "nom", "prenom"}  # aucun numéro d'identité
    sect = base["q"]("SELECT DISTINCT secteur_nat_code, secteur_libelle FROM entreprises")
    nat = ref.nomenclature_nat()
    assert all(nat[c] == l for c, l in zip(sect.secteur_nat_code, sect.secteur_libelle))


# --------------------------------------------------------------------------- identités comptables
def test_identite_achats_consommes(base):
    a = base["q"]("SELECT * FROM declarations_annuelles")
    consommes = a.stock_initial + a.achats_marchandises + a.achats_matieres - a.stock_final
    assert np.allclose(a.marge_brute, a.chiffre_affaires - consommes, atol=0.02)


def test_continuite_des_stocks(base):
    a = base["q"]("SELECT entreprise_id, annee, stock_initial, stock_final FROM declarations_annuelles ORDER BY 1, 2")
    a["suivant"] = a.groupby("entreprise_id").stock_initial.shift(-1)
    a["annee_suiv"] = a.groupby("entreprise_id").annee.shift(-1)
    ok = a.dropna()
    ok = ok[ok.annee_suiv == ok.annee + 1]
    assert np.allclose(ok.stock_final, ok.suivant, atol=0.01)


def test_marge_des_honnetes_conforme_au_secteur(base):
    gt = base["gt"].set_index("entreprise_id")
    a = base["q"]("""SELECT a.*, e.secteur_groupe FROM declarations_annuelles a JOIN entreprises e ON e.id = a.entreprise_id
                     WHERE e.statut = 'active'""")
    a = a[a.entreprise_id.map(gt.categorie) == "honnete"]
    for cle, s in ref.SECTEURS.items():
        if not s.b1_applicable:
            continue
        d = a[(a.secteur_groupe == cle)]
        cout = d.stock_initial + d.achats_marchandises + d.achats_matieres - d.stock_final
        d = d[cout > 0.2 * d.chiffre_affaires]
        if s.statut_export == "totalement exportatrice" or d.empty:
            continue
        marge = d.chiffre_affaires / cout[d.index] - 1
        assert abs(marge.median() - s.marge_mediane) < 2 * s.marge_sd, cle


def test_douane_base_tva_et_tva_import(base):
    d = base["q"]("SELECT * FROM declarations_douane WHERE flux = 'import'")
    taxable = d[(d.regime == "mise à la consommation") & (d.est_equipement == 0)]
    assert np.allclose(taxable.base_tva, taxable.valeur_cif_dt + taxable.droits_douane, atol=0.002)
    assert np.allclose(taxable.tva_import, taxable.base_tva * TVA, atol=0.002)
    assert np.allclose(taxable.droits_douane, taxable.valeur_cif_dt * taxable.taux_droits, atol=0.01 + taxable.valeur_cif_dt * 1e-6)
    suspensif = d[(d.regime != "mise à la consommation") | (d.est_equipement == 1)]
    assert (suspensif.tva_import == 0).all() and (suspensif.droits_douane == 0).all()
    cif = d.valeur_fob + d.fret + d.assurance
    assert np.allclose(cif, d.valeur_cif_dt, atol=0.005)


def test_indicateur_equipement_coherent_avec_annexe(base):
    d = base["q"]("SELECT DISTINCT code_sh, est_equipement FROM declarations_douane")
    for code, eq in zip(d.code_sh, d.est_equipement):
        assert bool(eq) == ref.est_equipement(code), code


def _annuel(base, sql):
    return base["q"](sql).set_index(["entreprise_id", "annee"])


def test_honnetes_tva_import_deduite_egale_payee(base):
    gt = base["gt"].set_index("entreprise_id")
    ded = base["q"]("SELECT entreprise_id, annee, mois, tva_deductible_import FROM declarations_tva")
    paye = base["q"]("""SELECT entreprise_id, CAST(strftime('%Y', date) AS INT) annee, CAST(strftime('%m', date) AS INT) mois,
                        SUM(tva_import) tva FROM declarations_douane WHERE flux='import' GROUP BY 1, 2, 3""")
    ded = ded[(ded.entreprise_id.map(gt.categorie) != "fraudeur") & (ded.entreprise_id.map(gt.statut) == "active")]
    tot_ded = ded.groupby("entreprise_id").tva_deductible_import.sum()
    tot_paye = paye.groupby("entreprise_id").tva.sum().reindex(tot_ded.index).fillna(0)
    # décalage d'un mois toléré : avec un décalage, la TVA de décembre 2025 est déduite en janvier 2026 (hors période)
    dec_2025 = paye[(paye.annee == 2025) & (paye.mois == 12)].set_index("entreprise_id").tva.reindex(tot_ded.index).fillna(0)
    assert (tot_ded <= tot_paye + 0.5).all()
    assert (tot_paye - tot_ded <= dec_2025 + 0.5).all()


def test_honnetes_tiers_inferieurs_au_ca(base):
    gt = base["gt"].set_index("entreprise_id")
    ca = _annuel(base, "SELECT entreprise_id, annee, SUM(ca_local_ht + ca_export_ht) ca FROM declarations_tva GROUP BY 1, 2").ca
    tej = _annuel(base, """SELECT beneficiaire_id entreprise_id, CAST(strftime('%Y', date) AS INT) annee, SUM(montant_brut) m
                           FROM retenues_source GROUP BY 1, 2""").m
    fac = _annuel(base, """SELECT emetteur_id entreprise_id, CAST(strftime('%Y', date) AS INT) annee, SUM(montant_ht) m
                           FROM factures_electroniques GROUP BY 1, 2""").m
    for serie in (tej, fac):
        df = pd.concat([serie.rename("m"), ca], axis=1).dropna()
        df = df[df.index.get_level_values(0).map(gt.categorie) != "fraudeur"]
        assert (df.m <= df.ca * 1.0 + 1).all()


def test_honnetes_encaissements_bancaires(base):
    gt = base["gt"].set_index("entreprise_id")
    tva = base["q"]("""SELECT entreprise_id, SUM(ca_local_ht) * 1.19 + SUM(ca_export_ht) ttc FROM declarations_tva
                       GROUP BY 1""").set_index("entreprise_id").ttc
    banque = base["q"]("SELECT entreprise_id, SUM(total_encaissements) b FROM encaissements_bancaires GROUP BY 1").set_index("entreprise_id").b
    df = pd.concat([tva, banque], axis=1).dropna()
    df = df[(df.index.map(gt.categorie) == "honnete") & (df.ttc > 10_000)]
    ratio = df.b / df.ttc
    assert ratio.between(0.97, 1.23).all(), ratio.describe()


# --------------------------------------------------------------------------- vitrines
def test_sahel_electro_valeurs_exactes_2025(base):
    q, sid = base["q"], _id(base, "Sahel Électro SARL")
    imp = q("""SELECT SUM(base_tva) base, SUM(tva_import) tva FROM declarations_douane
               WHERE entreprise_id=? AND flux='import' AND strftime('%Y', date)='2025'""", (sid,)).iloc[0]
    assert imp.base == pytest.approx(3_000_000, abs=0.01)
    assert imp.tva == pytest.approx(570_000, abs=0.01)
    a = q("SELECT * FROM declarations_annuelles WHERE entreprise_id=? AND annee=2025", (sid,)).iloc[0]
    assert a.stock_final - a.stock_initial == pytest.approx(200_000, abs=0.01)
    assert a.chiffre_affaires == pytest.approx(800_000, abs=0.01)
    assert a.achats_marchandises == pytest.approx(3_000_000, abs=0.01)
    t = q("SELECT SUM(tva_deductible_import) d, SUM(ca_local_ht) ca FROM declarations_tva WHERE entreprise_id=? AND annee=2025", (sid,)).iloc[0]
    assert t.d == pytest.approx(610_000, abs=0.01)
    assert t.ca == pytest.approx(800_000, abs=0.01)
    tej = q("SELECT SUM(montant_brut) m FROM retenues_source WHERE beneficiaire_id=? AND strftime('%Y', date)='2025'", (sid,)).m.iloc[0]
    assert tej == pytest.approx(1_200_000, abs=0.01)
    # calcul de référence de la section 5.4 (écart répété sur 3 ans)
    cout = 3_000_000 - 200_000
    assert round(cout * 1.20 - 800_000) == 2_560_000
    for annee in (2023, 2024, 2025):
        a = q("SELECT * FROM declarations_annuelles WHERE entreprise_id=? AND annee=?", (sid, annee)).iloc[0]
        cout = a.stock_initial + a.achats_marchandises - a.stock_final
        assert a.chiffre_affaires < 0.35 * cout


def test_sahel_gerant_lie_a_une_societe_radiee_redressee(base):
    q, sid = base["q"], _id(base, "Sahel Électro SARL")
    liees = q("""SELECT e.raison_sociale, e.statut, c.redressement FROM roles r1
                 JOIN roles r2 ON r1.personne_id = r2.personne_id AND r2.entreprise_id != r1.entreprise_id
                 JOIN entreprises e ON e.id = r2.entreprise_id
                 JOIN controles_historiques c ON c.entreprise_id = e.id
                 WHERE r1.entreprise_id = ?""", (sid,))
    assert ((liees.statut == "radiée") & (liees.redressement == 1)).any()


def test_cap_bon_piege_stock(base):
    q, cid = base["q"], _id(base, "Cap Bon Distribution SARL")
    a = q("SELECT * FROM declarations_annuelles WHERE entreprise_id=? AND annee=2025", (cid,)).iloc[0]
    assert a.stock_final - a.stock_initial == pytest.approx(2_300_000, abs=0.01)
    assert a.chiffre_affaires == pytest.approx(800_000, abs=0.01)
    imp = q("SELECT SUM(base_tva) b FROM declarations_douane WHERE entreprise_id=? AND flux='import' AND strftime('%Y', date)='2025'", (cid,)).b.iloc[0]
    assert imp == pytest.approx(3_000_000, abs=0.01)
    tej = q("SELECT SUM(montant_brut) m FROM retenues_source WHERE beneficiaire_id=? AND strftime('%Y', date)='2025'", (cid,)).m.iloc[0]
    assert tej == pytest.approx(780_000, abs=0.01)


def test_djerba_piege_equipement(base):
    q, did = base["q"], _id(base, "Djerba Industries SA")
    eq = q("""SELECT SUM(valeur_cif_dt) v, MIN(est_equipement) tous FROM declarations_douane
              WHERE entreprise_id=? AND est_equipement=1 AND strftime('%Y', date)='2025'""", (did,)).iloc[0]
    assert eq.v == pytest.approx(3_000_000, abs=0.01) and eq.tous == 1
    a = q("SELECT chiffre_affaires FROM declarations_annuelles WHERE entreprise_id=? AND annee=2025", (did,)).iloc[0]
    assert a.chiffre_affaires == pytest.approx(800_000, abs=0.01)


def test_nour_textile_totalement_exportatrice_coherente(base):
    q, nid = base["q"], _id(base, "Nour Textile SA")
    regimes = set(q("SELECT DISTINCT regime FROM declarations_douane WHERE entreprise_id=?", (nid,)).regime)
    assert regimes == {"admission temporaire", "réexportation"}
    exp = q("SELECT SUM(valeur_cif_dt) v FROM declarations_douane WHERE entreprise_id=? AND flux='export'", (nid,)).v.iloc[0]
    decl = q("SELECT SUM(ca_export_ht) v FROM declarations_tva WHERE entreprise_id=?", (nid,)).v.iloc[0]
    assert decl == pytest.approx(exp, rel=1e-6)
    assert decl == pytest.approx(6_200_000 + 6_500_000 + 6_800_000, abs=1)


def test_medina_trade_sous_evaluation(base):
    q, mid = base["q"], _id(base, "Médina Trade SUARL")
    tv = q("""SELECT valeur_cif_dt / quantite pu FROM declarations_douane WHERE entreprise_id=? AND code_sh='85287200'
              AND pays_origine='Chine' AND strftime('%Y', date)='2025'""", (mid,))
    assert len(tv) == 14
    refp = q("SELECT prix_unitaire_median FROM prix_reference WHERE code_sh='85287200' AND pays_origine='Chine'").iloc[0, 0]
    assert 0.38 < (tv.pu / refp).median() < 0.52


def test_carrousel_vitrine(base):
    q = base["q"]
    ids = [_id(base, n) for n in ("Carthage Négoce SARL", "Atlas Services SUARL", "Yasmine Distribution SARL")]
    for a, b in zip(ids, ids[1:] + ids[:1]):
        n = q("""SELECT COUNT(DISTINCT strftime('%m', date)) n FROM factures_electroniques
                 WHERE emetteur_id=? AND client_id=? AND strftime('%Y', date)='2025'""", (a, b)).n.iloc[0]
        assert n >= 6
    manquants = q("SELECT COUNT(*) n FROM declarations_tva WHERE entreprise_id=? AND deposee=0", (ids[1],)).n.iloc[0]
    assert manquants >= 6
