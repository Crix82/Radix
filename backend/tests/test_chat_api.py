import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AuditLog,
    Chunk,
    Collection,
    Document,
    DocumentStatus,
    Source,
    SourceType,
    User,
)
from tests.conftest import create_sqlite_chunks_table


class FakeProvider:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens

    def complete(self, messages, stream=True, json_schema=None) -> Iterator[str]:
        yield from self.tokens


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0, 0.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0]


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if event:
            events.append((event, data))
    return events


@pytest.fixture
def chat_corpus(api_db: Session, monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    create_sqlite_chunks_table(api_db.get_bind())
    # the streaming generator opens its own session — bind it to the same test engine
    monkeypatch.setattr("app.api.chat.SessionLocal", sessionmaker(bind=api_db.get_bind()))
    monkeypatch.setattr("app.api.chat.get_embedder", lambda: FakeEmbedder())
    monkeypatch.setattr("app.api.chat.get_client", lambda: object())

    col = Collection(name="C")
    api_db.add(col)
    api_db.flush()
    src = Source(type=SourceType.local, path="/x", collection_id=col.id)
    api_db.add(src)
    api_db.flush()
    doc = Document(
        source_id=src.id,
        collection_id=col.id,
        rel_path="boll.pdf",
        title="Bollettino RS",
        content_hash="b" * 64,
        status=DocumentStatus.indexed,
        lang="it",
    )
    api_db.add(doc)
    api_db.flush()
    ch = Chunk(
        document_id=doc.id,
        page_start=8,
        page_end=8,
        lang="it",
        bboxes={"8": [[0.1, 0.1, 0.5, 0.2]]},
        text="Verifica della coppia di serraggio della testata.",
    )
    api_db.add(ch)
    api_db.commit()
    return {"chunk": ch.id, "doc": doc.id}


def _wire(monkeypatch, dense, fts, tokens) -> None:
    monkeypatch.setattr("app.services.vectorstore.search", lambda *a, **k: list(dense))
    monkeypatch.setattr("app.services.rag.fts_search", lambda *a, **k: list(fts))
    monkeypatch.setattr("app.api.chat.get_llm_provider", lambda: FakeProvider(tokens))


def test_chat_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 401


def test_chat_streams_tokens_and_final_citation(
    client: TestClient, api_db: Session, admin_user: User, chat_corpus, monkeypatch
) -> None:
    _wire(
        monkeypatch,
        dense=[(chat_corpus["chunk"], 0.72)],
        fts=[chat_corpus["chunk"]],
        tokens=["La coppia è ", "85 Nm ", "[1]."],
    )
    resp = client.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "coppia di serraggio testata?"}]},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(resp.text)
    tokens = [d["text"] for e, d in events if e == "token"]
    assert "".join(tokens) == "La coppia è 85 Nm [1]."
    final = next(d for e, d in events if e == "final")
    assert final["refusal"] is False
    assert final["answer_md"] == "La coppia è 85 Nm [1]."
    assert final["citations"][0]["chunk_id"] == chat_corpus["chunk"]
    assert final["citations"][0]["page"] == 8
    assert final["citations"][0]["bboxes"] == {"8": [[0.1, 0.1, 0.5, 0.2]]}


def test_chat_refuses_below_threshold(
    client: TestClient, api_db: Session, admin_user: User, chat_corpus, monkeypatch
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.20)], fts=[], tokens=["unused"])
    resp = client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": "modello RS-55?"}]}
    )
    final = next(d for e, d in parse_sse(resp.text) if e == "final")
    assert final["refusal"] is True
    assert final["answer_md"] == "Non presente nella documentazione indicizzata."
    assert final["citations"] == []


def test_chat_is_audited(
    client: TestClient, api_db: Session, admin_user: User, chat_corpus, monkeypatch
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["x [1]"])
    client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "domanda audit"}]})
    audit = api_db.scalar(select(AuditLog).where(AuditLog.action == "chat"))
    assert audit is not None and audit.meta["q"] == "domanda audit"


def test_chat_without_user_message_is_422(
    client: TestClient, api_db: Session, admin_user: User, chat_corpus, monkeypatch
) -> None:
    _wire(monkeypatch, dense=[], fts=[], tokens=[])
    resp = client.post(
        "/api/v1/chat", json={"messages": [{"role": "assistant", "content": "ciao"}]}
    )
    assert resp.status_code == 422
