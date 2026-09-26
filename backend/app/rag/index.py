"""Chargement de l'index RAG pré-existant (LECTURE SEULE).

Contrôle obligatoire au démarrage : index.ntotal == nombre de lignes de
metadata_unified.jsonl, et la ligne i correspond au vecteur i (faiss_position).
Les sources sont lues dynamiquement depuis le manifeste : une future v3 de
l'index s'utilise sans modification du code.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import faiss
import numpy as np

from .. import config

log = logging.getLogger("rasd.rag")


class IndexIntegrityError(RuntimeError):
    """L'index et ses métadonnées ne correspondent pas."""


_HEADER_PREFIXES = ("Document :", "Section :", "Page PDF :")


def strip_header(content: str) -> str:
    """Retire l'en-tête de 3 lignes (Document / Section / Page PDF) pour l'affichage."""
    lines = content.split("\n")
    i = 0
    while i < len(lines) and i < 3 and lines[i].startswith(_HEADER_PREFIXES):
        i += 1
    if i and i < len(lines) and not lines[i].strip():
        i += 1
    return "\n".join(lines[i:]).strip() if i else content.strip()


_ARTICLE_NUM_RE = re.compile(r"article\s+(premier|\d+)\s*(bis|ter|quater|quinquies)?", re.I)


def normalize_article_number(value: str | None) -> str | None:
    """'Article 16' / 'article 16 bis' / 'Article premier' -> '16', '16 bis', '1'."""
    if not value:
        return None
    m = _ARTICLE_NUM_RE.search(value)
    if not m:
        return None
    num = "1" if m.group(1).lower() == "premier" else m.group(1)
    return f"{num} {m.group(2).lower()}" if m.group(2) else num


@dataclass
class RagIndex:
    index: faiss.Index
    records: list[dict]
    manifest: dict
    embedding_config: dict
    by_id: dict[str, int] = field(default_factory=dict)

    @property
    def ntotal(self) -> int:
        return int(self.index.ntotal)

    @property
    def dimension(self) -> int:
        return int(self.index.d)

    @property
    def sources(self) -> dict[str, int]:
        return dict(self.manifest.get("records_per_source_id", {}))

    def source_titles(self) -> dict[str, str]:
        titles: dict[str, str] = {}
        for r in self.records:
            titles.setdefault(r["source_id"], r.get("source_title", r["source_id"]))
        return titles

    def get(self, record_id: str) -> dict | None:
        pos = self.by_id.get(record_id)
        return self.records[pos] if pos is not None else None

    def vector(self, position: int) -> np.ndarray:
        return self.index.reconstruct(int(position))


def load_index(index_dir: Path | None = None) -> RagIndex:
    index_dir = Path(index_dir or config.RAG_INDEX_DIR)
    faiss_file = index_dir / config.FAISS_INDEX_FILE.name
    meta_file = index_dir / config.METADATA_FILE.name
    manifest_file = index_dir / config.MANIFEST_FILE.name
    emb_file = index_dir / config.EMBEDDING_CONFIG_FILE.name
    for f in (faiss_file, meta_file, manifest_file):
        if not f.exists():
            raise IndexIntegrityError(
                f"Fichier d'index introuvable : {f}. Dézipper l'index RAG dans {index_dir} (voir README)."
            )

    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    emb_cfg = json.loads(emb_file.read_text(encoding="utf-8")) if emb_file.exists() else {}
    if manifest.get("status") != "READY":
        raise IndexIntegrityError(f"Statut du manifeste = {manifest.get('status')!r}, attendu 'READY'.")

    index = faiss.read_index(str(faiss_file))
    records: list[dict] = []
    with meta_file.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if index.ntotal != len(records):
        raise IndexIntegrityError(
            f"Incohérence : index.ntotal = {index.ntotal} mais {len(records)} lignes de métadonnées."
        )
    for i, r in enumerate(records):
        if r.get("faiss_position", i) != i:
            raise IndexIntegrityError(f"Ligne {i} : faiss_position = {r.get('faiss_position')} (attendu {i}).")
    expected = manifest.get("records")
    if expected is not None and expected != index.ntotal:
        raise IndexIntegrityError(f"Manifeste : {expected} records annoncés, index : {index.ntotal}.")

    by_id = {r["id"]: i for i, r in enumerate(records)}
    log.info("Index RAG chargé : %d vecteurs, dimension %d, %d sources", index.ntotal, index.d, len(manifest.get("records_per_source_id", {})))
    return RagIndex(index=index, records=records, manifest=manifest, embedding_config=emb_cfg, by_id=by_id)


@lru_cache(maxsize=1)
def get_index() -> RagIndex:
    return load_index()
