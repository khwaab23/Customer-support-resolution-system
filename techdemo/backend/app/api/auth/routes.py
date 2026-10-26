from secrets import token_urlsafe
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.auth.dependencies import (
    get_current_auth_context,
    require_csrf,
    validate_request_origin,
)
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.schemas.auth import AuthenticatedIdentity, LoginRequest, LogoutResponse
from app.services.auth_service import AuthContext, AuthService, InvalidCredentialsError

router = APIRouter()


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


@router.get("/csrf", status_code=status.HTTP_204_NO_CONTENT)
def issue_csrf_cookie(
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[None, Depends(validate_request_origin)],
) -> Response:
    """Issue a JavaScript-readable token required for authenticated writes."""
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token_urlsafe(32),
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return response


@router.post("/login", response_model=AuthenticatedIdentity)
def login(
    payload: LoginRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[None, Depends(validate_request_origin)],
) -> AuthenticatedIdentity:
    try:
        service = AuthService(db)
        user = service.authenticate(payload.email, payload.password.get_secret_value())
        _, raw_token = service.create_session(user)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        ) from None

    set_session_cookie(response, raw_token, settings)
    return AuthenticatedIdentity.from_user(user)


@router.get("/me", response_model=AuthenticatedIdentity)
def get_me(
    auth_context: Annotated[AuthContext, Depends(get_current_auth_context)],
) -> AuthenticatedIdentity:
    return AuthenticatedIdentity.from_user(auth_context.user)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    _: Annotated[None, Depends(require_csrf)],
    auth_context: Annotated[AuthContext, Depends(get_current_auth_context)],
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> LogoutResponse:
    AuthService(db).logout(auth_context.user_session)
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return LogoutResponse(status="ok")
