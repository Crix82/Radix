from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.deps import AdminUser, DbSession
from app.models import AuditLog, User
from app.models.schemas import AuditEntryOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntryOut])
def list_audit(
    db: DbSession,
    _admin: AdminUser,
    user_id: int | None = None,
    action: str | None = None,
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEntryOut]:
    stmt = select(AuditLog, User.email).join(User, AuditLog.user_id == User.id, isouter=True)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if from_ts is not None:
        stmt = stmt.where(AuditLog.ts >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(AuditLog.ts <= to_ts)
    stmt = stmt.order_by(AuditLog.ts.desc(), AuditLog.id.desc()).limit(limit)

    return [
        AuditEntryOut(
            id=entry.id,
            ts=entry.ts,
            user_id=entry.user_id,
            user_email=email,
            action=entry.action,
            object_type=entry.object_type,
            object_id=entry.object_id,
            ip=str(entry.ip) if entry.ip is not None else None,
        )
        for entry, email in db.execute(stmt).all()
    ]
