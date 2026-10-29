import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import engine

settings = get_settings()
logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s in %s mode", settings.app_name, settings.app_env)
    yield
    engine.dispose()
    logger.info("Database engine disposed")


app = FastAPI(
    title=settings.app_name,
    description="AI-assisted procurement invoice exception resolution API.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"], summary="Application liveness")
def health() -> dict[str, str]:
    """Liveness probe: confirms the API process is responding, without requiring the DB."""
    return {"status": "ok", "service": "procureops-ai"}


@app.get("/health/ready", tags=["health"], summary="Application and database readiness")
def readiness() -> dict[str, Any]:
    """Readiness probe: returns success only when PostgreSQL accepts a query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Readiness check failed: database unavailable (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "unavailable"},
        ) from exc

    return {"status": "ready", "database": "connected"}
