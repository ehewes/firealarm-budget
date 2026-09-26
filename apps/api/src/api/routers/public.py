"""The public context: what Grok (or anyone holding the code) fetches.

Deliberately open. The session code is the capability; the context never says
who created the session.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from psycopg_pool import AsyncConnectionPool

from api.deps import get_pool, get_settings
from api.errors import ApiError
from api.services.context import Context, load_context, load_session, render_json, render_markdown
from api.settings import ApiSettings
from eden_core.codes import is_session_code

router = APIRouter(prefix="/public", tags=["public"])


async def _context(code: str, pool: AsyncConnectionPool, settings: ApiSettings) -> Context:
    if not is_session_code(code):
        raise ApiError(404, "not_found", "There is no session with that code.")
    async with pool.connection() as conn:
        row = await load_session(conn, code)
        if row is None:
            raise ApiError(404, "not_found", "There is no session with that code.")
        if row.expired():
            raise ApiError(410, "expired", "This session has expired.")
        return await load_context(conn, row, settings.public_base_url)


def _headers(ctx: Context) -> dict[str, str]:
    # A finished snapshot can be cached briefly; one still filling must not be.
    cache = "public, max-age=300" if ctx.row.complete else "no-store"
    return {"Cache-Control": cache, "X-Robots-Tag": "noindex"}


@router.get("/sessions/{code}.md", response_class=PlainTextResponse)
async def context_markdown(
    code: str,
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: ApiSettings = Depends(get_settings),
) -> PlainTextResponse:
    ctx = await _context(code, pool, settings)
    return PlainTextResponse(
        render_markdown(ctx), media_type="text/markdown; charset=utf-8", headers=_headers(ctx)
    )


@router.get("/sessions/{code}.json")
async def context_json(
    code: str,
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: ApiSettings = Depends(get_settings),
) -> JSONResponse:
    ctx = await _context(code, pool, settings)
    return JSONResponse(render_json(ctx), headers=_headers(ctx))
