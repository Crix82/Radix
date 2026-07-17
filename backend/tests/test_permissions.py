from sqlalchemy.orm import Session

from app.api.search import _effective_collections
from app.core.permissions import allowed_collection_ids
from app.models import Collection, User, UserCollection, UserRole, UserStatus


def _user(db: Session, role: UserRole) -> User:
    u = User(
        name="U", email=f"{role.value}@x", password_hash="x", role=role, status=UserStatus.active
    )
    db.add(u)
    db.commit()
    return u


def test_admin_reads_all_collections(db_session: Session) -> None:
    admin = _user(db_session, UserRole.admin)
    assert allowed_collection_ids(db_session, admin) is None


def test_user_reads_only_assigned_collections(db_session: Session) -> None:
    user = _user(db_session, UserRole.user)
    for name in ("A", "B", "C"):
        db_session.add(Collection(name=name))
    db_session.commit()
    cols = db_session.query(Collection).order_by(Collection.id).all()
    db_session.add(UserCollection(user_id=user.id, collection_id=cols[0].id))
    db_session.add(UserCollection(user_id=user.id, collection_id=cols[2].id))
    db_session.commit()

    allowed = allowed_collection_ids(db_session, user)
    assert set(allowed) == {cols[0].id, cols[2].id}


def test_user_with_no_collections_gets_empty_list(db_session: Session) -> None:
    user = _user(db_session, UserRole.user)
    assert allowed_collection_ids(db_session, user) == []


def test_effective_collections_logic() -> None:
    # admin, no filter -> unrestricted
    assert _effective_collections(None, None) is None
    # admin, filter -> just that collection
    assert _effective_collections(None, 5) == [5]
    # user, no filter -> their collections
    assert _effective_collections([1, 2], None) == [1, 2]
    # user, filter within their collections -> that one
    assert _effective_collections([1, 2], 2) == [2]
    # user, filter outside their collections -> nothing
    assert _effective_collections([1, 2], 9) == []
