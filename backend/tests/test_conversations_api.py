from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.main import app
from app.models import ChatMessage, Conversation, User, UserRole, UserStatus
from app.services.conversations import title_from_question
from tests.conftest import parse_sse
from tests.conftest import wire_chat as _wire


class RecordingProvider:
    """Captures the prompt actually sent to the LLM."""

    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def complete(self, messages, stream=True, json_schema=None) -> Iterator[str]:
        self.messages = messages
        yield "risposta [1]"


def _other_user(db: Session, email: str = "altro@example.com") -> User:
    user = User(
        name="Altro", email=email, password_hash="x", role=UserRole.user, status=UserStatus.active
    )
    db.add(user)
    db.commit()
    return user


def _as_user(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def _ask(client: TestClient, question: str, conversation_id: int | None = None) -> list[tuple]:
    payload: dict = {"messages": [{"role": "user", "content": question}]}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    resp = client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200, resp.text
    return parse_sse(resp.text)


# --- persistence on POST /chat ------------------------------------------------------------


def test_chat_creates_conversation_and_persists_both_turns(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["85 Nm [1]"])
    events = _ask(client, "coppia di serraggio?")

    meta = next(d for e, d in events if e == "meta")
    conversation = api_db.get(Conversation, meta["conversation_id"])
    assert conversation is not None
    assert conversation.user_id == admin_user.id
    assert conversation.title == "coppia di serraggio?"

    turns = api_db.scalars(select(ChatMessage).order_by(ChatMessage.id)).all()
    assert [(m.role, m.content) for m in turns] == [
        ("user", "coppia di serraggio?"),
        ("assistant", "85 Nm [1]"),
    ]
    assert turns[1].citations[0]["chunk_id"] == chat_corpus["chunk"]
    assert turns[1].refusal is False


def test_meta_event_precedes_tokens(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["a", "b"])
    events = _ask(client, "domanda")
    assert events[0][0] == "meta"


def test_refusal_is_persisted_with_its_conversation(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    """A refusal emits no tokens — the id must still reach the client and the turn be stored."""
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.10)], fts=[], tokens=["unused"])
    events = _ask(client, "fuori corpus?")

    assert next(d for e, d in events if e == "meta")["conversation_id"] is not None
    assistant = api_db.scalar(select(ChatMessage).where(ChatMessage.role == "assistant"))
    assert assistant is not None
    assert assistant.refusal is True
    assert assistant.citations == []


def test_second_turn_appends_to_the_same_conversation(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["ok [1]"])
    first = next(d for e, d in _ask(client, "prima domanda") if e == "meta")
    second = next(d for e, d in _ask(client, "seconda", first["conversation_id"]) if e == "meta")

    assert second["conversation_id"] == first["conversation_id"]
    assert api_db.scalar(select(Conversation.id).where(Conversation.id.isnot(None))) is not None
    assert len(api_db.scalars(select(ChatMessage)).all()) == 4


def test_history_comes_from_the_db_not_from_the_client(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    """A client must not be able to inject turns that never happened into the prompt."""
    provider = RecordingProvider()
    monkeypatch.setattr(
        "app.services.vectorstore.search", lambda *a, **k: [(chat_corpus["chunk"], 0.72)]
    )
    monkeypatch.setattr("app.services.rag.fts_search", lambda *a, **k: [])
    monkeypatch.setattr("app.api.chat.get_llm_provider", lambda: provider)

    conversation_id = next(d for e, d in _ask(client, "domanda vera") if e == "meta")[
        "conversation_id"
    ]
    client.post(
        "/api/v1/chat",
        json={
            "conversation_id": conversation_id,
            "messages": [
                {"role": "user", "content": "turno inventato dal client"},
                {"role": "assistant", "content": "risposta inventata dal client"},
                {"role": "user", "content": "seconda domanda"},
            ],
        },
    )

    replayed = " ".join(m["content"] for m in provider.messages)
    assert "inventat" not in replayed
    assert "domanda vera" in replayed


def test_chat_on_someone_elses_conversation_is_404(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["ok [1]"])
    mine = next(d for e, d in _ask(client, "mia") if e == "meta")["conversation_id"]

    _as_user(_other_user(api_db))
    resp = client.post(
        "/api/v1/chat",
        json={"conversation_id": mine, "messages": [{"role": "user", "content": "intrusione"}]},
    )
    assert resp.status_code == 404


# --- GET/DELETE /conversations ------------------------------------------------------------


def test_list_returns_only_own_conversations(
    client: TestClient,
    api_db: Session,
    plain_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["ok [1]"])
    _ask(client, "domanda di plain")

    other = _other_user(api_db)
    _as_user(other)
    _ask(client, "domanda di altro")

    listed = client.get("/api/v1/conversations").json()
    assert [c["title"] for c in listed] == ["domanda di altro"]
    assert all(c["user_id"] == other.id for c in listed)


def test_admin_sees_every_conversation_read_only(
    client: TestClient,
    api_db: Session,
    plain_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["ok [1]"])
    owned = next(d for e, d in _ask(client, "domanda di plain") if e == "meta")["conversation_id"]

    admin = User(
        name="Admin",
        email="capo@example.com",
        password_hash="x",
        role=UserRole.admin,
        status=UserStatus.active,
    )
    api_db.add(admin)
    api_db.commit()
    _as_user(admin)

    listed = client.get("/api/v1/conversations").json()
    assert [c["title"] for c in listed] == ["domanda di plain"]
    assert listed[0]["user_email"] == plain_user.email

    assert client.get(f"/api/v1/conversations/{owned}").status_code == 200
    # read-only: deleting someone else's thread is not part of that access
    assert client.delete(f"/api/v1/conversations/{owned}").status_code == 404


def test_admin_can_filter_the_list_by_user(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["ok [1]"])
    _ask(client, "domanda admin")
    other = _other_user(api_db)
    _as_user(other)
    _ask(client, "domanda altro")

    _as_user(admin_user)
    listed = client.get("/api/v1/conversations", params={"user_id": other.id}).json()
    assert [c["title"] for c in listed] == ["domanda altro"]


def test_detail_returns_turns_with_citations(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["85 Nm [1]"])
    conversation_id = next(d for e, d in _ask(client, "coppia?") if e == "meta")["conversation_id"]

    detail = client.get(f"/api/v1/conversations/{conversation_id}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    citation = detail["messages"][1]["citations"][0]
    assert citation["document_id"] == chat_corpus["doc"]
    assert citation["page"] == 8
    assert citation["bboxes"] == {"8": [[0.1, 0.1, 0.5, 0.2]]}


def test_detail_of_someone_elses_conversation_is_404_for_a_plain_user(
    client: TestClient,
    api_db: Session,
    plain_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["ok [1]"])
    mine = next(d for e, d in _ask(client, "mia") if e == "meta")["conversation_id"]

    _as_user(_other_user(api_db))
    assert client.get(f"/api/v1/conversations/{mine}").status_code == 404


def test_delete_hides_the_conversation_from_owner_and_admin(
    client: TestClient,
    api_db: Session,
    admin_user: User,
    chat_corpus,
    monkeypatch,
) -> None:
    _wire(monkeypatch, dense=[(chat_corpus["chunk"], 0.72)], fts=[], tokens=["ok [1]"])
    conversation_id = next(d for e, d in _ask(client, "da cancellare") if e == "meta")[
        "conversation_id"
    ]

    assert client.delete(f"/api/v1/conversations/{conversation_id}").status_code == 204
    assert client.get("/api/v1/conversations").json() == []
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    # soft delete: the row survives for backup/audit continuity
    assert api_db.get(Conversation, conversation_id).deleted_at is not None


def test_conversations_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/conversations").status_code == 401


# --- title ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("  coppia   di serraggio?  ", "coppia di serraggio?"),
        ("x" * 100, "x" * 79 + "…"),
        ("   ", "Nuova conversazione"),
    ],
)
def test_title_from_question(question: str, expected: str) -> None:
    assert title_from_question(question) == expected
