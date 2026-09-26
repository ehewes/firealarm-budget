"""The API against a real Supabase Postgres: sessions, reuse, limits, context, rules."""

import uuid

import pytest

pytestmark = pytest.mark.db

URL = "https://www.joinfleek.com/collections/april-eom-rl-drop"


def _queue(db) -> list[dict]:
    return [r["message"] for r in db.execute("select message from pgmq.q_scrape order by msg_id")]


def _create(client, url=URL, ip="203.0.113.7", **extra):
    headers = {"CF-Connecting-IP": ip, **extra.pop("headers", {})}
    return client.post("/api/v1/sessions", json={"url": url, **extra}, headers=headers)


def test_create_enqueues_one_job_and_a_refresh_reuses_the_session(client_factory, db):
    client = client_factory()
    first = _create(client, URL + "?click_source=COLLECTIONS")
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["code"].startswith("EM-") and body["reused"] is False
    assert (
        body["context_url"] == f"https://go.example.test/api/v1/public/sessions/{body['code']}.md"
    )
    jobs = _queue(db)
    assert len(jobs) == 1 and jobs[0]["kind"] == "page" and jobs[0]["url"] == URL

    again = _create(client)
    assert again.status_code == 200 and again.json()["code"] == body["code"]
    assert len(_queue(db)) == 1

    # Another shopper gets their own session but shares the fresh scrape.
    other = _create(client, ip="198.51.100.2")
    assert other.status_code == 201 and other.json()["code"] != body["code"]
    assert len(_queue(db)) == 1
    scrapes = db.execute("select count(*) as n from public.scrapes").fetchone()["n"]
    assert scrapes == 1
    stored = db.execute("select requester_ip_hash from public.sessions").fetchall()
    assert all("203.0.113" not in r["requester_ip_hash"] for r in stored)


def test_bad_and_self_addresses_are_refused(client_factory):
    client = client_factory()
    assert _create(client, "localhost/x").json()["error"]["code"] == "bad_url"
    assert _create(client, "go.edenmatrix.xyz/x").json()["error"]["code"] == "self"
    limited = client_factory(gate_allowed_sites="joinfleek.com")
    assert _create(limited, "example.org/x").status_code == 403


def test_guest_rate_limit(client_factory):
    client = client_factory(guest_sessions_per_hour=2)
    assert _create(client, "joinfleek.com/a").status_code == 201
    assert _create(client, "joinfleek.com/b").status_code == 201
    third = _create(client, "joinfleek.com/c")
    assert third.status_code == 429 and int(third.headers["Retry-After"]) > 0


def test_scrape_budget_is_enforced_but_sharing_is_free(client_factory, db):
    client = client_factory(scrape_monthly_max=5)
    assert _create(client).status_code == 201
    db.execute(
        "insert into public.usage_counters (period, key, amount) "
        "values (date_trunc('month', now())::date, 'scrapes', 5)"
    )
    assert _create(client, "joinfleek.com/new").json()["error"]["code"] == "budget_exhausted"
    assert _create(client, ip="198.51.100.3").status_code == 201


def test_status_and_context_follow_the_scrape(client_factory, db):
    client = client_factory()
    code = _create(client).json()["code"]
    status = client.get(f"/api/v1/sessions/{code}").json()
    assert status["ready"] is False and status["grok_url"] is None
    md = client.get(f"/api/v1/public/sessions/{code}.md")
    assert md.status_code == 200 and "still being read" in md.text
    assert md.headers["cache-control"] == "no-store"

    scrape_id = db.execute("select id from public.scrapes").fetchone()["id"]
    db.execute(
        "update public.scrapes set status='ready', title='April EOM RL drop', "
        "root_fetched_at=now(), pages_done=1, product_count=1 where id=%s",
        (scrape_id,),
    )
    db.execute(
        "insert into public.products (scrape_id, source_url, title, price, currency, pieces) "
        "values (%s, 'https://www.joinfleek.com/products/rl-pant', 'RL Pant', 450, 'USD', 20)",
        (scrape_id,),
    )
    status = client.get(f"/api/v1/sessions/{code}").json()
    assert status["ready"] is True and status["grok_url"].startswith("https://grok.com/?q=")
    md = client.get(f"/api/v1/public/sessions/{code}.md")
    assert "RL Pant" in md.text and md.headers["cache-control"] == "public, max-age=300"
    assert md.headers["content-type"].startswith("text/markdown")
    assert (
        client.get(f"/api/v1/public/sessions/{code}.json").json()["items"][0]["title"] == "RL Pant"
    )

    db.execute("update public.sessions set expires_at = now() - interval '1 minute'")
    assert client.get(f"/api/v1/public/sessions/{code}.md").status_code == 410
    assert client.get("/api/v1/public/sessions/EM-22222222.md").status_code == 404
    assert client.get("/api/v1/public/sessions/nope.md").status_code == 404


def test_rules_are_snapshotted_into_sessions(client_factory, db):
    user_id = str(uuid.uuid4())
    db.execute(
        "insert into auth.users (id, email, aud, role) "
        "values (%s, %s, 'authenticated', 'authenticated')",
        (user_id, f"{user_id}@example.test"),
    )
    client = client_factory(user_id=user_id)
    auth = {"Authorization": "Bearer test"}
    assert client.get("/api/v1/me/ruleset").status_code == 401
    assert client.put("/api/v1/me/ruleset", json={"rule": " only pants "}, headers=auth).json() == {
        "rule": "only pants"
    }
    assert client.get("/api/v1/me/ruleset", headers=auth).json() == {"rule": "only pants"}

    code = _create(client, headers=auth).json()["code"]
    row = db.execute(
        "select rules, classified_at, user_id from public.sessions where code=%s", (code,)
    ).fetchone()
    assert row["rules"] == {"text": "only pants"} and row["classified_at"] is None
    assert str(row["user_id"]) == user_id
    status = client.get(f"/api/v1/sessions/{code}").json()
    assert status["rule"] == {"text": "only pants", "shown": 0, "classified": False}

    # A guest sharing the same scrape keeps no rule, so it is classified at once.
    guest = client_factory()
    guest_code = _create(guest, ip="198.51.100.9").json()["code"]
    guest_row = db.execute(
        "select rules, classified_at from public.sessions where code=%s", (guest_code,)
    ).fetchone()
    assert guest_row["rules"] == {} and guest_row["classified_at"] is not None

    assert client.delete("/api/v1/me/ruleset", headers=auth).status_code == 204
    assert db.execute("select count(*) as n from public.rulesets").fetchone()["n"] == 0
    db.execute("delete from auth.users where id=%s", (user_id,))


def test_probes(client_factory):
    client = client_factory()
    assert client.get("/api/v1/healthz").json()["status"] == "ok"
    ready = client.get("/api/v1/readyz").json()
    assert ready["status"] == "ok" and "queue_depth" in ready
