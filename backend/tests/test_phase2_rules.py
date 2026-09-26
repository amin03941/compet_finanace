"""Phase 2 : tests unitaires de chaque règle (section 6.2) et de la décision (section 6.3)."""
from __future__ import annotations

from datetime import date

import pytest

from app.risk.rules import REGLES_PAR_CODE
from app.risk.scoring import decider, force_indices, montant_en_jeu

from .fabrique import Fabrique


def _eval(ctx, code):
    return REGLES_PAR_CODE[code].evaluer(ctx)


def _base(f: Fabrique, eid: int, ca: float = 800_000, **kw) -> Fabrique:
    """Entreprise cohérente sur 3 ans (déclarations annuelles et TVA)."""
    f.entreprise(eid, **kw)
    for y in (2023, 2024, 2025):
        f.annuelle(eid, y, ca=ca, achats=ca / 1.2).annee_tva(eid, y, ca_local=ca)
    return f


# ------------------------------------------------------------------ niveau A
def test_A1_paiements_clients_superieurs_au_ca():
    f = _base(Fabrique(), 1).entreprise(9)
    _base(f, 2)
    for q in range(4):
        f.tej_(9, 1, date(2025, 3 * q + 3, 25), 300_000)   # 1 200 000 attestés pour 800 000 déclarés
        f.tej_(9, 2, date(2025, 3 * q + 3, 25), 195_000)   # 780 000 : cohérent
    r = _eval(f.contexte(), "A1")
    assert r.at[1, "declenchee"] and r.at[1, "montant"] == pytest.approx(400_000 * 0.19)
    assert r.at[1, "valeur"] == pytest.approx(1.5)
    assert not r.at[2, "declenchee"]
    phrase = REGLES_PAR_CODE["A1"].phrase(r.loc[1].to_dict(), f.contexte(), 1)
    assert "1 200 000 DT" in phrase and "800 000 DT" in phrase


def test_A2_factures_emises_superieures_au_ca():
    f = _base(Fabrique(), 1).entreprise(9)
    _base(f, 2)
    for m in range(1, 13):
        f.facture(1, 9, date(2025, m, 15), 90_000)   # 1 080 000 > 800 000 × 1,05
        f.facture(2, 9, date(2025, m, 15), 60_000)   # 720 000 : cohérent
    r = _eval(f.contexte(), "A2")
    assert r.at[1, "declenchee"] and not r.at[2, "declenchee"]


def test_A3_tva_deduite_import_superieure_a_payee_avec_decalage_tolere():
    f = Fabrique()
    for eid, ded in ((1, 610_000), (2, 575_000), (3, 570_000)):
        f.entreprise(eid)
        for y in (2023, 2024):
            f.annee_tva(eid, y, ca_local=800_000, ded_import=0)
        f.annee_tva(eid, 2025, ca_local=800_000, ded_import=ded)
        for m in range(1, 13):
            f.import_(eid, date(2025, m, 10), 250_000)   # TVA payée : 570 000
    r = _eval(f.contexte(), "A3")
    assert r.at[1, "declenchee"] and r.at[1, "montant"] == pytest.approx(40_000)
    assert not r.at[2, "declenchee"]  # écart de 5 000 DT < 2 %
    assert not r.at[3, "declenchee"]


def test_A4_fausses_exportations_et_services_neutralises():
    f = Fabrique()
    f.entreprise(1).annee_tva(1, 2025, ca_local=100_000, ca_export=1_500_000)
    f.import_(1, date(2025, 6, 1), 1_000_000, flux="export", regime="export définitif")
    f.entreprise(2, secteur="conseil").annee_tva(2, 2025, ca_local=100_000, ca_export=900_000)  # export de services
    r = _eval(f.contexte(), "A4")
    assert r.at[1, "declenchee"] and r.at[1, "montant"] == pytest.approx(500_000 * 0.19)
    assert not r.at[2, "declenchee"]


def test_A5_defaut_de_declaration():
    f = Fabrique()
    f.entreprise(1).annee_tva(1, 2025, ca_local=600_000, non_deposes=(3, 4, 5, 6, 7)).banque_annee(1, 2025, 840_000)
    f.entreprise(2).annee_tva(2, 2025, ca_local=600_000, non_deposes=(3, 4)).banque_annee(2, 2025, 840_000)
    r = _eval(f.contexte(), "A5")
    assert r.at[1, "declenchee"] and r.at[1, "valeur"] == 5
    assert not r.at[2, "declenchee"]


# ------------------------------------------------------------------ niveau B
def test_B1_marge_impossible_sur_deux_ans_et_stock_neutralise():
    f = Fabrique()
    for eid in range(10, 30):  # population de référence du secteur (marges normales)
        _base(f, eid)
    f.entreprise(1)  # Sahel : coût 2,8 M, CA 0,8 M, 3 ans
    stock = 300_000
    for y, imp, ca, ds in ((2023, 2_400_000, 700_000, 100_000), (2024, 2_700_000, 750_000, 150_000), (2025, 3_000_000, 800_000, 200_000)):
        f.annuelle(1, y, ca=ca, achats=imp, s0=stock, s1=stock + ds).annee_tva(1, y, ca_local=ca)
        stock += ds
        f.import_(1, date(y, 6, 1), imp)
    f.entreprise(2)  # Cap Bon : même écart brut, mais stock +2,3 M (nouvel entrepôt)
    f.annuelle(2, 2024, ca=790_000, achats=658_333.33).annee_tva(2, 2024, ca_local=790_000)
    f.annuelle(2, 2025, ca=800_000, achats=3_000_000, s0=0, s1=2_300_000).annee_tva(2, 2025, ca_local=800_000)
    f.import_(2, date(2025, 11, 1), 3_000_000)
    ctx = f.contexte()
    r = _eval(ctx, "B1")
    assert r.at[1, "declenchee"] and len(r.at[1, "annees"]) == 3
    assert r.at[1, "montant"] == pytest.approx((2_800_000 * 1.2 - 800_000) * 0.19)  # 486 400 DT
    assert not r.at[2, "declenchee"]
    assert not r.loc[10:29, "declenchee"].any()


def test_B1_une_seule_annee_ne_suffit_pas():
    f = Fabrique()
    for eid in range(10, 30):
        _base(f, eid)
    f.entreprise(1).annuelle(1, 2025, ca=500_000, achats=900_000).annee_tva(1, 2025, ca_local=500_000)
    f.import_(1, date(2025, 3, 1), 900_000)
    assert not _eval(f.contexte(), "B1").at[1, "declenchee"]


def test_B2_sous_evaluation_repetee():
    f = Fabrique().prix_ref("85287200", "Chine", 810.0, 700.0, 950.0)
    f.entreprise(1).entreprise(2)
    for k in range(3):
        f.import_(1, date(2025, k + 1, 5), 36_450, code_sh="85287200", qte=100)   # 364,5 DT/u = 45 % de 810
    for k in range(2):
        f.import_(2, date(2025, k + 1, 5), 36_450, code_sh="85287200", qte=100)   # 2 déclarations seulement
    f.import_(2, date(2025, 5, 5), 80_000, code_sh="85287200", qte=100)           # 800 DT/u : normal
    r = _eval(f.contexte(), "B2")
    assert r.at[1, "declenchee"] and r.at[1, "valeur"] == pytest.approx(0.45)
    assert not r.at[2, "declenchee"]


def test_B3_carrousel_avec_maillon_defaillant():
    f = Fabrique()
    for eid in (1, 2, 3, 4, 5, 6):
        f.entreprise(eid).annee_tva(eid, 2025, ca_local=2_500_000, non_deposes=(3, 4, 5, 6) if eid == 2 else ())
    for m in (3, 4, 5, 6, 7, 8):
        for a, b in ((1, 2), (2, 3), (3, 1), (4, 5), (5, 6), (6, 4)):  # 4-5-6 : cycle sans maillon défaillant
            f.facture(a, b, date(2025, m, 10), 350_000)
    r = _eval(f.contexte(), "B3")
    assert r.loc[[1, 2, 3], "declenchee"].all()
    assert not r.loc[[4, 5, 6], "declenchee"].any()
    assert r.at[2, "montant"] == pytest.approx(6 * 350_000 * 0.19)


def test_B4_encaissements_tres_superieurs_au_ca():
    f = Fabrique()
    f.entreprise(1).annee_tva(1, 2025, ca_local=800_000).banque_annee(1, 2025, 4_000_000)
    f.entreprise(2).annee_tva(2, 2025, ca_local=800_000).banque_annee(2, 2025, 800_000 * 1.19 * 1.1)
    r = _eval(f.contexte(), "B4")
    assert r.at[1, "declenchee"] and not r.at[2, "declenchee"]


# ------------------------------------------------------------------ niveau C
def test_C1_fractionnement():
    f = Fabrique().entreprise(1).entreprise(2)
    for j in range(6):
        f.import_(1, date(2025, 4, 2 + j), 2_500, fournisseur="X")        # 6 déclarations en 6 jours
        f.import_(2, date(2025, 4, 1 + 5 * j), 2_500, fournisseur="X")    # étalées sur un mois
    r = _eval(f.contexte(), "C1")
    assert r.at[1, "declenchee"] and r.at[1, "valeur"] == 6
    assert not r.at[2, "declenchee"]


def test_C2_revente_equipement_exonere():
    f = Fabrique().entreprise(1).entreprise(2).entreprise(9)
    f.import_(1, date(2025, 2, 1), 500_000, equip=True, code_sh="84771000")
    f.facture(1, 9, date(2025, 6, 1), 550_000, code_sh="84771000")
    f.import_(2, date(2025, 2, 1), 500_000, equip=True, code_sh="84771000")   # machine gardée
    r = _eval(f.contexte(), "C2")
    assert r.at[1, "declenchee"] and not r.at[2, "declenchee"]


def test_C3_credit_structurel_hors_exportateurs():
    f = Fabrique()
    f.entreprise(1).annee_tva(1, 2025, ca_local=800_000, ded_import=600_000, remboursement_decembre=100_000)
    f.entreprise(2, secteur="textile_export", statut_export="totalement exportatrice")
    f.annee_tva(2, 2025, ca_export=5_000_000, ded_local=200_000, remboursement_decembre=100_000)
    r = _eval(f.contexte(), "C3")
    assert r.at[1, "declenchee"] and not r.at[2, "declenchee"]


def test_C4_reseau_a_risque():
    f = Fabrique()
    f.entreprise(1).entreprise(2).entreprise(3, statut="radiée", date_radiation=date(2024, 3, 31)).entreprise(4)
    f.role(1, 100).role(3, 100).role(2, 200).role(4, 300).controle(3, True)
    f.entreprise(5, date_creation=date(2025, 3, 1)).annee_tva(5, 2025, ca_local=0).banque_annee(5, 2025, 900_000)
    r = _eval(f.contexte(), "C4")
    assert r.at[1, "declenchee"] and not r.at[2, "declenchee"] and r.at[5, "declenchee"]
    assert "radiée" in REGLES_PAR_CODE["C4"].phrase(r.loc[1].to_dict(), f.contexte(), 1)


def test_C5_importations_sans_personnel():
    f = Fabrique().entreprise(1, effectif=1).entreprise(2, effectif=12)
    for eid in (1, 2):
        f.annee_tva(eid, 2025, ca_local=900_000).import_(eid, date(2025, 5, 1), 600_000)
    r = _eval(f.contexte(), "C5")
    assert r.at[1, "declenchee"] and not r.at[2, "declenchee"]


# ------------------------------------------------------------------ décision
def _ind(code, niveau, montant=0.0):
    return {"code": code, "niveau": niveau, "declenchee": True, "montant_en_jeu": montant}


def test_decision_categories():
    assert decider([_ind("A1", "A", 76_000)], False)[0] == "rouge"
    assert decider([_ind("A3", "A", 8_000)], False)[0] == "orange"          # A de faible montant compte comme un B
    assert decider([_ind("B1", "B"), _ind("B4", "B")], False)[0] == "rouge"
    assert decider([_ind("B2", "B"), _ind("C4", "C"), _ind("C5", "C")], False)[0] == "rouge"
    assert decider([_ind("B2", "B")], False)[0] == "orange"
    assert decider([_ind("C4", "C"), _ind("C5", "C")], False)[0] == "orange"
    assert decider([_ind("C4", "C")], False)[0] == "vert"                    # un signal C ne suffit jamais seul
    assert decider([], True)[0] == "gris"
    assert decider([_ind("A1", "A", 90_000)], True)[0] == "rouge"            # la preuve de tiers prime


def test_montant_en_jeu_sans_double_comptage():
    ind = [_ind("A1", "A", 76_000), _ind("B1", "B", 486_400), _ind("B4", "B", 414_000), _ind("A3", "A", 40_000),
           _ind("C4", "C")]
    assert montant_en_jeu(ind) == pytest.approx(526_400)
    s, poids = force_indices(ind)
    assert 0 < s < 1 and set(poids) == {"A1", "B1", "B4", "A3", "C4"}
