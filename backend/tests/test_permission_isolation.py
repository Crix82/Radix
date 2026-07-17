"""M5 DoD: a `user` cannot see/find documents of unassigned collections, and all five
audit events are recorded (login, search, chat, open_document, admin_change)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import hash_password
from app.main import app
from app.models import (
    AuditLog,
    Chunk,
    Collection,
    Document,
    DocumentStatus,
    Source,
    SourceType,
    User,
    UserCollection,
    UserRole,
    UserStatus,
)
from tests.conftest import create_sqlite_chunks_table


def _doc(db: Session, source: Source, collection_id: int, name: str) -> Document:
    doc = Document(
        source_id=source.id,
        collection_id=collection_id,
        rel_path=f"{name}.pdf",
        title=name,
        content_hash=name.ljust(64, "0")[:64],
        status=DocumentStatus.indexed,
        lang="it",
    )
    db.add(doc)
    db.flush()
    return doc


@pytest.fixture
def two_collections(api_db: Session):
    col_a, col_b = Collection(name="Manuali"), Collection(name="Riservata")
    api_db.add_all([col_a, col_b])
    api_db.flush()
    src = Source(type=SourceType.local, path="/x", collection_id=col_a.id)
    api_db.add(src)
    api_db.flush()
    doc_a = _doc(api_db, src, col_a.id, "manuale_pubblico")
    doc_b = _doc(api_db, src, col_b.id, "documento_riservato")
    api_db.commit()
    return {"a": col_a.id, "b": col_b.id, "doc_a": doc_a.id, "doc_b": doc_b.id}


def _become_user(db: Session, role: UserRole, collection_ids: list[int]) -> User:
    user = User(name="U", email="u@x.it", password_hash="x", role=role, status=UserStatus.active)
    db.add(user)
    db.flush()
    for cid in collection_ids:
        db.add(UserCollection(user_id=user.id, collection_id=cid))
    db.commit()
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def test_user_cannot_get_document_of_unassigned_collection(
    client: TestClient, api_db: Session, two_collections
) -> None:
    _become_user(api_db, UserRole.user, [two_collections["a"]])
    # assigned collection: visible
    assert client.get(f"/api/v1/documents/{two_collections['doc_a']}").status_code == 200
    # unassigned collection: 404 (existence hidden)
    assert client.get(f"/api/v1/documents/{two_collections['doc_b']}").status_code == 404
    assert (
        client.get(f"/api/v1/documents/{two_collections['doc_b']}/pages/1.png").status_code == 404
    )


def test_admin_sees_all_documents(client: TestClient, api_db: Session, two_collections) -> None:
    _become_user(api_db, UserRole.admin, [])
    assert client.get(f"/api/v1/documents/{two_collections['doc_b']}").status_code == 200


def test_user_search_excludes_unassigned_collections(
    client: TestClient, api_db: Session, two_collections, monkeypatch
) -> None:
    create_sqlite_chunks_table(api_db.get_bind())
    # both docs have a chunk; the faked retrievers return both
    for key in ("doc_a", "doc_b"):
        api_db.add(
            Chunk(
                document_id=two_collections[key],
                page_start=1,
                page_end=1,
                text="coppia di serraggio testata",
                lang="it",
            )
        )
    api_db.commit()
    chunk_ids = list(api_db.scalars(select(Chunk.id)))
    monkeypatch.setattr("app.services.search.dense_search", lambda *a, **k: chunk_ids)
    monkeypatch.setattr("app.services.search.fts_search", lambda *a, **k: chunk_ids)
    monkeypatch.setattr("app.api.search.get_embedder", lambda: object())
    monkeypatch.setattr("app.api.search.get_client", lambda: object())

    _become_user(api_db, UserRole.user, [two_collections["a"]])
    results = client.get("/api/v1/search?q=coppia di serraggio testata").json()
    doc_ids = {r["document"]["id"] for r in results}
    assert two_collections["doc_a"] in doc_ids
    assert two_collections["doc_b"] not in doc_ids  # unassigned collection filtered out


def test_all_five_audit_events_recorded(
    client: TestClient, api_db: Session, two_collections, monkeypatch
) -> None:
    create_sqlite_chunks_table(api_db.get_bind())
    api_db.add(
        Chunk(
            document_id=two_collections["doc_a"],
            page_start=1,
            page_end=1,
            text="coppia di serraggio testata",
            lang="it",
            bboxes={"1": [[0.1, 0.1, 0.5, 0.2]]},
        )
    )
    api_db.commit()
    chunk_id = api_db.scalar(select(Chunk.id))

    # login: a real active user with a password
    login_user = User(
        name="L",
        email="login@x.it",
        password_hash=hash_password("pw123456"),
        role=UserRole.admin,
        status=UserStatus.active,
    )
    api_db.add(login_user)
    api_db.commit()
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "login@x.it", "password": "pw123456"}
        ).status_code
        == 200
    )

    _become_user(api_db, UserRole.admin, [])

    # admin_change: create a collection
    assert client.post("/api/v1/collections", json={"name": "Nuova"}).status_code == 201

    # open_document
    assert client.get(f"/api/v1/documents/{two_collections['doc_a']}").status_code == 200

    # search
    from app.services.rag.prompts import REFUSAL_PHRASE  # noqa: F401

    monkeypatch.setattr("app.services.search.dense_search", lambda *a, **k: [chunk_id])
    monkeypatch.setattr("app.services.search.fts_search", lambda *a, **k: [chunk_id])
    monkeypatch.setattr("app.api.search.get_embedder", lambda: object())
    monkeypatch.setattr("app.api.search.get_client", lambda: object())
    assert client.get("/api/v1/search?q=coppia").status_code == 200

    # chat
    class FakeEmb:
        def embed_query(self, t):
            return [0.0, 0.0, 0.0]

        def embed_texts(self, ts):
            return [[0.0, 0.0, 0.0] for _ in ts]

    class FakeProvider:
        def complete(self, messages, stream=True, json_schema=None):
            yield "risposta [1]"

    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr("app.api.chat.SessionLocal", sessionmaker(bind=api_db.get_bind()))
    monkeypatch.setattr("app.api.chat.get_embedder", lambda: FakeEmb())
    monkeypatch.setattr("app.api.chat.get_client", lambda: object())
    monkeypatch.setattr("app.api.chat.get_llm_provider", lambda: FakeProvider())
    monkeypatch.setattr("app.services.vectorstore.search", lambda *a, **k: [(chunk_id, 0.9)])
    monkeypatch.setattr("app.services.rag.fts_search", lambda *a, **k: [chunk_id])
    assert (
        client.post(
            "/api/v1/chat", json={"messages": [{"role": "user", "content": "coppia?"}]}
        ).status_code
        == 200
    )

    actions = set(api_db.scalars(select(AuditLog.action)))
    assert {"login", "search", "chat", "open_document", "admin_change"} <= actions
