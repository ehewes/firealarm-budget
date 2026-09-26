"""Jev (typesafe/jev-1.13): typed decisions, reached through OpenRouter.

Jev generates no text. It takes a small state plus typed questions and returns typed
answers with probabilities: `choice` picks one option, `noul` answers yes/no. We use
it to place products in the fixed tree (choice, level by level) and to score how well
an item fits a shopper's free-text notes (noul). Ported from stock-aggregator's
rupert/decide.py, where it has run in production.

Two measured traits shape how answers are used: `choice` runs overconfident out of
distribution, so a low-confidence placement falls back to keywords; `noul` runs
underconfident, which makes it a safe ranking signal. Keep the state to the one item
being judged, and never ask something the state cannot answer.

Every call's reported cost is added to the monthly `jev_usd` counter, and nothing is
asked once JEV_MONTHLY_BUDGET_USD is spent: callers fall back to heuristics.
"""

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx
from supabase import AsyncClient

from app.config import Settings
from app.services import usage
from app.services.taxonomy import CATEGORY_DESCRIPTIONS, TAXONOMY

logger = logging.getLogger(__name__)

API_URL = "https://openrouter.ai/api/alpha/decisions"
# Pinned, not `~typesafe/jev-latest`: a stored placement should mean the same thing tomorrow.
MODEL = "typesafe/jev-1.13"
RETRY_STATUSES = frozenset({429, 529})
MIN_CHOICE_CONFIDENCE = 0.55


class DecideError(RuntimeError):
    """The decision could not be made or came back unusable."""


class Unavailable(DecideError):
    """No key, or the monthly budget is spent. Callers use their fallback."""


@dataclass(frozen=True, slots=True)
class Choice:
    chosen: str
    confidence: float


@dataclass(frozen=True, slots=True)
class Decision:
    choices: Mapping[str, Choice]
    nouls: Mapping[str, float]
    cost_usd: float


class Jev:
    def __init__(
        self,
        settings: Settings,
        db: AsyncClient,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._settings = settings
        self._db = db
        self._transport = transport
        self._limit = asyncio.Semaphore(6)

    @property
    def configured(self) -> bool:
        return bool(self._settings.jev_key)

    async def decide(self, state: Any, questions: Mapping[str, Any]) -> Decision:
        if not self._settings.jev_key:
            raise Unavailable("no Jev key configured")
        if await usage.jev_budget_left(self._db, self._settings.jev_monthly_budget_usd) <= 0:
            raise Unavailable("this month's Jev budget is spent")
        async with self._limit:
            body = await self._post({"model": MODEL, "state": state, "questions": dict(questions)})
        decision = _parse(body)
        if decision.cost_usd:
            await usage.add(self._db, usage.JEV_USD, decision.cost_usd)
        return decision

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._settings.jev_key}",
            "HTTP-Referer": self._settings.web_origin,
            "X-Title": "eden-matrix",
        }
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            for attempt in range(3):
                try:
                    res = await client.post(API_URL, json=payload, headers=headers)
                except httpx.HTTPError as exc:
                    raise DecideError(f"Jev request failed: {type(exc).__name__}") from exc
                if res.status_code not in RETRY_STATUSES:
                    break
                await asyncio.sleep(2 * (attempt + 1))
        if res.status_code >= 400:
            raise DecideError(f"Jev returned HTTP {res.status_code}")
        try:
            body = res.json()
        except ValueError as exc:
            raise DecideError("Jev did not return JSON") from exc
        if not isinstance(body, dict) or "error" in body:
            raise DecideError(
                f"Jev reported an error: {body.get('error') if isinstance(body, dict) else body}"
            )
        return body

    # ------------------------------------------------------------ what we ask

    async def place(self, title: str, details: str = "") -> tuple[str, str] | None:
        """Category then type, one level at a time. None if Jev is unsure or unavailable."""
        state = {"item": {"title": title, "details": details[:600]}}
        top = await self.decide(
            state,
            {
                "category": {
                    "type": "choice",
                    "instructions": (
                        "Which kind of clothing is this item for sale? Judge only from its title "
                        "and details. If it bundles several different kinds, choose mixed."
                    ),
                    "criteria": dict(CATEGORY_DESCRIPTIONS),
                }
            },
        )
        category = top.choices.get("category")
        if category is None or category.confidence < MIN_CHOICE_CONFIDENCE:
            return None
        kinds = TAXONOMY.get(category.chosen, {})
        if len(kinds) == 1:
            return category.chosen, next(iter(kinds))
        sub = await self.decide(
            state,
            {
                "type": {
                    "type": "choice",
                    "instructions": (
                        f"This item is {category.chosen}. Which type of {category.chosen} is it?"
                    ),
                    "criteria": dict(kinds),
                }
            },
        )
        kind = sub.choices.get("type")
        if kind is None or kind.confidence < MIN_CHOICE_CONFIDENCE:
            return None
        return category.chosen, kind.chosen

    async def product_links(self, page: str, links: list[tuple[str, str]]) -> dict[str, float]:
        """Probability, per link, that it opens the page of one specific product for sale.

        A dozen links per request: the state is only the page title and those links, so
        each yes/no question is answerable from what Jev can see.
        """
        verdicts: dict[str, float] = {}
        for start in range(0, len(links), 12):
            batch = links[start : start + 12]
            state = {
                "page": page[:200],
                "links": [
                    {"id": f"L{n}", "text": text[:120], "path": urlsplit(url).path[:160]}
                    for n, (url, text) in enumerate(batch)
                ],
            }
            questions = {
                f"L{n}": {
                    "type": "noul",
                    "instructions": (
                        f"Look at link L{n} in the state. Does it open the page of one specific "
                        "product that a shopper could buy? Judge only from its text and path."
                    ),
                    "criteria": {
                        "true": "It opens a single product: one item with its own page.",
                        "false": "It opens a category, collection, brand, search, account, cart, "
                        "help or marketing page, or anything that is not one product.",
                    },
                }
                for n in range(len(batch))
            }
            decision = await self.decide(state, questions)
            for n, (url, _) in enumerate(batch):
                verdicts[url] = decision.nouls.get(f"L{n}", 0.0)
        return verdicts

    async def fits_notes(self, notes: list[str], title: str, details: str = "") -> float:
        """Probability that the item fits the shopper's free-text preferences."""
        decision = await self.decide(
            {"preferences": notes, "item": {"title": title, "details": details[:600]}},
            {
                "fits": {
                    "type": "noul",
                    "instructions": (
                        "A shopper listed preferences in the state. Does this item fit them? "
                        "Use only the item's title and details. "
                        "If they don't say enough, answer false."
                    ),
                    "criteria": {
                        "true": "The item's title or details show it matches the preferences.",
                        "false": "It goes against a preference, or the details are too thin.",
                    },
                }
            },
        )
        return decision.nouls.get("fits", 0.0)


def _parse(body: dict[str, Any]) -> Decision:
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise DecideError("Jev response carried no answers")
    choices: dict[str, Choice] = {}
    nouls: dict[str, float] = {}
    for key, answer in answers.items():
        if not isinstance(answer, dict):
            raise DecideError(f"answer {key!r} is not an object")
        if answer.get("type") == "noul" and isinstance(answer.get("noul"), int | float):
            nouls[key] = float(answer["noul"])
        elif answer.get("type") == "choice":
            chosen, probs = answer.get("choice"), answer.get("probabilities")
            confidence = answer.get("confidence")
            if not isinstance(chosen, str) or not isinstance(probs, dict) or chosen not in probs:
                raise DecideError(f"answer {key!r} is not a usable choice")
            if not isinstance(confidence, int | float):
                raise DecideError(f"answer {key!r} has no confidence")
            choices[key] = Choice(chosen=chosen, confidence=float(confidence))
    if not choices and not nouls:
        raise DecideError("Jev response carried no usable answers")
    cost = (body.get("usage") or {}).get("cost") or 0
    return Decision(choices=choices, nouls=nouls, cost_usd=float(cost))
