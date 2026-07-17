from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func, select

from app.core.deps import AdminUser, DbSession
from app.core.security import hash_password
from app.models import AuditLog, Collection, User, UserCollection, UserRole, UserStatus
from app.models.schemas import UserCreate, UserDetailOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])

MAX_USERS = 20  # per-installation cap (SPEC §1)


def _collection_ids(db: DbSession, user_id: int) -> list[int]:
    return list(
        db.scalars(select(UserCollection.collection_id).where(UserCollection.user_id == user_id))
    )


def _detail(db: DbSession, user: User) -> UserDetailOut:
    out = UserDetailOut.model_validate(user)
    out.collection_ids = _collection_ids(db, user.id)
    return out


def _set_collections(db: DbSession, user_id: int, collection_ids: list[int]) -> None:
    valid = set(db.scalars(select(Collection.id).where(Collection.id.in_(collection_ids))))
    unknown = set(collection_ids) - valid
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown collections: {sorted(unknown)}"
        )
    db.execute(delete(UserCollection).where(UserCollection.user_id == user_id))
    for cid in set(collection_ids):
        db.add(UserCollection(user_id=user_id, collection_id=cid))


def _audit(db: DbSession, admin_id: int, op: str, user: User) -> None:
    db.add(
        AuditLog(
            user_id=admin_id,
            action="admin_change",
            object_type="user",
            object_id=str(user.id),
            meta={"op": op, "email": user.email, "role": user.role.value},
        )
    )


@router.get("", response_model=list[UserDetailOut])
def list_users(db: DbSession, _admin: AdminUser) -> list[UserDetailOut]:
    users = db.scalars(select(User).order_by(User.id)).all()
    return [_detail(db, u) for u in users]


@router.post("", response_model=UserDetailOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: DbSession, admin: AdminUser) -> UserDetailOut:
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    if (db.scalar(select(func.count()).select_from(User)) or 0) >= MAX_USERS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"User limit reached ({MAX_USERS})"
        )
    # With a password the user is active; without one they stay 'invited' until activated.
    user = User(
        name=body.name.strip() or body.email,
        email=body.email,
        role=body.role,
        status=UserStatus.active if body.password else UserStatus.invited,
        password_hash=hash_password(body.password) if body.password else None,
    )
    db.add(user)
    db.flush()
    _set_collections(db, user.id, body.collection_ids)
    _audit(db, admin.id, "invited", user)
    db.commit()
    return _detail(db, user)


@router.patch("/{user_id}", response_model=UserDetailOut)
def update_user(user_id: int, body: UserUpdate, db: DbSession, admin: AdminUser) -> UserDetailOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    # Guard against self-lockout: an admin cannot demote or disable their own account.
    if user.id == admin.id and (
        (body.role is not None and body.role != UserRole.admin)
        or (body.status is not None and body.status != UserStatus.active)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot demote or disable your own account",
        )

    if body.name is not None:
        user.name = body.name.strip() or user.name
    if body.role is not None:
        user.role = body.role
    if body.status is not None:
        user.status = body.status
    if body.password is not None:
        user.password_hash = hash_password(body.password)
        if user.status == UserStatus.invited:
            user.status = UserStatus.active  # activation
    if body.collection_ids is not None:
        _set_collections(db, user.id, body.collection_ids)

    _audit(db, admin.id, "updated", user)
    db.commit()
    return _detail(db, user)
