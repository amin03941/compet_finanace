"""Nomenclature d'activités tunisienne NAT 2009 (INS) : hiérarchie Section > Division > Groupe > Classe.

Chaque entreprise porte un code de classe NAT (ex. « 46.52 »). Le filtre du ciblage accepte un code de n'importe quel
niveau : section (« G »), division (« 46 »), groupe (« 46.5 ») ou classe (« 46.52 »).
"""
from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from functools import lru_cache

from . import config

NIVEAUX = ("section", "division", "groupe", "classe")


@lru_cache(maxsize=1)
def classes() -> dict[str, dict]:
    """class_code -> {section, division, groupe, classe : (code, libellé)} lu dans le fichier officiel de l'INS."""
    out = {}
    with config.NAT_NOMENCLATURE_FILE.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            out[r["class_code"]] = {
                "section": (r["section_code"], r["section_title"]), "division": (r["division_code"], r["division_title"]),
                "groupe": (r["group_code"], r["group_title"]), "classe": (r["class_code"], r["class_title"]),
            }
    return out


def niveau(code: str) -> str | None:
    """Niveau d'un code NAT d'après sa forme : lettre, deux chiffres, « dd.d » ou « dd.dd »."""
    code = (code or "").strip().upper()
    if re.fullmatch(r"[A-U]", code):
        return "section"
    if re.fullmatch(r"\d{2}", code):
        return "division"
    if re.fullmatch(r"\d{2}\.\d", code):
        return "groupe"
    if re.fullmatch(r"\d{2}\.\d{2}", code):
        return "classe"
    return None


def classes_de(code: str) -> set[str]:
    """Toutes les classes NAT couvertes par un code (quel que soit son niveau). Code inconnu : ensemble vide."""
    n = niveau(code)
    if n is None:
        return set()
    code = code.strip().upper()
    return {c for c, h in classes().items() if h[n][0] == code}


def libelle(code: str) -> str | None:
    n = niveau(code)
    if n is None:
        return None
    code = code.strip().upper()
    return next((h[n][1] for h in classes().values() if h[n][0] == code), None)


def arbre(codes_presents: Iterable[tuple[str, int]]) -> list[dict]:
    """Arbre NAT restreint aux classes réellement présentes, avec le nombre d'entreprises à chaque niveau."""
    racine: dict = {}
    for classe, n in codes_presents:
        h = classes().get(classe)
        if h is None:
            continue
        noeud = racine
        for niv in NIVEAUX:
            code, lib = h[niv]
            enfant = noeud.setdefault(code, {"code": code, "libelle": lib, "niveau": niv, "entreprises": 0, "_enfants": {}})
            enfant["entreprises"] += int(n)
            noeud = enfant["_enfants"]

    def figer(noeuds: dict) -> list[dict]:
        out = []
        for code in sorted(noeuds):
            x = noeuds[code]
            enfants = figer(x.pop("_enfants"))
            out.append({**x, **({"enfants": enfants} if enfants else {})})
        return out

    return figer(racine)
