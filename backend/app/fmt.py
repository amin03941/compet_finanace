"""Formats d'affichage français : 1 234 567 DT (espace insécable), 12,5 %, jj/mm/aaaa."""
from __future__ import annotations

import math
from datetime import date, datetime

NBSP = " "
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")


def dt(x: float | None, decimales: int = 0) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    s = f"{x:,.{decimales}f}".replace(",", NBSP).replace(".", ",")
    return f"{s}{NBSP}DT"


def nombre(x: float, decimales: int = 0) -> str:
    return f"{x:,.{decimales}f}".replace(",", NBSP).replace(".", ",")


def pct(x: float | None, decimales: int = 1) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "—"
    return f"{x * 100:.{decimales}f}".replace(".", ",") + f"{NBSP}%"


def ratio(x: float) -> str:
    if math.isinf(x):
        return "∞"
    return f"{x:.2f}".replace(".", ",")


def date_fr(d: date | datetime | str | None) -> str:
    if d is None:
        return "—"
    if isinstance(d, str):
        d = datetime.fromisoformat(d[:10])
    return d.strftime("%d/%m/%Y")


def mois_fr(annee: int, mois: int) -> str:
    return f"{MOIS[mois - 1]} {annee}"
