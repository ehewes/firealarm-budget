"""Fixtures for the database tests, which run against local Supabase.

`make api-test-db` starts nothing itself: run `make db` first. It exports
TEST_SUPABASE_URL, TEST_SUPABASE_SERVICE_ROLE_KEY and TEST_DATABASE_URL from
`supabase status`. Without them the `db` tests skip, unless REQUIRE_DB_TESTS=1 (CI),
where a missing database is a failure rather than a quiet skip.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.auth import User
from app.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"

_TABLES = (
    "public.session_picks, public.purchase_intents, public.sessions, public.products, "
    "public.scrapes, public.page_cache, public.usage_counters, public.rulesets, public.card_links"
)


class FakeVerifier:
    """Any bearer token is this (anonymous) user."""

    def __init__(self, user_id: str):
        self.user_id = user_id

    def verify(self, token: str) -> User:
        return User(id=self.user_id, is_anonymous=True)


@pytest.fixture
def local_supabase() -> Iterator[tuple[str, str, psycopg.Connection, str]]:
    url = os.environ.get("TEST_SUPABASE_URL")
    key = os.environ.get("TEST_SUPABASE_SERVICE_ROLE_KEY")
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not (url and key and dsn):
        if os.environ.get("REQUIRE_DB_TESTS") == "1":
            pytest.fail("REQUIRE_DB_TESTS=1 but the TEST_* Supabase variables are not set")
        pytest.skip("local Supabase not configured (make db, then make api-test-db)")
    user_id = str(uuid.uuid4())
    with psycopg.connect(dsn, autocommit=True, row_factory=psycopg.rows.dict_row) as conn:
        conn.execute(f"truncate {_TABLES} cascade")
        conn.execute(
            "insert into auth.users (id, email, aud, role, is_anonymous) "
            "values (%s, %s, 'authenticated', 'authenticated', true)",
            (user_id, f"{user_id}@example.test"),
        )
        yield url, key, conn, user_id
        conn.execute(f"truncate {_TABLES} cascade")
        conn.execute("delete from auth.users where id = %s", (user_id,))


@pytest.fixture
def make_client(local_supabase):
    url, key, conn, user_id = local_supabase
    clients: list[TestClient] = []

    def factory(fetcher=None, **overrides) -> TestClient:
        settings = Settings(
            _env_file=None,
            supabase_url=url,
            supabase_service_role_key=key,
            fixtures_dir=str(FIXTURES),
            web_origin="https://go.example.test",
            allowed_domains="joinfleek.com",
            **overrides,
        )
        app = create_app(settings, fetcher=fetcher)
        client = TestClient(app)
        client.__enter__()
        app.state.verifier = FakeVerifier(user_id)
        clients.append(client)
        return client

    yield factory, conn, user_id
    for client in clients:
        client.__exit__(None, None, None)
