
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth.routes import router as auth_router
from app.core.database import get_db


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="TechDemo API")
    app.include_router(auth_router, prefix="/v1/auth", tags=["auth"])

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/health/db")
    def database_health_check(
        db: Annotated[Session, Depends(get_db)],
    ) -> dict[str, str]:
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database unavailable",
            ) from exc

        return {"status": "ok", "database": "connected"}

    return app


app = create_app()
