"""Calculs du pré-dossier (section 7.1) — Python déterministe. Le LLM ne calcule JAMAIS :
tous les montants viennent d'ici et lui sont passés en JSON. Chaque montant affiche sa
formule et ses hypothèses.
"""
from __future__ import annotations

import math
from datetime import date

from .. import fmt
from ..risk.features import Contexte

MENTION = "Estimation indicative, à confirmer par la procédure contradictoire."


def _param(ctx: Contexte, cle: str, defaut: float) -> tuple[float, bool, str]:
    t = ctx.tables["parametres"]
    row = t[t.cle == cle]
    if len(row):
        r = row.iloc[0]
        return float(r.valeur), bool(r.a_verifier), str(r.source)
    return defaut, True, "Valeur par défaut — à vérifier"


def _mois_de_retard(echeance: date, reference: date) -> int:
    """Nombre de mois ou fraction de mois entre l'échéance et la date de référence (article 81)."""
    if reference <= echeance:
        return 0
    mois = (reference.year - echeance.year) * 12 + (reference.month - echeance.month)
    if reference.day > echeance.day:
        mois += 1
    return max(mois, 1)


def calculer(ctx: Contexte, eid: int, indices: list[dict], reference: date | None = None) -> dict:
    """Écarts chiffrés d'une entreprise à partir des indices déclenchés (montants déterministes)."""
    reference = reference or date.today()
    taux_tva, tva_a_verif, tva_src = _param(ctx, "taux_tva_normal", 0.19)
    taux_is, is_a_verif, is_src = _param(ctx, "taux_is", 0.15)
    taux_pen, _, pen_src = _param(ctx, "taux_penalite_retard_mensuel", 0.0125)
    dec = {i["code"]: i for i in indices if i["declenchee"]}
    sect = ctx.ent.at[eid, "secteur_groupe"]
    marge_ref = ctx.marge_mediane_secteur(sect)
    lignes: list[dict] = []
    hypotheses: list[str] = []
    annee = max((i["annee"] for i in dec.values()), default=int(ctx.annuel.loc[eid].index.max()))

    # --- ventes omises : reconstitution par les achats (B1) prioritaire, sinon données de tiers
    ecart_ventes, base_ventes = 0.0, None
    if "B1" in dec:
        a = ctx.annuel.loc[(eid, dec["B1"]["annee"])]
        annee = int(dec["B1"]["annee"])
        cout, ca = float(a.cout_net), float(a.ca_decl)
        ca_recon = cout * (1 + marge_ref)
        ecart_ventes = max(0.0, ca_recon - ca)
        base_ventes = "B1"
        lignes += [
            {"cle": "cout_ventes", "libelle": "Coût des ventes net", "montant": cout,
             "formule": f"{fmt.dt(a.imports_revente)} importations à revendre + {fmt.dt(a.achats_locaux)} achats locaux "
                        f"− {fmt.dt(a.delta_stock)} de variation de stock",
             "source": "Douane (hors équipements et régimes suspensifs) + déclaration annuelle"},
            {"cle": "ca_reconstitue", "libelle": "Chiffre d'affaires reconstitué", "montant": ca_recon,
             "formule": f"{fmt.dt(cout)} × (1 + {fmt.pct(marge_ref)} de marge médiane du secteur)",
             "source": "Référentiel sectoriel (marge médiane)"},
            {"cle": "ca_declare", "libelle": "Chiffre d'affaires déclaré", "montant": ca, "formule": f"Déclarations de TVA {annee}",
             "source": "Déclarations mensuelles de TVA"},
            {"cle": "ecart_ca", "libelle": "Écart de chiffre d'affaires", "montant": ecart_ventes,
             "formule": f"{fmt.dt(ca_recon)} − {fmt.dt(ca)}", "source": "Calcul"},
        ]
        hypotheses.append(f"Marge du secteur : médiane de référence de {fmt.pct(marge_ref)} appliquée au coût des ventes net.")
    else:
        for code, champ, lib in (("A1", "tej_recu", "paiements attestés par les clients (TEJ)"),
                                 ("A2", "factures_emises", "factures El Fatoora émises"),
                                 ("B4", "encaissements", "encaissements bancaires")):
            if code in dec:
                a = ctx.annuel.loc[(eid, dec[code]["annee"])]
                annee = int(dec[code]["annee"])
                base = float(a[champ]) if code != "B4" else float(a.encaissements) / (1.2 * (1 + taux_tva))
                ca = float(a.ca_decl)
                ecart = max(0.0, base - ca)
                if ecart > ecart_ventes:
                    ecart_ventes, base_ventes = ecart, code
                    lignes = [
                        {"cle": "base_tiers", "libelle": f"Montant attesté par les tiers ({lib})", "montant": base,
                         "formule": "Encaissements ÷ (1,2 × 1,19), borne haute du ratio normal" if code == "B4" else f"Σ {lib} {annee}",
                         "source": lib.capitalize()},
                        {"cle": "ca_declare", "libelle": "Chiffre d'affaires déclaré", "montant": ca, "formule": f"Déclarations de TVA {annee}",
                         "source": "Déclarations mensuelles de TVA"},
                        {"cle": "ecart_ca", "libelle": "Écart de chiffre d'affaires", "montant": ecart,
                         "formule": f"{fmt.dt(base)} − {fmt.dt(ca)}", "source": "Calcul"},
                    ]
    tva_omise = ecart_ventes * taux_tva
    if ecart_ventes > 0:
        lignes.append({"cle": "tva_ventes_omises", "libelle": "TVA sur ventes omises", "montant": tva_omise,
                       "formule": f"{fmt.dt(ecart_ventes)} × {fmt.pct(taux_tva, 0)}", "source": tva_src, "a_verifier": tva_a_verif})
    # --- TVA déduite en trop (A3)
    tva_trop = 0.0
    if "A3" in dec:
        a = ctx.annuel.loc[(eid, dec["A3"]["annee"])]
        paye = max(float(a.tva_import_payee), float(a.tva_import_payee_decalee))
        tva_trop = max(0.0, float(a.tva_deductible_import) - paye)
        lignes.append({"cle": "tva_deduite_trop", "libelle": "TVA déduite en trop à l'import", "montant": tva_trop,
                       "formule": f"{fmt.dt(a.tva_deductible_import)} déduits − {fmt.dt(paye)} payés en douane",
                       "source": "Déclarations de TVA / douane (règle A3)"})
    # --- autres enjeux fiscaux déjà chiffrés par les règles (DGI)
    tva_a4 = 0.0
    if "A4" in dec and dec["A4"]["montant_en_jeu"] > 0:
        tva_a4 = dec["A4"]["montant_en_jeu"]
        lignes.append({"cle": "enjeu_A4", "libelle": "TVA sur exportations non justifiées", "montant": tva_a4,
                       "formule": "Montant en jeu de l'indice A4", "source": "Règle A4"})
    if base_ventes is None and ("A5" in dec or "B3" in dec):  # TVA non reversée
        code = "B3" if "B3" in dec else "A5"
        tva_omise = dec[code]["montant_en_jeu"]
        lignes.append({"cle": "tva_non_reversee", "libelle": "TVA non reversée (estimation)", "montant": tva_omise,
                       "formule": f"Montant en jeu de l'indice {code}", "source": f"Règle {code}"})
    for l in lignes:
        l["partie"] = "dgi"
    total_tva = tva_omise + tva_trop
    total_dgi = total_tva + tva_a4

    # --- partie douane : sous-évaluation (B2) détaillée déclaration par déclaration, avantages revendus (C2)
    lignes_douane: list[dict] = []
    ecart_valeur = droits = tva_import = 0.0
    if "B2" in dec:
        from ..risk.rules import REGLES_PAR_CODE

        annee_b2 = int(dec["B2"]["annee"])
        d = REGLES_PAR_CODE["B2"]._lignes(ctx)
        d = d[(d.entreprise_id == eid) & (d.date.dt.year == annee_b2)]
        ecarts = (d.prix_unitaire_median * d.quantite - d.valeur_cif_dt).clip(lower=0)
        droits_l = ecarts * d.taux_droits
        valeur_ref, valeur_decl = float((d.prix_unitaire_median * d.quantite).sum()), float(d.valeur_cif_dt.sum())
        ecart_valeur, droits = float(ecarts.sum()), float(droits_l.sum())
        tva_import = float(((ecarts + droits_l) * taux_tva).sum())
        taux_moyen = droits / ecart_valeur if ecart_valeur else 0.0
        n_decl = int(d.numero_declaration.nunique())
        lignes_douane += [
            {"cle": "valeur_reference", "libelle": "Valeur au prix de référence", "montant": valeur_ref,
             "formule": f"Σ prix de référence médian × quantité ({n_decl} déclarations {annee_b2})",
             "source": "Référentiel de prix (même produit, même origine)"},
            {"cle": "valeur_declaree", "libelle": "Valeur déclarée en douane", "montant": valeur_decl,
             "formule": f"Σ valeur CIF déclarée ({n_decl} déclarations {annee_b2})", "source": "Déclarations en douane"},
            {"cle": "ecart_valeur", "libelle": "Écart de valeur", "montant": ecart_valeur,
             "formule": "Σ (prix de référence − prix déclaré) × quantité", "source": "Calcul"},
            {"cle": "droits_eludes", "libelle": "Droits de douane éludés", "montant": droits,
             "formule": f"{fmt.dt(ecart_valeur)} × taux de droits de chaque déclaration ({fmt.pct(taux_moyen)} en moyenne pondérée)",
             "source": "Tarif appliqué dans les déclarations en douane"},
            {"cle": "tva_import_eludee", "libelle": "TVA à l'import éludée", "montant": tva_import,
             "formule": f"({fmt.dt(ecart_valeur)} + {fmt.dt(droits)}) × {fmt.pct(taux_tva, 0)}", "source": tva_src,
             "a_verifier": tva_a_verif},
        ]
    enjeu_c2 = 0.0
    if "C2" in dec and dec["C2"]["montant_en_jeu"] > 0:
        enjeu_c2 = dec["C2"]["montant_en_jeu"]
        lignes_douane.append({"cle": "enjeu_C2", "libelle": "TVA suspendue sur équipements exonérés revendus", "montant": enjeu_c2,
                              "formule": "Montant en jeu de l'indice C2", "source": "Règle C2"})
    total_douane = droits + tva_import + enjeu_c2
    for l in lignes_douane:
        l["partie"] = "douane"

    # --- totaux séparés : chaque administration perçoit ses propres droits et taxes
    if total_dgi > 0:
        lignes.append({"cle": "total_dgi", "libelle": "Total — impôts perçus par la DGI", "montant": total_dgi,
                       "formule": " + ".join(fmt.dt(x) for x in (tva_omise, tva_trop, tva_a4) if x), "source": "Calcul",
                       "total": True, "partie": "dgi"})
    if total_douane > 0:
        lignes_douane.append({"cle": "total_douane", "libelle": "Total — droits et taxes perçus par la douane",
                              "montant": total_douane,
                              "formule": " + ".join(fmt.dt(x) for x in (droits, tva_import, enjeu_c2) if x), "source": "Calcul",
                              "total": True, "partie": "douane"})
    total = total_dgi + total_douane

    # --- IS et pénalités (DGI) : indicatifs, seulement s'il y a des ventes omises ou de la TVA due
    is_indicatif = ecart_ventes * marge_ref * taux_is
    if is_indicatif > 0:
        lignes.append({"cle": "is_indicatif", "libelle": "Impôt sur les sociétés (indicatif)", "montant": is_indicatif,
                       "formule": f"{fmt.dt(ecart_ventes)} × {fmt.pct(marge_ref)} × {fmt.pct(taux_is, 0)}",
                       "source": is_src, "a_verifier": is_a_verif, "indicatif": True, "partie": "dgi"})
    penalites, mois_moyens = 0.0, 0.0
    if total_tva > 0:
        # TVA supposée exigible mois par mois sur l'année ; échéance le 28 du mois suivant
        parts = []
        for m in range(1, 13):
            ech = date(annee + (m == 12), m % 12 + 1, 28)
            parts.append(_mois_de_retard(ech, reference))
        mois_moyens = sum(parts) / 12
        penalites = sum(total_tva / 12 * taux_pen * n for n in parts)
        lignes.append({"cle": "penalites", "libelle": "Pénalités de retard (indicatives)", "montant": penalites,
                       "formule": f"{fmt.pct(taux_pen, 2)} par mois ou fraction de mois × {mois_moyens:.1f} mois en moyenne "
                                  f"(échéances {annee} → {fmt.date_fr(reference)})".replace(".", ","),
                       "source": pen_src, "indicatif": True, "partie": "dgi",
                       "article": "cdpf_2024__code_des_droits_et_procedures_fiscaux_article_81"})
    lignes += lignes_douane
    cles = {l["cle"] for l in lignes}
    # hypothèses : uniquement celles qui correspondent à une ligne réellement calculée, rangées par administration
    hyp = {"dgi": list(hypotheses), "douane": []}
    tva = f"Taux de TVA de {fmt.pct(taux_tva, 0)} : paramètre à vérifier dans le code de la TVA (non indexé)."
    if "tva_ventes_omises" in cles:
        hyp["dgi"].append(tva)
    if "is_indicatif" in cles:
        hyp["dgi"].append(f"Taux d'IS de {fmt.pct(taux_is, 0)} : paramètre à vérifier dans le code de l'IRPP et de l'IS (non indexé).")
    if "penalites" in cles:
        hyp["dgi"].append("Pénalités : 1,25 % par mois ou fraction de mois (article 81 du code des droits et procédures fiscaux), "
                          f"calculées jusqu'au {fmt.date_fr(reference)} à titre indicatif.")
    if "tva_import_eludee" in cles:
        hyp["douane"].append(tva)
    if "ecart_valeur" in cles:
        hyp["douane"] += ["Prix de référence : médiane des prix unitaires déclarés pour le même produit (code SH) et la même origine.",
                          "Droits éludés : taux de droits figurant sur chaque déclaration en douane concernée."]
    hypotheses = list(dict.fromkeys(hyp["dgi"] + hyp["douane"]))
    for l in lignes:
        l["montant"] = round(float(l["montant"]), 2)
        l["montant_affiche"] = fmt.dt(l["montant"])
    return {
        "annee": annee, "lignes": lignes, "base_ventes": base_ventes, "ecart_ca": round(ecart_ventes, 2),
        "tva_ventes_omises": round(tva_omise, 2), "tva_deduite_en_trop": round(tva_trop, 2),
        "total_tva": round(total_tva, 2), "total_dgi": round(total_dgi, 2), "total_douane": round(total_douane, 2),
        "ecart_valeur": round(ecart_valeur, 2), "droits_eludes": round(droits, 2), "tva_import_eludee": round(tva_import, 2),
        "total_estime": round(total, 2), "is_indicatif": round(is_indicatif, 2), "penalites_indicatives": round(penalites, 2),
        "parametres": {"taux_tva": taux_tva, "taux_is": taux_is, "taux_penalite_mensuel": taux_pen, "marge_mediane_secteur": marge_ref},
        "hypotheses": hypotheses, "hypotheses_par_partie": hyp, "mention": MENTION, "date_reference": reference.isoformat(),
    }


def montants_autorises(calc: dict) -> set[str]:
    """Montants (formatés) que la rédaction a le droit de citer."""
    vals = {calc.get(k, 0.0) for k in ("ecart_ca", "tva_ventes_omises", "tva_deduite_en_trop", "total_tva", "total_dgi",
                                       "total_douane", "ecart_valeur", "droits_eludes", "tva_import_eludee", "total_estime",
                                       "is_indicatif", "penalites_indicatives")}
    vals |= {l["montant"] for l in calc["lignes"]}
    out = set()
    for v in vals:
        if v and not math.isnan(v):
            out.add(fmt.nombre(v).replace(" ", " "))
            out.add(fmt.nombre(round(v)).replace(" ", " "))
            out.add(fmt.nombre(math.floor(v)).replace(" ", " "))  # centimes tronqués : même montant
    return out
