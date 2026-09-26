"""Creating sessions (called by the web gates) and reporting their status (polled by the page)."""

from fastapi import APIRouter, Depends, Request, Response
from psycopg_pool import AsyncConnectionPool

from api.client_ip import client_ip
from api.deps import get_pool, get_settings, optional_user
from api.errors import ApiError
from api.models import RuleState, SessionCreate, SessionCreated, SessionStatus
from api.services import sessions as service
from api.services.context import context_url, count_picks, load_session
from api.services.grok import grok_prompt, grok_url
from api.settings import ApiSettings
from eden_core.codes import is_session_code

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=SessionCreated, status_code=201)
async def create_session(
    body: SessionCreate,
    request: Request,
    response: Response,
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: ApiSettings = Depends(get_settings),
    user_id: str | None = Depends(optional_user),
) -> SessionCreated:
    """Create (or, on a quick refresh, return) a session for a page.

    In production Caddy refuses this route from outside: sessions are created
    only through the web gates, which filter prefetches and link-preview bots.
    """
    created = await service.create_session(
        pool,
        settings,
        url=body.url,
        entry=body.entry,
        referrer_origin=body.referrer_origin,
        ip=client_ip(request),
        user_id=user_id,
    )
    if created.reused:
        response.status_code = 200
    base = settings.public_base_url.rstrip("/")
    return SessionCreated(
        code=created.code,
        status=created.status,
        reused=created.reused,
        session_url=f"{base}/s/{created.code}",
        context_url=context_url(base, created.code),
    )


@router.get("/sessions/{code}", response_model=SessionStatus)
async def session_status(
    code: str,
    response: Response,
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: ApiSettings = Depends(get_settings),
) -> SessionStatus:
    if not is_session_code(code):
        raise ApiError(404, "not_found", "There is no session with that code.")
    async with pool.connection() as conn:
        row = await load_session(conn, code)
        if row is None:
            raise ApiError(404, "not_found", "There is no session with that code.")
        if row.expired():
            raise ApiError(410, "expired", "This session has expired.")
        shown = await count_picks(conn, row.id) if row.rule_text else row.product_count
    response.headers["Cache-Control"] = "no-store"

    ctx_url = context_url(settings.public_base_url, row.code)
    prompt = (
        grok_prompt(domain=row.domain, title=row.title, context_url=ctx_url) if row.ready else None
    )
    return SessionStatus(
        code=row.code,
        status=row.status,
        ready=row.ready,
        target_url=row.url,
        domain=row.domain,
        title=row.title,
        product_count=row.product_count,
        pages_done=row.pages_done,
        pages_planned=row.pages_planned,
        rule=(
            RuleState(text=row.rule_text, shown=shown, classified=row.classified_at is not None)
            if row.rule_text
            else None
        ),
        error=row.error,
        context_url=ctx_url,
        grok_url=grok_url(prompt) if prompt else None,
        grok_prompt=prompt,
        created_at=row.created_at,
        expires_at=row.expires_at,
    )
