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
    # --- autres enjeux déjà chiffrés par les règles
    autres = {"A4": "TVA sur exportations non justifiées", "B2": "Droits et TVA éludés (sous-évaluation en douane)",
              "C2": "TVA suspendue sur équipements revendus"}
    tva_autres = 0.0
    for code, lib in autres.items():
        if code in dec and dec[code]["montant_en_jeu"] > 0:
            tva_autres += dec[code]["montant_en_jeu"]
            lignes.append({"cle": f"enjeu_{code}", "libelle": lib, "montant": dec[code]["montant_en_jeu"],
                           "formule": f"Montant en jeu de l'indice {code}", "source": f"Règle {code}"})
    if base_ventes is None and ("A5" in dec or "B3" in dec):  # TVA non reversée
        code = "B3" if "B3" in dec else "A5"
        tva_omise = dec[code]["montant_en_jeu"]
        lignes.append({"cle": "tva_non_reversee", "libelle": "TVA non reversée (estimation)", "montant": tva_omise,
                       "formule": f"Montant en jeu de l'indice {code}", "source": f"Règle {code}"})
    total_tva = tva_omise + tva_trop
    total = total_tva + tva_autres
    if total_tva > 0:
        lignes.append({"cle": "total_tva", "libelle": "Total TVA estimée", "montant": total_tva,
                       "formule": " + ".join(fmt.dt(x) for x in (tva_omise, tva_trop) if x), "source": "Calcul", "total": True})
    if tva_autres > 0:
        lignes.append({"cle": "total_estime", "libelle": "Total des droits et taxes en jeu", "montant": total,
                       "formule": " + ".join(fmt.dt(x) for x in (total_tva, tva_autres) if x), "source": "Calcul", "total": True})
    # --- IS et pénalités : indicatifs
    is_indicatif = ecart_ventes * marge_ref * taux_is
    if is_indicatif > 0:
        lignes.append({"cle": "is_indicatif", "libelle": "Impôt sur les sociétés (indicatif)", "montant": is_indicatif,
                       "formule": f"{fmt.dt(ecart_ventes)} × {fmt.pct(marge_ref)} × {fmt.pct(taux_is, 0)}",
                       "source": is_src, "a_verifier": is_a_verif, "indicatif": True})
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
                       "source": pen_src, "indicatif": True, "article": "cdpf_2024__code_des_droits_et_procedures_fiscaux_article_81"})
    hypotheses += [
        f"Taux de TVA de {fmt.pct(taux_tva, 0)} : paramètre à vérifier dans le code de la TVA (non indexé).",
        f"Taux d'IS de {fmt.pct(taux_is, 0)} : paramètre à vérifier dans le code de l'IRPP et de l'IS (non indexé).",
        "Pénalités : 1,25 % par mois ou fraction de mois (article 81 du code des droits et procédures fiscaux), "
        f"calculées jusqu'au {fmt.date_fr(reference)} à titre indicatif.",
    ]
    for l in lignes:
        l["montant"] = round(float(l["montant"]), 2)
        l["montant_affiche"] = fmt.dt(l["montant"])
    return {
        "annee": annee, "lignes": lignes, "base_ventes": base_ventes, "ecart_ca": round(ecart_ventes, 2),
        "tva_ventes_omises": round(tva_omise, 2), "tva_deduite_en_trop": round(tva_trop, 2),
        "total_tva": round(total_tva, 2), "autres_enjeux": round(tva_autres, 2), "total_estime": round(total, 2),
        "is_indicatif": round(is_indicatif, 2), "penalites_indicatives": round(penalites, 2),
        "parametres": {"taux_tva": taux_tva, "taux_is": taux_is, "taux_penalite_mensuel": taux_pen, "marge_mediane_secteur": marge_ref},
        "hypotheses": hypotheses, "mention": MENTION, "date_reference": reference.isoformat(),
    }


def montants_autorises(calc: dict) -> set[str]:
    """Montants (formatés) que la rédaction a le droit de citer."""
    vals = {calc[k] for k in ("ecart_ca", "tva_ventes_omises", "tva_deduite_en_trop", "total_tva", "total_estime",
                              "is_indicatif", "penalites_indicatives")}
    vals |= {l["montant"] for l in calc["lignes"]}
    out = set()
    for v in vals:
        if v and not math.isnan(v):
            out.add(fmt.nombre(v).replace(" ", " "))
            out.add(fmt.nombre(round(v)).replace(" ", " "))
    return out
