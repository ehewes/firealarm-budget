"""The category tree every product is placed in: category → type → tier.

Fixed on purpose. Jev chooses *within* these options (see jev.py); it never invents a
branch, so the tree the shopper sees is stable across scrapes and rules can name
categories that will always exist. The keyword fallback places a product when Jev is
unavailable or over budget, and is also the first, instant placement shown in the
live tree before Jev refines it.
"""

import re

TAXONOMY: dict[str, dict[str, str]] = {
    "tops": {
        "t-shirts": "T-shirts and tees",
        "shirts": "Button-up and casual shirts",
        "polos": "Polo shirts and rugby shirts",
        "sweatshirts": "Sweatshirts and crewnecks",
        "hoodies": "Hoodies",
        "jerseys": "Sports jerseys",
        "knitwear": "Jumpers, sweaters and cardigans",
    },
    "bottoms": {
        "jeans": "Jeans and denim trousers",
        "trousers": "Trousers, pants and chinos",
        "trackpants": "Trackpants, joggers and sweatpants",
        "cargo pants": "Cargo pants",
        "shorts": "Shorts",
        "skirts": "Skirts",
    },
    "outerwear": {
        "jackets": "Jackets, windbreakers and bombers",
        "coats": "Coats, parkas and puffers",
        "fleeces": "Fleeces",
        "gilets": "Gilets and vests",
    },
    "dresses": {"dresses": "Dresses and jumpsuits"},
    "footwear": {"trainers": "Trainers and sneakers", "boots": "Boots", "shoes": "Other shoes"},
    "accessories": {
        "caps": "Caps and hats",
        "bags": "Bags",
        "scarves": "Scarves",
        "other accessories": "Belts, sunglasses and other accessories",
    },
    "mixed": {"mixed bundle": "A bundle mixing several kinds of clothing"},
}

CATEGORY_DESCRIPTIONS = {
    "tops": (
        "Clothing for the upper body: t-shirts, shirts, polos, sweatshirts, hoodies, "
        "jerseys, knitwear."
    ),
    "bottoms": (
        "Clothing for the legs: jeans, trousers, pants, trackpants, cargo pants, shorts, skirts."
    ),
    "outerwear": "Worn over other clothes: jackets, coats, fleeces, gilets.",
    "dresses": "Dresses and jumpsuits.",
    "footwear": "Shoes, trainers and boots.",
    "accessories": "Caps, hats, bags, scarves, belts and other accessories.",
    "mixed": "A bundle that mixes several different kinds of clothing.",
}

TIERS = ("premium", "standard")

# Checked in order: the first matching pattern wins, so specific beats general
# ("track pant" before "pant", "t-shirt" before "shirt").
_KEYWORDS: list[tuple[str, str, str]] = [
    (r"track ?(pant|suit|bottom)|jogger|sweat ?pant", "bottoms", "trackpants"),
    (r"cargo", "bottoms", "cargo pants"),
    (r"jean|denim", "bottoms", "jeans"),
    (r"\bshorts?\b", "bottoms", "shorts"),
    (r"skirt", "bottoms", "skirts"),
    (r"trouser|\bpants?\b|chino|slacks", "bottoms", "trousers"),
    (r"t-?shirt|\btees?\b", "tops", "t-shirts"),
    (r"polo|rugby", "tops", "polos"),
    (r"hood(ie|y)", "tops", "hoodies"),
    (r"sweatshirt|crewneck|crew neck", "tops", "sweatshirts"),
    (r"jersey", "tops", "jerseys"),
    (r"knit|jumper|sweater|cardigan", "tops", "knitwear"),
    (r"shirt|blouse|flannel", "tops", "shirts"),
    (r"fleece", "outerwear", "fleeces"),
    (r"gilet|\bvests?\b|bodywarmer", "outerwear", "gilets"),
    (r"coat|parka|puffer", "outerwear", "coats"),
    (r"jacket|windbreaker|bomber|anorak", "outerwear", "jackets"),
    (r"dress|jumpsuit", "dresses", "dresses"),
    (r"boot", "footwear", "boots"),
    (r"trainer|sneaker", "footwear", "trainers"),
    (r"shoe", "footwear", "shoes"),
    (r"\bcaps?\b|\bhats?\b|beanie", "accessories", "caps"),
    (r"\bbags?\b|backpack", "accessories", "bags"),
    (r"scarf|scarves", "accessories", "scarves"),
    (r"belt|sunglass", "accessories", "other accessories"),
    (r"mix|assorted|bundle", "mixed", "mixed bundle"),
]
_COMPILED = [(re.compile(p, re.IGNORECASE), c, t) for p, c, t in _KEYWORDS]
_PREMIUM = re.compile(r"premium|grade ?a\b|\ba ?grade|high[- ]end|designer", re.IGNORECASE)
# Brand names that contain a product word: "Polo Ralph Lauren Shirts" are shirts, not polos.
_BRAND_NOISE = re.compile(r"\bpolo (?:by )?ralph lauren\b", re.IGNORECASE)


def keyword_place(text: str) -> tuple[str, str] | None:
    """The first matching (category, type), or None if the text names no kind of clothing."""
    text = _BRAND_NOISE.sub("ralph lauren", text)
    for pattern, category, kind in _COMPILED:
        if pattern.search(text):
            return category, kind
    return None


def tier_of(text: str) -> str:
    return "premium" if _PREMIUM.search(text) else "standard"


def keyword_path(title: str, extra: str = "") -> list[str]:
    """The title decides; `extra` (breadcrumbs, description) only places items whose title
    names no kind of clothing. Searching them together would let a "Trousers" breadcrumb
    or a description mentioning jeans outvote a title that says T-shirts."""
    placed = keyword_place(title) or keyword_place(extra) or ("mixed", "mixed bundle")
    return [*placed, tier_of(f"{title} {extra}")]
