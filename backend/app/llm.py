"""Client Ollama (LLM local). Un seul modèle chargé à la fois, mode « thinking » désactivé."""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator

import httpx

from . import config

log = logging.getLogger("rasd.llm")


class LLMUnavailable(RuntimeError):
    """Ollama ne répond pas : l'interface affiche un message clair, le reste continue."""


def _options(extra: dict | None = None) -> dict:
    return {"temperature": config.LLM_TEMPERATURE, "num_ctx": config.LLM_NUM_CTX, **(extra or {})}


def prechauffer(model: str | None = None) -> bool:
    """Charge le modèle en VRAM (keep_alive) pour que la première réponse de la démo soit rapide."""
    try:
        # mêmes options (num_ctx) que les vraies requêtes, sinon Ollama recharge le modèle
        httpx.post(f"{config.OLLAMA_URL}/api/generate", json={"model": model or config.LLM_MODEL, "keep_alive": "30m",
                                                              "options": _options()}, timeout=120)
        return True
    except httpx.HTTPError:
        return False


def ollama_status(timeout: float = 3.0) -> dict:
    try:
        r = httpx.get(f"{config.OLLAMA_URL}/api/tags", timeout=timeout)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {
            "status": "ok",
            "modele_par_defaut": config.LLM_MODEL,
            "modele_disponible": config.LLM_MODEL in models,
            "modeles": models,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "indisponible", "message": f"Ollama ne répond pas ({exc.__class__.__name__}). Lancer « ollama serve »."}


def chat(
    messages: list[dict],
    model: str | None = None,
    fmt: dict | str | None = None,
    timeout: float | None = None,
    options: dict | None = None,
) -> str:
    """Appel non streamé ; `fmt` = schéma JSON pour les sorties structurées."""
    payload: dict = {
        "model": model or config.LLM_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
        "options": _options(options),
        "keep_alive": "30m",
    }
    if fmt is not None:
        payload["format"] = fmt
    t0 = time.perf_counter()
    try:
        r = httpx.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=timeout or config.LLM_TIMEOUT_S)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMUnavailable(f"Ollama indisponible : {exc.__class__.__name__}") from exc
    content = r.json().get("message", {}).get("content", "")
    log.info("LLM %s : %.1f s", payload["model"], time.perf_counter() - t0)
    return content


def chat_stream(messages: list[dict], model: str | None = None, timeout: float | None = None,
                options: dict | None = None) -> Iterator[str]:
    """Streaming token par token (NDJSON d'Ollama)."""
    payload = {
        "model": model or config.LLM_MODEL,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": _options(options),
        "keep_alive": "30m",
    }
    try:
        with httpx.stream(
            "POST", f"{config.OLLAMA_URL}/api/chat", json=payload,
            timeout=httpx.Timeout(timeout or config.LLM_TIMEOUT_S, connect=5.0),
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
                if chunk.get("done"):
                    break
    except httpx.HTTPError as exc:
        raise LLMUnavailable(f"Ollama indisponible : {exc.__class__.__name__}") from exc
