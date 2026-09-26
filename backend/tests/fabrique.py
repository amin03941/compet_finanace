"""Fabrique de petits contextes synthétiques pour tester chaque règle isolément."""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.risk.features import Contexte

SECTEURS = pd.DataFrame([
    {"secteur_groupe": "telephonie", "libelle": "Téléphonie", "type": "negoce", "marge_mediane": 0.20, "marge_sd": 0.04,
     "habituellement_crediteur": False, "ventes_biens": True},
    {"secteur_groupe": "conseil", "libelle": "Conseil", "type": "services", "marge_mediane": 3.0, "marge_sd": 0.6,
     "habituellement_crediteur": False, "ventes_biens": False},
    {"secteur_groupe": "textile_export", "libelle": "Textile export", "type": "industrie", "marge_mediane": 0.55,
     "marge_sd": 0.1, "habituellement_crediteur": True, "ventes_biens": True},
])
PARAMETRES = pd.DataFrame([
    {"cle": "taux_tva_normal", "valeur": 0.19, "source": "test", "a_verifier": True},
    {"cle": "marge_mediane.telephonie", "valeur": 0.20, "source": "test", "a_verifier": False},
    {"cle": "seuil_fractionnement_dt", "valeur": 3000.0, "source": "test", "a_verifier": True},
])


class Fabrique:
    def __init__(self):
        self.ent, self.douane, self.tva, self.ann = [], [], [], []
        self.tej, self.fac, self.banque, self.roles, self.ctrl, self.prix = [], [], [], [], [], []

    def entreprise(self, eid: int, secteur: str = "telephonie", **kw) -> "Fabrique":
        e = {"id": eid, "matricule_fiscal": f"{eid:07d}A/A/M/000", "raison_sociale": kw.pop("nom", f"Entreprise {eid}"),
             "forme_juridique": "SARL", "date_creation": date(2015, 1, 1), "gouvernorat": "Tunis", "delegation": "Bab Bhar",
             "adresse_id": eid, "secteur_nat_code": "46.52", "secteur_libelle": "x", "secteur_groupe": secteur,
             "regime_fiscal": "réel", "statut_export": "local", "capital": 10_000.0, "effectif": 5, "statut_oea": False,
             "bureau_controle": "x", "statut": "active", "date_radiation": None}
        e.update(kw)
        self.ent.append(e)
        return self

    def annee_tva(self, eid: int, annee: int, ca_local: float = 0.0, ca_export: float = 0.0, ded_import: float = 0.0,
                  ded_local: float = 0.0, remboursement_decembre: float = 0.0, non_deposes: tuple[int, ...] = ()) -> "Fabrique":
        for m in range(1, 13):
            dep = m not in non_deposes
            col = ca_local / 12 * 0.19
            ded = (ded_import + ded_local) / 12
            self.tva.append({"entreprise_id": eid, "annee": annee, "mois": m, "date_depot": date(annee + (m == 12), m % 12 + 1, 28) if dep else None,
                             "deposee": dep, "ca_local_ht": ca_local / 12 if dep else 0.0, "ca_export_ht": ca_export / 12 if dep else 0.0,
                             "tva_collectee": col if dep else 0.0, "tva_deductible_import": ded_import / 12 if dep else 0.0,
                             "tva_deductible_local": ded_local / 12 if dep else 0.0, "tva_deductible_immobilisations": 0.0,
                             "credit_reporte": max(0.0, ded - col) * m if dep else 0.0, "tva_due": max(0.0, col - ded) if dep else 0.0,
                             "remboursement_demande": remboursement_decembre if (m == 12 and dep) else 0.0})
        return self

    def annuelle(self, eid: int, annee: int, ca: float, achats: float = 0.0, s0: float = 0.0, s1: float = 0.0,
                 matieres: float = 0.0) -> "Fabrique":
        cons = s0 + achats + matieres - s1
        self.ann.append({"entreprise_id": eid, "annee": annee, "chiffre_affaires": ca, "achats_marchandises": achats,
                         "achats_matieres": matieres, "stock_initial": s0, "stock_final": s1, "marge_brute": ca - cons,
                         "charges_personnel": 0.0, "autres_charges": 0.0, "resultat_comptable": 0.0, "resultat_fiscal": 0.0,
                         "impot_du": 0.0, "immobilisations_acquises": 0.0})
        return self

    def import_(self, eid: int, d: date, base: float, *, regime: str = "mise à la consommation", equip: bool = False,
                code_sh: str = "85171300", pays: str = "Chine", qte: float = 1.0, fournisseur: str = "F1",
                numero: str | None = None, taux_droits: float = 0.0, flux: str = "import") -> "Fabrique":
        suspensif = equip or regime != "mise à la consommation"
        tva = 0.0 if suspensif or flux == "export" else base * 0.19
        self.douane.append({"id": len(self.douane) + 1, "entreprise_id": eid, "numero_declaration": numero or f"D{len(self.douane) + 1}",
                            "date": d, "bureau": "x", "flux": flux, "regime": regime, "code_sh": code_sh, "designation": "Produit",
                            "pays_origine": pays, "fournisseur_etranger": fournisseur, "quantite": qte, "unite": "u",
                            "poids_kg": 1.0, "valeur_fob": base, "fret": 0.0, "assurance": 0.0, "valeur_cif_dt": base / (1 + taux_droits),
                            "taux_droits": taux_droits, "droits_douane": base - base / (1 + taux_droits),
                            "base_tva": 0.0 if (suspensif or flux == "export") else base, "tva_import": tva,
                            "avance_impot_import": 0.0, "est_equipement": equip, "circuit": "vert", "resultat_controle": None})
        return self

    def tej_(self, payeur: int, benef: int, d: date, montant: float) -> "Fabrique":
        self.tej.append({"id": len(self.tej) + 1, "payeur_id": payeur, "beneficiaire_id": benef, "date": d,
                         "montant_brut": montant, "taux": 0.015, "montant_retenu": montant * 0.015})
        return self

    def facture(self, emetteur: int, client: int, d: date, montant: float, code_sh: str | None = None) -> "Fabrique":
        self.fac.append({"id": len(self.fac) + 1, "emetteur_id": emetteur, "client_id": client, "date": d,
                         "montant_ht": montant, "tva": montant * 0.19, "code_sh_principal": code_sh})
        return self

    def banque_annee(self, eid: int, annee: int, total: float) -> "Fabrique":
        for m in range(1, 13):
            self.banque.append({"entreprise_id": eid, "annee": annee, "mois": m, "total_encaissements": total / 12})
        return self

    def role(self, eid: int, personne: int, role: str = "gérant") -> "Fabrique":
        self.roles.append({"entreprise_id": eid, "personne_id": personne, "role": role})
        return self

    def controle(self, eid: int, redressement: bool, annee: int = 2023) -> "Fabrique":
        self.ctrl.append({"id": len(self.ctrl) + 1, "entreprise_id": eid, "annee_controlee": annee, "date_controle": date(annee + 1, 3, 1),
                          "type": "approfondie", "origine_selection": "aléatoire", "redressement": redressement,
                          "montant_redresse": 10_000.0 if redressement else 0.0, "motif_categorie": None})
        return self

    def prix_ref(self, code_sh: str, pays: str, mediane: float, p10: float, p90: float) -> "Fabrique":
        self.prix.append({"code_sh": code_sh, "pays_origine": pays, "prix_unitaire_median": mediane, "p10": p10, "p90": p90, "nb_obs": 50})
        return self

    def contexte(self) -> Contexte:
        cols = {
            "declarations_douane": ["id", "entreprise_id", "numero_declaration", "date", "bureau", "flux", "regime", "code_sh",
                                    "designation", "pays_origine", "fournisseur_etranger", "quantite", "unite", "poids_kg",
                                    "valeur_fob", "fret", "assurance", "valeur_cif_dt", "taux_droits", "droits_douane", "base_tva",
                                    "tva_import", "avance_impot_import", "est_equipement", "circuit", "resultat_controle"],
            "declarations_tva": ["entreprise_id", "annee", "mois", "date_depot", "deposee", "ca_local_ht", "ca_export_ht",
                                 "tva_collectee", "tva_deductible_import", "tva_deductible_local", "tva_deductible_immobilisations",
                                 "credit_reporte", "tva_due", "remboursement_demande"],
            "declarations_annuelles": ["entreprise_id", "annee", "chiffre_affaires", "achats_marchandises", "achats_matieres",
                                       "stock_initial", "stock_final", "marge_brute", "charges_personnel", "autres_charges",
                                       "resultat_comptable", "resultat_fiscal", "impot_du", "immobilisations_acquises"],
            "retenues_source": ["id", "payeur_id", "beneficiaire_id", "date", "montant_brut", "taux", "montant_retenu"],
            "factures_electroniques": ["id", "emetteur_id", "client_id", "date", "montant_ht", "tva", "code_sh_principal"],
            "encaissements_bancaires": ["entreprise_id", "annee", "mois", "total_encaissements"],
            "roles": ["entreprise_id", "personne_id", "role"],
            "controles_historiques": ["id", "entreprise_id", "annee_controlee", "date_controle", "type", "origine_selection",
                                      "redressement", "montant_redresse", "motif_categorie"],
            "prix_reference": ["code_sh", "pays_origine", "prix_unitaire_median", "p10", "p90", "nb_obs"],
        }
        data = {"declarations_douane": self.douane, "declarations_tva": self.tva, "declarations_annuelles": self.ann,
                "retenues_source": self.tej, "factures_electroniques": self.fac, "encaissements_bancaires": self.banque,
                "roles": self.roles, "controles_historiques": self.ctrl, "prix_reference": self.prix}
        t = {k: pd.DataFrame(v, columns=cols[k]) for k, v in data.items()}
        t["entreprises"] = pd.DataFrame(self.ent)
        t["parametres"] = PARAMETRES.copy()
        t["secteurs_reference"] = SECTEURS.copy()
        for k, c in (("declarations_douane", "date"), ("retenues_source", "date"), ("factures_electroniques", "date"),
                     ("controles_historiques", "date_controle")):
            t[k][c] = pd.to_datetime(t[k][c])
        for c in ("date_creation", "date_radiation"):
            t["entreprises"][c] = pd.to_datetime(t["entreprises"][c])
        t["declarations_douane"]["est_equipement"] = t["declarations_douane"]["est_equipement"].astype(bool)
        t["declarations_tva"]["deposee"] = t["declarations_tva"]["deposee"].astype(bool)
        return Contexte(t)
