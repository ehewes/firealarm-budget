"""Sessions: what the web app creates and what Grok Bot reads. See docs/API.md."""

import asyncio
import contextlib
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse
from supabase import AsyncClient

from app.auth import User
from app.config import Settings
from app.deps import client_ip, current_user, get_db, get_settings
from app.errors import EdenError
from app.models import (
    ProductDetail,
    ProductItem,
    ProductsOut,
    RefreshOut,
    Rules,
    SessionCreate,
    SessionCreated,
    SessionOut,
    TreeNode,
    TreeOut,
)
from app.services import grok
from app.services import rules as rule_engine
from app.services.extract import parse_product
from app.services.fetch import BudgetExhausted, FetchError, get_page
from app.services.grok import grok_bot_prompt, grok_prompt, grok_url
from app.services.jev import DecideError, Unavailable
from app.services.scraper import run_scrape
from app.services.sessions import can_purchase, create_session, load_session
from app.services.urls import site_of

router = APIRouter(prefix="/sessions", tags=["sessions"])

MAX_SCORED = 25  # Jev scores at most this many candidates per request, cheapest first


def _session_url(settings: Settings, code: str) -> str:
    return f"{settings.web_origin.rstrip('/')}/s/{code}"


@router.post("", status_code=202, response_model=SessionCreated)
async def create(
    body: SessionCreate,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(current_user),
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SessionCreated:
    """Create a session and start scraping. Returns before the scrape finishes."""
    created = await create_session(db, settings, user, body, client_ip(request))
    state = request.app.state
    if created.new_scrape:
        background.add_task(
            run_scrape, db, settings, state.fetcher, state.jev, created.scrape_id, created.url
        )
    code = created.session["code"]
    return SessionCreated(
        code=code,
        status="crawling",
        session_url=_session_url(settings, code),
        grok_url=grok_url(settings, code=code, store=site_of(created.url), collection=None),
        scrape_id=created.scrape_id,
    )


@router.get("/{code}", response_model=SessionOut)
async def get_session(
    code: str, db: AsyncClient = Depends(get_db), settings: Settings = Depends(get_settings)
) -> SessionOut:
    session, scrape = await load_session(db, code)
    return SessionOut(
        code=session["code"],
        store=scrape["domain"],
        collection=scrape.get("title"),
        status=scrape["status"],
        error=scrape.get("error") if scrape["status"] == "failed" else None,
        product_count=scrape["product_count"],
        snapshot_at=scrape["scraped_at"],
        rules=Rules.model_validate(session["rules"] or {}),
        can_purchase=await can_purchase(db, session),
        session_url=_session_url(settings, session["code"]),
        scrape_id=scrape["id"],
        expires_at=session["expires_at"],
    )


async def _products(db: AsyncClient, scrape_id: str) -> list[dict[str, Any]]:
    res = await db.table("products").select("*").eq("scrape_id", scrape_id).limit(1000).execute()
    return res.data


@router.get("/{code}/tree", response_model=TreeOut)
async def get_tree(code: str, db: AsyncClient = Depends(get_db)) -> TreeOut:
    _, scrape = await load_session(db, code)
    counts: dict[str, Any] = defaultdict(lambda: [0, defaultdict(lambda: [0, defaultdict(int)])])
    for product in await _products(db, scrape["id"]):
        path = (product.get("tree_path") or []) + ["mixed", "mixed bundle", "standard"]
        category, kind, tier = path[0], path[1], path[2]
        counts[category][0] += 1
        counts[category][1][kind][0] += 1
        counts[category][1][kind][1][tier] += 1
    tree = [
        TreeNode(
            name=category,
            count=total,
            children=[
                TreeNode(
                    name=kind,
                    count=kind_total,
                    children=[TreeNode(name=t, count=n) for t, n in sorted(tiers.items())],
                )
                for kind, (kind_total, tiers) in sorted(kinds.items(), key=lambda kv: -kv[1][0])
            ],
        )
        for category, (total, kinds) in sorted(counts.items(), key=lambda kv: -kv[1][0])
    ]
    return TreeOut(tree=tree)


def _sort_key(product: dict[str, Any], score: float | None) -> tuple:
    per_piece = product.get("per_piece")
    price = product.get("price")
    return (
        -(score or 0.0),
        float(per_piece) if per_piece is not None else float("inf"),
        float(price) if price is not None else float("inf"),
    )


@router.get("/{code}/products", response_model=ProductsOut)
async def get_products(
    code: str,
    request: Request,
    q: str | None = Query(None, description="Text that must appear in the title"),
    category: str | None = Query(None, description="Only this category or type"),
    max_per_piece: float | None = Query(
        None, ge=0, description="Tighter per-piece cap for this call"
    ),
    limit: int = Query(10, ge=1, le=25),
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProductsOut:
    """Ranked products with the session's rules applied. Returned items become its picks."""
    session, scrape = await load_session(db, code)
    rules = rule_engine.with_query(
        Rules.model_validate(session["rules"] or {}), max_per_piece=max_per_piece, category=category
    )
    needle = (q or "").strip().lower()
    matching = [
        p
        for p in await _products(db, scrape["id"])
        if rule_engine.passes(p, rules) and (not needle or needle in (p.get("title") or "").lower())
    ]

    scores: dict[str, float] = {}
    jev = request.app.state.jev
    if rules.notes and jev.configured and matching:
        cache: dict[tuple[str, str], float] = request.app.state.note_scores
        candidates = sorted(matching, key=lambda p: _sort_key(p, None))[:MAX_SCORED]

        async def score(p: dict[str, Any]) -> None:
            key = (session["id"], p["id"])
            if key not in cache:
                details = (p.get("attrs") or {}).get("description") or ""
                cache[key] = await jev.fits_notes(rules.notes, p["title"], details)
            scores[p["id"]] = cache[key]

        # On failure, rank by price instead; the hard filters already held.
        with contextlib.suppress(Unavailable, DecideError):
            await asyncio.gather(*(score(p) for p in candidates))

    matching.sort(key=lambda p: _sort_key(p, scores.get(p["id"])))
    chosen = matching[:limit]
    items = [
        ProductItem(
            id=p["id"],
            title=p["title"],
            price=p.get("price"),
            per_piece=p.get("per_piece"),
            pieces=p.get("pieces"),
            currency=p.get("currency"),
            tree_path=p.get("tree_path") or [],
            image_url=p.get("image_url"),
            source_url=p["source_url"],
            why=rule_engine.why(p, rules, scores.get(p["id"])),
        )
        for p in chosen
    ]
    if items:
        await (
            db.table("session_picks")
            .upsert(
                [
                    {
                        "session_id": session["id"],
                        "product_id": str(item.id),
                        "rank": rank,
                        "why": item.why,
                    }
                    for rank, item in enumerate(items, start=1)
                ],
                on_conflict="session_id,product_id",
            )
            .execute()
        )
    return ProductsOut(
        items=items,
        total_matching=len(matching),
        session_url=_session_url(settings, session["code"]),
    )


async def _product(db: AsyncClient, scrape_id: str, product_id: str) -> dict[str, Any]:
    res = (
        await db.table("products")
        .select("*")
        .eq("scrape_id", scrape_id)
        .eq("id", product_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        raise EdenError("product_not_found", "That product isn't part of this session.", 404)
    return res.data[0]


def _detail(p: dict[str, Any], rules: Rules) -> ProductDetail:
    return ProductDetail(
        id=p["id"],
        title=p["title"],
        price=p.get("price"),
        per_piece=p.get("per_piece"),
        pieces=p.get("pieces"),
        currency=p.get("currency"),
        tree_path=p.get("tree_path") or [],
        image_url=p.get("image_url"),
        source_url=p["source_url"],
        why=rule_engine.why(p, rules)
        if rule_engine.passes(p, rules)
        else "Doesn't match your rules",
        external_id=p.get("external_id"),
        compare_at_price=p.get("compare_at_price"),
        in_stock=p.get("in_stock"),
        attrs=p.get("attrs") or {},
        updated_at=p["updated_at"],
    )


@router.get("/{code}/products/{product_id}", response_model=ProductDetail)
async def get_product(
    code: str, product_id: str, db: AsyncClient = Depends(get_db)
) -> ProductDetail:
    session, scrape = await load_session(db, code)
    return _detail(
        await _product(db, scrape["id"], product_id), Rules.model_validate(session["rules"] or {})
    )


@router.post("/{code}/products/{product_id}/refresh", response_model=RefreshOut)
async def refresh_product(
    code: str,
    product_id: str,
    request: Request,
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> RefreshOut:
    """Re-fetch the product page for current price and stock."""
    session, scrape = await load_session(db, code)
    product = await _product(db, scrape["id"], product_id)
    fetcher = request.app.state.fetcher
    if fetcher is None:
        raise EdenError("scrape_failed", "Scraping isn't configured on this server.", 502)
    try:
        page = parse_product(
            await get_page(db, fetcher, settings, product["source_url"], fresh=True),
            product["source_url"],
        )
    except BudgetExhausted as exc:
        raise EdenError("budget_exhausted", "This month's scraping budget is spent.", 503) from exc
    except FetchError as exc:
        raise EdenError("scrape_failed", f"Couldn't re-check that product: {exc}", 502) from exc

    changed: dict[str, list] = {}
    update: dict[str, Any] = {}
    if (
        page.price is not None
        and product.get("price") is not None
        and float(product["price"]) != page.price
    ):
        changed["price"] = [float(product["price"]), page.price]
        update["price"] = page.price
        if product.get("pieces"):
            update["per_piece"] = round(page.price / product["pieces"], 2)
    if page.in_stock is not None and product.get("in_stock") != page.in_stock:
        changed["in_stock"] = [product.get("in_stock"), page.in_stock]
        update["in_stock"] = page.in_stock
    if update:
        res = await db.table("products").update(update).eq("id", product_id).execute()
        product = res.data[0]
    return RefreshOut(
        product=_detail(product, Rules.model_validate(session["rules"] or {})), changed=changed
    )


@router.get("/{code}/grok", include_in_schema=False)
async def grok_link(
    code: str, db: AsyncClient = Depends(get_db), settings: Settings = Depends(get_settings)
) -> JSONResponse:
    """The Continue to Grok link, rebuilt with the collection name once the scrape has one;
    its prompt; and Grok Bot's prompt, which also keeps a session log on the bot's computer.
    Grok Bot's app links can't carry a prompt, so the session page copies it."""
    session, scrape = await load_session(db, code)
    where = {"code": session["code"], "store": scrape["domain"], "collection": scrape.get("title")}
    return JSONResponse(
        {
            "grok_url": grok_url(settings, **where),
            "prompt": grok_prompt(settings, **where),
            "bot_prompt": grok_bot_prompt(settings, **where),
        }
    )


@router.post("/{code}/send-to-grok-bot", include_in_schema=False)
async def send_to_grok_bot(
    code: str,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Post the session to the caller's Grok Bot automation, so the bot starts on it."""
    session, scrape = await load_session(db, code)
    res = await db.table("bot_webhooks").select("*").eq("user_id", user.id).limit(1).execute()
    if not res.data:
        raise EdenError("no_webhook", "Connect a Grok Bot automation on your Eden dashboard first.")
    webhook = res.data[0]
    where = {"code": session["code"], "store": scrape["domain"], "collection": scrape.get("title")}
    payload = {
        "source": "eden-matrix",
        "prompt": grok_bot_prompt(settings, **where),
        "session": {
            **where,
            "session_url": _session_url(settings, session["code"]),
            "products_url": f"{settings.api_base}/sessions/{session['code']}/products",
        },
    }
    await grok.send_to_bot(
        webhook["url"], webhook["secret"], payload, transport=request.app.state.webhook_transport
    )
    await (
        db.table("bot_webhooks")
        .update({"last_sent_at": datetime.now(UTC).isoformat()})
        .eq("user_id", user.id)
        .execute()
    )
    return JSONResponse({"sent": True})
