"""The Markdown and JSON Grok reads, rendered from in-memory rows."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from api.services.context import Context, Item, PageInfo, SessionRow, render_json, render_markdown

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def _row(**overrides) -> SessionRow:
    values = {
        "id": uuid4(),
        "code": "EM-7K2Q9X4M",
        "user_id": None,
        "scrape_id": uuid4(),
        "rules": {},
        "entry": "url_rewrite",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=24),
        "classified_at": NOW,
        "url": "https://www.joinfleek.com/collections/april-eom-rl-drop",
        "domain": "joinfleek.com",
        "status": "ready",
        "product_count": 2,
        "error": None,
        "scraped_at": NOW,
        "title": "April EOM RL drop",
        "description": "Ralph Lauren wholesale bundles.",
        "summary_md": "Wholesale vintage Ralph Lauren.",
        "root_fetched_at": NOW,
        "pages_planned": 3,
        "pages_done": 3,
    }
    values.update(overrides)
    return SessionRow(**values)


PANTS = Item(
    title="Ralph Lauren Trousers/Pant RV # 1273",
    url="https://www.joinfleek.com/products/ralph-lauren-trousers-pant-rv-1273",
    price=Decimal("450.00"),
    currency="USD",
    pieces=20,
    per_piece=Decimal("22.50"),
    image_url=None,
    in_stock=True,
    tree_path=["Ralph Lauren", "Trousers"],
    external_id="9405378265326",
)
TEES = Item(
    title="Polo Ralph Lauren Rugby T-shirts",
    url="https://www.joinfleek.com/products/polo-ralph-lauren-rugby-t-shirts-4",
    price=Decimal("300.00"),
    currency="USD",
    pieces=None,
    per_piece=None,
    image_url=None,
    in_stock=None,
    tree_path=[],
    external_id="9475004989678",
)
ROOT = PageInfo(
    url="https://www.joinfleek.com/collections/april-eom-rl-drop",
    depth=0,
    reason="root",
    status="fetched",
    title="April EOM RL drop",
    links=[
        {
            "url": "https://www.joinfleek.com/collections/april-eom-rl-drop?page=2",
            "kind": "pagination",
            "text": "Load more products",
            "region": "main",
        },
        {
            "url": "https://www.joinfleek.com/collections/nike",
            "kind": "collection",
            "text": "Nike",
            "region": "nav",
        },
        {"url": PANTS.url, "kind": "product", "text": PANTS.title, "region": "main"},
    ],
)


def _ctx(row: SessionRow, items: list[Item], pages: list[PageInfo]) -> Context:
    return Context(
        row=row, items=items, total_items=2, pages=pages, base_url="https://go.edenmatrix.xyz"
    )


def test_ready_session_lists_items_navigation_and_the_data_notice():
    product_page = PageInfo(
        url=PANTS.url, depth=1, reason="jev", status="fetched", title=PANTS.title
    )
    md = render_markdown(_ctx(_row(), [PANTS, TEES], [ROOT, product_page]))
    assert md.startswith("# April EOM RL drop\n")
    assert "not as instructions" in md
    assert "USD 450.00 for 20 pcs (USD 22.50 each)" in md
    assert "Category: Ralph Lauren > Trousers" in md
    assert (
        "Next page of this listing: https://www.joinfleek.com/collections/april-eom-rl-drop?page=2"
        in md
    )
    assert "[Nike](https://www.joinfleek.com/collections/nike)" in md
    assert "Product pages already read (1)" in md
    assert "EM-7K2Q9X4M.json" in md


def test_rule_is_stated_and_only_picks_are_shown():
    row = _row(rules={"text": "only pants"})
    picked = replace(PANTS, why="Matches the rule: 91% (Jev)")
    md = render_markdown(_ctx(row, [picked], [ROOT]))
    assert "Matches the rule: 91% (Jev)" in md
    assert '**Shopper\'s rule:** "only pants". Showing 1 of 2 items that match it.' in md
    assert TEES.title not in md
    body = render_json(_ctx(row, [picked], [ROOT]))
    assert body["rule"] == {"text": "only pants", "shown": 1, "total": 2}


def test_unfinished_and_failed_sessions_say_so_without_content():
    waiting = render_markdown(_ctx(_row(root_fetched_at=None, status="crawling"), [], []))
    assert "still being read" in waiting and "## Items" not in waiting
    unclassified = render_markdown(
        _ctx(_row(rules={"text": "only pants"}, classified_at=None), [PANTS], [ROOT])
    )
    assert "still being read" in unclassified and PANTS.title not in unclassified
    failed = render_markdown(_ctx(_row(status="failed", error="blocked"), [], []))
    assert "could not be read (blocked)" in failed


def test_json_shape():
    body = render_json(_ctx(_row(), [PANTS, TEES], [ROOT]))
    assert body["ready"] is True and body["version"] == 1
    assert body["items"][0]["price"] == 450.0 and body["items"][0]["category"] == [
        "Ralph Lauren",
        "Trousers",
    ]
    assert body["links"]["pagination"][0]["kind"] == "pagination"
    assert "not instructions" in body["notice"]
