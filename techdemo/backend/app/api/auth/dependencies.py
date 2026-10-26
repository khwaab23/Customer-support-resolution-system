from secrets import compare_digest
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.user import User, UserRole
from app.services.auth_service import AuthContext, AuthService, InvalidSessionError


def _not_authenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )


def _referer_origin(referer: str) -> str | None:
    parsed = urlsplit(referer)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def validate_request_origin(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Require an explicitly trusted browser origin or referer."""
    origin = request.headers.get("origin")
    if origin is not None:
        if origin in settings.allowed_origins:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed",
        )

    referer = request.headers.get("referer")
    if referer is not None and _referer_origin(referer) in settings.allowed_origins:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Request origin is required",
    )


def require_csrf(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Apply origin and double-submit CSRF checks to cookie-authenticated writes."""
    validate_request_origin(request, settings)
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    csrf_header = request.headers.get("x-csrf-token")
    if (
        csrf_cookie is None
        or csrf_header is None
        or not compare_digest(csrf_cookie, csrf_header)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed",
        )


def get_current_auth_context(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthContext:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token is None:
        raise _not_authenticated()

    try:
        return AuthService(db).get_auth_context(raw_token)
    except InvalidSessionError:
        raise _not_authenticated() from None


def get_current_user(
    auth_context: Annotated[AuthContext, Depends(get_current_auth_context)],
) -> User:
    return auth_context.user


def require_customer(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != UserRole.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer role required",
        )
    return user


def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator role required",
        )
    return user
