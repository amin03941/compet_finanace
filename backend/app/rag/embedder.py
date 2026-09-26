"""Encodage des questions avec le MÊME modèle que l'index (BAAI/bge-m3, vecteurs normalisés).

Option recommandée : sentence-transformers sur CPU (laisse la VRAM à Ollama).
Option alternative : bge-m3 via Ollama, uniquement si le test de compatibilité passe.
Test de compatibilité : cosinus moyen >= 0,98 entre l'encodage de 20 records et leurs
vecteurs stockés ; sinon bascule sur l'autre option avec un avertissement journalisé.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import httpx
import numpy as np

from .. import config
from .index import RagIndex

log = logging.getLogger("rasd.embedder")


class EmbeddingBackend:
    name = "abstract"

    def encode(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


class SentenceTransformerBackend(EmbeddingBackend):
    name = "sentence_transformers"

    def __init__(self, model_name: str = config.EMBED_MODEL_ST, device: str = config.EMBED_DEVICE):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, device=device)

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = self.model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=4, show_progress_bar=False)
        return np.asarray(vecs, dtype="float32")


class OllamaBackend(EmbeddingBackend):
    name = "ollama"

    def __init__(self, model_name: str = config.EMBED_MODEL_OLLAMA, url: str = config.OLLAMA_URL):
        self.model_name = model_name
        self.url = url.rstrip("/") + "/api/embed"

    def encode(self, texts: list[str]) -> np.ndarray:
        resp = httpx.post(self.url, json={"model": self.model_name, "input": texts}, timeout=120)
        resp.raise_for_status()
        vecs = np.asarray(resp.json()["embeddings"], dtype="float32")
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs / np.clip(norms, 1e-12, None)


_BACKENDS = {"sentence_transformers": SentenceTransformerBackend, "ollama": OllamaBackend}


def compat_sample_positions(ntotal: int, n: int = config.EMBED_COMPAT_SAMPLES) -> list[int]:
    """Positions déterministes, réparties sur tout l'index (toutes les sources)."""
    return sorted({int(round(x)) for x in np.linspace(0, ntotal - 1, n)})


def compatibility_test(backend: EmbeddingBackend, rag: RagIndex, n: int = config.EMBED_COMPAT_SAMPLES) -> dict:
    positions = compat_sample_positions(rag.ntotal, n)
    texts = [rag.records[p]["content"] for p in positions]  # encodage : content tel quel
    t0 = time.perf_counter()
    enc = backend.encode(texts)
    elapsed = time.perf_counter() - t0
    stored = np.vstack([rag.vector(p) for p in positions])
    cos = np.sum(enc * stored, axis=1) / (np.linalg.norm(enc, axis=1) * np.linalg.norm(stored, axis=1))
    return {
        "backend": backend.name,
        "samples": len(positions),
        "mean_cosine": round(float(cos.mean()), 5),
        "min_cosine": round(float(cos.min()), 5),
        "passed": bool(cos.mean() >= config.EMBED_COMPAT_MIN_COSINE),
        "seconds": round(elapsed, 2),
    }


@dataclass
class EmbedderState:
    status: str = "pending"  # pending | loading | ready | degraded | error
    backend: EmbeddingBackend | None = None
    tests: list[dict] = field(default_factory=list)
    warning: str | None = None
    error: str | None = None
    ready_event: threading.Event = field(default_factory=threading.Event)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "backend": self.backend.name if self.backend else None,
            "compatibility_tests": self.tests,
            "warning": self.warning,
            "error": self.error,
        }


_state = EmbedderState()
_lock = threading.Lock()


def state() -> EmbedderState:
    return _state


def initialize(rag: RagIndex, preferred: str = config.EMBED_BACKEND) -> EmbedderState:
    """Charge le backend préféré, lance le test de compatibilité, bascule si besoin."""
    with _lock:
        if _state.status in ("ready", "degraded", "loading"):
            return _state
        _state.status = "loading"
    order = [preferred] + [b for b in _BACKENDS if b != preferred]
    best: tuple[float, EmbeddingBackend] | None = None
    for name in order:
        try:
            backend = _BACKENDS[name]()
            result = compatibility_test(backend, rag)
        except Exception as exc:  # noqa: BLE001 - on journalise et on tente l'autre option
            log.warning("Backend d'embeddings %s indisponible : %s", name, exc)
            _state.tests.append({"backend": name, "passed": False, "error": str(exc)})
            continue
        _state.tests.append(result)
        log.info("Test de compatibilité %s : cosinus moyen %.4f", name, result["mean_cosine"])
        if result["passed"]:
            _state.backend = backend
            _state.status = "ready"
            if name != preferred:
                _state.warning = f"Bascule sur le backend '{name}' : le backend préféré '{preferred}' a échoué au test."
                log.warning(_state.warning)
            break
        if best is None or result["mean_cosine"] > best[0]:
            best = (result["mean_cosine"], backend)
    else:
        if best is not None:
            _state.backend = best[1]
            _state.status = "degraded"
            _state.warning = "Aucun backend n'atteint un cosinus moyen de 0,98 : résultats de recherche dégradés."
            log.warning(_state.warning)
        else:
            _state.status = "error"
            _state.error = "Aucun backend d'embeddings n'a pu être chargé."
            log.error(_state.error)
    _state.ready_event.set()
    return _state


def encode_queries(texts: list[str], timeout: float = 180) -> np.ndarray:
    """Encode plusieurs requêtes en un seul lot (plus rapide sur CPU)."""
    if not _state.ready_event.wait(timeout):
        raise RuntimeError("Le modèle d'embeddings est encore en cours de chargement.")
    if _state.backend is None:
        raise RuntimeError(_state.error or "Modèle d'embeddings indisponible.")
    return _state.backend.encode(texts)


def encode_query(text: str, timeout: float = 180) -> np.ndarray:
    return encode_queries([text], timeout)
