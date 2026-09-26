"""Phase 0 : intégrité de l'index RAG et compatibilité des embeddings (section 4)."""
import numpy as np
import pytest

from app import config
from app.rag.index import get_index, normalize_article_number, strip_header


def test_index_ntotal_egal_metadata():
    rag = get_index()
    assert rag.ntotal == len(rag.records) == 4523
    assert rag.dimension == 1024


def test_positions_alignees():
    rag = get_index()
    assert all(r["faiss_position"] == i for i, r in enumerate(rag.records))


def test_sources_lues_depuis_manifeste():
    rag = get_index()
    assert rag.sources["cdpf_2024"] == 380
    assert set(rag.sources) >= {"code_douanes_2016", "decret_oea_2018_612"}


def test_vecteurs_normalises():
    rag = get_index()
    v = np.vstack([rag.vector(i) for i in (0, 1000, 4522)])
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-3)


def test_strip_header_et_utf8():
    rag = get_index()
    rec = rag.get("cdpf_2024__code_des_droits_et_procedures_fiscaux_article_16")
    assert rec is not None
    txt = strip_header(rec["content"])
    assert txt.startswith("Article 16")
    assert "Document :" not in txt
    assert "procédures" in rec["source_title"]  # accents correctement décodés (utf-8)


def test_normalize_article_number():
    assert normalize_article_number("Article 16") == "16"
    assert normalize_article_number("article 17 bis") == "17 bis"
    assert normalize_article_number("Article premier") == "1"
    assert normalize_article_number(None) is None


@pytest.mark.slow
def test_compatibilite_embeddings():
    from app.rag.embedder import SentenceTransformerBackend, compatibility_test

    res = compatibility_test(SentenceTransformerBackend(), get_index())
    assert res["samples"] == config.EMBED_COMPAT_SAMPLES
    assert res["mean_cosine"] >= 0.98, res
