"""The scrape pipeline, run as a FastAPI BackgroundTask after POST /v1/sessions returns.

pending → crawling (fetch the listing, insert products with an instant keyword
placement so the live tree fills straight away; enrich from product pages) →
classifying (Jev refines each placement) → ready. Any failure of the listing itself
marks the scrape failed with a message the session page can show; a product page that
fails only loses its enrichment.

It runs inside the API process, so a restart kills scrapes in flight.
`mark_interrupted` runs at startup to fail any scrape left mid-way.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from supabase import AsyncClient

from app.config import Settings
from app.services import taxonomy
from app.services.extract import Item, parse_listing, parse_product
from app.services.fetch import BudgetExhausted, Fetcher, FetchError, get_page, prune_page_cache
from app.services.jev import DecideError, Jev, Unavailable

logger = logging.getLogger(__name__)

_INTERRUPTED_AFTER = timedelta(minutes=10)


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _update(db: AsyncClient, scrape_id: str, **fields: Any) -> None:
    await db.table("scrapes").update(fields).eq("id", scrape_id).execute()


def _product_row(scrape_id: str, item: Item) -> dict[str, Any]:
    details = " ".join(
        str(v) for v in (item.attrs.get("description"), item.attrs.get("brand")) if v
    )
    return {
        "scrape_id": scrape_id,
        "source_url": item.source_url,
        "external_id": item.external_id,
        "title": item.title,
        "image_url": item.image_url,
        "price": item.price,
        "compare_at_price": item.compare_at_price,
        "per_piece": item.per_piece,
        "pieces": item.pieces,
        "currency": item.currency,
        "tree_path": taxonomy.keyword_path(item.title, details),
        "attrs": item.attrs,
        "in_stock": item.in_stock,
        "updated_at": _now(),
    }


async def run_scrape(
    db: AsyncClient, settings: Settings, fetcher: Fetcher | None, jev: Jev, scrape_id: str, url: str
) -> None:
    try:
        if fetcher is None:
            raise FetchError("scraping is not configured (no Bright Data key)")
        await _update(db, scrape_id, status="crawling", updated_at=_now())
        await prune_page_cache(db, settings)

        listing = parse_listing(await get_page(db, fetcher, settings, url), url)
        if not listing.items:
            raise FetchError("no products were found on that page")
        rows = [_product_row(scrape_id, item) for item in listing.items]
        await db.table("products").upsert(rows, on_conflict="scrape_id,source_url").execute()
        await _update(
            db, scrape_id, title=listing.title, product_count=len(rows), updated_at=_now()
        )

        await _enrich(db, settings, fetcher, scrape_id, listing.items[: settings.max_product_pages])

        await _update(db, scrape_id, status="classifying", updated_at=_now())
        await _classify(db, jev, scrape_id)
        await _update(db, scrape_id, status="ready", updated_at=_now())
    except BudgetExhausted:
        await _update(db, scrape_id, status="failed", error="budget_exhausted", updated_at=_now())
    except FetchError as exc:
        await _update(db, scrape_id, status="failed", error=str(exc)[:300], updated_at=_now())
    except Exception:
        logger.exception("scrape %s failed", scrape_id)
        await _update(db, scrape_id, status="failed", error="internal error", updated_at=_now())


async def _enrich(
    db: AsyncClient, settings: Settings, fetcher: Fetcher, scrape_id: str, items: list[Item]
) -> None:
    """Product pages add brand, breadcrumbs and a fuller description, and confirm price/stock."""
    limit = asyncio.Semaphore(settings.scrape_concurrency)
    stop = asyncio.Event()

    async def one(item: Item) -> None:
        if stop.is_set():
            return
        async with limit:
            try:
                page = parse_product(
                    await get_page(db, fetcher, settings, item.source_url), item.source_url
                )
            except BudgetExhausted:
                stop.set()
                return
            except FetchError:
                return
        attrs = {**item.attrs}
        if page.brand:
            attrs["brand"] = page.brand
        if page.breadcrumbs:
            attrs["breadcrumbs"] = page.breadcrumbs
        if page.description:
            attrs["description"] = page.description[:1200]
        update: dict[str, Any] = {
            "attrs": attrs,
            "tree_path": taxonomy.keyword_path(
                item.title, " ".join([*page.breadcrumbs, page.description or ""])
            ),
            "updated_at": _now(),
        }
        if item.price is None and page.price is not None:
            update["price"] = page.price
        if page.in_stock is not None:
            update["in_stock"] = page.in_stock
        await (
            db.table("products")
            .update(update)
            .eq("scrape_id", scrape_id)
            .eq("source_url", item.source_url)
            .execute()
        )

    await asyncio.gather(*(one(item) for item in items))


async def _classify(db: AsyncClient, jev: Jev, scrape_id: str) -> None:
    """Jev places each product in the tree; the keyword placement stays when Jev is unsure."""
    if not jev.configured:
        return
    res = (
        await db.table("products")
        .select("id,title,attrs,tree_path")
        .eq("scrape_id", scrape_id)
        .execute()
    )
    stop = asyncio.Event()

    async def one(product: dict[str, Any]) -> None:
        if stop.is_set():
            return
        attrs = product.get("attrs") or {}
        details = " ".join(
            str(v)
            for v in (
                attrs.get("brand"),
                " > ".join(attrs.get("breadcrumbs") or []),
                attrs.get("description"),
            )
            if v
        )
        try:
            placed = await jev.place(product["title"], details)
        except Unavailable:
            stop.set()
            return
        except DecideError as exc:
            logger.info("Jev could not place %s: %s", product["id"], exc)
            return
        if placed:
            path = [*placed, taxonomy.tier_of(f"{product['title']} {details}")]
            if path != product.get("tree_path"):
                await (
                    db.table("products")
                    .update({"tree_path": path})
                    .eq("id", product["id"])
                    .execute()
                )

    await asyncio.gather(*(one(p) for p in res.data))


async def mark_interrupted(db: AsyncClient) -> None:
    """Fail scrapes a previous process left mid-way, so no session page spins forever."""
    cutoff = (datetime.now(UTC) - _INTERRUPTED_AFTER).isoformat()
    await (
        db.table("scrapes")
        .update({"status": "failed", "error": "interrupted by a restart; start a new session"})
        .in_("status", ["pending", "crawling", "classifying"])
        .lt("updated_at", cutoff)
        .execute()
    )
