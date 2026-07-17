from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.security import (
    create_session_token,
    login_rate_limiter,
    verify_password,
)
from app.models import AuditLog, User, UserStatus
from app.models.schemas import LoginRequest, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> User:
    client_ip = request.client.host if request.client else "unknown"
    if not login_rate_limiter.allow(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts"
        )

    user = db.scalar(select(User).where(User.email == body.email))
    if (
        user is None
        or user.password_hash is None
        or user.status != UserStatus.active
        or not verify_password(body.password, user.password_hash)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    settings = get_settings()
    token = create_session_token(user.id, user.role.value)
    response.set_cookie(
        key=settings.session_cookie,
        value=token,
        httponly=True,
        samesite="lax",
        secure=not settings.debug,
        max_age=settings.jwt_expire_minutes * 60,
    )
    db.add(AuditLog(user_id=user.id, action="login", ip=client_ip))
    db.commit()
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(get_settings().session_cookie)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> User:
    return user
