"""Mesure la latence des deux LLM locaux (section 9) : premier mot du chat et durée totale.

Usage (depuis la racine) : backend\\.venv\\Scripts\\python.exe scripts\\benchmark_llm.py
Résultat écrit dans data/models/benchmark_llm.json (cité dans le README).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "backend"))

from app import config, llm  # noqa: E402
from app.chat import assistant  # noqa: E402
from app.rag import embedder  # noqa: E402
from app.rag.index import get_index  # noqa: E402
from app.rag.retriever import get_retriever  # noqa: E402

QUESTIONS = [
    "Le fisc me demande la liste de mes clients, je suis obligée ? En combien de temps ?",
    "Quelle est la durée maximale d'une vérification approfondie ?",
    "Quel est le taux de la pénalité de retard de paiement de l'impôt ?",
]


def mesurer(modele: str) -> dict:
    t = time.perf_counter()
    llm.prechauffer(modele)
    chargement = time.perf_counter() - t
    mesures = []
    for q in QUESTIONS:
        ref = assistant.reformuler(q)
        rech = get_retriever().rechercher(q, requetes_sup=[ref] if ref else None)
        messages, sources = assistant.construire_messages(q, rech, "contribuable", "fr", ref, None)
        t0 = time.perf_counter()
        premier, texte = None, []
        for tok in llm.chat_stream(messages, model=modele):
            premier = premier or time.perf_counter() - t0
            texte.append(tok)
        rep = "".join(texte)
        mesures.append({"question": q, "premier_mot_s": round(premier or 0, 2), "total_s": round(time.perf_counter() - t0, 2),
                        "citations": assistant.verifier_citations(rep, len(sources))[0],
                        "chiffres_non_verifies": assistant.verifier_chiffres(rep, sources)})
    return {"modele": modele, "chargement_s": round(chargement, 1),
            "premier_mot_moyen_s": round(sum(m["premier_mot_s"] for m in mesures) / len(mesures), 2),
            "total_moyen_s": round(sum(m["total_s"] for m in mesures) / len(mesures), 2), "mesures": mesures}


if __name__ == "__main__":
    embedder.initialize(get_index())
    res = [mesurer(m) for m in (config.LLM_MODEL_QUALITY, config.LLM_MODEL)]  # le modèle par défaut reste chargé à la fin
    sortie = config.MODELS_DIR / "benchmark_llm.json"
    sortie.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in res:
        print(f"{r['modele']:12s} chargement {r['chargement_s']} s | premier mot {r['premier_mot_moyen_s']} s | réponse {r['total_moyen_s']} s")
