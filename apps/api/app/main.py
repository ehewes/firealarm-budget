"""The Eden API. `uvicorn app.main:app --reload --port 8000` locally; `python -m app` in Docker."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import acreate_client

from app.auth import Verifier
from app.config import Settings, get_settings
from app.errors import EdenError, eden_error_handler
from app.routers import account, health, mcp, purchases, rulesets, sessions
from app.services.fetch import Fetcher, make_fetcher
from app.services.jev import Jev
from app.services.scraper import mark_interrupted


def create_app(
    settings: Settings | None = None,
    *,
    fetcher: Fetcher | None = None,
    jev_transport: httpx.AsyncBaseTransport | None = None,
    webhook_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = await acreate_client(settings.supabase_url, settings.supabase_service_role_key)
        app.state.settings = settings
        app.state.db = db
        app.state.verifier = Verifier(settings)
        app.state.fetcher = fetcher or make_fetcher(settings)
        app.state.jev = Jev(settings, db, transport=jev_transport)
        app.state.webhook_transport = webhook_transport
        # Jev's note scores per (session, product): the same Grok conversation asks
        # for the shortlist repeatedly, and a score doesn't change within a session.
        app.state.note_scores = {}
        await mark_interrupted(db)
        yield

    app = FastAPI(
        title="Eden API",
        version="1.0.0",
        description=(
            "Store pages turned into agent-ready data. Session codes are read-only capabilities."
        ),
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url=None,
    )
    # The web app calls the API from the browser. In production both share one origin
    # behind Caddy; locally they are :3000 and :8000.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(EdenError, eden_error_handler)
    for module in (health, sessions, rulesets, account, purchases, mcp):
        app.include_router(module.router, prefix="/v1")
    return app


app = create_app()
