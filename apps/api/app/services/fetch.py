"""Getting a page's HTML: page_cache first, then Bright Data's Web Unlocker.

Every real fetch is counted against SCRAPE_MONTHLY_MAX before it is made, so the cap
holds even when many scrapes run at once. Unlocker bills per success and answers
failures for free, but a blocked page often comes back as a 200 challenge page, so
those are detected and treated as failures rather than stored as the store's content.
"""

import asyncio
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from supabase import AsyncClient

from app.config import Settings
from app.services import usage

UNLOCKER_URL = "https://api.brightdata.com/request"
MAX_HTML = 2_000_000  # a page bigger than this is not a store page we can use

# A 200 that is a bot check, not the page. Matched on the opening bytes only: a real page
# can mention these words further down.
_CHALLENGE = re.compile(
    r"(just a moment|checking your browser|verify you are (a )?human|attention required"
    r"|access denied|are you a robot|captcha)",
    re.IGNORECASE,
)


class FetchError(RuntimeError):
    """The page could not be fetched. The message is safe to store on the scrape."""


class BudgetExhausted(RuntimeError):
    """This month's scrape budget is spent."""


class Fetcher(Protocol):
    async def fetch(self, url: str) -> str: ...


class BrightDataFetcher:
    def __init__(self, api_key: str, zone: str, *, timeout: float = 90.0):
        self._api_key = api_key
        self._zone = zone
        self._timeout = timeout

    async def fetch(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                res = await client.post(
                    UNLOCKER_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"zone": self._zone, "url": url, "format": "raw"},
                )
        except httpx.HTTPError as exc:
            raise FetchError(f"Bright Data request failed: {type(exc).__name__}") from exc
        if res.status_code >= 400:
            raise FetchError(f"Bright Data returned HTTP {res.status_code}")
        return _usable(res.text)


class FixtureFetcher:
    """Offline development and tests: serve saved HTML instead of calling Bright Data.

    `/products/...` paths get `product.html`; everything else gets `collection.html`.
    """

    def __init__(self, directory: str):
        self._dir = Path(directory)

    async def fetch(self, url: str) -> str:
        name = "product.html" if "/products/" in urlsplit(url).path else "collection.html"
        path = self._dir / name
        if not path.exists():
            raise FetchError(f"no fixture {name}")
        return _usable(await asyncio.to_thread(path.read_text, encoding="utf-8"))


def make_fetcher(settings: Settings) -> Fetcher | None:
    if settings.fixtures_dir:
        return FixtureFetcher(settings.fixtures_dir)
    if settings.brightdata_api_key and settings.brightdata_unlocker_zone:
        return BrightDataFetcher(settings.brightdata_api_key, settings.brightdata_unlocker_zone)
    return None


def _usable(html: str) -> str:
    if not html.strip():
        raise FetchError("the page came back empty")
    if len(html) > MAX_HTML:
        raise FetchError("the page is too large")
    if _CHALLENGE.search(html[:2000]) and len(html) < 20_000:
        raise FetchError("the store showed a bot check instead of the page")
    return html


async def get_page(
    db: AsyncClient, fetcher: Fetcher, settings: Settings, url: str, *, fresh: bool = False
) -> str:
    """The page's HTML, from page_cache when recent enough, otherwise fetched and cached."""
    if not fresh:
        since = (datetime.now(UTC) - timedelta(minutes=settings.page_cache_minutes)).isoformat()
        cached = (
            await db.table("page_cache")
            .select("html")
            .eq("url", url)
            .gte("fetched_at", since)
            .limit(1)
            .execute()
        )
        if cached.data:
            return cached.data[0]["html"]

    if await usage.scrapes_left(db, settings.scrape_monthly_max) <= 0:
        raise BudgetExhausted("this month's scrape budget is spent")
    await usage.add(db, usage.SCRAPES, 1)
    html = await fetcher.fetch(url)
    await (
        db.table("page_cache")
        .upsert(
            {"url": url, "html": html, "fetched_at": datetime.now(UTC).isoformat()},
            on_conflict="url",
        )
        .execute()
    )
    return html


async def prune_page_cache(db: AsyncClient, settings: Settings) -> None:
    """Drop cached pages older than the reuse window. Store pages are ~200 KB each, and the
    free Supabase tier has 500 MB, so the cache must not grow forever."""
    cutoff = (datetime.now(UTC) - timedelta(minutes=settings.page_cache_minutes)).isoformat()
    await db.table("page_cache").delete().lt("fetched_at", cutoff).execute()
