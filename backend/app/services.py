"""Requêtes de lecture pour l'API : tableau de bord, liste de ciblage, fiche 360, facilitation, performance."""
from __future__ import annotations

import json
import threading
from functools import lru_cache

import numpy as np
import pandas as pd
from sqlalchemy import text

from . import db, fmt
from .risk.evaluation import LIBELLES_SCHEMAS
from .risk.features import ANNEES, Contexte, charger_contexte
from .risk.rules import REGLES, REGLES_PAR_CODE
from .risk.scoring import CATEGORIES

_ctx_lock = threading.Lock()


@lru_cache(maxsize=1)
def _contexte() -> Contexte:
    return charger_contexte()


def contexte() -> Contexte:
    with _ctx_lock:
        return _contexte()


def invalider_caches() -> None:
    _contexte.cache_clear()
    _scores.cache_clear()


@lru_cache(maxsize=1)
def _scores() -> pd.DataFrame:
    return db.read_sql("""
        SELECT s.entreprise_id AS id, s.score, s.categorie, s.probabilite, s.score_anomalie, s.force_indices, s.montant_en_jeu,
               s.priorite, s.rang, s.regles_declenchees, s.premiere_raison, s.facilitation, s.score_regles,
               e.raison_sociale, e.matricule_fiscal, e.forme_juridique, e.gouvernorat, e.delegation, e.secteur_groupe,
               e.secteur_libelle, e.secteur_nat_code, e.statut_export, e.effectif, e.statut_oea, r.libelle AS secteur
        FROM scores s JOIN entreprises e ON e.id = s.entreprise_id
        LEFT JOIN secteurs_reference r ON r.secteur_groupe = e.secteur_groupe""")


def scores() -> pd.DataFrame:
    return _scores().copy()


def metrique(cle: str):
    df = db.read_sql("SELECT valeur FROM metriques WHERE cle = :c", {"c": cle})
    return json.loads(df.valeur.iloc[0]) if len(df) else None


def _ligne_liste(r: pd.Series) -> dict:
    return {
        "id": int(r.id), "rang": int(r.rang), "raison_sociale": r.raison_sociale, "matricule_fiscal": r.matricule_fiscal,
        "secteur": r.secteur, "secteur_groupe": r.secteur_groupe, "gouvernorat": r.gouvernorat, "score": float(r.score),
        "categorie": r.categorie, "categorie_libelle": CATEGORIES[r.categorie], "probabilite": float(r.probabilite),
        "montant_en_jeu": float(r.montant_en_jeu), "priorite": float(r.priorite),
        "regles": json.loads(r.regles_declenchees), "premiere_raison": r.premiere_raison,
    }


# ------------------------------------------------------------------ tableau de bord
def statistiques() -> dict:
    s = scores()
    perf = metrique("performance") or {}
    alertes = s[s.categorie.isin(["rouge", "orange"])]
    parts = {c: int((s.categorie == c).sum()) for c in CATEGORIES}
    bins = list(range(0, 101, 10))
    hist = pd.cut(s.score, bins=bins, right=False, include_lowest=True).value_counts().sort_index()
    distribution = [{"tranche": f"{int(i.left)}–{int(i.right)}", "entreprises": int(v)} for i, v in hist.items()]
    distribution[-1]["entreprises"] += int((s.score >= 100).sum())
    # montant associé à chaque indice (non additif : un même enjeu peut être signalé par plusieurs indices)
    par_regle: dict[str, dict] = {}
    details = db.read_sql("SELECT entreprise_id, details FROM scores WHERE categorie IN ('rouge', 'orange')")
    for d in details.details:
        for i in json.loads(d)["indices"]:
            if i["declenchee"]:
                x = par_regle.setdefault(i["code"], {"code": i["code"], "libelle": i["libelle"], "niveau": i["niveau"],
                                                     "entreprises": 0, "montant": 0.0})
                x["entreprises"] += 1
                x["montant"] += i["montant_en_jeu"]
    gouv = s.groupby("gouvernorat").agg(rouges=("categorie", lambda c: int((c == "rouge").sum())),
                                        oranges=("categorie", lambda c: int((c == "orange").sum())),
                                        entreprises=("id", "size")).reset_index()
    gouv = gouv.sort_values(["rouges", "oranges"], ascending=False)
    resume = perf.get("resume", {})
    top5 = s.sort_values("rang").head(5)
    return {
        "kpis": {
            "entreprises_analysees": int(len(s)),
            "alertes_rouges": parts["rouge"],
            "demandes_justification": parts["orange"],
            "montant_en_jeu": float(alertes.montant_en_jeu.sum()),
            "precision_ciblage": resume.get("precision_top100_regles_ia"),
            "precision_hasard": resume.get("precision_hasard"),
            "gain_vs_hasard": resume.get("gain_vs_hasard"),
        },
        "categories": [{"code": c, "libelle": CATEGORIES[c], "entreprises": parts[c]} for c in CATEGORIES],
        "distribution_scores": distribution,
        "montant_par_indice": sorted(par_regle.values(), key=lambda x: -x["montant"]),
        "alertes_par_gouvernorat": gouv.to_dict("records"),
        "evolution_mensuelle": metrique("alertes_mensuelles") or [],
        "top5": [_ligne_liste(r) for _, r in top5.iterrows()],
        "calcule_le": calcule_le(),
    }


# ------------------------------------------------------------------ ciblage
def liste(categorie: str | None = None, secteur: str | None = None, gouvernorat: str | None = None, regle: str | None = None,
          q: str | None = None, montant_min: float | None = None, tri: str = "priorite", page: int = 1, taille: int = 50) -> dict:
    s = scores()
    if categorie:
        s = s[s.categorie.isin(categorie.split(","))]
    if secteur:
        s = s[s.secteur_groupe.isin(secteur.split(","))]
    if gouvernorat:
        s = s[s.gouvernorat.isin(gouvernorat.split(","))]
    if regle:
        codes = regle.split(",")
        s = s[s.regles_declenchees.map(lambda r: any(c in json.loads(r) for c in codes))]
    if q:
        qq = q.lower()
        s = s[s.raison_sociale.str.lower().str.contains(qq, regex=False) | s.matricule_fiscal.str.lower().str.contains(qq, regex=False)]
    if montant_min:
        s = s[s.montant_en_jeu >= montant_min]
    ordre = {"priorite": (["priorite", "score"], False), "score": (["score"], False), "montant": (["montant_en_jeu"], False),
             "nom": (["raison_sociale"], True)}.get(tri, (["priorite", "score"], False))
    s = s.sort_values(ordre[0], ascending=ordre[1], kind="mergesort")
    total = len(s)
    page = max(1, page)
    sl = s.iloc[(page - 1) * taille: page * taille]
    return {"total": total, "page": page, "taille": taille, "resultats": [_ligne_liste(r) for _, r in sl.iterrows()]}


def liste_csv(**filtres) -> str:
    res = liste(**filtres, page=1, taille=100_000)["resultats"]
    lignes = ["rang;entreprise;matricule;secteur;gouvernorat;score;categorie;indices;montant_en_jeu_dt;premiere_raison"]
    for r in res:
        raison = (r["premiere_raison"] or "").replace(";", ",").replace("\n", " ")
        lignes.append(f"{r['rang']};{r['raison_sociale']};{r['matricule_fiscal']};{r['secteur']};{r['gouvernorat']};"
                      f"{r['score']:.1f};{r['categorie_libelle']};{' '.join(r['regles'])};{r['montant_en_jeu']:.0f};{raison}")
    return "\n".join(lignes)


# ------------------------------------------------------------------ fiche 360
def _series(ctx: Contexte, eid: int) -> list[dict]:
    mois = [(y, m) for y in ANNEES for m in range(1, 13)]
    d = ctx.douane[(ctx.douane.entreprise_id == eid) & (ctx.douane.flux == "import")]
    imp = d.groupby(["annee", "mois"]).apply(lambda g: (g.valeur_cif_dt + g.droits_douane).sum(), include_groups=False)
    v = ctx.tva[ctx.tva.entreprise_id == eid].set_index(["annee", "mois"])
    t = ctx.tej[ctx.tej.beneficiaire_id == eid]
    tej = t.groupby([t.date.dt.year, t.date.dt.month]).montant_brut.sum()
    f = ctx.factures[ctx.factures.emetteur_id == eid]
    fac = f.groupby([f.date.dt.year, f.date.dt.month]).montant_ht.sum()
    b = ctx.banque[ctx.banque.entreprise_id == eid].set_index(["annee", "mois"]).total_encaissements
    out, cum = [], {"importations": 0.0, "ca_declare": 0.0, "paiements_tej": 0.0, "factures_emises": 0.0, "encaissements": 0.0}
    for y, m in mois:
        val = {"importations": float(imp.get((y, m), 0.0)),
               "ca_declare": float(v.ca_local_ht.get((y, m), 0.0) + v.ca_export_ht.get((y, m), 0.0)) if len(v) else 0.0,
               "paiements_tej": float(tej.get((y, m), 0.0)), "factures_emises": float(fac.get((y, m), 0.0)),
               "encaissements_ht": float(b.get((y, m), 0.0)) / 1.19}
        row = {"periode": f"{y}-{m:02d}", **val}
        for k in cum:
            cle = "encaissements_ht" if k == "encaissements" else k
            cum[k] += val[cle]
            row[f"cumul_{k}"] = cum[k]
        out.append(row)
    return out


def _reseau(ctx: Contexte, eid: int, cycle: list[int] | None) -> dict:
    ent = ctx.ent
    roles = ctx.tables["roles"]
    pers = db.read_sql("SELECT id, nom, prenom FROM personnes WHERE id IN (SELECT personne_id FROM roles WHERE entreprise_id = :e)",
                       {"e": eid})
    redressees = set(ctx.tables["controles_historiques"].query("redressement == True").entreprise_id)
    m = ctx.mensuel
    nd = m[~m.deposee.astype(bool)].groupby("entreprise_id").size()
    defaillantes = set(nd[nd >= 3].index)
    nodes, edges, vus = [], [], set()

    def ajout_ent(i: int, relation: str | None = None):
        if ("e", i) in vus:
            return
        vus.add(("e", i))
        nodes.append({"id": f"e{i}", "type": "entreprise", "label": ent.at[i, "raison_sociale"], "entreprise_id": int(i),
                      "centrale": i == eid, "radiee": ent.at[i, "statut"] == "radiée", "redressee": i in redressees,
                      "defaillante": i in defaillantes, "relation": relation})

    ajout_ent(eid)
    for _, p in pers.iterrows():
        pid = f"p{p.id}"
        nodes.append({"id": pid, "type": "personne", "label": f"{p.prenom} {p.nom}"})
        for _, r in roles[roles.personne_id == p.id].iterrows():
            ajout_ent(int(r.entreprise_id), "dirigeant commun")
            edges.append({"source": pid, "target": f"e{int(r.entreprise_id)}", "label": r.role})
    adr = ent.at[eid, "adresse_id"]
    voisins = ent.index[(ent.adresse_id == adr) & (ent.index != eid)]
    if len(voisins):
        a = db.read_sql("SELECT adresse FROM adresses WHERE id = :a", {"a": int(adr)})
        nodes.append({"id": f"a{adr}", "type": "adresse", "label": a.adresse.iloc[0] if len(a) else "Adresse"})
        for i in [eid, *voisins]:
            ajout_ent(int(i), "adresse commune")
            edges.append({"source": f"a{adr}", "target": f"e{int(i)}", "label": "domiciliée"})
    if cycle:
        for u, v in zip(cycle, cycle[1:] + cycle[:1]):
            ajout_ent(int(u), "circuit de factures")
            ajout_ent(int(v), "circuit de factures")
            edges.append({"source": f"e{u}", "target": f"e{v}", "label": "factures", "circuit": True})
    return {"nodes": nodes, "edges": edges}


def _donnees_brutes(ctx: Contexte, eid: int) -> dict:
    def recs(df: pd.DataFrame, cols: dict) -> list[dict]:
        df = df.copy()
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                df[c] = df[c].dt.strftime("%d/%m/%Y")
        return df[list(cols)].rename(columns=cols).replace({np.nan: None}).to_dict("records")

    d = ctx.douane[ctx.douane.entreprise_id == eid].sort_values("date", ascending=False).head(60)
    v = ctx.tva[ctx.tva.entreprise_id == eid].sort_values(["annee", "mois"], ascending=False).copy()
    v["periode"] = [f"{m:02d}/{y}" for y, m in zip(v.annee, v.mois)]
    v["deposee"] = v.deposee.map({True: "oui", False: "non"})
    t = ctx.tej[ctx.tej.beneficiaire_id == eid].merge(ctx.ent[["raison_sociale"]], left_on="payeur_id", right_index=True)
    f = ctx.factures[ctx.factures.emetteur_id == eid].merge(ctx.ent[["raison_sociale"]], left_on="client_id", right_index=True)
    a = ctx.tables["declarations_annuelles"]
    a = a[a.entreprise_id == eid].sort_values("annee")
    return {
        "douane": {"titre": "Douane (déclarations en détail)", "lignes": recs(d, {
            "numero_declaration": "Déclaration", "date": "Date", "flux": "Flux", "regime": "Régime", "code_sh": "Code SH",
            "designation": "Désignation", "pays_origine": "Origine", "valeur_cif_dt": "Valeur CIF (DT)", "tva_import": "TVA (DT)"})},
        "impots": {"titre": "Impôts (déclarations mensuelles de TVA)", "lignes": recs(v, {
            "periode": "Mois", "deposee": "Déposée", "ca_local_ht": "CA local HT", "ca_export_ht": "CA export HT",
            "tva_collectee": "TVA collectée", "tva_deductible_import": "Déductible import", "tva_deductible_local": "Déductible local",
            "remboursement_demande": "Remboursement demandé"})},
        "tej": {"titre": "TEJ (retenues à la source attestées par les clients)", "lignes": recs(
            t.sort_values("date", ascending=False).head(60),
            {"date": "Date", "raison_sociale": "Client payeur", "montant_brut": "Montant brut", "montant_retenu": "Retenue"})},
        "el_fatoora": {"titre": "El Fatoora (factures électroniques émises)", "lignes": recs(
            f.sort_values("date", ascending=False).head(60),
            {"date": "Date", "raison_sociale": "Client", "montant_ht": "Montant HT", "tva": "TVA", "code_sh_principal": "Code SH"})},
        "annuelles": {"titre": "Déclarations annuelles", "lignes": recs(a, {
            "annee": "Année", "chiffre_affaires": "Chiffre d'affaires", "achats_marchandises": "Achats de marchandises",
            "achats_matieres": "Achats de matières", "stock_initial": "Stock initial", "stock_final": "Stock final",
            "marge_brute": "Marge brute", "resultat_fiscal": "Résultat fiscal", "impot_du": "Impôt dû"})},
    }


def fiche(eid: int) -> dict | None:
    s = scores()
    row = s[s.id == eid]
    ctx = contexte()
    if eid not in ctx.ent.index:
        return None
    e = ctx.ent.loc[eid]
    adresse = db.read_sql("SELECT adresse FROM adresses WHERE id = :a", {"a": int(e.adresse_id)})
    dirigeants = db.read_sql("""SELECT p.prenom, p.nom, r.role FROM roles r JOIN personnes p ON p.id = r.personne_id
                                WHERE r.entreprise_id = :e""", {"e": eid}).to_dict("records")
    ident = {
        "id": int(eid), "raison_sociale": e.raison_sociale, "matricule_fiscal": e.matricule_fiscal, "forme_juridique": e.forme_juridique,
        "date_creation": fmt.date_fr(e.date_creation), "gouvernorat": e.gouvernorat, "delegation": e.delegation,
        "adresse": adresse.adresse.iloc[0] if len(adresse) else None, "secteur": ctx.secteur_info(e.secteur_groupe).get("libelle"),
        "secteur_nat": f"{e.secteur_nat_code} — {e.secteur_libelle}", "regime_fiscal": e.regime_fiscal, "statut_export": e.statut_export,
        "capital": float(e.capital), "effectif": int(e.effectif), "statut_oea": bool(e.statut_oea), "bureau_controle": e.bureau_controle,
        "statut": e.statut, "dirigeants": dirigeants,
    }
    if row.empty:
        return {"identite": ident, "score": None}
    r = row.iloc[0]
    det = json.loads(db.read_sql("SELECT details FROM scores WHERE entreprise_id = :e", {"e": eid}).details.iloc[0])
    b3 = next((i for i in det["indices"] if i["code"] == "B3" and i["declenchee"]), None)
    cycle = None
    if b3:
        res_b3 = REGLES_PAR_CODE["B3"].evaluer(ctx)
        cycle = res_b3.at[eid, "details"].get("cycle")
    historique = db.read_sql("""SELECT annee_controlee, date_controle, type, origine_selection, redressement, montant_redresse
                                FROM controles_historiques WHERE entreprise_id = :e ORDER BY date_controle""", {"e": eid})
    resultats = db.read_sql("SELECT * FROM resultats_controle WHERE entreprise_id = :e ORDER BY saisi_le", {"e": eid})
    return {
        "identite": ident,
        "score": {"score": float(r.score), "categorie": r.categorie, "categorie_libelle": CATEGORIES[r.categorie],
                  "raison_categorie": det["raison_categorie"], "probabilite": float(r.probabilite),
                  "anomalie": float(r.score_anomalie), "force_indices": float(r.force_indices),
                  "montant_en_jeu": float(r.montant_en_jeu), "priorite": float(r.priorite), "rang": int(r.rang),
                  "total": int(len(s))},
        "indices": det["indices"], "neutralisations": det["neutralisations"], "cascade": det["cascade"],
        "facilitation": det.get("facilitation"),
        "series": _series(ctx, eid), "reseau": _reseau(ctx, eid, cycle), "donnees_brutes": _donnees_brutes(ctx, eid),
        "historique_controles": historique.assign(date_controle=historique.date_controle.astype(str)).to_dict("records"),
        "resultats_saisis": resultats.to_dict("records"),
    }


def preuves(eid: int, code: str) -> dict | None:
    regle = REGLES_PAR_CODE.get(code.upper())
    if regle is None:
        return None
    ctx = contexte()
    p = regle.preuves(ctx, eid)
    return {"regle": regle.as_dict(), **p}


# ------------------------------------------------------------------ facilitation, performance, référentiels
def facilitation() -> dict:
    s = scores()
    s = s[s.facilitation.astype(bool)]
    det = db.read_sql("SELECT entreprise_id, details FROM scores WHERE facilitation = 1").set_index("entreprise_id").details
    out = []
    for _, r in s.sort_values("score").iterrows():
        f = json.loads(det[r.id])["facilitation"]
        out.append({**_ligne_liste(r), "statut_export": r.statut_export, "criteres": f["criteres"],
                    "candidat_oea": f["candidat_oea"], "candidat_remboursement_rapide": f["candidat_remboursement_rapide"]})
    return {"total": len(out), "candidats_oea": sum(1 for x in out if x["candidat_oea"]),
            "candidats_remboursement": sum(1 for x in out if x["candidat_remboursement_rapide"]), "entreprises": out}


def calcule_le() -> str | None:
    df = db.read_sql("SELECT calcule_le FROM metriques LIMIT 1")
    return df.calcule_le.iloc[0] if len(df) else None


def performance() -> dict:
    return {"performance": metrique("performance"), "modele": metrique("modele"), "calcule_le": calcule_le()}


def audit(action: str, objet: str, agent: str = "agent.demo", details: dict | None = None) -> None:
    """Journal d'audit : qui a consulté, généré ou validé quel dossier."""
    from datetime import datetime

    with db.get_engine().begin() as conn:
        conn.execute(db.journal_audit.insert().values(horodatage=datetime.now().isoformat(timespec="seconds"), agent=agent,
                                                      action=action, objet=objet,
                                                      details=json.dumps(details or {}, ensure_ascii=False)))


def journal(limite: int = 100) -> list[dict]:
    return db.read_sql("SELECT * FROM journal_audit ORDER BY id DESC LIMIT :n", {"n": limite}).to_dict("records")


def referentiels() -> dict:
    s = scores()
    secteurs = db.read_sql("SELECT secteur_groupe AS code, libelle FROM secteurs_reference ORDER BY libelle").to_dict("records")
    return {
        "secteurs": secteurs, "gouvernorats": sorted(s.gouvernorat.unique().tolist()),
        "categories": [{"code": c, "libelle": l} for c, l in CATEGORIES.items()],
        "regles": [r.as_dict() for r in REGLES], "schemas": LIBELLES_SCHEMAS,
        "parametres": db.read_sql("SELECT * FROM parametres").to_dict("records"),
    }


def enregistrer_resultat(eid: int, redressement: bool, montant: float, commentaire: str, agent: str) -> dict:
    from datetime import datetime

    with db.get_engine().begin() as conn:
        conn.execute(db.resultats_controle.insert().values(entreprise_id=eid, redressement=redressement, montant=montant,
                                                           commentaire=commentaire, agent=agent,
                                                           saisi_le=datetime.now().isoformat(timespec="seconds")))
        n = conn.execute(text("SELECT COUNT(*) FROM resultats_controle")).scalar()
    return {"enregistre": True, "resultats_en_attente": int(n)}
