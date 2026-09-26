"""Rules, applied server-side (CLAUDE.md rule 7): Grok only ever sees what passed.

Hard filters are exact code, never a model's judgement: a price cap is arithmetic, and
Jev is explicitly not a calculator. Free-text `notes` only rank what already passed.
An item that can't be checked against a hard filter (no per-piece price when the rule
caps per-piece price) is excluded rather than assumed to pass.
"""

import re
from typing import Any

from app.models import Rules


def merge(base: Rules, override: Rules | None) -> Rules:
    """`override`'s set fields win; list fields are replaced, not concatenated."""
    if override is None:
        return base
    return base.model_copy(update=override.model_dump(exclude_unset=True))


def with_query(rules: Rules, *, max_per_piece: float | None, category: str | None) -> Rules:
    update: dict[str, Any] = {}
    if max_per_piece is not None:
        current = rules.max_per_piece
        update["max_per_piece"] = (
            min(current, max_per_piece) if current is not None else max_per_piece
        )
    if category:
        update["include_categories"] = [category]
    return rules.model_copy(update=update)


def _norm(word: str) -> str:
    word = word.strip().lower()
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _mentions(product: dict[str, Any], term: str) -> bool:
    needle = _norm(term)
    path = [_norm(p) for p in product.get("tree_path") or []]
    return (
        any(needle == p or needle in p for p in path)
        or needle in (product.get("title") or "").lower()
    )


def passes(product: dict[str, Any], rules: Rules) -> bool:
    per_piece, price, pieces = product.get("per_piece"), product.get("price"), product.get("pieces")
    if rules.max_per_piece is not None and (
        per_piece is None or float(per_piece) > rules.max_per_piece
    ):
        return False
    if rules.max_total is not None and (price is None or float(price) > rules.max_total):
        return False
    if rules.min_pieces is not None and (pieces is None or int(pieces) < rules.min_pieces):
        return False
    tier = (product.get("tree_path") or [None, None, None])[-1]
    if rules.grades and (tier or "").lower() not in {g.lower() for g in rules.grades}:
        return False
    if rules.include_categories and not any(
        _mentions(product, c) for c in rules.include_categories
    ):
        return False
    return not any(_mentions(product, c) for c in rules.exclude_categories)


def money(amount: Any, currency: str | None) -> str:
    symbol = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency or "", "")
    return (
        f"{symbol}{float(amount):.2f}"
        if symbol
        else f"{float(amount):.2f} {currency or ''}".strip()
    )


def why(product: dict[str, Any], rules: Rules, score: float | None = None) -> str:
    """A short, factual reason built from stored fields only."""
    currency = product.get("currency")
    parts = []
    path = product.get("tree_path") or []
    if rules.grades and path:
        parts.append(f"{path[-1].capitalize()} grade")
    per_piece = product.get("per_piece")
    if rules.max_per_piece is not None and per_piece is not None:
        cap = money(rules.max_per_piece, currency)
        parts.append(f"{money(per_piece, currency)}/pc under your {cap} cap")
    elif per_piece is not None:
        parts.append(f"{money(per_piece, currency)}/pc")
    if rules.min_pieces is not None and product.get("pieces"):
        parts.append(f"{product['pieces']} pieces (you wanted {rules.min_pieces}+)")
    if rules.max_total is not None and product.get("price") is not None:
        within = money(rules.max_total, currency)
        parts.append(f"{money(product['price'], currency)} total, within {within}")
    if rules.include_categories and len(path) >= 2:
        parts.append(f"{path[1]} in {path[0]}")
    if score is not None and rules.notes:
        parts.append(f"fits your notes ({score:.0%})")
    return "; ".join(parts) or "Matches your rules"


# ---------------------------------------------------------------- parsing text

_NUM = r"[$£€]?\s*(\d+(?:\.\d+)?)"
_CAP_WORDS = r"under|below|less than|max(?:imum)?|up to|at most|<"
_EACH = r"\s*(?:a|per|/|each)\s*(?:piece|pc|pcs|item|unit)"
_PER_PIECE = re.compile(rf"(?:{_CAP_WORDS})\s*{_NUM}{_EACH}", re.IGNORECASE)
_TOTAL = re.compile(rf"(?:{_CAP_WORDS}|budget(?: of)?)\s*{_NUM}(?!{_EACH})", re.IGNORECASE)
_MIN_PIECES = re.compile(
    r"(?:at least|min(?:imum)?|over|more than)\s*(\d+)\s*(?:pieces|pcs|items|units)", re.IGNORECASE
)
_EXCLUDE = re.compile(
    r"\b(?:no|not|without|exclude|except)\s+([a-z][a-z\- ]{1,30}?)(?=,|\.|;|$|\s+and\b|\s+or\b)",
    re.IGNORECASE,
)
_ONLY = re.compile(
    r"\bonly\s+([a-z][a-z\- ]{1,30}?)(?=,|\.|;|$|\s+and\b|\s+under\b|\s+below\b)", re.IGNORECASE
)


def parse_text(text: str) -> Rules:
    """A deterministic parser for common phrasings; the fallback when the Grok API is off."""
    rules: dict[str, Any] = {"grades": [], "include_categories": [], "exclude_categories": []}
    if m := _PER_PIECE.search(text):
        rules["max_per_piece"] = float(m.group(1))
        text_wo = text[: m.start()] + text[m.end() :]
    else:
        text_wo = text
    if m := _TOTAL.search(text_wo):
        rules["max_total"] = float(m.group(1))
    if m := _MIN_PIECES.search(text):
        rules["min_pieces"] = int(m.group(1))
    for grade in ("premium", "standard"):
        if re.search(rf"\b{grade}\b", text, re.IGNORECASE):
            rules["grades"].append(grade)
    for m in _EXCLUDE.finditer(text):
        rules["exclude_categories"].append(m.group(1).strip().lower())
    for m in _ONLY.finditer(text):
        term = m.group(1).strip().lower()
        if term not in ("premium", "standard"):
            rules["include_categories"].append(term)
    parsed = Rules(**rules)
    if parsed.is_empty():
        parsed = Rules(notes=[text.strip()])
    return parsed
