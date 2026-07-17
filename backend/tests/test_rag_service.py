from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.models import Chunk, Collection, Document, DocumentStatus, Source, SourceType
from app.services import rag
from app.services.rag.prompts import REFUSAL_PHRASE
from tests.conftest import create_sqlite_chunks_table


class FakeProvider:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.received: list[dict[str, str]] | None = None

    def complete(self, messages, stream=True, json_schema=None) -> Iterator[str]:
        self.received = messages
        yield from self.tokens


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0]


@pytest.fixture
def corpus(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    create_sqlite_chunks_table(db_session.get_bind())
    col = Collection(name="C")
    db_session.add(col)
    db_session.flush()
    src = Source(type=SourceType.local, path="/x", collection_id=col.id)
    db_session.add(src)
    db_session.flush()
    ids: dict[str, int] = {}
    for key, title, page, txt in [
        ("rs30", "RS-30 manual", 142, "Tighten the cylinder head bolts to 85 Nm."),
        ("boll", "Bollettino RS", 8, "Verifica della coppia di serraggio della testata."),
    ]:
        doc = Document(
            source_id=src.id,
            collection_id=col.id,
            rel_path=f"{key}.pdf",
            title=title,
            content_hash=key.ljust(64, "0"),
            status=DocumentStatus.indexed,
            lang="it",
        )
        db_session.add(doc)
        db_session.flush()
        ch = Chunk(
            document_id=doc.id,
            page_start=page,
            page_end=page,
            text=txt,
            lang="it",
            bboxes={str(page): [[0.1, 0.1, 0.5, 0.2]]},
        )
        db_session.add(ch)
        db_session.flush()
        ids[key] = ch.id
    db_session.commit()
    return ids


def _wire(monkeypatch, dense: list[tuple[int, float]], fts: list[int]) -> None:
    monkeypatch.setattr("app.services.vectorstore.search", lambda *a, **k: list(dense))
    monkeypatch.setattr("app.services.rag.fts_search", lambda *a, **k: list(fts))


def test_retrieve_hydrates_context(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.71), (corpus["rs30"], 0.63)], fts=[corpus["boll"]])
    r = rag.retrieve(db_session, FakeEmbedder(), object(), "coppia di serraggio testata", None)
    assert r.max_dense_score == 0.71
    assert [c.n for c in r.chunks] == [1, 2]
    assert r.chunks[0].chunk_id == corpus["boll"]
    assert r.chunks[0].page == 8
    assert r.chunks[0].bboxes == {"8": [[0.1, 0.1, 0.5, 0.2]]}


def test_answer_stream_refuses_below_threshold(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.30)], fts=[])
    provider = FakeProvider(["should not be called"])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            provider,
            [{"role": "user", "content": "modello RS-55?"}],
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    assert len(events) == 1
    kind, result = events[0]
    assert kind == "final"
    assert result.refusal is True
    assert result.answer_md == REFUSAL_PHRASE
    assert provider.received is None  # LLM never called on refusal


def test_answer_stream_streams_and_cites(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.72), (corpus["rs30"], 0.64)], fts=[corpus["boll"]])
    provider = FakeProvider(["La coppia è ", "85 Nm ", "[1]."])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            provider,
            [{"role": "user", "content": "coppia di serraggio testata?"}],
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    tokens = [p for k, p in events if k == "token"]
    assert "".join(tokens) == "La coppia è 85 Nm [1]."
    kind, result = events[-1]
    assert kind == "final" and result.refusal is False
    assert result.answer_md == "La coppia è 85 Nm [1]."
    assert [c.n for c in result.citations] == [1]
    assert result.citations[0].chunk_id == corpus["boll"]
    # the LLM saw the grounding system prompt + context
    assert provider.received[0]["role"] == "system"
    assert "[1]" in provider.received[-1]["content"]


def test_answer_stream_refuses_when_no_chunks(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[], fts=[])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            FakeProvider([]),
            [{"role": "user", "content": "domanda"}],
            allowed_collection_ids=None,
            refusal_threshold=0.55,
        )
    )
    assert events[-1][1].refusal is True


def test_answer_stream_empty_allowed_refuses(corpus, db_session, monkeypatch) -> None:
    _wire(monkeypatch, dense=[(corpus["boll"], 0.9)], fts=[corpus["boll"]])
    events = list(
        rag.answer_stream(
            db_session,
            FakeEmbedder(),
            object(),
            FakeProvider(["x"]),
            [{"role": "user", "content": "domanda"}],
            allowed_collection_ids=[],
            refusal_threshold=0.55,
        )
    )
    assert events[-1][1].refusal is True
