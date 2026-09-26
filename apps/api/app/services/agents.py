"""Agent links: the personal tokens that let a shopper's own agent (Grok Bot) act for them.

The shopper makes one on the dashboard and pastes it into the agent's MCP settings.
Eden keeps only the token's SHA-256, so the token itself exists in one place: the agent.
An agent can read sessions and ask to buy; it can never confirm a purchase (rule 2).
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from supabase import AsyncClient

TOKEN_PREFIX = "em_agent_"


@dataclass(frozen=True, slots=True)
class Agent:
    link_id: str
    user_id: str
    name: str


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create(db: AsyncClient, user_id: str, name: str) -> tuple[dict[str, Any], str]:
    """A new link and its token. The token is returned once and never stored."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    res = await (
        db.table("agent_links")
        .insert(
            {
                "user_id": user_id,
                "name": name,
                "token_hash": token_hash(token),
                "token_hint": token[-4:],
            }
        )
        .execute()
    )
    return res.data[0], token


async def resolve(db: AsyncClient, token: str) -> Agent | None:
    if not token.startswith(TOKEN_PREFIX):
        return None
    res = await (
        db.table("agent_links")
        .select("id, user_id, name")
        .eq("token_hash", token_hash(token))
        .is_("revoked_at", "null")
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    row = res.data[0]
    await (
        db.table("agent_links")
        .update({"last_used_at": datetime.now(UTC).isoformat()})
        .eq("id", row["id"])
        .execute()
    )
    return Agent(link_id=row["id"], user_id=row["user_id"], name=row["name"])


async def active(db: AsyncClient, user_id: str) -> list[dict[str, Any]]:
    res = await (
        db.table("agent_links")
        .select("id, name, token_hint, created_at, last_used_at")
        .eq("user_id", user_id)
        .is_("revoked_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return res.data


async def revoke(db: AsyncClient, user_id: str, link_id: str) -> bool:
    res = await (
        db.table("agent_links")
        .update({"revoked_at": datetime.now(UTC).isoformat()})
        .eq("id", link_id)
        .eq("user_id", user_id)
        .is_("revoked_at", "null")
        .execute()
    )
    return bool(res.data)
