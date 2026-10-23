from app.services import vectorstore
from app.services.vectorstore import UPSERT_BATCH, ChunkPoint


class _RecordingClient:
    def __init__(self) -> None:
        self.calls: list[list[int]] = []

    def upsert(self, collection_name: str, points: list) -> None:
        self.calls.append([p.id for p in points])


def _point(i: int) -> ChunkPoint:
    return ChunkPoint(
        chunk_id=i,
        vector=[0.0],
        document_id=1,
        collection_id=1,
        page_start=1,
        lang="en",
        doc_type=None,
    )


def test_upsert_splits_large_documents_into_batches() -> None:
    """A whole book in one request exceeds Qdrant's 32 MB body limit."""
    client = _RecordingClient()
    n = UPSERT_BATCH * 2 + 3
    vectorstore.upsert_chunks(client, [_point(i) for i in range(n)])  # type: ignore[arg-type]
    assert [len(c) for c in client.calls] == [UPSERT_BATCH, UPSERT_BATCH, 3]
    assert [i for c in client.calls for i in c] == list(range(n))  # every point, in order


def test_upsert_with_no_points_sends_nothing() -> None:
    client = _RecordingClient()
    vectorstore.upsert_chunks(client, [])  # type: ignore[arg-type]
    assert client.calls == []
