from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import AuditLog, Collection, User


def test_collections_require_admin(client: TestClient, plain_user: User) -> None:
    assert client.get("/api/v1/collections").status_code == 403
    assert client.post("/api/v1/collections", json={"name": "X"}).status_code == 403


def test_create_and_list_collection(client: TestClient, api_db: Session, admin_user: User) -> None:
    resp = client.post("/api/v1/collections", json={"name": "Qualità"})
    assert resp.status_code == 201 and resp.json()["name"] == "Qualità"
    body = client.get("/api/v1/collections").json()
    assert [c["name"] for c in body] == ["Qualità"]
    assert body[0]["document_count"] == 0


def test_duplicate_collection_is_409(client: TestClient, api_db: Session, admin_user: User) -> None:
    client.post("/api/v1/collections", json={"name": "Manuali"})
    assert client.post("/api/v1/collections", json={"name": "Manuali"}).status_code == 409


def test_blank_collection_name_is_422(
    client: TestClient, api_db: Session, admin_user: User
) -> None:
    assert client.post("/api/v1/collections", json={"name": "  "}).status_code == 422


def test_audit_requires_admin(client: TestClient, plain_user: User) -> None:
    assert client.get("/api/v1/audit").status_code == 403


def test_audit_lists_and_filters(client: TestClient, api_db: Session, admin_user: User) -> None:
    api_db.add_all(
        [
            AuditLog(user_id=admin_user.id, action="login"),
            AuditLog(user_id=admin_user.id, action="search", meta={"q": "x"}),
            AuditLog(user_id=admin_user.id, action="open_document", object_id="7"),
        ]
    )
    api_db.commit()

    all_entries = client.get("/api/v1/audit").json()
    assert {e["action"] for e in all_entries} == {"login", "search", "open_document"}
    assert all_entries[0]["user_email"] == admin_user.email

    only_search = client.get("/api/v1/audit?action=search").json()
    assert len(only_search) == 1 and only_search[0]["action"] == "search"


def test_collections_seeded_default(client: TestClient, api_db: Session, admin_user: User) -> None:
    api_db.add(Collection(name="Generale"))
    api_db.commit()
    body = client.get("/api/v1/collections").json()
    assert any(c["name"] == "Generale" for c in body)
