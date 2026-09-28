"""Export PDF du pré-dossier (ReportLab). Logo RASD 360 dessiné (aucun logo officiel), bandeau
« Prototype — données entièrement fictives », filigrane BROUILLON tant que le dossier n'est pas validé.
"""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from .. import fmt

BLEU = colors.HexColor("#0B2545")
BLEU_ACTION = colors.HexColor("#1D4ED8")
GRIS = colors.HexColor("#64748B")
BORDURE = colors.HexColor("#E2E8F0")
FOND = colors.HexColor("#F6F8FB")
ROUGE, ORANGE, VERT, GRIS_STATUT = (colors.HexColor(c) for c in ("#DC2626", "#F59E0B", "#16A34A", "#94A3B8"))
COULEUR_CAT = {"rouge": ROUGE, "orange": ORANGE, "vert": VERT, "gris": GRIS_STATUT}


def _polices() -> tuple[str, str]:
    candidats = [(Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf"))]
    import reportlab
    rl = Path(reportlab.__file__).parent / "fonts"
    candidats.append((rl / "Vera.ttf", rl / "VeraBd.ttf"))
    for normal, gras in candidats:
        if normal.exists() and gras.exists():
            try:
                pdfmetrics.registerFont(TTFont("RasdSans", str(normal)))
                pdfmetrics.registerFont(TTFont("RasdSans-Bold", str(gras)))
                return "RasdSans", "RasdSans-Bold"
            except Exception:  # noqa: BLE001
                continue
    return "Helvetica", "Helvetica-Bold"


POLICE, POLICE_GRAS = _polices()
S = {
    "titre": ParagraphStyle("titre", fontName=POLICE_GRAS, fontSize=15, leading=19, textColor=BLEU, spaceAfter=2),
    "sous": ParagraphStyle("sous", fontName=POLICE, fontSize=9, leading=12, textColor=GRIS),
    "h1": ParagraphStyle("h1", fontName=POLICE_GRAS, fontSize=13, leading=17, textColor=BLEU_ACTION, spaceBefore=14, spaceAfter=4),
    "h2": ParagraphStyle("h2", fontName=POLICE_GRAS, fontSize=11.5, leading=15, textColor=BLEU, spaceBefore=10, spaceAfter=5),
    "p": ParagraphStyle("p", fontName=POLICE, fontSize=9.2, leading=12.8, alignment=TA_JUSTIFY),
    "petit": ParagraphStyle("petit", fontName=POLICE, fontSize=8, leading=10.5, textColor=GRIS),
    "cel": ParagraphStyle("cel", fontName=POLICE, fontSize=8.4, leading=11),
    "celg": ParagraphStyle("celg", fontName=POLICE_GRAS, fontSize=8.4, leading=11),
    "extrait": ParagraphStyle("extrait", fontName=POLICE, fontSize=8, leading=10.8, textColor=colors.HexColor("#334155"),
                              leftIndent=6, borderPadding=4),
}


def _p(txt, style="p"):
    return Paragraph(escape(str(txt or "")).replace("\n", "<br/>"), S[style])


def _logo(c, x, y):
    """Petit radar stylisé RASD 360 (dessiné, aucun logo institutionnel)."""
    c.saveState()
    c.setStrokeColor(BLEU_ACTION)
    c.setLineWidth(1.1)
    for r in (7, 4.5, 2):
        c.circle(x, y, r * mm / 2.2, stroke=1, fill=0)
    c.setFillColor(BLEU_ACTION)
    c.circle(x + 1.2 * mm, y + 0.8 * mm, 0.6 * mm, stroke=0, fill=1)
    c.line(x, y, x + 2.9 * mm, y + 1.9 * mm)
    c.setFont(POLICE_GRAS, 11)
    c.setFillColor(BLEU)
    c.drawString(x + 5 * mm, y - 1.4 * mm, "RASD 360")
    c.setFont(POLICE, 6.5)
    c.setFillColor(GRIS)
    c.drawString(x + 5 * mm, y - 4.4 * mm, "Radar fiscal et douanier")
    c.restoreState()


def _decor(statut: str, reference: str):
    def dessiner(c, doc):
        w, h = A4
        c.saveState()
        c.setFillColor(colors.HexColor("#FEF3C7"))
        c.rect(0, h - 7 * mm, w, 7 * mm, stroke=0, fill=1)
        c.setFillColor(colors.HexColor("#92400E"))
        c.setFont(POLICE_GRAS, 7.5)
        c.drawCentredString(w / 2, h - 4.6 * mm, "PROTOTYPE — DONNÉES ENTIÈREMENT FICTIVES — AIDE À LA DÉCISION, SANS VALEUR JURIDIQUE")
        _logo(c, 18 * mm, h - 16 * mm)
        c.setFont(POLICE, 7.5)
        c.setFillColor(GRIS)
        c.drawRightString(w - 15 * mm, h - 14 * mm, f"Réf. {reference}")
        c.drawRightString(w - 15 * mm, h - 17.5 * mm, "Statut : " + ("VALIDÉ" if statut == "valide" else "BROUILLON"))
        c.setStrokeColor(BORDURE)
        c.line(15 * mm, h - 21 * mm, w - 15 * mm, h - 21 * mm)
        c.drawString(15 * mm, 10 * mm, "RASD 360 — pré-dossier de contrôle généré automatiquement, à valider par l'agent.")
        c.drawRightString(w - 15 * mm, 10 * mm, f"Page {doc.page}")
        if statut != "valide":
            c.setFont(POLICE_GRAS, 70)
            c.setFillColor(colors.Color(0.86, 0.15, 0.15, alpha=0.07))
            c.translate(w / 2, h / 2)
            c.rotate(35)
            c.drawCentredString(0, 0, "BROUILLON")
        c.restoreState()
    return dessiner


def _table(data, largeurs, entete=True, total_rows=()):
    t = Table(data, colWidths=largeurs, repeatRows=1 if entete else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, BORDURE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    if entete:
        style += [("BACKGROUND", (0, 0), (-1, 0), FOND)]
    for r in total_rows:
        style += [("BACKGROUND", (0, r), (-1, r), colors.HexColor("#EFF6FF"))]
    t.setStyle(TableStyle(style))
    return t


NOMS_PARTIES = {"dgi": "DGI — Direction générale des impôts", "douane": "Douane — Direction générale des douanes"}
SENS = {"douane_vers_dgi": "Douane → DGI", "dgi_vers_douane": "DGI → Douane"}


def _partie(el: list, c: dict, partie: str, n: int, conjoint: bool) -> int:
    """Sections d'une administration : écarts, indices, articles, pièces, lettre. Retourne le prochain numéro de section."""
    lignes = [l for l in c["ecarts"]["lignes"] if l.get("partie", "dgi") == partie]
    indices = [i for i in c["indices"] if partie in i.get("parties", ["dgi"])]
    articles = [a for a in c["articles"] if a.get("partie", "dgi") == partie]
    pre = "Partie " + ("DGI" if partie == "dgi" else "Douane") + " — " if conjoint else ""

    el.append(_p(f"{n}. {pre}Tableau des écarts (calculs déterministes)", "h2"))
    if lignes:
        rows = [[_p("Poste", "celg"), _p("Montant", "celg"), _p("Formule et hypothèse", "celg")]]
        totaux = []
        for k, l in enumerate(lignes, start=1):
            lib = l["libelle"] + (" *" if l.get("a_verifier") else "")
            rows.append([_p(lib, "celg" if l.get("total") else "cel"), _p(l["montant_affiche"], "celg" if l.get("total") else "cel"),
                         _p(l["formule"], "cel")])
            if l.get("total"):
                totaux.append(k)
        el.append(_table(rows, [55 * mm, 32 * mm, 93 * mm], total_rows=totaux))
    else:
        el.append(_p("Aucun montant chiffré pour cette administration.", "petit"))
    el.append(Spacer(1, 3))
    for h in c["ecarts"].get("hypotheses_par_partie", {}).get(partie, c["ecarts"]["hypotheses"] if not conjoint else []):
        el.append(_p(f"* {h}", "petit"))
    el.append(_p(c["ecarts"]["mention"], "celg"))

    el.append(_p(f"{n + 1}. {pre}Faisceau d'indices", "h2"))
    rows = [[_p("Indice", "celg"), _p("Constat", "celg"), _p("En jeu", "celg")]]
    for i in indices:
        rows.append([_p(f"{i['code']} (force {i['niveau']})", "celg"), _p(i["phrase"], "cel"),
                     _p(fmt.dt(i["montant_en_jeu"]) if i["montant_en_jeu"] else "—", "cel")])
    el.append(_table(rows, [24 * mm, 126 * mm, 30 * mm]))
    el.append(_p("Les preuves (déclarations, certificats, factures) sont consultables dans la fiche 360 de l'entreprise.", "petit"))

    el.append(_p(f"{n + 2}. {pre}Articles applicables (textes retrouvés dans la base)", "h2"))
    if c.get("articles_modifies"):
        el.append(_p("Liste des articles modifiée par l'agent (voir historique).", "celg"))
    if c.get("notes_articles", {}).get(partie):
        el.append(_p(c["notes_articles"][partie], "petit"))
    for a in articles:
        extrait = a["extrait"] if len(a["extrait"]) < 900 else a["extrait"][:900] + " […]"
        origine = "ajouté par l'agent" if a.get("origine") == "agent" else \
            "proposé par le système — suggestion automatique, à vérifier" if a.get("suggestion") else "proposé par le système"
        motif = f"Motif de l'agent : {a['motif']}" if a.get("origine") == "agent" else a["motif"]
        bloc = [_p(f"{a['article']} — {a['document']}" + (f" ({a['edition']})" if a.get("edition") else "") + f" · {origine}", "celg"),
                _p(motif, "petit"), _p(extrait, "extrait"), _p(a.get("locator") or "", "petit"), Spacer(1, 4)]
        el.append(KeepTogether(bloc))

    el.append(_p(f"{n + 3}. {pre}Documents à demander", "h2"))
    for d in c["documents"].get(partie, []):
        el.append(_p(f"☐ {d}"))

    lettre = c["lettres"][partie]
    el.append(_p(f"{n + 4}. {pre}Projet de lettre de demande de justification", "h2"))
    el.append(_p(f"Émetteur : {lettre.get('emetteur', '')} — Destinataire : {lettre['destinataire']}", "petit"))
    el.append(_p(f"Objet : {lettre['objet']}", "celg"))
    el.append(Spacer(1, 3))
    el.append(_p(lettre["corps"]))
    el.append(Spacer(1, 6))
    el.append(_p(f"L'agent : {c['entete'].get('agent') or '________________'}", "p"))
    return n + 5


def _fiche_transmission(el: list, t: dict) -> None:
    el.append(PageBreak())
    el.append(_p(f"Fiche de transmission — {SENS.get(t['sens'], t['sens'])}", "titre"))
    el.append(_p(t["mention"], "sous"))
    el.append(Spacer(1, 5))
    info = [
        [_p("Administration émettrice", "celg"), _p(t["emetteur"], "cel")],
        [_p("Destinataire", "celg"), _p(t["destinataire"], "cel")],
        [_p("Entreprise", "celg"), _p(f"{t['entreprise']['raison_sociale']} — matricule {t['entreprise']['matricule_fiscal']} (fictif)", "cel")],
        [_p("Date", "celg"), _p(t["date"], "cel")],
        [_p("Agent", "celg"), _p(t["agent"], "cel")],
    ]
    el.append(_table(info, [45 * mm, 135 * mm], entete=False))
    el.append(_p("Indices concernés", "h2"))
    for i in t["indices"]:
        el.append(_p(f"• {i['code']} — {i['libelle']}"))
    el.append(_p("Pièces transmises", "h2"))
    for piece in t["pieces"]:
        el.append(_p(f"☐ {piece}"))
    b = t["base_legale"]
    el.append(_p(f"Base légale : {b['article']} du {b['document'].lower()} (extrait exact de la base)", "h2"))
    el.append(_p(b["extrait"], "extrait"))


def pdf(dossier: dict) -> bytes:
    c = dossier["contenu"]
    e = c["entete"]
    conjoint = e.get("type_dossier") == "conjoint"
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=26 * mm, bottomMargin=16 * mm,
                            title=f"{e.get('titre', 'Pré-dossier de contrôle')} — {e['raison_sociale']}", author="RASD 360 (prototype)")
    el = []
    el.append(_p(e.get("titre", "Pré-dossier de contrôle fiscal"), "titre"))
    el.append(_p(f"{e['raison_sociale']} — matricule {e['matricule_fiscal']} (fictif) — exercice {e['periode']}", "sous"))
    el.append(Spacer(1, 5))
    cat = COULEUR_CAT.get(e["categorie"], GRIS)
    destinataires = " ; ".join(f"{d['administration']} — {d['service']}" for d in e.get("destinataires", []))
    info = [
        [_p("Entreprise", "celg"), _p(f"{e['raison_sociale']} ({e.get('forme_juridique') or ''})", "cel"),
         _p("Score", "celg"), _p(f"{e['score']:.0f}/100".replace(".", ","), "cel")],
        [_p("Adresse", "celg"), _p(e.get("adresse"), "cel"), _p("Catégorie", "celg"),
         Paragraph(f'<font color="{cat.hexval()}">■</font> {escape(e["categorie_libelle"])}', S["cel"])],
        [_p("Secteur", "celg"), _p(e.get("secteur"), "cel"), _p("Type de dossier", "celg"),
         _p(e.get("type_libelle", "Fiscal") + (" (preuve douanière)" if e.get("preuve_douaniere") and not conjoint else ""), "cel")],
        [_p("Destinataire", "celg"), _p(destinataires, "cel"), _p("Montant en jeu", "celg"), _p(fmt.dt(c["ecarts"]["total_estime"]), "cel")],
        [_p("Agent", "celg"), _p(e.get("agent"), "cel"), _p("Date", "celg"), _p(e.get("date"), "cel")],
    ]
    el.append(_table(info, [25 * mm, 80 * mm, 28 * mm, 47 * mm], entete=False))

    el.append(_p("1. Synthèse", "h2"))
    for ligne in c["synthese"]:
        el.append(_p(f"• {ligne}"))

    n = 2
    for partie in e.get("parties", ["dgi"]):
        if conjoint:
            el.append(_p(f"Partie {NOMS_PARTIES[partie]}", "h1"))
        n = _partie(el, c, partie, n, conjoint)

    el.append(_p(f"{n}. Avertissements", "h2"))
    for a in c["avertissements"]:
        el.append(_p(f"• {a}", "petit"))
    gen = c.get("generation", {})
    el.append(_p(f"Rédaction : {'modèle local ' + gen.get('modele') if gen.get('modele') else 'modèle de rédaction déterministe'} ; "
                 "tous les montants proviennent des calculs de RASD 360 ; chaque article cité correspond à un texte retrouvé dans la base.",
                 "petit"))
    for t in c.get("transmissions", []):
        _fiche_transmission(el, t)
    doc.build(el, onFirstPage=_decor(dossier["statut"], e.get("reference", "")), onLaterPages=_decor(dossier["statut"], e.get("reference", "")))
    return buf.getvalue()
