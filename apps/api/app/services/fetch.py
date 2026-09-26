"""Getting a page's HTML: page_cache first, then Bright Data's Web Unlocker.

Every real fetch is counted against SCRAPE_MONTHLY_MAX before it is made, so the cap
holds even when many scrapes run at once. Unlocker bills per success and answers
failures for free, but a blocked page often comes back as a 200 challenge page, so
those are detected and treated as failures rather than stored as the store's content.
"""

import asyncio
import ipaddress
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx
from supabase import AsyncClient

from app.config import Settings
from app.services import usage

UNLOCKER_URL = "https://api.brightdata.com/request"
# Big retailers ship multi-megabyte pages (Zara's is ~3 MB of inline data), so the fetch
# cap is generous, but only pages under CACHE_MAX go into page_cache: the free Supabase
# tier holds 500 MB and a handful of these would fill it.
MAX_HTML = 15_000_000
CACHE_MAX = 2_500_000

# A 200 that is a bot check, not the page. Matched on the opening bytes only: a real page
# can mention these words further down.
_CHALLENGE = re.compile(
    r"(just a moment|checking your browser|verify you are (a )?human|attention required"
    r"|access denied|are you a robot|captcha|bm-verify)",
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


class DirectFetcher:
    """Local development without a Bright Data key (DIRECT_FETCH=true): fetch from this machine.

    Never in production, where every fetch goes through Bright Data (the API refuses to
    start with it set). Only public addresses are fetched, and every redirect is checked
    again, so a pasted link can't point it at localhost, the LAN or a metadata endpoint.
    """

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    }

    def __init__(self, *, timeout: float = 15.0, transport: httpx.AsyncBaseTransport | None = None):
        self._timeout = timeout
        self._transport = transport

    async def fetch(self, url: str) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, headers=self._HEADERS, transport=self._transport
            ) as client:
                for _ in range(5):
                    await require_public(url)
                    res = await client.get(url)
                    if not res.is_redirect:
                        break
                    url = urljoin(url, res.headers["location"])
                else:
                    raise FetchError("the store redirected too many times")
        except httpx.HTTPError as exc:
            raise FetchError(f"HTTP request failed: {type(exc).__name__}") from exc
        if res.status_code >= 400:
            raise FetchError(f"Store returned HTTP {res.status_code}")
        return _usable(res.text)


async def _addresses(host: str) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    return [info[4][0] for info in infos]


async def require_public(url: str) -> None:
    """FetchError unless every address the URL's host resolves to is a public one."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("the store sent us to an address we don't fetch")
    try:
        addresses = await _addresses(parts.hostname)
    except OSError as exc:
        raise FetchError("the store's address didn't resolve") from exc
    if not addresses or not all(ipaddress.ip_address(a).is_global for a in addresses):
        raise FetchError("the store's address isn't a public one")


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
    if settings.direct_fetch:
        return DirectFetcher()
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
    if len(html) <= CACHE_MAX:
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
