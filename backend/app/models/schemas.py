from pydantic import BaseModel, EmailStr

from app.models.tables import UserRole, UserStatus


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: UserRole
    status: UserStatus

    model_config = {"from_attributes": True}


class ComponentHealth(BaseModel):
    status: str  # "ok" | "error"
    detail: str | None = None


class HealthOut(BaseModel):
    status: str
    components: dict[str, ComponentHealth]
