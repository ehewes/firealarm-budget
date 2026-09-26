"""Grok: the "Continue to Grok" handoff link, and (optionally) the Grok API for rule parsing.

The handoff is `grok.com/?q=<prompt>`, which pre-fills the prompt. It is
community-documented rather than an official API, so it is built only here. The prompt
points Grok at the session's products endpoint, which already applies the rules, and
tells it to quote only what that API returns (CLAUDE.md rule 3).
"""

import json
import logging
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.errors import EdenError
from app.models import Rules
from app.services.fetch import FetchError, require_public

logger = logging.getLogger(__name__)

XAI_URL = "https://api.x.ai/v1/chat/completions"


def grok_prompt(settings: Settings, *, code: str, store: str, collection: str | None) -> str:
    api = settings.api_base
    what = f"{collection} on {store}" if collection else store
    return (
        f"I'm shopping {what}. My Eden Matrix session is {code}. "
        f"Get my shortlist from {api}/sessions/{code}/products (it already applies my rules; "
        "add ?q= or ?category= to narrow it) and recommend the best items. "
        "Quote only the titles and prices that API returns. "
        f"Session details: {api}/sessions/{code}"
    )


def grok_bot_prompt(settings: Settings, *, code: str, store: str, collection: str | None) -> str:
    """The same ask for Grok Bot, plus memory. Its computer keeps /workspace between tasks
    (docs.x.ai/grok-bot), so it logs each session there and can recall earlier ones."""
    what = f"{collection} on {store}" if collection else store
    session_url = f"{settings.web_origin.rstrip('/')}/s/{code}"
    return (
        grok_prompt(settings, code=code, store=store, collection=collection)
        + " Keep a log of my Eden Matrix sessions in /workspace/eden-matrix/sessions.md: add this "
        f"one ({code}, {what}, today's date, {session_url}) and read that file whenever I mention "
        "an earlier session or shop. If the Eden Matrix MCP server is connected, list_my_sessions "
        "has my full history, and create_purchase_intent asks to buy: I confirm every purchase on "
        "Eden before anything is charged."
    )


def grok_url(settings: Settings, *, code: str, store: str, collection: str | None) -> str:
    prompt = grok_prompt(settings, code=code, store=store, collection=collection)
    base = settings.grok_bot_url
    return f"{base}{'&' if '?' in base else '?'}{urlencode({'q': prompt})}"


async def send_to_bot(
    url: str, key: str, payload: dict, *, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Start the shopper's Grok Bot automation ("When a webhook fires") with a session.

    Grok Bot's app links can't carry a prompt, but its webhook trigger takes a body, so
    this is how a session reaches the bot with nothing to paste. The URL is the shopper's
    own, so it gets the same public-address check as a direct fetch, and no redirects.
    """
    try:
        await require_public(url)
    except FetchError as exc:
        raise EdenError("invalid_webhook", f"That webhook URL can't be used: {exc}.") from exc
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as client:
            res = await client.post(url, json=payload, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as exc:
        raise EdenError(
            "grok_bot_unreachable", "Couldn't reach your Grok Bot automation.", 502
        ) from exc
    if res.status_code >= 300:
        raise EdenError(
            "grok_bot_unreachable",
            f"Your Grok Bot automation answered HTTP {res.status_code}. Check its webhook URL "
            "and key on your Eden dashboard.",
            502,
        )


async def parse_rules(settings: Settings, text: str) -> Rules | None:
    """Plain-language rules → a rules object via the Grok API, or None to use the fallback."""
    if not settings.grok_api_key:
        return None
    schema = Rules.model_json_schema()
    payload = {
        "model": settings.grok_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Turn a shopper's rules for buying wholesale clothing into JSON matching the "
                    "schema. Prices are numbers without currency symbols. Put anything that is a "
                    "preference rather than a hard limit in notes. Output only JSON."
                ),
            },
            {"role": "user", "content": text},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "rules", "schema": schema},
        },
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(
                XAI_URL, json=payload, headers={"Authorization": f"Bearer {settings.grok_api_key}"}
            )
        res.raise_for_status()
        content = res.json()["choices"][0]["message"]["content"]
        return Rules.model_validate(json.loads(content))
    except Exception as exc:  # any failure means the deterministic parser takes over
        logger.warning("Grok rule parsing failed, using the fallback: %s", type(exc).__name__)
        return None
