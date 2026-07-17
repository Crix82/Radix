from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import func, select

from app.api import api_router
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import User, UserRole, UserStatus


def seed_admin() -> None:
    """Create the initial admin from env if no user exists yet (idempotent)."""
    settings = get_settings()
    if not settings.admin_email or not settings.admin_password:
        return
    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            return
        db.add(
            User(
                name="Admin",
                email=settings.admin_email,
                password_hash=hash_password(settings.admin_password),
                role=UserRole.admin,
                status=UserStatus.active,
            )
        )
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    seed_admin()
    yield


app = FastAPI(title="Radix", lifespan=lifespan)
app.include_router(api_router)
