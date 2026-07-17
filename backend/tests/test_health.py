import pytest
from fastapi.testclient import TestClient

from app.api import health
from app.models.schemas import ComponentHealth

ALL_COMPONENTS = {"api", "db", "redis", "qdrant", "llm"}


def test_health_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    checks = {name: lambda: ComponentHealth(status="ok") for name in ALL_COMPONENTS}
    monkeypatch.setattr(health, "CHECKS", checks)

    resp = client.get("/api/v1/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["components"]) == ALL_COMPONENTS
    assert all(c["status"] == "ok" for c in body["components"].values())


def test_health_degraded_returns_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    checks = {name: lambda: ComponentHealth(status="ok") for name in ALL_COMPONENTS}
    checks["qdrant"] = lambda: ComponentHealth(status="error", detail="connection refused")
    monkeypatch.setattr(health, "CHECKS", checks)

    resp = client.get("/api/v1/health")

    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"
    assert resp.json()["components"]["qdrant"]["status"] == "error"
