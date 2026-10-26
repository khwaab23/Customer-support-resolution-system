from collections.abc import Generator
from functools import lru_cache

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def build_database_url(settings: Settings) -> URL:
    """Build a PostgreSQL URL without exposing credentials in source code."""
    return URL.create(
        drivername="postgresql+psycopg",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
    )


@lru_cache
def get_engine() -> Engine:
    """Create the shared SQLAlchemy engine on first database use."""
    return create_engine(
        build_database_url(get_settings()),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_recycle=1800,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Create the session factory used by request-scoped dependencies."""
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    """Yield one database session for a request and close it afterwards."""
    try:
        session = get_session_factory()()
    except (SQLAlchemyError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc

    try:
        yield session
    finally:
        session.close()
