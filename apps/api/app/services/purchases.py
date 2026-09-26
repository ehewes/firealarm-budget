"""Purchases: an agent asks, the shopper confirms on Eden, a card is issued, checkout runs.

CLAUDE.md rules 1, 2 and 4 live here:
- An agent can only create a pending intent. Nothing is bought until the signed-in
  owner confirms it on the Eden confirm page (`confirm`, called only from there).
- Right before a card is issued, every item's price and stock are re-checked on the
  store. Any change means `price_changed` and a fresh confirmation.
- The agent only ever learns "card_ready", the last four digits and the limit.

The card and the checkout are demo stand-ins for now. The demo provider issues no
real card, and checkout records an order reference without contacting the store.
"""

import asyncio
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import BackgroundTasks
from postgrest.exceptions import APIError
from supabase import AsyncClient

from app.auth import User
from app.config import Settings
from app.errors import EdenError
from app.models import CardReady, PurchaseItem, PurchaseOut
from app.services.agents import Agent
from app.services.extract import parse_product
from app.services.fetch import BudgetExhausted, Fetcher, FetchError, get_page
from app.services.rules import money
from app.services.sessions import load_session

DEMO_PROVIDER = "demo"
# A card may pay the confirmed total plus 5% (shipping, rounding), never above the spend cap.
CARD_BUFFER = 1.05
MAX_ITEMS = 10
_OPEN = ("pending", "price_changed")


def _now() -> str:
    return datetime.now(UTC).isoformat()


# ---------------------------------------------------------------- cards


async def card_for(db: AsyncClient, user_id: str) -> dict[str, Any] | None:
    res = await db.table("card_links").select("*").eq("user_id", user_id).limit(1).execute()
    return res.data[0] if res.data else None


async def link_demo_card(
    db: AsyncClient, user_id: str, spend_cap: float, currency: str
) -> dict[str, Any]:
    """Link (or update) the account's demo card. Its last four digits stay the same."""
    existing = await card_for(db, user_id)
    row = {
        "user_id": user_id,
        "provider": DEMO_PROVIDER,
        # The demo provider holds no credentials, so this points at no Vault secret.
        "credential_ref": existing["credential_ref"] if existing else str(uuid.uuid4()),
        "label": "Eden demo card",
        "last4": existing["last4"] if existing else f"{secrets.randbelow(10_000):04d}",
        "spend_cap": spend_cap,
        "currency": currency,
        "updated_at": _now(),
    }
    res = await db.table("card_links").upsert(row, on_conflict="user_id").execute()
    return res.data[0]


# ---------------------------------------------------------------- intents


async def _products(db: AsyncClient, scrape_id: str, ids: list[str]) -> list[dict[str, Any]]:
    res = await db.table("products").select("*").eq("scrape_id", scrape_id).in_("id", ids).execute()
    by_id = {row["id"]: row for row in res.data}
    return [by_id[i] for i in ids if i in by_id]


async def create_intent(
    db: AsyncClient, settings: Settings, agent: Agent, code: str, product_ids: list[str]
) -> dict[str, Any]:
    """A pending purchase of some of a session's products, priced from the database."""
    session, scrape = await load_session(db, code)
    card = await card_for(db, agent.user_id)
    if card is None:
        raise EdenError(
            "no_card", f"Link a card on your Eden dashboard first: {settings.web_origin}/dashboard"
        )
    ids = list(dict.fromkeys(str(i) for i in product_ids))
    if not 1 <= len(ids) <= MAX_ITEMS:
        raise EdenError("invalid_request", f"Choose between 1 and {MAX_ITEMS} products.")
    try:
        products = await _products(db, scrape["id"], ids)
    except APIError as exc:
        raise EdenError("product_not_found", "Those aren't product ids from this session.") from exc
    if len(products) != len(ids):
        raise EdenError("product_not_found", "Some of those products aren't in this session.", 404)
    for p in products:
        if p.get("price") is None:
            raise EdenError("no_price", f"{p['title']} has no price yet, so it can't be bought.")
        if p.get("in_stock") is False:
            raise EdenError("out_of_stock", f"{p['title']} is out of stock.", 409)
    currencies = {p.get("currency") or card["currency"] for p in products}
    if len(currencies) > 1:
        raise EdenError("mixed_currencies", "Those products are priced in different currencies.")
    currency = currencies.pop()
    total = round(sum(float(p["price"]) for p in products), 2)
    cap = card.get("spend_cap")
    if cap is not None and total > float(cap):
        raise EdenError(
            "over_spend_cap",
            f"That comes to {money(total, currency)}, over your "
            f"{money(cap, currency)} limit per purchase.",
        )
    res = await (
        db.table("purchase_intents")
        .insert(
            {
                "user_id": agent.user_id,
                "session_id": session["id"],
                "product_ids": ids,
                "quoted_total": total,
                "merchant": scrape["domain"],
                "currency": currency,
                "agent_link_id": agent.link_id,
            }
        )
        .execute()
    )
    return res.data[0]


async def load_intent(db: AsyncClient, intent_id: str, user_id: str) -> dict[str, Any]:
    """The owner's intent. Anyone else gets the same 404 as a missing one."""
    res = await (
        db.table("purchase_intents")
        .select("*, session:sessions(code, scrape_id)")
        .eq("id", intent_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise EdenError("intent_not_found", "There's no purchase with that id for you.", 404)
    return res.data[0]


async def view(db: AsyncClient, settings: Settings, intent: dict[str, Any]) -> PurchaseOut:
    session = intent.get("session") or {}
    products = (
        await _products(db, session["scrape_id"], intent["product_ids"])
        if session.get("scrape_id")
        else []
    )
    confirmed = intent["status"] in ("executing", "completed") or intent.get("card_last4")
    return PurchaseOut(
        id=intent["id"],
        status=intent["status"],
        store=intent.get("merchant"),
        session_code=session.get("code"),
        items=[
            PurchaseItem(
                id=p["id"],
                title=p["title"],
                price=p.get("price"),
                currency=p.get("currency"),
                image_url=p.get("image_url"),
                source_url=p["source_url"],
                in_stock=p.get("in_stock"),
            )
            for p in products
        ],
        total=float(intent["quoted_total"]),
        currency=intent.get("currency"),
        card=CardReady(last4=intent.get("card_last4"), limit=intent.get("card_limit"))
        if confirmed
        else None,
        confirm_url=f"{settings.web_origin.rstrip('/')}/confirm/{intent['id']}",
        expires_at=intent["expires_at"],
        order_ref=intent.get("order_ref"),
        error=intent.get("error"),
    )


async def _set(db: AsyncClient, intent_id: str, **fields: Any) -> None:
    await (
        db.table("purchase_intents")
        .update({**fields, "updated_at": _now()})
        .eq("id", intent_id)
        .execute()
    )


async def _recheck(
    db: AsyncClient, settings: Settings, fetcher: Fetcher, products: list[dict[str, Any]]
) -> list[str]:
    """Re-read each product page now; update the database; describe what changed."""
    changes = []
    for p in products:
        try:
            page = parse_product(
                await get_page(db, fetcher, settings, p["source_url"], fresh=True), p["source_url"]
            )
        except BudgetExhausted as exc:
            raise EdenError(
                "budget_exhausted", "Prices can't be re-checked now. Nothing was bought.", 503
            ) from exc
        except FetchError as exc:
            raise EdenError(
                "scrape_failed", f"Couldn't re-check {p['title']} ({exc}). Nothing was bought.", 502
            ) from exc
        update: dict[str, Any] = {}
        old = float(p["price"]) if p.get("price") is not None else None
        if page.price is not None and page.price != old:
            changes.append(
                f"{p['title']}: {money(old or 0, p.get('currency'))} → "
                f"{money(page.price, p.get('currency'))}"
            )
            update["price"] = page.price
            pieces = p.get("pieces")
            update["per_piece"] = round(page.price / pieces, 2) if pieces else page.price
        if page.in_stock is False and p.get("in_stock") is not False:
            changes.append(f"{p['title']}: now out of stock")
            update["in_stock"] = False
        if update:
            await db.table("products").update(update).eq("id", p["id"]).execute()
            p.update(update)
    return changes


async def confirm(
    db: AsyncClient,
    settings: Settings,
    fetcher: Fetcher | None,
    user: User,
    intent_id: str,
    background: BackgroundTasks,
) -> PurchaseOut:
    """The owner's yes, from the Eden confirm page only: re-check, issue the card, check out."""
    intent = await load_intent(db, intent_id, user.id)
    if intent["status"] not in _OPEN:
        raise EdenError("intent_closed", f"This purchase is already {intent['status']}.", 409)
    if datetime.fromisoformat(intent["expires_at"]) <= datetime.now(UTC):
        await _set(db, intent_id, status="cancelled", error="expired before it was confirmed")
        raise EdenError("intent_expired", "This request expired. Ask your agent again.", 410)
    card = await card_for(db, user.id)
    if card is None:
        raise EdenError("no_card", "Link a card on your account first.")
    if fetcher is None:
        raise EdenError("scrape_failed", "Prices can't be re-checked now. Nothing was bought.", 503)

    products = await _products(db, intent["session"]["scrape_id"], intent["product_ids"])
    changes = await _recheck(db, settings, fetcher, products)
    currency = intent.get("currency")
    total = round(sum(float(p["price"]) for p in products if p.get("price") is not None), 2)
    if changes:
        await _set(db, intent_id, status="price_changed", quoted_total=total)
        raise EdenError(
            "price_changed",
            "Prices changed since your agent asked: "
            + "; ".join(changes)
            + f". The new total is {money(total, currency)}. Review it and confirm again.",
            409,
        )
    if any(p.get("in_stock") is False for p in products):
        await _set(db, intent_id, status="failed", error="an item is out of stock")
        raise EdenError("out_of_stock", "An item is out of stock, so nothing was bought.", 409)
    cap = float(card["spend_cap"]) if card.get("spend_cap") is not None else None
    if cap is not None and total > cap:
        raise EdenError(
            "over_spend_cap",
            f"{money(total, currency)} is over your {money(cap, currency)} limit per purchase.",
        )

    limit = round(total * CARD_BUFFER, 2)
    await _set(
        db,
        intent_id,
        status="executing",
        quoted_total=total,
        confirmed_at=_now(),
        card_last4=card["last4"],
        card_limit=min(limit, cap) if cap is not None else limit,
    )
    background.add_task(demo_checkout, db, intent_id, settings.demo_checkout_seconds)
    return await view(db, settings, await load_intent(db, intent_id, user.id))


async def demo_checkout(db: AsyncClient, intent_id: str, seconds: float) -> None:
    """Stands in for the store's checkout: nothing is sent to the store or charged."""
    await asyncio.sleep(seconds)
    await _set(
        db,
        intent_id,
        status="completed",
        order_ref="EDEN-DEMO-" + secrets.token_hex(3).upper(),
        completed_at=_now(),
    )


async def cancel(db: AsyncClient, settings: Settings, user: User, intent_id: str) -> PurchaseOut:
    intent = await load_intent(db, intent_id, user.id)
    if intent["status"] not in _OPEN:
        raise EdenError("intent_closed", f"This purchase is already {intent['status']}.", 409)
    await _set(db, intent_id, status="cancelled")
    return await view(db, settings, await load_intent(db, intent_id, user.id))
