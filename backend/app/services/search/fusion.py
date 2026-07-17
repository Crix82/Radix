"""Reciprocal Rank Fusion (SPEC §8). Pure: combine ranked id lists into one ranking."""

from collections.abc import Sequence

RRF_K = 60


def rrf_fuse(ranked_lists: Sequence[Sequence[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Fuse several ranked id lists into [(id, score)] sorted by descending RRF score.

    Each list contributes 1 / (k + rank) per id (rank starts at 1). Ids appearing in
    multiple lists accumulate their contributions.
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
