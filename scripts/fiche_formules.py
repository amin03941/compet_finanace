"""Génère docs/RASD360_fiche_formules.pdf : toutes les formules de RASD 360 (annexe pour le jury).

Usage (depuis la racine) : backend\\.venv\\Scripts\\python.exe scripts\\fiche_formules.py
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "docs" / "RASD360_fiche_formules.pdf"

BLEU, ACTION, GRIS, LIGNE, FOND = (colors.HexColor(c) for c in ("#0B2545", "#1D4ED8", "#64748B", "#E2E8F0", "#F1F5F9"))
ROUGE, ORANGE, VERT, GRIS_S = (colors.HexColor(c) for c in ("#DC2626", "#F59E0B", "#16A34A", "#94A3B8"))


def _polices() -> tuple[str, str]:
    import reportlab
    rl = Path(reportlab.__file__).parent / "fonts"
    for n, g in ((Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")), (rl / "Vera.ttf", rl / "VeraBd.ttf")):
        if n.exists() and g.exists():
            pdfmetrics.registerFont(TTFont("F", str(n)))
            pdfmetrics.registerFont(TTFont("F-B", str(g)))
            return "F", "F-B"
    return "Helvetica", "Helvetica-Bold"


N, B = _polices()
ST = {
    "titre": ParagraphStyle("titre", fontName=B, fontSize=20, leading=24, textColor=BLEU),
    "sous": ParagraphStyle("sous", fontName=N, fontSize=10, leading=14, textColor=GRIS),
    "h1": ParagraphStyle("h1", fontName=B, fontSize=13, leading=17, textColor=BLEU, spaceBefore=12, spaceAfter=5),
    "h2": ParagraphStyle("h2", fontName=B, fontSize=10.5, leading=14, textColor=ACTION, spaceBefore=6, spaceAfter=3),
    "p": ParagraphStyle("p", fontName=N, fontSize=9.3, leading=13),
    "puce": ParagraphStyle("puce", fontName=N, fontSize=9.3, leading=13, leftIndent=10, bulletIndent=2),
    "formule": ParagraphStyle("formule", fontName=B, fontSize=10, leading=14, textColor=BLEU, backColor=colors.HexColor("#EFF6FF"),
                              borderPadding=(5, 7, 5, 7), spaceBefore=4, spaceAfter=7, leftIndent=4, rightIndent=4),
    "cel": ParagraphStyle("cel", fontName=N, fontSize=8.5, leading=11),
    "celb": ParagraphStyle("celb", fontName=B, fontSize=8.5, leading=11),
    "note": ParagraphStyle("note", fontName=N, fontSize=8, leading=10.5, textColor=GRIS),
    "oral": ParagraphStyle("oral", fontName=N, fontSize=10, leading=14.5, textColor=BLEU, backColor=colors.HexColor("#FEF9C3"),
                           borderPadding=(7, 9, 7, 9), spaceBefore=4, spaceAfter=8, leftIndent=5, rightIndent=5),
}


def P(t, s="p"):
    return Paragraph(t, ST[s])


def puces(items):
    return [Paragraph(t, ST["puce"], bulletText="•") for t in items]


def F(t):
    return P(t, "formule")


def tableau(lignes, largeurs, entete=True, gras_premiere_col=True):
    data = []
    for i, l in enumerate(lignes):
        data.append([P(c, "celb" if (entete and i == 0) or (gras_premiere_col and j == 0) else "cel") for j, c in enumerate(l)])
    t = Table(data, colWidths=largeurs, repeatRows=1 if entete else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, LIGNE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if entete:
        st.append(("BACKGROUND", (0, 0), (-1, 0), FOND))
    t.setStyle(TableStyle(st))
    return t


def pied(c, doc):
    w, h = A4
    c.saveState()
    c.setFillColor(colors.HexColor("#FEF3C7"))
    c.rect(0, h - 7 * mm, w, 7 * mm, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#92400E"))
    c.setFont(B, 7.5)
    c.drawCentredString(w / 2, h - 4.6 * mm, "RASD 360 — PROTOTYPE, DONNÉES ENTIÈREMENT FICTIVES")
    c.setFont(N, 7.5)
    c.setFillColor(GRIS)
    c.drawString(15 * mm, 9 * mm, "RASD 360 — Fiche des formules (annexe)")
    c.drawRightString(w - 15 * mm, 9 * mm, f"Page {doc.page}")
    c.restoreState()


def puce_couleur(couleur, texte):
    return f'<font color="{couleur.hexval()}">■</font> {texte}'


def contenu():
    W = 180 * mm
    el = [P("RASD 360 — Comment on calcule tout", "titre"),
          P("Fiche des formules · annexe de la présentation · montants en dinars (DT) · données fictives 2023–2025", "sous"),
          Spacer(1, 8)]

    el.append(P("À dire au jury (30 secondes)", "h1"))
    el.append(P("« On ne compare pas bêtement importations et chiffre d'affaires. D'abord on <b>corrige les écarts honnêtes</b> "
                "(stock, machines, exportations). Ensuite on <b>croise des sources que l'entreprise ne contrôle pas</b>, avec "
                "14 règles chiffrées. Enfin l'IA <b>classe</b> : priorité = probabilité de réussite × montant en jeu. "
                "<b>L'agent décide.</b> »", "oral"))
    el += puces(["<b>« C'est du machine learning ? »</b> Les règles sont des calculs fixes et vérifiables. Le ML sert seulement à "
                 "classer (LightGBM) et à repérer l'inhabituel (Isolation Forest). SHAP explique chaque score.",
                 "<b>« Et si l'entreprise est honnête ? »</b> Montrer Cap Bon Distribution : même écart brut que Sahel Électro, "
                 "mais le stock l'explique. Elle est verte."])

    # 1
    el.append(P("1. Les données", "h1"))
    el += puces(["5 sources par entreprise : <b>douane</b> (importations, exportations), <b>impôts</b> (TVA mensuelle, déclaration "
                 "annuelle), <b>TEJ</b> (paiements attestés par les clients), <b>El Fatoora</b> (factures émises), <b>banque</b> (encaissements).",
                 "Taux de TVA 19 % et taux d'IS 15 % : paramètres « à vérifier » (codes de la TVA et de l'IS non indexés).",
                 "<b>Prix de référence</b> = médiane, 10<super>e</super> et 90<super>e</super> centiles du prix unitaire CIF "
                 "(valeur CIF ÷ quantité), par couple (code SH, pays d'origine), au moins 5 observations."])

    # 2
    el.append(P("2. Neutraliser les explications honnêtes", "h1"))
    el.append(F("Coût des ventes net = importations à revendre + achats locaux − variation de stock"))
    el += puces(["<b>Importations à revendre</b> = Σ (valeur CIF + droits), mise à la consommation, <b>hors machines</b> "
                 "(annexe du décret 2017-419) et <b>hors admission temporaire</b>.",
                 "<b>Achats locaux</b> = max(0 ; achats déclarés − importations à revendre − admission temporaire).",
                 "<b>Variation de stock</b> = stock final − stock initial.",
                 "<b>CA</b> = Σ déclarations mensuelles de TVA (ventes locales + exportations) ; "
                 "<b>CA TTC</b> = ventes locales × 1,19 + exportations."])
    el.append(F("Marge implicite = CA ÷ coût des ventes net − 1"))
    el += puces(["<b>Sur 36 mois</b> : Σ CA sur 3 ans ÷ Σ coûts sur 3 ans − 1 (neutralise le décalage de période).",
                 "<b>Comparaison au secteur</b> (code d'activité NAT 2009, simple table de correspondance, pas de ML) : "
                 "marge médiane de référence du secteur et 5<super>e</super> centile des marges du secteur.",
                 "Marge non calculée pour les services, si l'admission temporaire dépasse 20 % des achats, ou si le coût est "
                 "inférieur à 5 % du CA ou à 10 000 DT."])

    # 3
    el.append(P("3. Les 14 règles", "h1"))
    el.append(P(puce_couleur(ROUGE, "<b>Niveau A — contradiction directe avec des tiers (quasi-preuve)</b>"), "h2"))
    el.append(tableau([
        ["Règle", "Se déclenche si", "Montant en jeu"],
        ["A1", "TEJ ÷ CA > 1,05 et TEJ − CA > 5 000 DT", "(TEJ − CA) × 19 %"],
        ["A2", "factures El Fatoora ÷ CA > 1,05 et écart > 5 000 DT", "(factures − CA) × 19 %"],
        ["A3", "TVA déduite à l'import − TVA payée en douane > 2 % de la TVA payée et > 5 000 DT "
               "(TVA payée = maximum entre janvier–décembre et décembre précédent–novembre : 1 mois de décalage toléré)",
         "TVA déduite − TVA payée"],
        ["A4", "exportations déclarées ÷ exportations en douane > 1,10 et écart > 10 000 DT (vente de biens)", "écart × 19 %"],
        ["A5", "au moins 3 mois sans déclaration de TVA alors qu'il y a > 10 000 DT d'encaissements ou une importation",
         "encaissements ÷ 1,2 × 19/119"],
    ], [14 * mm, 116 * mm, 50 * mm]))
    el.append(P(puce_couleur(ORANGE, "<b>Niveau B — anomalie économique forte, après neutralisation</b>"), "h2"))
    el.append(tableau([
        ["Règle", "Se déclenche si", "Montant en jeu"],
        ["B1", "marge < max(5<super>e</super> centile du secteur ; 0), au moins 2 ans sur 3",
         "(coût × (1 + marge médiane du secteur) − CA) × 19 %"],
        ["B2", "prix unitaire < 10<super>e</super> centile et < 70 % de la médiane (même code SH, même origine), "
               "sur au moins 3 déclarations", "(médiane × quantité − valeur CIF) × (droits + 19 % × (1 + droits))"],
        ["B3", "cycle de 3 ou 4 sociétés dans le graphe des factures (liens ≥ 50 000 DT) passant par un maillon suspect "
               "(≥ 2 mois de TVA non déposée, ou CA déclaré < la moitié des factures émises)", "TVA des factures du circuit"],
        ["B4", "encaissements ÷ CA TTC > 1,5 et encaissements > 50 000 DT", "(encaissements ÷ 1,2 − CA TTC) × 19/119"],
    ], [14 * mm, 106 * mm, 60 * mm]))
    el.append(P(puce_couleur(GRIS_S, "<b>Niveau C — contexte (jamais suffisant seul)</b>"), "h2"))
    el.append(tableau([
        ["Règle", "Se déclenche si"],
        ["C1", "au moins 5 déclarations en douane de moins de 3 000 DT en 7 jours, chez le même fournisseur"],
        ["C2", "machine importée sans TVA (avantage fiscal) puis refacturée sous le même code SH — montant : min(revendu ; importé) × 19 %"],
        ["C3", "au moins 10 mois sur 12 en crédit de TVA, avec demandes de remboursement, dans un secteur normalement débiteur (hors exportatrices)"],
        ["C4", "même dirigeant ou même adresse qu'une société radiée, redressée ou défaillante (≥ 3 mois de TVA non déposée) ; "
               "ou société de moins de 18 mois avec plus de 500 000 DT de flux"],
        ["C5", "CA par salarié > 99<super>e</super> centile du secteur, ou plus de 500 000 DT d'importations avec 0 ou 1 salarié"],
    ], [14 * mm, 166 * mm]))
    el.append(P("Chaque montant est calculé sur la dernière année où la règle se déclenche.", "note"))

    # 4-6
    el.append(P("4. Montant en jeu de l'entreprise (sans double comptage)", "h1"))
    el.append(F("Montant = Σ par famille du plus grand montant de la famille"))
    el.append(tableau([
        ["Famille", "Règles"],
        ["Ventes cachées ou TVA non reversée", "A1, A2, A5, B1, B3, B4"],
        ["TVA à l'import", "A3"], ["Exportations", "A4"], ["Douane", "B2"], ["Avantages fiscaux", "C2"],
    ], [70 * mm, 110 * mm]))
    el.append(P("Exemple Sahel Électro : max(A1 = 76 000 ; B1 = 486 400 ; B4) + A3 40 000 = <b>526 400 DT</b>. "
                "C1, C3, C4 et C5 n'ont pas de montant.", "p"))

    el.append(KeepTogether([P("5. Catégorie (règles fixes)", "h1"),
        *puces([puce_couleur(ROUGE, "<b>Contrôle recommandé</b> : au moins 1 indice A avec plus de 20 000 DT en jeu, ou au moins 2 B, ou 1 B + 2 C."),
                puce_couleur(GRIS_S, "<b>Données insuffisantes</b> : une déclaration annuelle manque (sauf si déjà rouge : la preuve de tiers prime)."),
                puce_couleur(ORANGE, "<b>Demande de justification</b> : 1 B ou 2 C."),
                puce_couleur(VERT, "<b>Cohérent</b> : sinon."),
                "Un indice A de 20 000 DT ou moins compte comme un B. Un seul indice C ne suffit jamais."])]))

    el.append(KeepTogether([P("6. Force des indices", "h1"),
        F("Force = 1 − (1 − p<sub>1</sub>) × (1 − p<sub>2</sub>) × … avec p = 0,40 (A), 0,25 (B), 0,10 (C)"),
        *puces(["Zitouna Électro Maison (B2 + C4) : 1 − 0,75 × 0,90 = <b>0,325</b>",
                "Sahel Électro (A1, A3, B1, B4, C3, C4) : 1 − 0,6<super>2</super> × 0,75<super>2</super> × 0,9<super>2</super> = <b>0,836</b>"])]))

    # 7-8
    el.append(P("7. Score (0 à 100)", "h1"))
    el.append(F("Score = 100 × (0,45 × probabilité IA + 0,40 × force des indices + 0,15 × atypicité)"))
    el += puces([
        "<b>Probabilité IA</b> — LightGBM entraîné sur 580 contrôles passés (redressement = 1, sinon 0), environ 30 variables "
        "(« excès » comme max(0 ; TEJ ÷ CA − 1), marge sur 36 mois en écarts-types du secteur, ancienneté, taille, secteur…). "
        "Contraintes monotones : un excès plus grand ne fait jamais baisser le risque. Calibration isotonique (validation croisée "
        "5 plis) ; score hors échantillon pour les entreprises déjà contrôlées. Bornée entre 1 % et 90 % "
        "(≈ 10 % des fraudeurs contrôlés ressortent sans redressement).",
        "<b>Atypicité</b> — Isolation Forest par secteur, sur 10 indicateurs neutralisés. r = rang dans le secteur (0 à 1) ; "
        "<b>atypicité = max(0 ; 2r − 1)</b> : 0 pour la moitié la plus normale du secteur.",
        "<b>Cascade SHAP</b> — score = niveau moyen + 45 × (probabilité − moyenne), réparti entre variables selon SHAP "
        "+ 40 × (force − moyenne), réparti selon −ln(1 − p) + 15 × (atypicité − moyenne).",
        "Exemple Zitouna : 0,45 × 90 + 0,40 × 32,5 + 0,15 × 81 = <b>65,6</b>."])

    el.append(KeepTogether([P("8. Priorité (ordre de la liste de ciblage)", "h1"),
        F("Priorité = probabilité × montant en jeu"),
        *puces(["Sahel Électro : 0,90 × 526 400 ≈ 473 760 → 1<super>re</super>",
                "Zitouna Électro Maison : 0,90 × 475 702 ≈ 428 132 → 2<super>e</super>"])]))

    # 9
    el.append(KeepTogether([P("9. Dossier de contrôle — exemple Sahel Électro (2025)", "h1"),
        tableau([
            ["Poste", "Calcul", "Montant"],
            ["Coût des ventes net", "3 000 000 + 0 − 200 000", "2 800 000 DT"],
            ["CA reconstitué", "2 800 000 × (1 + 20 %)", "3 360 000 DT"],
            ["Écart de CA", "3 360 000 − 800 000", "2 560 000 DT"],
            ["TVA sur ventes omises", "2 560 000 × 19 %", "486 400 DT"],
            ["TVA déduite en trop", "610 000 − 570 000", "40 000 DT"],
            ["<b>Total TVA estimée</b>", "486 400 + 40 000", "<b>526 400 DT</b>"],
            ["IS (indicatif)", "2 560 000 × 20 % × 15 %", "76 800 DT"],
            ["Pénalités (indicatives)", "Σ sur 12 mois de (TVA ÷ 12 × 1,25 % × mois de retard)", "≈ 88 800 DT"],
        ], [55 * mm, 85 * mm, 40 * mm]),
        Spacer(1, 3),
        P("Mois de retard : « par mois ou fraction de mois » (article 81 du CDPF), chaque mois étant dû le 28 du mois suivant. "
          "Estimation indicative, à confirmer par la procédure contradictoire. Le LLM ne calcule rien : il recopie ces montants ; "
          "une rédaction contenant un autre montant est rejetée au profit d'un modèle déterministe.", "note")]))

    # 10-11
    el.append(P("10. Mesure de la performance (vérité cachée, jamais utilisée pour entraîner)", "h1"))
    el.append(F("Précision (top N) = fraudeurs réels parmi les N premiers ÷ N"))
    el += puces(["Top 100 : <b>100 %</b>, contre 11 % au hasard (× 9,1).",
                 "<b>Rappel (top N)</b> = fraudeurs dans le top N ÷ 220 fraudeurs.",
                 "<b>Montant détecté (top N)</b> = Σ montants réellement éludés par les fraudeurs du top N. "
                 "Top 100 : 67,0 M DT (règles + IA) contre 41,2 M DT (règles seules), <b>+63 %</b>.",
                 "<b>Fausses alertes sur les pièges</b> = pièges classés rouge ou orange ÷ 340 pièges : <b>1,5 %</b> pour l'outil, "
                 "contre 72 % pour la règle naïve « importations > CA local »."])
    el.append(P("11. Facilitation (T4)", "h1"))
    el += puces(["<b>Fiable</b> = aucun indice sur 3 ans + déclarations annuelles complètes + TVA à temps (au moins 24 mois, au plus 1 retard) "
                 "+ score < 10 + ancienneté ≥ 5 ans + aucun redressement + CA ≥ 500 000 DT.",
                 "<b>Candidate OEA</b> = fiable, importatrice ou exportatrice, pas encore agréée.",
                 "<b>Remboursement rapide de TVA</b> = fiable et exportatrice."])

    # T9
    el.append(PageBreak())
    el.append(P("12. Assistant réglementaire (T9) — pour le contribuable ET pour l'agent", "h1"))
    el.append(tableau([
        ["", "Mode contribuable — Amel, gérante de PME", "Mode agent — Sami, vérificateur"],
        ["Besoin", "comprendre ses droits et obligations", "trouver l'article exact en préparant un contrôle"],
        ["Style", "langage simple, étapes concrètes, délais, pièces", "technique : article, alinéa, conditions, exceptions, renvois"],
        ["Exemple", "« Le fisc me demande la liste de mes clients, en combien de temps ? » → article 16 : trente jours",
         "« Durée maximale d'une vérification approfondie ? » → article 40 : 6 mois (1 an si comptabilité non conforme)"],
        ["Autres", "pénalité si je paie en retard (art. 81) ; le contrôleur peut-il venir sans prévenir ; conditions OEA",
         "banques et relevés (art. 17) ; taxation d'office (art. 47) ; tarif de transaction (arrêté du 8 janvier 2002)"],
    ], [20 * mm, 80 * mm, 80 * mm]))
    el.append(Spacer(1, 4))
    el.append(P("Même moteur de recherche, même garde-fous : seule la consigne de rédaction change. Le dossier de contrôle (T3) "
                "utilise aussi ce moteur pour citer les articles 16, 17, 40, 47, 81.", "p"))
    el.append(P("Les formules de l'assistant", "h2"))
    el.append(F("Proximité = cosinus(question, extrait) = produit scalaire des vecteurs bge-m3 normalisés (1 024 dimensions)"))
    el.append(F("Fusion RRF : score(extrait) = Σ poids ÷ (60 + rang dans chaque liste)"))
    el += puces(["Listes : sens (bge-m3 + FAISS) et mots-clés (BM25), pour la question et sa reformulation en français juridique "
                 "(poids 1), plus l'expansion par le lexique juridique (poids 0,5). « Article N » cité → mis en tête directement.",
                 "Test au démarrage : cosinus moyen sur 20 extraits ≥ 0,98 (mesuré : 1,0).",
                 "8 meilleurs extraits transmis au modèle local (Qwen3 8B) ; lignes de tarif douanier exclues sauf question sur les équipements.",
                 "<b>Abstention</b> si le meilleur cosinus < 0,517 — calibré sur 20 questions : 0,483 (plus haute question hors sujet) "
                 "+ (0,587 (plus basse question couverte) − 0,483) ÷ 3.",
                 "<b>Garde-fous</b> : chaque citation [n] doit correspondre à un extrait fourni (sinon retirée) ; chaque délai, taux ou "
                 "montant doit figurer dans les extraits (sinon affiché « à vérifier ») ; TVA et IRPP/IS signalés non couverts ; "
                 "Code des douanes signalé en édition 2016."])

    el.append(Spacer(1, 10))
    el.append(P("<b>En une phrase</b> : on corrige les écarts honnêtes, on croise des sources indépendantes avec 14 règles, on classe "
                "avec deux modèles de machine learning expliqués par SHAP, et l'agent décide.", "oral"))
    return el


def generer() -> Path:
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(SORTIE), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title="RASD 360 — Fiche des formules", author="RASD 360 (prototype)")
    doc.build(contenu(), onFirstPage=pied, onLaterPages=pied)
    return SORTIE


if __name__ == "__main__":
    print(generer())
