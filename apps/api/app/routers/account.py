"""The signed-in shopper's own things: their card, their connected agents, their sessions.

For the web app's dashboard, so these stay out of the OpenAPI spec that Grok reads.
Cards and agents need a real account; past sessions work for guests too (this device's).
"""

from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from supabase import AsyncClient

from app.auth import User
from app.config import Settings
from app.deps import account_user, current_user, get_db, get_settings
from app.errors import EdenError
from app.models import (
    AgentCreated,
    AgentIn,
    AgentOut,
    CardIn,
    CardOut,
    MeOut,
    PastSession,
    WebhookIn,
    WebhookOut,
)
from app.services import agents, purchases
from app.services.fetch import FetchError, require_public

router = APIRouter(prefix="/me", tags=["account"], include_in_schema=False)


def _card(row: dict | None) -> CardOut | None:
    if row is None:
        return None
    return CardOut(
        provider=row["provider"],
        label=row.get("label"),
        last4=row.get("last4"),
        spend_cap=row.get("spend_cap"),
        currency=row.get("currency") or "GBP",
    )


async def webhook_for(db: AsyncClient, user_id: str) -> dict | None:
    res = await db.table("bot_webhooks").select("*").eq("user_id", user_id).limit(1).execute()
    return res.data[0] if res.data else None


def _webhook(row: dict | None) -> WebhookOut | None:
    if row is None:
        return None
    host = urlsplit(row["url"]).hostname or ""
    return WebhookOut(host=host, last_sent_at=row.get("last_sent_at"))


def mcp_url(settings: Settings) -> str:
    return f"{settings.api_base}/mcp"


@router.get("", response_model=MeOut)
async def me(user: User = Depends(current_user), db: AsyncClient = Depends(get_db)) -> MeOut:
    return MeOut(
        id=user.id,
        email=user.email,
        is_anonymous=user.is_anonymous,
        card=_card(await purchases.card_for(db, user.id)),
        agents=[AgentOut(**row) for row in await agents.active(db, user.id)],
        grok_bot_webhook=_webhook(await webhook_for(db, user.id)),
    )


@router.put("/card", response_model=CardOut)
async def link_card(
    body: CardIn, user: User = Depends(account_user), db: AsyncClient = Depends(get_db)
) -> CardOut:
    """Link the demo agent card, or change its spend cap."""
    card = _card(await purchases.link_demo_card(db, user.id, body.spend_cap, body.currency))
    assert card is not None
    return card


@router.delete("/card", status_code=204)
async def unlink_card(
    user: User = Depends(account_user), db: AsyncClient = Depends(get_db)
) -> Response:
    await db.table("card_links").delete().eq("user_id", user.id).execute()
    return Response(status_code=204)


@router.post("/agents", status_code=201, response_model=AgentCreated)
async def connect_agent(
    body: AgentIn,
    user: User = Depends(account_user),
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AgentCreated:
    """A token for the shopper's agent, and the MCP settings to paste into it."""
    row, token = await agents.create(db, user.id, body.name)
    url = mcp_url(settings)
    return AgentCreated(
        id=row["id"],
        name=row["name"],
        token_hint=row["token_hint"],
        created_at=row["created_at"],
        last_used_at=None,
        token=token,
        mcp_url=url,
        mcp_config={
            "mcpServers": {
                "eden-matrix": {"url": url, "headers": {"Authorization": f"Bearer {token}"}}
            }
        },
        connector_url=f"{url}?key={token}",
    )


@router.delete("/agents/{agent_id}", status_code=204)
async def disconnect_agent(
    agent_id: UUID, user: User = Depends(account_user), db: AsyncClient = Depends(get_db)
) -> Response:
    if not await agents.revoke(db, user.id, str(agent_id)):
        raise EdenError("agent_not_found", "That agent isn't connected to your account.", 404)
    return Response(status_code=204)


@router.put("/grok-bot-webhook", response_model=WebhookOut)
async def set_webhook(
    body: WebhookIn, user: User = Depends(account_user), db: AsyncClient = Depends(get_db)
) -> WebhookOut:
    """Where Send to Grok Bot posts: a Grok Bot automation triggered by a webhook."""
    try:
        await require_public(body.url)
    except FetchError as exc:
        raise EdenError("invalid_webhook", f"That webhook URL can't be used: {exc}.") from exc
    res = await (
        db.table("bot_webhooks")
        .upsert(
            {"user_id": user.id, "url": body.url, "secret": body.key, "last_sent_at": None},
            on_conflict="user_id",
        )
        .execute()
    )
    webhook = _webhook(res.data[0])
    assert webhook is not None
    return webhook


@router.delete("/grok-bot-webhook", status_code=204)
async def remove_webhook(
    user: User = Depends(account_user), db: AsyncClient = Depends(get_db)
) -> Response:
    await db.table("bot_webhooks").delete().eq("user_id", user.id).execute()
    return Response(status_code=204)


async def past_sessions(
    db: AsyncClient, settings: Settings, user_id: str, limit: int
) -> list[PastSession]:
    res = await (
        db.table("sessions")
        .select(
            "code, created_at, expires_at, scrape:scrapes(domain, title, status, product_count)"
        )
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [
        PastSession(
            code=row["code"],
            store=row["scrape"]["domain"],
            collection=row["scrape"].get("title"),
            status=row["scrape"]["status"],
            product_count=row["scrape"]["product_count"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            session_url=f"{settings.web_origin.rstrip('/')}/s/{row['code']}",
        )
        for row in res.data
    ]


@router.get("/sessions", response_model=list[PastSession])
async def my_sessions(
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(current_user),
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[PastSession]:
    return await past_sessions(db, settings, user.id, limit)
