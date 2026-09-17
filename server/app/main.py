"""Die Lab-API.

Uvicorn startet die App als Factory (``app.main:create_app --factory``). So
liest niemand beim bloßen Import die Einstellungen, und Tests bauen sich ihre
eigene App mit eigenen Werten.

Im Moment nur ``GET /health``. Ingest, Stream und Statistik kommen in den
Schritten 4.1 und 5.1.

Erreichbar ist die App ausschließlich über Caddy auf
``https://api.tomkaufmann.dev`` (E-021). CORS setzt Caddy, nicht diese App,
sonst stünden zwei ``Access-Control-Allow-Origin``-Header in der Antwort.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings, get_settings
from app.db import create_engine, create_session_factory
from app.logging import configure_logging

logger = logging.getLogger("lab.api")

router = APIRouter()


async def database_reachable(request: Request) -> bool:
    """Prüft die Datenbank mit ``SELECT 1``. Tests ersetzen diese Abhängigkeit."""
    engine: AsyncEngine | None = getattr(request.app.state, "engine", None)
    if engine is None:
        return False
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - jeder Fehler heißt: nicht erreichbar
        logger.warning("datenbank nicht erreichbar", extra={"error": type(exc).__name__})
        return False
    return True


@router.get("/health")
async def health(reachable: bool = Depends(database_reachable)) -> JSONResponse:
    """Antwortet 200, solange die Datenbank erreichbar ist, sonst 503."""
    payload = {
        "status": "ok" if reachable else "degraded",
        "database": "ok" if reachable else "error",
    }
    return JSONResponse(payload, status_code=200 if reachable else 503)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    logger.info("api gestartet", extra={"environment": settings.environment})
    try:
        yield
    finally:
        await engine.dispose()
        logger.info("api beendet")


def create_app() -> FastAPI:
    settings = get_settings()
    in_production = settings.environment == "production"
    app = FastAPI(
        title="Honeypot-Lab API",
        version="0.1.0",
        lifespan=lifespan,
        # Im Betrieb keine öffentliche Schema-Seite. Die API steht im Internet.
        docs_url=None if in_production else "/docs",
        redoc_url=None,
        openapi_url=None if in_production else "/openapi.json",
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Loggt jede Anfrage ohne die Adresse des Clients (E-009)."""
        started = time.perf_counter()
        response = await call_next(request)
        logger.info(
            "anfrage",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response

    app.include_router(router)
    return app
