"""Dense embeddings service (SPEC §2): BAAI/bge-m3, 1024-dim, cosine.

The model is heavy (torch); it is loaded lazily and cached so unit tests that don't
touch embeddings never import it. Vectors are L2-normalized so Qdrant cosine == dot.
"""

from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

from app.core.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class Embedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def _resolve_device(configured: str) -> str:
    if configured != "auto":
        return configured
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=1)
def _model() -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    model: SentenceTransformer = SentenceTransformer(
        settings.embed_model, device=_resolve_device(settings.embed_device)
    )
    return model


class BGEEmbedder:
    """Concrete Embedder backed by sentence-transformers / bge-m3."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = _model().encode(
            texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]


def get_embedder() -> Embedder:
    return BGEEmbedder()
