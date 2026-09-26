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
from app.models import Rules

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


def grok_url(settings: Settings, *, code: str, store: str, collection: str | None) -> str:
    prompt = grok_prompt(settings, code=code, store=store, collection=collection)
    base = settings.grok_bot_url
    return f"{base}{'&' if '?' in base else '?'}{urlencode({'q': prompt})}"


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
