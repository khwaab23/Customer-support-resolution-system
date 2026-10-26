from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.models.user import User, UserRole


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)


class AuthenticatedIdentity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    role: UserRole
    customer_id: str | None

    @classmethod
    def from_user(cls, user: User) -> "AuthenticatedIdentity":
        return cls(
            user_id=user.user_id,
            role=user.role,
            customer_id=user.customer_id,
        )


class LogoutResponse(BaseModel):
    status: str
