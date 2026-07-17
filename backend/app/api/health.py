import httpx
import redis
from fastapi import APIRouter, Response
from qdrant_client import QdrantClient
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import engine
from app.models.schemas import ComponentHealth, HealthOut

router = APIRouter(tags=["health"])


def check_db() -> ComponentHealth:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return ComponentHealth(status="ok")
    except Exception as exc:  # noqa: BLE001 - health check reports any failure
        return ComponentHealth(status="error", detail=str(exc))


def check_redis() -> ComponentHealth:
    try:
        client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
        client.ping()
        return ComponentHealth(status="ok")
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(status="error", detail=str(exc))


def check_qdrant() -> ComponentHealth:
    try:
        client = QdrantClient(url=get_settings().qdrant_url, timeout=2)
        client.get_collections()
        return ComponentHealth(status="ok")
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(status="error", detail=str(exc))


def check_llm() -> ComponentHealth:
    settings = get_settings()
    try:
        resp = httpx.get(f"{settings.llm_base_url.rstrip('/')}/models", timeout=3)
        resp.raise_for_status()
        return ComponentHealth(status="ok")
    except Exception as exc:  # noqa: BLE001
        return ComponentHealth(status="error", detail=str(exc))


CHECKS = {
    "api": lambda: ComponentHealth(status="ok"),
    "db": check_db,
    "redis": check_redis,
    "qdrant": check_qdrant,
    "llm": check_llm,
}


@router.get("/health", response_model=HealthOut)
def health(response: Response) -> HealthOut:
    components = {name: check() for name, check in CHECKS.items()}
    ok = all(c.status == "ok" for c in components.values())
    if not ok:
        response.status_code = 503
    return HealthOut(status="ok" if ok else "degraded", components=components)
