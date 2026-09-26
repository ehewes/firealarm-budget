"""Shared API test fixtures.

Database tests are marked `db` and need TEST_DATABASE_URL (local Supabase, via
`make db`). They skip without it, except in CI, where REQUIRE_DB_TESTS=1 makes a
missing database a failure rather than a quiet skip.
"""

import os
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.settings import ApiSettings


@pytest.fixture
def db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if os.environ.get("REQUIRE_DB_TESTS") == "1":
            pytest.fail("REQUIRE_DB_TESTS=1 but TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL not set (run `make db`, then `make test-db`)")
    return url


@pytest.fixture
def db(db_url: str) -> Iterator[psycopg.Connection]:
    """A clean database: every table the pipeline writes is emptied first."""
    with psycopg.connect(db_url, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        conn.execute(
            "truncate public.session_picks, public.sessions, public.products, "
            "public.scrape_pages, public.scrapes, public.usage_counters, public.rulesets, "
            "public.page_cache cascade"
        )
        conn.execute("select pgmq.purge_queue('scrape')")
        yield conn


def make_settings(db_url: str, **overrides) -> ApiSettings:
    values = {
        "supabase_db_url": db_url,
        "public_base_url": "https://go.example.test",
        "gate_resolve_dns": False,
        "ip_hash_salt": "test-salt",
        **overrides,
    }
    return ApiSettings(_env_file=None, **values)


class FakeVerifier:
    """Stands in for the JWKS verifier: any token is the given user."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    def verify(self, token: str) -> dict:
        return {"sub": self.user_id, "role": "authenticated"}


@pytest.fixture
def client_factory(db, db_url):
    clients: list[TestClient] = []

    def factory(user_id: str | None = None, **overrides) -> TestClient:
        app = create_app(make_settings(db_url, **overrides))
        client = TestClient(app)
        client.__enter__()
        if user_id:
            app.state.verifier = FakeVerifier(user_id)
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)
