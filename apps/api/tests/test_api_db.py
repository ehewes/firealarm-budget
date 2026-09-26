"""The API end to end against local Supabase, scraping the saved joinfleek-shaped fixtures."""

import pytest

pytestmark = pytest.mark.db

AUTH = {"Authorization": "Bearer test", "CF-Connecting-IP": "203.0.113.7"}
COLLECTION = "https:/www.joinfleek.com/collections/april-eom-rl-drop"


def _start(client, url=COLLECTION, **body):
    return client.post("/v1/sessions", json={"url": url, **body}, headers=AUTH)


def test_prefix_to_scrape_to_tree_to_products(make_client):
    factory, db, user_id = make_client
    client = factory()

    created = _start(client, rules={"max_per_piece": 14})
    assert created.status_code == 202, created.text
    body = created.json()
    code = body["code"]
    assert code.startswith("EM-") and body["session_url"] == f"https://go.example.test/s/{code}"
    assert f"sessions%2F{code}%2Fproducts" in body["grok_url"]

    # TestClient runs the BackgroundTask before returning, so the scrape has finished.
    session = client.get(f"/v1/sessions/{code}").json()
    assert session["status"] == "ready", session
    assert session["collection"] == "April EOM RL Drop"
    assert session["product_count"] == 6 and session["store"] == "joinfleek.com"
    assert session["rules"] == {**session["rules"], "max_per_piece": 14.0}
    assert session["can_purchase"] is False

    tree = {node["name"]: node for node in client.get(f"/v1/sessions/{code}/tree").json()["tree"]}
    assert tree["bottoms"]["count"] == 3 and tree["tops"]["count"] == 3
    assert {c["name"] for c in tree["bottoms"]["children"]} == {"shorts", "jeans", "trousers"}

    products = client.get(f"/v1/sessions/{code}/products").json()
    titles = [item["title"] for item in products["items"]]
    assert titles == [
        "Ralph Lauren Swim Shorts (FNC 694)",
        "Ralph Lauren Trousers/Pant RV # 1273",
        "Polo Ralph Lauren Shirts",
    ]  # everything at or under $14/pc, cheapest per piece first
    assert products["items"][0]["why"] == "$8.00/pc under your $14.00 cap"
    assert products["total_matching"] == 3
    grok = client.get(f"/v1/sessions/{code}/grok").json()
    assert grok["prompt"].startswith("I'm shopping April EOM RL Drop on joinfleek.com.")
    assert f"https://go.example.test/v1/sessions/{code}/products" in grok["prompt"]
    picks = db.execute("select count(*) as n from public.session_picks").fetchone()["n"]
    assert picks == 3

    bottoms = client.get(f"/v1/sessions/{code}/products", params={"category": "bottoms"}).json()
    assert [i["title"] for i in bottoms["items"]] == titles[:2]
    assert (
        client.get(f"/v1/sessions/{code}/products", params={"q": "jeans"}).json()["total_matching"]
        == 0
    )

    pant_id = products["items"][1]["id"]
    detail = client.get(f"/v1/sessions/{code}/products/{pant_id}").json()
    assert detail["attrs"]["brand"] == "Ralph Lauren"  # enriched from the product page
    assert detail["attrs"]["breadcrumbs"] == ["Home", "Bottoms", "Trousers"]

    refreshed = client.post(f"/v1/sessions/{code}/products/{pant_id}/refresh").json()
    assert refreshed["changed"] == {"price": [260.0, 275.0]}
    assert refreshed["product"]["price"] == 275.0

    scrapes = db.execute(
        "select amount from public.usage_counters where key = 'scrapes'"
    ).fetchone()
    assert int(scrapes["amount"]) == 8  # listing + 6 product pages + 1 refresh

    # A second session for the same page shares the fresh scrape: no new fetches.
    again = _start(client)
    assert again.status_code == 202
    assert again.json()["scrape_id"] == body["scrape_id"]


class _NothingToList:
    """A page that loads but lists nothing readable: an empty search, a bot wall, a blog."""

    async def fetch(self, url: str) -> str:
        return "<html><title>Shirts</title><body>" + "<p>Nothing here.</p>" * 100 + "</body></html>"


def test_a_page_without_products_fails_instead_of_inventing_some(make_client):
    factory, db, _ = make_client
    client = factory(fetcher=_NothingToList())

    code = _start(client).json()["code"]
    session = client.get(f"/v1/sessions/{code}").json()
    assert session["status"] == "failed"
    assert session["error"] == "no products were found on that page"
    assert db.execute("select count(*) as n from public.products").fetchone()["n"] == 0


def test_guards(make_client):
    factory, db, user_id = make_client
    client = factory(sessions_per_hour_per_ip=2, scrape_monthly_max=100)

    assert client.post("/v1/sessions", json={"url": COLLECTION}).status_code == 401
    other = _start(client, "https://example.org/shop")
    assert other.status_code == 400 and other.json()["error"]["code"] == "domain_not_allowed"

    db.execute(
        "insert into public.usage_counters (period, key, amount) "
        "values (date_trunc('month', now())::date, 'scrapes', 100)"
    )
    spent = _start(client)
    assert spent.status_code == 503 and spent.json()["error"]["code"] == "budget_exhausted"

    db.execute("delete from public.usage_counters")
    assert _start(client).status_code == 202
    assert _start(client, COLLECTION + "?page=2").status_code == 202
    limited = _start(client, COLLECTION + "?page=3")
    assert limited.status_code == 429 and limited.json()["error"]["code"] == "rate_limited"

    assert client.get("/v1/sessions/EM-22222222").json()["error"]["code"] == "session_not_found"
    db.execute("update public.sessions set expires_at = now() - interval '1 minute'")
    code = db.execute("select code from public.sessions limit 1").fetchone()["code"]
    assert client.get(f"/v1/sessions/{code}").json()["error"]["code"] == "session_expired"


def test_rulesets_and_parsing(make_client):
    factory, db, user_id = make_client
    client = factory()

    parsed = client.post("/v1/rules/parse", json={"text": "premium only, no shorts"}, headers=AUTH)
    assert parsed.json()["grades"] == ["premium"] and parsed.json()["exclude_categories"] == [
        "shorts"
    ]

    first = client.post(
        "/v1/rulesets",
        json={"name": "Cheap", "rules": {"max_per_piece": 14}, "is_default": True},
        headers=AUTH,
    ).json()
    second = client.post(
        "/v1/rulesets",
        json={"name": "Premium", "rules": {"grades": ["premium"]}, "is_default": True},
        headers=AUTH,
    ).json()
    listed = client.get("/v1/rulesets", headers=AUTH).json()
    assert [(r["name"], r["is_default"]) for r in listed] == [("Cheap", False), ("Premium", True)]

    patched = client.patch(
        f"/v1/rulesets/{first['id']}", json={"name": "Budget"}, headers=AUTH
    ).json()
    assert patched["name"] == "Budget"

    code = _start(client, ruleset_id=second["id"]).json()["code"]
    products = client.get(f"/v1/sessions/{code}/products").json()
    assert [i["title"] for i in products["items"]] == ["Premium Ralph Lauren Cable Knit Jumpers"]

    assert client.delete(f"/v1/rulesets/{first['id']}", headers=AUTH).status_code == 204
    assert len(client.get("/v1/rulesets", headers=AUTH).json()) == 1


def test_probes(make_client):
    factory, _, _ = make_client
    client = factory()
    assert client.get("/v1/health").json()["status"] == "ok"
    assert client.get("/v1/ready").json()["status"] == "ok"
