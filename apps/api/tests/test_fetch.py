"""Fetching: the opt-in direct fetcher, which must only ever reach public addresses."""

import httpx
import pytest

from app.config import Settings
from app.services import fetch
from app.services.fetch import BrightDataFetcher, DirectFetcher, FetchError, make_fetcher

PAGE = "<html><body>" + "<p>Oxford shirt £35.99</p>" * 50 + "</body></html>"
NOTHING = {"_env_file": None, "fixtures_dir": None, "brightdata_api_key": None}


def _dns(table: dict[str, list[str]]):
    async def addresses(host: str) -> list[str]:
        return table[host]

    return addresses


def test_nothing_is_fetched_directly_unless_asked():
    assert make_fetcher(Settings(**NOTHING)) is None
    assert isinstance(make_fetcher(Settings(**NOTHING, direct_fetch=True)), DirectFetcher)
    keyed = {**NOTHING, "brightdata_api_key": "key", "brightdata_unlocker_zone": "zone"}
    both = Settings(**keyed, direct_fetch=True)
    assert isinstance(make_fetcher(both), BrightDataFetcher)
    production = Settings(**NOTHING, environment="production", direct_fetch=True)
    assert any("DIRECT_FETCH" in problem for problem in production.production_problems())


async def test_direct_fetch_follows_redirects_between_public_hosts(monkeypatch):
    dns = {"shop.test": ["93.184.215.14"], "www.shop.test": ["2606:4700::1"]}
    monkeypatch.setattr(fetch, "_addresses", _dns(dns))

    def store(request: httpx.Request) -> httpx.Response:
        if request.url.host == "shop.test":
            return httpx.Response(301, headers={"location": "https://www.shop.test/men"})
        return httpx.Response(200, text=PAGE)

    fetcher = DirectFetcher(transport=httpx.MockTransport(store))
    assert await fetcher.fetch("https://shop.test/men") == PAGE


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.5", "100.102.111.88", "169.254.169.254", "::1"]
)
async def test_direct_fetch_never_reaches_a_private_address(monkeypatch, address):
    monkeypatch.setattr(
        fetch, "_addresses", _dns({"shop.test": ["93.184.215.14"], "inside.test": [address]})
    )
    requested = []

    def store(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.host)
        return httpx.Response(302, headers={"location": "http://inside.test/admin"})

    fetcher = DirectFetcher(transport=httpx.MockTransport(store))
    with pytest.raises(FetchError, match="public"):
        await fetcher.fetch("https://shop.test/men")
    assert requested == ["shop.test"]  # the redirect's target was checked, never requested
    with pytest.raises(FetchError, match="public"):
        await fetcher.fetch("http://inside.test/")
