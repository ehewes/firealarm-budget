"""Accounts, the demo agent card, MCP and purchases, end to end against local Supabase.

The flow a demo shows: a guest starts a session, signs up, links a card, connects Grok
Bot over MCP; the bot recalls the session, asks to buy, and the shopper confirms on Eden.
"""

import json

import httpx
import pytest

from app.services import fetch

pytestmark = pytest.mark.db

GUEST = {"Authorization": "Bearer test", "CF-Connecting-IP": "203.0.113.7"}
ACCOUNT = {"Authorization": "Bearer account", "CF-Connecting-IP": "203.0.113.7"}
STRANGER = {"Authorization": "Bearer stranger"}
COLLECTION = "https://www.joinfleek.com/collections/april-eom-rl-drop"


def _rpc(client, token, method, params=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/v1/mcp", json=body, headers={"Authorization": f"Bearer {token}"})


def _tool(client, token, name, **arguments):
    call = {"name": name, "arguments": arguments}
    return _rpc(client, token, "tools/call", call).json()["result"]


def test_signed_up_shopper_buys_through_their_agent(make_client):
    factory, db, _ = make_client
    client = factory(demo_checkout_seconds=0)

    code = client.post("/v1/sessions", json={"url": COLLECTION}, headers=GUEST).json()["code"]
    assert client.get("/v1/me", headers=GUEST).json()["is_anonymous"] is True
    refused = client.put("/v1/me/card", json={"spend_cap": 300}, headers=GUEST)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "account_required"

    # Signing up keeps the same user, so the guest's session is the account's.
    card = client.put("/v1/me/card", json={"spend_cap": 300}, headers=ACCOUNT).json()
    assert card["provider"] == "demo" and len(card["last4"]) == 4 and card["spend_cap"] == 300
    raised = client.put("/v1/me/card", json={"spend_cap": 400}, headers=ACCOUNT).json()
    assert raised["last4"] == card["last4"] and raised["spend_cap"] == 400

    agent = client.post("/v1/me/agents", json={"name": "Grok Bot"}, headers=ACCOUNT).json()
    token = agent["token"]
    assert token.startswith("em_agent_") and agent["mcp_url"] == "https://go.example.test/v1/mcp"
    server = agent["mcp_config"]["mcpServers"]["eden-matrix"]
    assert server == {"url": agent["mcp_url"], "headers": {"Authorization": f"Bearer {token}"}}
    assert db.execute("select token_hash from public.agent_links").fetchone()["token_hash"] != token

    hello = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}}
    init = _rpc(client, token, "initialize", hello).json()["result"]
    assert init["protocolVersion"] == "2025-06-18" and "tools" in init["capabilities"]
    note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    auth = {"Authorization": f"Bearer {token}"}
    assert client.post("/v1/mcp", json=note, headers=auth).status_code == 202
    assert client.get("/v1/mcp", headers=auth).status_code == 405
    assert _rpc(client, "em_agent_not-a-real-token", "tools/list").status_code == 401
    tools = {tool["name"] for tool in _rpc(client, token, "tools/list").json()["result"]["tools"]}
    assert {"list_my_sessions", "find_products", "create_purchase_intent"} <= tools

    # grok.com's custom connectors take only a URL, so the token can ride in it instead.
    assert agent["connector_url"] == f"{agent['mcp_url']}?key={token}"
    listing = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    by_url = client.post("/v1/mcp", params={"key": token}, json=listing)
    assert by_url.status_code == 200 and len(by_url.json()["result"]["tools"]) == len(tools)
    assert client.post("/v1/mcp", params={"key": "em_agent_nope"}, json=listing).status_code == 401

    # The agent recalls the shopper's sessions and reads the shortlist.
    sessions = _tool(client, token, "list_my_sessions")["structuredContent"]["sessions"]
    assert [s["code"] for s in sessions] == [code]
    items = _tool(client, token, "find_products", code=code, limit=10)["structuredContent"]["items"]
    pant = next(item for item in items if "Trousers" in item["title"])

    intent = _tool(client, token, "create_purchase_intent", code=code, product_ids=[pant["id"]])
    intent = intent["structuredContent"]
    assert (intent["status"], intent["total"], intent["card"]) == ("pending", 260.0, None)
    assert intent["confirm_url"] == f"https://go.example.test/confirm/{intent['id']}"
    confirm = f"/v1/purchase-intents/{intent['id']}/confirm"

    # Only the signed-in owner, on Eden, can say yes (rule 2).
    assert client.post(confirm, headers=GUEST).status_code == 403
    assert client.post(confirm, headers=auth).status_code == 401  # an agent token isn't a user
    assert client.get(f"/v1/purchase-intents/{intent['id']}", headers=STRANGER).status_code == 404

    # The store's price moved since the agent asked: 409, then a fresh yes (rule 4).
    moved = client.post(confirm, headers=ACCOUNT)
    assert moved.status_code == 409 and moved.json()["error"]["code"] == "price_changed"
    assert "$260.00 → $275.00" in moved.json()["error"]["message"]
    status = _tool(client, token, "get_purchase_status", intent_id=intent["id"])
    assert status["structuredContent"]["status"] == "price_changed"
    assert status["structuredContent"]["total"] == 275.0

    done = client.post(confirm, headers=ACCOUNT)
    assert done.status_code == 200 and done.json()["status"] == "executing"
    assert done.json()["card"] == {"status": "card_ready", "last4": card["last4"], "limit": 288.75}
    final = _tool(client, token, "get_purchase_status", intent_id=intent["id"])
    assert final["structuredContent"]["status"] == "completed"
    assert final["structuredContent"]["order_ref"].startswith("EDEN-DEMO-")
    assert client.post(confirm, headers=ACCOUNT).json()["error"]["code"] == "intent_closed"

    # Over the spend cap: refused before any intent exists.
    client.put("/v1/me/card", json={"spend_cap": 5}, headers=ACCOUNT)
    over = _tool(client, token, "create_purchase_intent", code=code, product_ids=[pant["id"]])
    assert over["isError"] and "limit per purchase" in over["content"][0]["text"]

    assert client.delete(f"/v1/me/agents/{agent['id']}", headers=ACCOUNT).status_code == 204
    assert _rpc(client, token, "tools/list").status_code == 401


async def _public(host: str) -> list[str]:
    return ["93.184.215.14"]


async def _inside(host: str) -> list[str]:
    return ["10.0.0.7"]


def test_send_to_grok_bot_posts_the_session_to_the_automation(make_client, monkeypatch):
    received = []

    def automation(request: httpx.Request) -> httpx.Response:
        received.append((request.headers["authorization"], json.loads(request.content)))
        return httpx.Response(202)

    factory, _, _ = make_client
    client = factory(webhook_transport=httpx.MockTransport(automation))
    monkeypatch.setattr(fetch, "_addresses", _public)
    code = client.post("/v1/sessions", json={"url": COLLECTION}, headers=GUEST).json()["code"]
    send = f"/v1/sessions/{code}/send-to-grok-bot"
    assert client.post(send, headers=ACCOUNT).json()["error"]["code"] == "no_webhook"

    hook = {"url": "https://hooks.bot.test/w/abc", "key": "whk_secret_123"}
    assert client.put("/v1/me/grok-bot-webhook", json=hook, headers=GUEST).status_code == 403
    saved = client.put("/v1/me/grok-bot-webhook", json=hook, headers=ACCOUNT).json()
    assert saved == {"host": "hooks.bot.test", "last_sent_at": None}

    assert client.post(send, headers=ACCOUNT).json() == {"sent": True}
    authorization, body = received[0]
    assert authorization == "Bearer whk_secret_123"
    assert body["source"] == "eden-matrix" and body["session"]["code"] == code
    assert "/workspace/eden-matrix/sessions.md" in body["prompt"]
    me = client.get("/v1/me", headers=ACCOUNT).json()
    assert me["grok_bot_webhook"]["last_sent_at"] is not None
    assert "whk_secret_123" not in json.dumps(me)

    monkeypatch.setattr(fetch, "_addresses", _inside)
    inside = {"url": "https://hooks.inside.test/w", "key": "whk_secret_123"}
    bad = client.put("/v1/me/grok-bot-webhook", json=inside, headers=ACCOUNT)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_webhook"
