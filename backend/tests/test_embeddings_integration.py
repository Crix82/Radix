"""Real bge-m3 embeddings. Skipped unless sentence-transformers is installed (heavy).

Verifies the vector contract (1024-dim, normalized) and the cross-lingual property the
M3 DoD relies on: an Italian query is closer to an English sentence on the same topic
than to an unrelated one.
"""

import math

import pytest

pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")

from app.services.embeddings import get_embedder  # noqa: E402


def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


@pytest.mark.slow
def test_embeddings_are_1024_normalized() -> None:
    vecs = get_embedder().embed_texts(["coppia di serraggio della testata", "safety instructions"])
    assert len(vecs) == 2
    for v in vecs:
        assert len(v) == 1024
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, abs_tol=1e-2)


@pytest.mark.slow
def test_cross_lingual_similarity() -> None:
    emb = get_embedder()
    query_it = emb.embed_query("coppia di serraggio della testata del cilindro")
    en_same = emb.embed_query("tighten the cylinder head bolts to the correct torque")
    en_other = emb.embed_query("the packaging line conveyor belt speed settings")

    assert _cos(query_it, en_same) > _cos(query_it, en_other)
