"""Génère docs/RASD360_note_synthese.pdf : note de synthèse du projet (2 pages maximum, livrable 4.3).

Usage (depuis la racine) : backend\\.venv\\Scripts\\python.exe scripts\\note_synthese.py
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import CondPageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "docs" / "RASD360_note_synthese.pdf"

BLEU, ACTION, GRIS, LIGNE, FOND = (colors.HexColor(c) for c in ("#0B2545", "#1D4ED8", "#64748B", "#E2E8F0", "#F1F5F9"))


def _polices() -> tuple[str, str]:
    import reportlab
    rl = Path(reportlab.__file__).parent / "fonts"
    for n, g in ((Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")), (rl / "Vera.ttf", rl / "VeraBd.ttf")):
        if n.exists() and g.exists():
            pdfmetrics.registerFont(TTFont("F", str(n)))
            pdfmetrics.registerFont(TTFont("F-B", str(g)))
            pdfmetrics.registerFontFamily("F", normal="F", bold="F-B", italic="F", boldItalic="F-B")
            return "F", "F-B"
    return "Helvetica", "Helvetica-Bold"


N, B = _polices()
ST = {
    "titre": ParagraphStyle("titre", fontName=B, fontSize=17, leading=20, textColor=BLEU),
    "sous": ParagraphStyle("sous", fontName=N, fontSize=8.8, leading=12, textColor=GRIS),
    "h1": ParagraphStyle("h1", fontName=B, fontSize=11, leading=14, textColor=BLEU, spaceBefore=5, spaceAfter=2),
    "p": ParagraphStyle("p", fontName=N, fontSize=8.6, leading=11.2, spaceAfter=2),
    "puce": ParagraphStyle("puce", fontName=N, fontSize=8.6, leading=11.2, leftIndent=10, bulletIndent=2, spaceAfter=1),
    "cel": ParagraphStyle("cel", fontName=N, fontSize=8.1, leading=10.4),
    "celb": ParagraphStyle("celb", fontName=B, fontSize=8.1, leading=10.4),
    "encadre": ParagraphStyle("encadre", fontName=N, fontSize=8.6, leading=11.2, textColor=BLEU, backColor=colors.HexColor("#EFF6FF"),
                              borderPadding=(4, 6, 4, 6), spaceBefore=3, spaceAfter=5, leftIndent=3, rightIndent=3),
    "alerte": ParagraphStyle("alerte", fontName=N, fontSize=8.4, leading=11.2, textColor=colors.HexColor("#78350F"),
                             backColor=colors.HexColor("#FEF3C7"), borderPadding=(4, 6, 4, 6), spaceBefore=4, spaceAfter=4,
                             leftIndent=3, rightIndent=3),
}


def P(t, s="p"):
    return Paragraph(t, ST[s])


def puces(items):
    return [Paragraph(t, ST["puce"], bulletText="•") for t in items]


def tableau(lignes, largeurs):
    data = [[P(c, "celb" if i == 0 or j == 0 else "cel") for j, c in enumerate(l)] for i, l in enumerate(lignes)]
    t = Table(data, colWidths=largeurs, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LIGNE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("BACKGROUND", (0, 0), (-1, 0), FOND),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return t


def pied(c, doc):
    w, h = A4
    c.saveState()
    c.setFillColor(colors.HexColor("#FEF3C7"))
    c.rect(0, h - 6 * mm, w, 6 * mm, stroke=0, fill=1)
    c.setFillColor(colors.HexColor("#92400E"))
    c.setFont(B, 7)
    c.drawCentredString(w / 2, h - 4 * mm, "RASD 360 — PROTOTYPE, DONNÉES ENTIÈREMENT FICTIVES")
    c.setFont(N, 7)
    c.setFillColor(GRIS)
    c.drawString(15 * mm, 8 * mm, "RASD 360 — Note de synthèse · Hackathon « IA & Finances publiques »")
    c.drawRightString(w - 15 * mm, 8 * mm, f"Page {doc.page} / 2")
    c.restoreState()


def contenu():
    W = 180 * mm
    el = [P("RASD 360 — Radar fiscal et douanier", "titre"),
          P("Note de synthèse · Hackathon « IA &amp; Finances publiques » · défi principal T20 (ciblage des contrôles), "
            "défi secondaire T9 (assistant réglementaire), avec T3 (dossier de contrôle) et T4 (facilitation) · septembre 2026", "sous"),
          Spacer(1, 4)]

    el.append(P("1. Défi choisi", "h1"))
    el.append(P("L'administration fiscale et douanière contrôle <b>peu, tard et à l'aveugle</b> : les données de la douane, des impôts, "
                "de la TEJ et d'El Fatoora sont cloisonnées ; le choix des contrôles repose sur l'expérience ou sur des listes ; "
                "préparer un dossier prend des jours ; contribuables et agents perdent du temps à chercher le bon article dans "
                "plusieurs codes. RASD 360 répond par quatre modules sur une même plateforme :"))
    el += puces(["<b>Cibler (T20)</b> : liste classée des entreprises à contrôler, avec raisons, preuves et montant en jeu.",
                 "<b>Préparer (T3)</b> : pré-dossier de contrôle généré en 15 s (écarts chiffrés, articles, pièces à demander, lettre, PDF).",
                 "<b>Répondre (T9)</b> : assistant réglementaire sourcé pour le contribuable et pour l'agent, en français, arabe ou tounsi.",
                 "<b>Récompenser (T4)</b> : repérage des entreprises fiables (candidates OEA, remboursement rapide de crédit de TVA)."])

    el.append(P("2. Données utilisées", "h1"))
    el += puces(["<b>Cinq sources croisées par entreprise</b>, déjà détenues par l'administration : douane (importations, exportations, "
                 "régimes), impôts (TVA mensuelle, déclaration annuelle, stocks), TEJ (paiements attestés par les clients), "
                 "El Fatoora (factures émises), banque (encaissements agrégés).",
                 "<b>Prototype</b> : 2 000 entreprises <b>entièrement fictives</b> (2023–2025), comptablement cohérentes, générées de façon "
                 "reproductible (graine 42) : 1 440 honnêtes, 340 honnêtes « pièges » (écart apparent mais justifié : stock, "
                 "équipements, exportations) et 220 fraudeurs selon 14 schémas. Aucune donnée réelle (loi organique 2004-63).",
                 "<b>Base réglementaire</b> : 4 523 extraits de textes officiels indexés article par article (code des droits et "
                 "procédures fiscaux 2024, code des douanes 2016, code de l'enregistrement et du timbre 2025, décret OEA 2018-612, "
                 "avantages fiscaux 2017)."])

    el.append(P("3. Approche technique et modèles", "h1"))
    el.append(P("<b>Ciblage — des règles pour prouver, l'IA pour classer.</b> (1) Les écarts honnêtes sont retirés avant le calcul "
                "(variation de stock, biens d'équipement, exportations). (2) <b>14 règles déterministes</b> croisent les sources : "
                "A = preuve directe (ex. factures ou paiements clients supérieurs au CA déclaré, TVA déduite supérieure à la TVA payée), "
                "B = anomalie forte (marge anormale, sous-facturation à l'import, circuit de factures, encaissements bancaires), "
                "C = signal de contexte. La couleur (rouge, orange, gris, vert) découle <b>uniquement</b> de ces règles, lisibles et "
                "opposables. (3) Un modèle <b>LightGBM</b> (contraintes monotones, calibration isotone, prédictions hors échantillon, "
                "probabilité plafonnée à 0,90) estime la chance qu'un contrôle aboutisse, apprise sur les contrôles passés. "
                "(4) Un <b>Isolation Forest</b> par secteur mesure l'atypicité, pour repérer des schémas inconnus. "
                "(5) <b>SHAP</b> décompose chaque score à l'écran."))
    el.append(P("Score (0–100) = 100 × (0,45 × probabilité + 0,40 × force des indices + 0,15 × atypicité), avec "
                "force = 1 − Π(1 − poids), poids A 0,40 · B 0,25 · C 0,10.  Ordre de la liste : priorité = probabilité × montant en jeu.",
                "encadre"))
    el.append(P("<b>Pré-dossier (T3).</b> Les montants sont calculés par du code déterministe (jamais par le modèle de langage), les "
                "articles sont vérifiés dans la base, le modèle de langage ne fait que rédiger ; en son absence, un modèle de "
                "rédaction fixe produit les mêmes montants et articles. Export PDF."))
    el.append(P("<b>Assistant (T9) — RAG hybride.</b> Reformulation juridique de la question ; recherche par le sens (FAISS, "
                "plongements BAAI/bge-m3) et par mots-clés (BM25), fusion RRF et accès direct par numéro d'article ; "
                "<b>abstention calibrée</b> (« je n'ai pas trouvé » plutôt qu'inventer) ; rédaction à partir des seuls extraits "
                "avec citation de l'article ; contrôle a posteriori des citations et des chiffres ; sujets non couverts signalés. "
                "Deux modes : contribuable (langage simple) et agent (article, alinéa, conditions). Modèle de langage "
                "<b>Qwen3-8B exécuté localement</b> (Ollama) : aucune donnée ne sort du poste."))
    el.append(P("<b>Architecture.</b> API FastAPI (Python 3.11), base SQLite, interface Next.js 14 ; 81 tests automatisés ; "
                "démonstration rejouable à l'identique par un script de remise à zéro."))

    el.append(P("4. Résultats obtenus (jeu fictif de 2 000 entreprises)", "h1"))
    el.append(tableau([
        ["Indicateur", "RASD 360", "Référence", "Comment c'est mesuré"],
        ["Contrôles justes dans les 100 premiers", "100 %", "11 % au hasard ; ≈ 25 % sélection type historique",
         "Liste comparée à l'étiquette cachée (fraudeur / honnête) posée par le générateur, jamais montrée à l'IA"],
        ["Honnêtes « pièges » alertés à tort", "1,5 % (5 / 340)", "72 % (245 / 340) avec la règle brute importations &gt; CA",
         "Nombre d'honnêtes à écart justifié placés en alerte"],
        ["Montant éludé couvert par les 100 premiers", "67,0 M DT", "41,2 M DT avec les règles seules (+63 %)",
         "Somme des montants réellement éludés, tri par probabilité × montant"],
        ["Pouvoir de discrimination (AUC)", "0,99 / 0,76", "—",
         "0,99 sur la vérité du générateur ; 0,76 en validation croisée sur les contrôles passés"],
        ["Fraudeurs non détectés", "20 / 220", "—", "dont 13 tout de même signalés comme atypiques"],
        ["Temps de réponse", "≈ 15 s · ≈ 1,9 s", "plusieurs jours de préparation manuelle",
         "Pré-dossier complet ; premier mot de l'assistant (poste de démonstration)"],
    ], [42 * mm, 26 * mm, 48 * mm, 64 * mm]))
    el.append(CondPageBreak(22 * mm))
    el.append(P("<b>Lecture honnête</b> : les fraudes et les règles ont été conçues par la même équipe ; ces chiffres valident la "
                "<b>mécanique</b> de bout en bout, pas encore l'efficacité réelle. Le résultat le plus parlant est la réduction des "
                "fausses alertes (1,5 % contre 72 %) : l'approche naïve accuse les honnêtes.", "alerte"))

    el.append(P("5. Limites identifiées", "h1"))
    el += puces(["<b>Données fictives</b> : aucune mesure d'efficacité réelle ; les seuils des règles et les poids du score restent à "
                 "calibrer sur des cas réels.",
                 "<b>Étiquettes d'apprentissage</b> : en réel, les contrôles passés sont biaisés (on n'observe que les entreprises "
                 "déjà contrôlées) ; le modèle risque de reproduire les choix historiques.",
                 "<b>Base réglementaire incomplète</b> : codes de la TVA, de l'IRPP et de l'IS non intégrés ; code des douanes en "
                 "édition 2016. Les réponses sur ces sujets sont signalées comme non couvertes.",
                 "<b>Modèle de langage de taille moyenne</b> (8 milliards de paramètres, local) : réponses revérifiées "
                 "automatiquement, mais à valider par l'agent ; l'assistant informe, il ne donne pas de conseil juridique.",
                 "<b>Montants indicatifs</b> : estimations à confirmer par la procédure contradictoire ; le score mesure l'utilité "
                 "d'un contrôle, pas la culpabilité. L'agent décide toujours."])

    el.append(P("6. Recommandations pour une mise en production", "h1"))
    el += puces(["<b>Valider avant de déployer</b> : (1) test rétrospectif sur l'historique des contrôles de la DGI et de la douane "
                 "(le système aurait-il retrouvé les redressements connus ?) ; (2) mode observation de 3 à 6 mois, liste produite "
                 "mais non utilisée ; (3) pilote comparatif dans une ou deux directions régionales, sélection RASD contre sélection "
                 "habituelle, sur le taux de redressement et le montant recouvré.",
                 "<b>Intégration</b> : connecteurs en lecture seule vers SINDA 2, TEJ, El Fatoora et les déclarations fiscales ; "
                 "l'assistant peut servir de moteur derrière les portails existants (El Diwani). Aucune nouvelle collecte de données.",
                 "<b>Gouvernance et sécurité</b> : hébergement souverain, habilitations par profil, journal d'audit centralisé, "
                 "avis de l'INPDP ; comité métier qui valide et versionne les règles A/B/C ; toute décision reste humaine.",
                 "<b>Vie du modèle</b> : saisie systématique des résultats de contrôle, réentraînement périodique, suivi de la "
                 "dérive et de l'équité entre secteurs et régions ; une part de contrôles aléatoires pour corriger le biais "
                 "de sélection.",
                 "<b>Base réglementaire</b> : intégrer les codes de la TVA, de l'IRPP et de l'IS, le code des douanes à jour et les "
                 "notes communes ; jeu de questions de référence validé par des juristes pour mesurer la qualité à chaque mise à jour.",
                 "<b>Adoption</b> : formation courte des vérificateurs, retour d'expérience intégré à l'outil, déploiement progressif "
                 "par direction."])
    el.append(Spacer(1, 6))
    el.append(P("<b>En une phrase</b> : RASD 360 ne remplace aucun système ni aucun agent ; il se branche sur les données existantes "
                "pour que chaque contrôle soit mieux choisi, mieux préparé et mieux expliqué — le score mesure l'utilité d'un "
                "contrôle, pas la culpabilité, et la décision reste humaine.", "encadre"))
    return el


def main() -> None:
    SORTIE.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(SORTIE), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=11 * mm,
                            bottomMargin=13 * mm, title="RASD 360 — Note de synthèse", author="Équipe RASD 360")
    doc.build(contenu(), onFirstPage=pied, onLaterPages=pied)
    print(f"PDF écrit : {SORTIE}")


if __name__ == "__main__":
    main()
