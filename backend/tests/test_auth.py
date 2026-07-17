from typing import Any

from fastapi.testclient import TestClient

from app.core.db import get_db
from app.main import app


class FakeDb:
    """Just enough of a Session for the login flow when no user matches."""

    def scalar(self, *args: Any, **kwargs: Any) -> None:
        return None

    def add(self, obj: Any) -> None:  # pragma: no cover - not reached on failed login
        pass

    def commit(self) -> None:  # pragma: no cover
        pass


def test_login_unknown_user_is_401(client: TestClient) -> None:
    app.dependency_overrides[get_db] = lambda: FakeDb()

    resp = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "x"})

    assert resp.status_code == 401


def test_me_without_session_is_401(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_clears_cookie(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
