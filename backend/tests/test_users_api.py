from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Collection, User


def _collections(db: Session) -> list[Collection]:
    cols = [Collection(name=n) for n in ("Manuali", "Qualità", "Formulazioni")]
    db.add_all(cols)
    db.commit()
    return cols


def test_users_require_admin(client: TestClient, plain_user: User) -> None:
    assert client.get("/api/v1/users").status_code == 403
    assert client.post("/api/v1/users", json={"name": "X", "email": "x@y.it"}).status_code == 403


def test_users_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/users").status_code == 401


def test_invite_user_without_password_is_invited(
    client: TestClient, api_db: Session, admin_user: User
) -> None:
    cols = _collections(api_db)
    resp = client.post(
        "/api/v1/users",
        json={
            "name": "Marco Ferri",
            "email": "m.ferri@x.it",
            "role": "user",
            "collection_ids": [cols[0].id, cols[1].id],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "invited"
    assert set(body["collection_ids"]) == {cols[0].id, cols[1].id}
    # invited user has no password hash and cannot log in yet
    user = api_db.get(User, body["id"])
    assert user.password_hash is None
    audit = api_db.scalar(
        select(AuditLog).where(AuditLog.action == "admin_change", AuditLog.object_type == "user")
    )
    assert audit is not None


def test_invite_with_password_is_active(
    client: TestClient, api_db: Session, admin_user: User
) -> None:
    resp = client.post(
        "/api/v1/users",
        json={"name": "Giulia", "email": "g@x.it", "role": "user", "password": "secret123"},
    )
    assert resp.json()["status"] == "active"


def test_duplicate_email_is_409(client: TestClient, api_db: Session, admin_user: User) -> None:
    client.post("/api/v1/users", json={"name": "A", "email": "dup@x.it"})
    resp = client.post("/api/v1/users", json={"name": "B", "email": "dup@x.it"})
    assert resp.status_code == 409


def test_invite_unknown_collection_is_404(
    client: TestClient, api_db: Session, admin_user: User
) -> None:
    resp = client.post(
        "/api/v1/users", json={"name": "A", "email": "a@x.it", "collection_ids": [999]}
    )
    assert resp.status_code == 404


def test_activate_and_reassign_collections(
    client: TestClient, api_db: Session, admin_user: User
) -> None:
    cols = _collections(api_db)
    uid = client.post(
        "/api/v1/users",
        json={"name": "A", "email": "a@x.it", "collection_ids": [cols[0].id]},
    ).json()["id"]

    resp = client.patch(
        f"/api/v1/users/{uid}",
        json={"password": "pw12345", "collection_ids": [cols[1].id, cols[2].id]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "active"  # activated by setting a password
    assert set(body["collection_ids"]) == {cols[1].id, cols[2].id}


def test_admin_cannot_demote_or_disable_self(
    client: TestClient, api_db: Session, admin_user: User
) -> None:
    assert client.patch(f"/api/v1/users/{admin_user.id}", json={"role": "user"}).status_code == 409
    assert (
        client.patch(f"/api/v1/users/{admin_user.id}", json={"status": "disabled"}).status_code
        == 409
    )


def test_disable_other_user(client: TestClient, api_db: Session, admin_user: User) -> None:
    uid = client.post(
        "/api/v1/users", json={"name": "A", "email": "a@x.it", "password": "pw12345"}
    ).json()["id"]
    resp = client.patch(f"/api/v1/users/{uid}", json={"status": "disabled"})
    assert resp.json()["status"] == "disabled"


def test_list_users_includes_collections(
    client: TestClient, api_db: Session, admin_user: User
) -> None:
    cols = _collections(api_db)
    client.post(
        "/api/v1/users",
        json={"name": "A", "email": "a@x.it", "collection_ids": [cols[0].id]},
    )
    body = client.get("/api/v1/users").json()
    invited = next(u for u in body if u["email"] == "a@x.it")
    assert invited["collection_ids"] == [cols[0].id]
