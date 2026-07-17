"""Collection-level read permissions (SPEC §6), enforced server-side on every query.

M3 wires enforcement into search; the assignment UI arrives in M5. Admins read every
collection; a regular user reads only the collections in `user_collections`.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserCollection, UserRole


def allowed_collection_ids(db: Session, user: User) -> list[int] | None:
    """Return the collection ids the user may read, or None for unrestricted (admin)."""
    if user.role == UserRole.admin:
        return None
    return list(
        db.scalars(select(UserCollection.collection_id).where(UserCollection.user_id == user.id))
    )
