
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth.routes import router as auth_router
from app.api.admin.routes import router as admin_router
from app.api.customer.routes import router as customer_router
from app.api.customer.chat_routes import router as customer_chat_router
from app.core.database import get_db


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(title="TechDemo API")
    app.include_router(auth_router, prefix="/v1/auth", tags=["auth"])
    app.include_router(admin_router, prefix="/v1/admin", tags=["admin"])
    app.include_router(customer_router, prefix="/v1/customer", tags=["customer"])
    app.include_router(customer_chat_router, prefix="/v1/customer", tags=["customer-chat"])

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
