# RASD 360 — Radar fiscal et douanier

> **Prototype — données entièrement fictives.** Hackathon national « IA & Finances publiques ».
> رصد (*rasd*) : veille, surveillance.

*« La douane a déjà une IA qui contrôle chaque déclaration. Personne ne regarde l'entreprise en entier,
impôts et douane ensemble, sur toute l'année. C'est là que la fraude se cache. »*

RASD 360 croise automatiquement, **pour toutes les entreprises et avant de choisir qui contrôler**, les données
de la douane, des déclarations fiscales, des retenues à la source (TEJ), des factures électroniques (El Fatoora)
et des encaissements bancaires. Trois modules et un bonus :

| Module | Défi | Pour qui | Ce qu'il produit |
|---|---|---|---|
| **Ciblage** | T20 (avec T7, T2) | Programmation des contrôles | Liste priorisée : score, raisons en phrases simples, preuves, montant en jeu |
| **Dossier de contrôle** | T3 (avec T14) | Vérificateur | Pré-dossier en un clic : écarts chiffrés, articles applicables, pièces à demander, projet de lettre, PDF |
| **Assistant réglementaire** | T9 | Contribuable et agent | Réponse en français, en arabe ou en dialecte, avec l'article exact et son texte |
| **Facilitation** | T4 (bonus) | Direction | Entreprises fiables : candidates OEA et remboursement rapide du crédit de TVA |

**Principe :** un écart ne prouve pas une fraude. Le score mesure **la probabilité qu'un contrôle soit utile**, pas
la culpabilité. L'outil construit un faisceau d'indices graves, précis et concordants ; **l'humain décide toujours**,
l'entreprise peut s'expliquer (procédure contradictoire), aucune sanction n'est automatique.

---

## Démarrage rapide (Windows, PowerShell)

```powershell
scripts\setup.ps1          # une seule fois : index, venv, modèles, base fictive, scores, frontend
scripts\run_backend.ps1    # API FastAPI  -> http://127.0.0.1:8000  (documentation : /docs)
scripts\run_frontend.ps1   # interface    -> http://localhost:3000   (option -Dev : mode développement)
scripts\reset_demo.ps1     # remet la démo à zéro (seed 42), avec ou sans l'API lancée
```

### Prérequis

| Élément | Version / remarque |
|---|---|
| Windows 10/11, PowerShell 5.1+ | si besoin : `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Python | 3.11 (lanceur `py -3.11`) |
| Node.js | 20 ou plus |
| Ollama | avec `qwen3:8b` (`ollama pull qwen3:8b`) ; GPU NVIDIA 8 Go conseillé |
| Index RAG | fourni par les organisateurs : fichiers dans `data\rag_index\`, ou archive passée à `setup.ps1 -IndexZip <chemin>` |

### Installation pas à pas (ce que fait `setup.ps1`)

1. Si besoin, dézippe l'index RAG (`-IndexZip`) dans `data\rag_index\` (**lecture seule**, jamais modifié).
2. Crée `backend\.venv`, installe PyTorch **CPU** puis `backend\requirements.txt`.
3. Télécharge `BAAI/bge-m3` dans le cache Hugging Face (encodage des questions sur CPU).
4. Vérifie Ollama et `qwen3:8b`.
5. Génère la base fictive (`python -m data_gen.generate`), calcule règles, modèle, scores et métriques
   (`python -m app.risk.scoring`), calibre le seuil d'abstention du retriever (`python -m app.rag.calibration`).
6. Installe et construit le frontend (`npm install`, `npm run build`).

Sans Ollama, tout fonctionne sauf la rédaction par LLM : l'assistant affiche un message clair et le dossier
utilise un modèle de rédaction déterministe (mêmes montants, mêmes articles).

---

## Parcours de démonstration (10 minutes)

1. **Tableau de bord** — 2 000 entreprises fictives analysées, alertes, montant en jeu, réussite du ciblage vs hasard.
2. **Ciblage** — *Sahel Électro SARL* en tête. Avec **le même écart brut** (3 M DT importés pour 0,8 M DT de CA),
   *Cap Bon Distribution* est verte : son stock a augmenté de 2,3 M DT (nouvel entrepôt).
3. **Fiche Sahel Électro** — les 4 sources qui divergent sur 36 mois ; indices A1 (clients TEJ > CA) et A3
   (TVA déduite > TVA payée) avec leurs preuves ; explications légitimes vérifiées ; cascade SHAP ; réseau
   (gérant lié à *Sahel Mobile SARL*, radiée après redressement).
4. **Préparer le dossier** — génération en direct : 526 400 DT de TVA estimée, articles 16, 17 et 81 du code des
   droits et procédures fiscaux avec leur texte, projet de lettre, export PDF.
5. **Assistant** — la question d'Amel en dialecte (« الجباية طلبت مني قائمة الحرفاء… ») : article 16, trente jours,
   source cliquable avec le passage surligné.
6. **Facilitation et Performance** — *Nour Textile SA* candidate OEA ; notre ciblage comparé au hasard, à l'écart
   brut naïf et aux règles seules.

Autres vitrines : *Djerba Industries* (machines de l'annexe 2017-419, verte), *Médina Trade* (sous-évaluation en
douane), *Carthage Négoce → Atlas Services → Yasmine Distribution* (carrousel de TVA, graphe du réseau).

---

## Architecture

```
 Sources (fictives)                 Backend FastAPI (Python 3.11)                          Interface Next.js 14
 ───────────────────               ──────────────────────────────────────────────────     ────────────────────
 Douane (déclarations)  ─┐         risk/      features → 14 règles A/B/C → décision        Tableau de bord
 TVA mensuelle          ─┤  SQLite            LightGBM calibré + Isolation Forest + SHAP   Ciblage
 Déclarations annuelles ─┼─ (seed ─►          évaluation sur vérité terrain                Fiche 360
 TEJ (retenues)         ─┤   42)   dossier/   calc.py (déterministe) → articles → LLM → PDF  Dossier T3
 El Fatoora (factures)  ─┤         rag/       FAISS + bge-m3 (CPU) + BM25, fusion RRF      Assistant T9
 Banque (encaissements) ─┘         chat/      assistant FR/AR/dialecte, citations vérifiées Facilitation, Performance
                                   llm.py     Ollama qwen3:8b (local, GPU)
```

```
hack_finance/
├── backend/app/
│   ├── main.py            routes, CORS, démarrage (contrôle de l'index, préchauffage)
│   ├── config.py          chemins, modèles, seuils, paramètres (surchargeables par .env)
│   ├── db.py              schéma SQLite (SQLAlchemy Core)
│   ├── rag/               index.py (chargement + contrôles), embedder.py (test de compatibilité),
│   │                      retriever.py (hybride), calibration.py (seuil d'abstention)
│   ├── risk/              features.py, rules.py, model.py, explain.py, scoring.py, evaluation.py
│   ├── dossier/           calc.py, articles.py, generator.py, export.py (PDF)
│   ├── chat/assistant.py  assistant réglementaire
│   ├── services.py        requêtes de l'API (fiche 360, statistiques…)
│   └── llm.py             client Ollama
├── backend/tests/         81 tests automatisés (pytest)
├── data_gen/              generate.py, scenarios.py, reference.py, demo_companies.py
├── data/                  rag_index/ (lecture seule), rasd.db, ground_truth.csv, models/  (générés, hors git)
├── frontend/              Next.js 14 + TypeScript + Tailwind + composants Radix (style shadcn/ui)
└── scripts/               setup.ps1, run_backend.ps1, run_frontend.ps1, reset_demo.ps1, benchmark_llm.py
```

---

## Module Ciblage (T20)

**1. Neutraliser les explications légitimes avant tout calcul** : variation de stock, comparaison glissante sur
12 et 36 mois, équipements exclus grâce au code SH (annexe du décret 2017-419), admission temporaire et
réexportation, exportations, données manquantes (catégorie « données insuffisantes »), comparaison au secteur.

**2. Croiser des sources indépendantes** — `backend/app/risk/rules.py`, chaque règle testée unitairement et
renvoyant valeur, seuil, déclenchement, force, montant en jeu, phrase explicative et preuves (lignes sources) :

| Niveau | Règles |
|---|---|
| **A** — contradiction avec des données de tiers | A1 paiements TEJ > CA · A2 factures El Fatoora > CA · A3 TVA déduite à l'import > TVA payée (1 mois de décalage toléré) · A4 exportations déclarées > douane · A5 défaut de déclaration malgré une activité |
| **B** — anomalie économique forte | B1 marge implicite impossible sur 2 ans (après neutralisation) · B2 sous-évaluation en douane · B3 carrousel (cycles de 3 ou 4 factures, NetworkX) · B4 encaissements > 1,5 × CA TTC |
| **C** — contexte (jamais suffisant seul) | C1 fractionnement · C2 équipements exonérés revendus · C3 crédit de TVA structurel · C4 réseau à risque · C5 productivité anormale |

**Décision** : 🔴 contrôle recommandé (≥ 1 indice A avec > 20 000 DT en jeu, ou ≥ 2 B, ou 1 B + 2 C) ;
🟠 demande de justification (1 B ou ≥ 2 C) ; ⚪ données insuffisantes ; 🟢 cohérent (candidate à la facilitation
si tous les critères sont remplis sur 3 ans).

**3. Apprendre des contrôles passés** : LightGBM à **contraintes monotones** (un excès plus grand ne diminue jamais
le risque) entraîné sur ~600 contrôles aux étiquettes imparfaites, calibration isotonique, score hors échantillon
pour les entreprises déjà contrôlées, probabilité bornée à 90 % (≈ 10 % des fraudeurs contrôlés ressortent sans
redressement). Isolation Forest **par secteur** sur des indicateurs neutralisés (signaux faibles). SHAP par entreprise.

**Score** = 45 % probabilité calibrée + 40 % force des indices + 15 % atypicité ; **priorité = probabilité × montant
en jeu**. La cascade affichée sur la fiche décompose exactement le score. Bouton « Résultat du contrôle » et
ré-entraînement (`POST /api/admin/reentrainer`) : boucle d'apprentissage.

**Évaluation** (page Performance) : hasard, écart brut naïf, règles seules, règles + IA — précision et rappel sur
les 50, 100 et 200 premiers contrôles, montant détecté, fausses alertes sur les pièges, détection par schéma.
**Aucun chiffre n'est écrit à la main** : tout est recalculé à chaque génération sur la vérité terrain
(`data/ground_truth.csv`), qui n'est **jamais** utilisée pour entraîner.

## Module Dossier (T3)

Règle d'or : **le LLM ne calcule jamais.** `dossier/calc.py` produit tous les montants (CA reconstitué, écart,
TVA sur ventes omises, TVA déduite en trop, IS et pénalités indicatifs à 1,25 % par mois ou fraction de mois —
article 81 du CDPF), avec formules et hypothèses ; les taux de TVA et d'IS sont des paramètres « à vérifier ».
Pour Sahel Électro : 2 800 000 × 1,20 − 800 000 = 2 560 000 DT d'écart ; 486 400 + 40 000 = **526 400 DT**.

Les articles applicables sont retrouvés dans l'index selon les indices déclenchés et **vérifiés par identifiant**,
avec l'extrait exact. Le LLM rédige la synthèse et la lettre en JSON (schéma Ollama + validation Pydantic, une
relance) ; si un montant de la rédaction ne vient pas de `calc.py`, la rédaction est écartée au profit d'un modèle
déterministe. Le dossier est modifiable, validable (statut Brouillon → Validé) et exportable en PDF.

## Module Assistant (T9)

Recherche hybride : `BAAI/bge-m3` sur CPU (même modèle que l'index, vérifié au démarrage : cosinus moyen ≥ 0,98 sur
20 records) + FAISS, BM25 (`rank-bm25`), fusion Reciprocal Rank Fusion, recherche directe d'article (« article 81 du
code… »), lignes tarifaires exclues par défaut, lexique juridique en expansion. La question est d'abord reformulée
en français juridique par le LLM (décodage déterministe), la réponse est rédigée dans la langue de l'utilisateur.

Garde-fous : réponse uniquement à partir des extraits, chaque affirmation citée `[n]`, citations vérifiées contre
les sources, chiffres absents des extraits signalés « à vérifier », abstention calibrée sur un jeu de 20 questions
(`backend/tests/rag_questions.json`), TVA et IRPP/IS signalés comme non couverts, Code des douanes signalé en
édition 2016, mention « Information, pas un conseil juridique ».

## Base fictive (seed 42)

`data_gen/` génère 2 000 entreprises actives (+ 45 sociétés radiées servant d'ancres au réseau) sur 2023–2025, avec
activité **réelle** cohérente comptablement puis déclarations falsifiées selon 8 schémas de fraude (F1 minoration du
CA, F2 sous-évaluation, F3 TVA déductible gonflée, F4 société écran, F5 carrousel, F6 fractionnement, F7 détournement
d'avantages, F8 fausses exportations) et 7 types de pièges honnêtes (stock, décalage de période, équipements,
admission temporaire, export, données manquantes, faible marge). Répartition : ~72 % honnêtes, ~17 % pièges, ~11 %
fraudeurs. Secteurs : nomenclature NAT 2009 (actif de l'index) ; équipements : annexe du décret 2017-419.
Noms, matricules et personnes inventés, aucun numéro d'identité.

## API (extrait)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/health` | index (ntotal), embeddings (test de compatibilité), Ollama, base |
| GET | `/api/stats` · `/api/entreprises` · `/api/entreprises.csv` | tableau de bord, ciblage filtrable, export CSV |
| GET | `/api/entreprises/{id}` · `/api/entreprises/{id}/preuves/{regle}` | fiche 360, lignes sources d'un indice |
| POST | `/api/entreprises/{id}/dossier` | pré-dossier (option `stream` : étapes en direct) |
| GET/PUT | `/api/dossiers/{id}` · GET `/api/dossiers/{id}/pdf` | lecture, modification, validation, PDF |
| POST | `/api/entreprises/{id}/resultat-controle` · `/api/admin/reentrainer` | boucle d'apprentissage |
| POST | `/api/chat` | assistant (streaming NDJSON : méta, sources, jetons, fin) |
| GET | `/api/rag/record/{id}` · `/api/rag/sources` | texte complet d'un article, sources indexées |
| GET | `/api/facilitation` · `/api/performance` · `/api/audit` | T4, évaluation, journal d'audit |
| POST | `/api/admin/reset-demo` | régénère la base (seed 42) |

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Couvrent : intégrité de l'index et compatibilité des embeddings, volumes et identités comptables de la base,
valeurs exactes des vitrines, chaque règle A/B/C sur des cas construits à la main, la décision, le ciblage de bout
en bout (Sahel rouge et en tête, Cap Bon et Djerba verts), les 7 tests d'acceptation du retriever (top 3),
l'abstention, l'assistant (question d'Amel, TVA non couverte), le calcul de référence de Sahel (526 400 DT), les
articles 16, 17 et 81 du dossier, l'export PDF et la validation. Les tests LLM sont ignorés si Ollama est absent.

## LLM local

Ollama sur `http://127.0.0.1:11434` (et non `localhost`, qui tente d'abord IPv6 sous Windows et ajoute ~2 s par
appel), mode « thinking » désactivé, température 0,2, contexte 8 192. `qwen3:8b` est le modèle par défaut :
`scripts/benchmark_llm.py` mesure la latence de `qwen3:8b` et `qwen3.5:9b` (résultat dans
`data/models/benchmark_llm.json`) ; sur 8 Go de VRAM, `qwen3:8b` offre le meilleur compromis. Un seul modèle est
chargé à la fois ; les embeddings des questions tournent sur CPU.

---

## Ressources pré-existantes et tierces (déclarées)

- **Index RAG** construit **avant le hackathon** par l'équipe (FAISS `IndexFlatIP`, 4 523 vecteurs bge-m3), filtré
  et complété pendant l'événement : Code des droits et procédures fiscaux 2024, Code des douanes 2016, Code des droits
  d'enregistrement et de timbre 2025, décret OEA 2018-612, loi 2017-8, décrets 2017-418 et 2017-419, et ses actifs
  (nomenclature NAT 2009, codes tarifaires des équipements).
- **Modèles** : `BAAI/bge-m3` (embeddings, sentence-transformers), **Qwen3 8B** via Ollama (rédaction et reformulation).
- **Bibliothèques Python** : FastAPI, Uvicorn, Pydantic, SQLAlchemy, pandas, NumPy, PyTorch (CPU), sentence-transformers,
  faiss-cpu, rank-bm25, scikit-learn, **LightGBM**, **SHAP**, NetworkX, httpx, ReportLab, pytest
  (versions : `backend/requirements.txt`).
- **Bibliothèques JavaScript** : Next.js 14, React 18, TypeScript, Tailwind CSS, Radix UI (composants au style
  shadcn/ui), Recharts, lucide-react, framer-motion, react-force-graph-2d, SWR, sonner, polices Inter et
  IBM Plex Sans Arabic (Fontsource) (versions : `frontend/package.json`).

## Garde-fous

Données 100 % fictives (loi organique 2004-63, INPDP) ; pas de logo officiel, bandeau « Prototype — données
entièrement fictives » permanent ; le score n'est jamais présenté comme une preuve ; validation humaine obligatoire
et procédure contradictoire ; le LLM ne calcule pas et n'invente pas d'article (citations vérifiées) ; paramètres
légaux non indexés marqués « à vérifier » ; journal d'audit (consultation, génération, validation, export).

## Limites et recommandations pour une mise en production

- Les performances sont mesurées sur des données synthétiques : à revalider sur l'historique réel des contrôles de la
  DGI, avec suivi de la dérive et de l'équité (secteurs, régions, tailles).
- Compléter l'index : Code de la TVA, Code de l'IRPP et de l'IS, Code des douanes à jour ; revue juridique des
  réponses et des modèles de lettre.
- Connexion sécurisée aux systèmes existants (SINDA 2, TEJ, El Fatoora, données bancaires sur réquisition) :
  on ne remplace rien, on se branche ; moteur réglementaire intégrable derrière El Diwani.
- Hébergement souverain, authentification et habilitations, journal d'audit centralisé, PostgreSQL à la place de
  SQLite, supervision des modèles et ré-entraînement contrôlé.
- Évaluation humaine systématique des sorties du LLM avant tout usage opposable.
