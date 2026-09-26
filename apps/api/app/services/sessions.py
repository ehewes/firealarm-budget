"""Creating and loading sessions.

A session is a read-only capability: its code appears in chat, so it can read one
session's data but never authorise spending (see docs/ARCHITECTURE.md). Scrapes are shared: the
same store page scraped in the last SCRAPE_FRESH_MINUTES is reused by every session
that asks for it, which is what makes rules cheap query-time filters.
"""

import hashlib
import hmac
import ipaddress
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.auth import User
from app.config import Settings
from app.errors import EdenError
from app.models import Rules, SessionCreate
from app.services import usage
from app.services.rules import merge
from app.services.urls import canonical, require_allowed, same_site

CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"  # no 0/O, 1/I/L or U: codes get read aloud


def new_code() -> str:
    return "EM-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def ip_hash(ip: str, salt: str) -> str:
    """A keyed hash, never the address. IPv6 is grouped by /64, the block one household gets."""
    try:
        parsed = ipaddress.ip_address(ip)
        if isinstance(parsed, ipaddress.IPv6Address):
            ip = str(ipaddress.ip_network(f"{parsed}/64", strict=False).network_address)
    except ValueError:
        pass
    return hmac.new(salt.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


@dataclass(slots=True)
class Created:
    session: dict[str, Any]
    scrape_id: str
    url: str
    new_scrape: bool


def _ago(**delta: float) -> str:
    return (datetime.now(UTC) - timedelta(**delta)).isoformat()


async def _count(db: AsyncClient, column: str, value: str) -> int:
    res = await (
        db.table("sessions")
        .select("id", count="exact")
        .eq(column, value)
        .gte("created_at", _ago(hours=1))
        .execute()
    )
    return res.count or 0


async def create_session(
    db: AsyncClient, settings: Settings, user: User, body: SessionCreate, ip: str
) -> Created:
    url = canonical(body.url)
    store = require_allowed(url, settings.domains)

    requester = ip_hash(ip, settings.ip_hash_salt)
    if (
        await _count(db, "user_id", user.id) >= settings.sessions_per_hour_per_user
        or await _count(db, "requester_ip_hash", requester) >= settings.sessions_per_hour_per_ip
    ):
        raise EdenError(
            "rate_limited",
            "That's a lot of sessions in an hour. Please wait a bit and try again.",
            429,
            headers={"Retry-After": "600"},
        )

    rules = Rules()
    if body.ruleset_id:
        res = (
            await db.table("rulesets")
            .select("rules")
            .eq("id", str(body.ruleset_id))
            .eq("user_id", user.id)
            .limit(1)
            .execute()
        )
        if not res.data:
            raise EdenError("ruleset_not_found", "That ruleset doesn't exist.", 404)
        rules = Rules.model_validate(res.data[0]["rules"] or {})
    rules = merge(rules, body.rules)

    fresh = (
        await db.table("scrapes")
        .select("id")
        .eq("url", url)
        .neq("status", "failed")
        .gte("scraped_at", _ago(minutes=settings.scrape_fresh_minutes))
        .order("scraped_at", desc=True)
        .limit(1)
        .execute()
    )
    if fresh.data:
        scrape_id, new_scrape = fresh.data[0]["id"], False
    else:
        if await usage.scrapes_left(db, settings.scrape_monthly_max) <= 0:
            raise EdenError(
                "budget_exhausted",
                "Eden Matrix has used this month's scraping budget. Please try again later.",
                503,
            )
        res = await db.table("scrapes").insert({"url": url, "domain": store}).execute()
        scrape_id, new_scrape = res.data[0]["id"], True

    referrer = body.referrer_origin
    row = {
        "user_id": user.id,
        "scrape_id": scrape_id,
        "rules": rules.model_dump(exclude_none=True),
        "expires_at": (datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours)).isoformat(),
        "entry": body.entry,
        "referrer_origin": referrer,
        # What the browser asserted, not proof: anything but a browser can send any Referer.
        "origin_verified": body.entry == "widget" and bool(referrer) and same_site(referrer, url),
        "requester_ip_hash": requester,
    }
    for _ in range(5):
        try:
            res = await db.table("sessions").insert({**row, "code": new_code()}).execute()
            return Created(session=res.data[0], scrape_id=scrape_id, url=url, new_scrape=new_scrape)
        except APIError as exc:
            if exc.code != "23505":  # unique_violation: a code collision, so try another
                raise
    raise EdenError("internal", "Could not create a session. Please try again.", 500)


async def load_session(db: AsyncClient, code: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The session and its scrape, or 404 session_not_found / session_expired."""
    res = (
        await db.table("sessions")
        .select("*, scrape:scrapes(*)")
        .eq("code", code.upper())
        .limit(1)
        .execute()
    )
    if not res.data:
        raise EdenError("session_not_found", "There's no session with that code.", 404)
    session = res.data[0]
    if datetime.fromisoformat(session["expires_at"]) <= datetime.now(UTC):
        raise EdenError(
            "session_expired", "This session has expired. Start a new one on Eden Matrix.", 404
        )
    return session, session.pop("scrape")


async def can_purchase(db: AsyncClient, session: dict[str, Any]) -> bool:
    """Purchases need a signed-in owner with a linked card (card links are never anonymous)."""
    if not session.get("user_id"):
        return False
    res = (
        await db.table("card_links")
        .select("user_id")
        .eq("user_id", session["user_id"])
        .limit(1)
        .execute()
    )
    return bool(res.data)
