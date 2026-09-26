"""Calibration du seuil d'abstention sur le jeu de 20 questions (backend/tests/rag_questions.json).

Usage : python -m app.rag.calibration   (depuis backend/)
Le seuil retenu sépare au mieux les questions couvertes par la base des questions hors sujet ;
il est écrit dans data/models/retriever_calibration.json et relu au démarrage du retriever.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import config
from . import embedder
from .index import get_index
from .retriever import get_retriever

JEU = Path(__file__).resolve().parents[2] / "tests" / "rag_questions.json"
log = logging.getLogger("rasd.calibration")


def calibrer() -> dict:
    rag = get_index()
    embedder.initialize(rag)
    r = get_retriever()
    qs = json.loads(JEU.read_text(encoding="utf-8"))["questions"]
    scores = []
    for q in qs:
        rech = r.rechercher(q["question"])
        scores.append({"question": q["question"], "dans_la_base": q["dans_la_base"], "meilleur": round(rech.meilleur_score, 4)})
    dedans = sorted(s["meilleur"] for s in scores if s["dans_la_base"])
    dehors = sorted(s["meilleur"] for s in scores if not s["dans_la_base"])
    # seuil placé au tiers inférieur de l'écart entre le plus haut score « hors sujet » et le plus bas score « couvert » :
    # on préfère ne pas s'abstenir à tort (questions en arabe ou en dialecte, aux scores plus bas), le prompt
    # interdisant de toute façon de répondre sans source.
    if dedans[0] > dehors[-1]:
        meilleur_seuil = dehors[-1] + (dedans[0] - dehors[-1]) / 3
    else:
        meilleur_seuil = (dedans[0] + dehors[-1]) / 2
    meilleure_exactitude = (sum(1 for x in dedans if x >= meilleur_seuil) + sum(1 for x in dehors if x < meilleur_seuil)) / len(scores)
    resultat = {"seuil": round(meilleur_seuil, 4), "exactitude": round(meilleure_exactitude, 3),
                "min_dans_la_base": dedans[0], "max_hors_base": dehors[-1], "questions": scores}
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (config.MODELS_DIR / "retriever_calibration.json").write_text(json.dumps(resultat, ensure_ascii=False, indent=1), encoding="utf-8")
    r.seuil = resultat["seuil"]
    return resultat


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    res = calibrer()
    print(json.dumps({k: v for k, v in res.items() if k != "questions"}, ensure_ascii=False, indent=1))
    for q in res["questions"]:
        print(f"{q['meilleur']:.3f}  {'OK ' if q['dans_la_base'] else 'HORS'}  {q['question']}")
