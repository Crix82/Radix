from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from tests.conftest import parse_sse
from tests.conftest import wire_chat as _wire


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
