"""MCP for agents linked to an Eden account (Grok Bot, or any MCP client).

POST /v1/mcp speaks MCP's Streamable HTTP transport with plain JSON responses and no
server-sent stream (GET answers 405, which the spec allows). The caller authenticates
with the agent token from the dashboard (`Authorization: Bearer em_agent_...`), so
every tool acts for that account. Grok Bot takes it in its MCP servers JSON as
`{"eden-matrix": {"url": ".../v1/mcp", "headers": {"Authorization": "Bearer ..."}}}`.

The tools read sessions and ask to buy. Buying only creates a pending intent that the
shopper confirms on Eden, and the agent never sees more of the card than "card_ready"
and the last four digits (CLAUDE.md rules 1 and 2). Titles and prices come from the
database (rule 3), and rules are applied server-side as for /products (rule 7).
"""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import JSONResponse
from supabase import AsyncClient

from app.auth import User
from app.config import Settings
from app.deps import client_ip, current_agent, get_db, get_settings
from app.errors import EdenError
from app.models import SessionCreate
from app.routers.account import past_sessions
from app.routers.sessions import get_products, get_session
from app.services import grok, purchases
from app.services.agents import Agent
from app.services.rules import parse_text
from app.services.scraper import run_scrape
from app.services.sessions import create_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["mcp"], include_in_schema=False)

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
INSTRUCTIONS = (
    "Eden Matrix turns store pages into shortlists that already apply the shopper's rules. "
    "list_my_sessions recalls the sessions they've done before; start_session reads a new store "
    "page; find_products gives a session's shortlist. To buy, call create_purchase_intent and "
    "send the shopper its confirm_url: nothing is charged until they confirm on Eden. Quote only "
    "titles and prices these tools return. If you have a persistent computer, keep a log of the "
    "shopper's sessions in /workspace/eden-matrix/sessions.md."
)

_CODE = {"type": "string", "description": "A session code, e.g. EM-7K2Q9X4M"}
TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_my_sessions",
        "title": "My Eden sessions",
        "description": "The shopper's Eden Matrix sessions, newest first, with store, "
        "collection, status and code. Use it to recall sessions they've done before.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
        },
    },
    {
        "name": "start_session",
        "title": "Read a store page",
        "description": "Read a store page (a category, search or collection) into a new session "
        "for the shopper. Returns its code. Call get_session until status is ready, then "
        "find_products.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "e.g. https://www.zara.com/uk/en/man-shirts-l737.html",
                },
                "rules": {
                    "type": "string",
                    "description": "Optional rules in plain words, e.g. 'under £50, no linen'",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "get_session",
        "title": "Session status",
        "description": "A session's store, collection, status, product count and rules.",
        "inputSchema": {"type": "object", "properties": {"code": _CODE}, "required": ["code"]},
    },
    {
        "name": "find_products",
        "title": "Shortlist",
        "description": "Ranked products from a session with its rules applied, each with a "
        "`why`. Narrow with q (title text), category, or a tighter max_per_piece.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": _CODE,
                "q": {"type": "string"},
                "category": {"type": "string", "description": "e.g. shirts, bottoms"},
                "max_per_piece": {"type": "number", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            "required": ["code"],
        },
    },
    {
        "name": "create_purchase_intent",
        "title": "Ask to buy",
        "description": "Ask to buy products from a session with the shopper's linked card. "
        "Nothing is charged: it returns a confirm_url that the shopper must open on Eden to "
        "confirm. Send them that link, then check get_purchase_status.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": _CODE,
                "product_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": purchases.MAX_ITEMS,
                    "description": "ids from find_products",
                },
            },
            "required": ["code", "product_ids"],
        },
    },
    {
        "name": "get_purchase_status",
        "title": "Purchase status",
        "description": "Where a purchase is: pending (waiting for the shopper), price_changed, "
        "executing (card_ready, checking out), completed (with an order reference), failed or "
        "cancelled.",
        "inputSchema": {
            "type": "object",
            "properties": {"intent_id": {"type": "string"}},
            "required": ["intent_id"],
        },
    },
]


class _Call:
    """One tool call's context: who is asking, and the app's state."""

    def __init__(
        self,
        request: Request,
        agent: Agent,
        db: AsyncClient,
        settings: Settings,
        background: BackgroundTasks,
    ):
        self.request = request
        self.agent = agent
        self.db = db
        self.settings = settings
        self.background = background
        self.user = User(id=agent.user_id, is_anonymous=False)


def _dump(model: Any) -> Any:
    return model.model_dump(mode="json")


async def _list_my_sessions(c: _Call, limit: int = 10) -> dict[str, Any]:
    found = await past_sessions(c.db, c.settings, c.user.id, max(1, min(int(limit), 50)))
    return {"sessions": [_dump(s) for s in found]}


async def _start_session(c: _Call, url: str, rules: str | None = None) -> dict[str, Any]:
    parsed = (await grok.parse_rules(c.settings, rules) or parse_text(rules)) if rules else None
    created = await create_session(
        c.db, c.settings, c.user, SessionCreate(url=url, rules=parsed), client_ip(c.request)
    )
    if created.new_scrape:
        state = c.request.app.state
        c.background.add_task(
            run_scrape, c.db, c.settings, state.fetcher, state.jev, created.scrape_id, created.url
        )
    code = created.session["code"]
    return {
        "code": code,
        "status": "crawling",
        "session_url": f"{c.settings.web_origin.rstrip('/')}/s/{code}",
    }


async def _get_session(c: _Call, code: str) -> dict[str, Any]:
    return _dump(await get_session(code, db=c.db, settings=c.settings))


async def _find_products(
    c: _Call,
    code: str,
    q: str | None = None,
    category: str | None = None,
    max_per_piece: float | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    found = await get_products(
        code,
        c.request,
        q=q,
        category=category,
        max_per_piece=max_per_piece,
        limit=max(1, min(int(limit), 25)),
        db=c.db,
        settings=c.settings,
    )
    return _dump(found)


async def _create_purchase_intent(c: _Call, code: str, product_ids: list[str]) -> dict[str, Any]:
    intent = await purchases.create_intent(c.db, c.settings, c.agent, code, product_ids)
    loaded = await purchases.load_intent(c.db, intent["id"], c.user.id)
    out = _dump(await purchases.view(c.db, c.settings, loaded))
    out["next_step"] = (
        f"Ask the shopper to confirm at {out['confirm_url']}. Nothing is charged until they do."
    )
    return out


async def _get_purchase_status(c: _Call, intent_id: str) -> dict[str, Any]:
    try:
        UUID(str(intent_id))
    except ValueError as exc:
        raise EdenError("intent_not_found", "That isn't a purchase id.", 404) from exc
    intent = await purchases.load_intent(c.db, str(intent_id), c.user.id)
    return _dump(await purchases.view(c.db, c.settings, intent))


HANDLERS: dict[str, Callable[..., Awaitable[dict[str, Any]]]] = {
    "list_my_sessions": _list_my_sessions,
    "start_session": _start_session,
    "get_session": _get_session,
    "find_products": _find_products,
    "create_purchase_intent": _create_purchase_intent,
    "get_purchase_status": _get_purchase_status,
}


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_text(text: str, *, error: bool = False, data: dict | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": error}
    if data is not None:
        out["structuredContent"] = data
    return out


async def _handle(msg: Any, call: _Call) -> dict[str, Any] | None:
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _error(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid request")
    method, msg_id = msg.get("method"), msg.get("id")
    if method is None or "id" not in msg:
        return None  # a notification, or a response to us: nothing to answer
    params = msg.get("params") or {}
    if method == "initialize":
        asked = params.get("protocolVersion")
        return _result(
            msg_id,
            {
                "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "eden-matrix", "title": "Eden Matrix", "version": "1.0.0"},
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _result(msg_id, {})
    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})
    if method != "tools/call":
        return _error(msg_id, -32601, f"Unknown method {method}")

    name, args = params.get("name"), params.get("arguments") or {}
    handler = HANDLERS.get(name)
    if handler is None or not isinstance(args, dict):
        return _error(msg_id, -32602, f"Unknown tool {name}")
    try:
        data = await handler(call, **args)
    except EdenError as exc:
        return _result(msg_id, _tool_text(exc.message, error=True))
    except (TypeError, ValueError) as exc:
        return _result(msg_id, _tool_text(f"Bad arguments for {name}: {exc}", error=True))
    return _result(msg_id, _tool_text(json.dumps(data), data=data))


@router.post("/mcp")
async def mcp(
    request: Request,
    background: BackgroundTasks,
    agent: Agent = Depends(current_agent),
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Response:
    try:
        body = await request.json()
    except ValueError:
        return JSONResponse(_error(None, -32700, "Parse error"), status_code=400)
    call = _Call(request, agent, db, settings, background)
    if isinstance(body, list):  # a batch, from clients on the 2025-03-26 revision
        replies = [reply for msg in body if (reply := await _handle(msg, call)) is not None]
        return JSONResponse(replies) if replies else Response(status_code=202)
    reply = await _handle(body, call)
    return JSONResponse(reply) if reply is not None else Response(status_code=202)


@router.api_route("/mcp", methods=["GET", "DELETE"])
async def mcp_no_stream() -> Response:
    """No server-sent stream and no sessions to end: every answer comes back on the POST."""
    return Response(status_code=405, headers={"Allow": "POST"})
