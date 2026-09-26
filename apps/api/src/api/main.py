"""The FastAPI application. Served by `python -m api` (see __main__.py)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.auth import TokenVerifier
from api.errors import ApiError, handle_api_error
from api.routers import health, me, public, sessions
from api.settings import ApiSettings, get_settings
from eden_core.db import open_pool


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.verifier = (
            TokenVerifier(settings.supabase_url, issuer=settings.supabase_jwt_issuer)
            if settings.supabase_url
            else None
        )
        app.state.pool = await open_pool(settings.supabase_db_url, max_size=settings.db_pool_max)
        try:
            yield
        finally:
            await app.state.pool.close()

    app = FastAPI(
        title="EdenMatrix go API",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url="/api/v1/openapi.json",
        # Interactive docs are for development; production serves the schema only.
        docs_url=None if settings.is_production else "/api/v1/docs",
        redoc_url=None,
    )
    app.add_exception_handler(ApiError, handle_api_error)
    for module in (health, sessions, public, me):
        app.include_router(module.router, prefix="/api/v1")
    return app
