"""HTML → products. Generic, with joinfleek's shape as the first real case.

Stores rarely publish schema.org Product markup on listing pages. What they nearly
always ship is the data their own front end renders from: `__NEXT_DATA__` on Next.js
stores (joinfleek puts 25 items per page there), raw objects in JSON-LD, or Shopify
JSON. So the listing extractor looks for the largest list of *product-like* objects
(something with a name, a price and an identity) anywhere in the page's JSON, and only
falls back to scraping anchors when there is none.

Rule 3 in CLAUDE.md starts here: every title, price and image shown later comes from
these fields, never from model text.
"""

import html as htmllib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from selectolax.parser import HTMLParser

from app.services.urls import canonical, same_site

_NAME_KEYS = ("title", "name")
_PRICE_KEYS = ("totalPrice", "price", "pricePerUnit", "offers", "priceRange", "salePrice")
_ID_KEYS = ("id", "slug", "handle", "url", "redirectUrl", "sku", "productId")
_PIECE_UNITS = {None, "", "piece", "pieces", "pcs", "pc", "unit", "units", "item", "items"}
_PRODUCT_PATH = re.compile(
    r"/(products?|p|item|items|dp|pd|goods)/[^/?#]+/?$|-[pP]\d+(?:\.html)?/?$",
    re.IGNORECASE,
)
_PIECES_IN_TEXT = re.compile(r"\b(\d{1,4})\s*(?:pcs|pieces|pc|units)\b", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


@dataclass(slots=True)
class Item:
    title: str
    source_url: str
    external_id: str | None = None
    price: float | None = None
    compare_at_price: float | None = None
    per_piece: float | None = None
    pieces: int | None = None
    currency: str | None = None
    image_url: str | None = None
    in_stock: bool | None = None
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Listing:
    title: str | None
    items: list[Item]
    total_items: int | None
    next_url: str | None


@dataclass(slots=True)
class ProductPage:
    title: str | None = None
    price: float | None = None
    currency: str | None = None
    in_stock: bool | None = None
    description: str | None = None
    brand: str | None = None
    breadcrumbs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- page JSON


def _page_json(tree: HTMLParser) -> list[Any]:
    """Every JSON document embedded in the page: __NEXT_DATA__ and each JSON-LD block."""
    docs: list[Any] = []
    for node in tree.css('script#__NEXT_DATA__, script[type="application/ld+json"]'):
        try:
            docs.append(json.loads(node.text() or ""))
        except json.JSONDecodeError:
            continue
    return docs


def _walk(obj: Any, depth: int = 0) -> Iterator[Any]:
    if depth > 14:
        return
    yield obj
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _walk(value, depth + 1)
    elif isinstance(obj, list):
        for value in obj[:500]:
            yield from _walk(value, depth + 1)


def _has(d: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(d.get(k) not in (None, "", [], {}) for k in keys)


def _product_like(d: Any) -> bool:
    return (
        isinstance(d, dict) and _has(d, _NAME_KEYS) and _has(d, _PRICE_KEYS) and _has(d, _ID_KEYS)
    )


def _product_lists(docs: list[Any]) -> list[list[dict[str, Any]]]:
    found = []
    for doc in docs:
        for node in _walk(doc):
            if isinstance(node, list) and len(node) >= 3:
                likes = [x for x in node if _product_like(x)]
                if len(likes) >= 0.8 * len(node):
                    found.append(likes)
    return found


def _find_key(docs: list[Any], key: str) -> Any:
    for doc in docs:
        for node in _walk(doc):
            if isinstance(node, dict) and key in node:
                return node[key]
    return None


# ---------------------------------------------------------------- values


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, dict):
        for key in ("amount", "value", "price", "minVariantPrice"):
            if key in value:
                return _number(value[key])
        return None
    if isinstance(value, str):
        match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value.replace(" ", ""))
        if match:
            return float(match.group(0).replace(",", ""))
    return None


def _currency(d: dict[str, Any]) -> str | None:
    for key in ("currencyCode", "currency", "priceCurrency"):
        if isinstance(d.get(key), str) and len(d[key]) == 3:
            return d[key].upper()
    for key in ("totalPrice", "price", "priceRange"):
        nested = d.get(key)
        if isinstance(nested, dict):
            found = _currency(nested)
            if found:
                return found
    return None


def _image(value: Any) -> str | None:
    if isinstance(value, str):
        return value or None
    if isinstance(value, list) and value:
        return _image(value[0])
    if isinstance(value, dict):
        for key in ("url", "src", "originalSrc", "contentUrl"):
            if isinstance(value.get(key), str):
                return value[key]
    return None


def clean_text(value: Any, limit: int = 600) -> str | None:
    if not isinstance(value, str):
        return None
    text = _WS.sub(" ", _TAGS.sub(" ", htmllib.unescape(htmllib.unescape(value)))).strip()
    return text[:limit] or None


def _item(d: dict[str, Any], base: str, position: int) -> Item | None:
    title = next((d[k] for k in _NAME_KEYS if isinstance(d.get(k), str) and d[k].strip()), None)
    if not title:
        return None
    href = next((d[k] for k in ("redirectUrl", "url", "href") if isinstance(d.get(k), str)), None)
    slug = d.get("slug") or d.get("handle")
    if not href and slug:
        href = f"/products/{slug}"
    if not href and d.get("id") is not None:
        href = f"/products/{d['id']}"
    if not href:
        return None
    try:
        source_url = canonical(urljoin(base, href))
    except Exception:
        return None
    if not same_site(source_url, base):
        return None

    offers = d.get("offers")
    offer = offers[0] if isinstance(offers, list) and offers else offers
    price = _number(d.get("totalPrice")) or _number(d.get("price")) or _number(d.get("salePrice"))
    if price is None and isinstance(offer, dict):
        price = _number(offer.get("price"))
    if price is None:
        price = _number(d.get("priceRange"))

    unit = d.get("measurementUnit")
    unit = unit.strip().lower() if isinstance(unit, str) else unit
    units = _number(d.get("units") or d.get("pieces") or d.get("quantity") or d.get("pieceCount"))
    pieces = int(units) if units and unit in _PIECE_UNITS else None
    if pieces is None:
        match = _PIECES_IN_TEXT.search(title)
        pieces = int(match.group(1)) if match else None
    per_piece = _number(d.get("pricePerUnit"))
    if per_piece is None and price is not None and pieces:
        per_piece = price / pieces
    per_piece = round(per_piece, 2) if per_piece is not None else None

    discount = _number(d.get("priceDiscountPercentage"))
    compare = _number(d.get("compareAtPrice") or d.get("originalPrice"))
    if compare is None and price is not None and discount and 0 < discount < 100:
        compare = round(price / (1 - discount / 100), 2)

    stock = next(
        (d[k] for k in ("availableForSale", "inStock", "available") if isinstance(d.get(k), bool)),
        None,
    )
    if stock is None and isinstance(d.get("soldOut"), bool):
        stock = not d["soldOut"]
    if stock is None and isinstance(offer, dict) and isinstance(offer.get("availability"), str):
        stock = "instock" in offer["availability"].lower()

    brand = d.get("brand")
    attrs = {
        "position": position,
        "slug": slug,
        "units": units,
        "measurement_unit": unit,
        "discount_pct": discount,
        "brand": brand.get("name") if isinstance(brand, dict) else brand,
        "description": clean_text(d.get("body") or d.get("description")),
    }
    return Item(
        title=clean_text(title, 300) or title,
        source_url=source_url,
        external_id=str(d["id"]) if d.get("id") is not None else None,
        price=price,
        compare_at_price=compare,
        per_piece=per_piece,
        pieces=pieces,
        currency=_currency(d) or (_currency(offer) if isinstance(offer, dict) else None),
        image_url=_image(
            d.get("imageUrl") or d.get("image") or d.get("images") or d.get("featuredImage")
        ),
        in_stock=stock,
        attrs={k: v for k, v in attrs.items() if v not in (None, "")},
    )


# ---------------------------------------------------------------- listing


def _title(tree: HTMLParser, docs: list[Any]) -> str | None:
    for doc in docs:
        for node in _walk(doc):
            if (
                isinstance(node, dict)
                and str(node.get("@type", "")).lower() == "collectionpage"
                and isinstance(node.get("name"), str)
            ):
                return clean_text(node["name"], 200)
    og = tree.css_first('meta[property="og:title"]')
    if og and og.attributes.get("content"):
        return clean_text(og.attributes["content"], 200)
    node = tree.css_first("title")
    text = clean_text(node.text() if node else None, 200)
    return re.split(r"\s[|–-]\s", text)[0] if text else None


def _next_url(tree: HTMLParser, base: str) -> str | None:
    link = tree.css_first('link[rel="next"]')
    if link and link.attributes.get("href"):
        return urljoin(base, link.attributes["href"])
    current = int((parse_qs(urlsplit(base).query).get("page") or ["1"])[0] or 1)
    for a in tree.css("a[href]"):
        href = urljoin(base, a.attributes.get("href") or "")
        page = parse_qs(urlsplit(href).query).get("page")
        if page and page[0].isdigit() and int(page[0]) == current + 1:
            return href
    return None


def _anchor_items(tree: HTMLParser, base: str) -> list[Item]:
    """The fallback: product-looking links, titled from the image alt text or visible text."""
    for noisy in tree.css("style, script, noscript, template"):
        noisy.decompose()
    items: dict[str, Item] = {}
    for a in tree.css("a[href]"):
        href = urljoin(base, a.attributes.get("href") or "")
        if not _PRODUCT_PATH.search(urlsplit(href).path) or not same_site(href, base):
            continue
        img = a.css_first("img")
        title = (img.attributes.get("alt") if img else None) or a.attributes.get("aria-label")
        title = clean_text(title or a.text(separator=" "), 300)
        if not title:
            continue
        try:
            url = canonical(href)
        except Exception:
            continue
        items.setdefault(
            url,
            Item(
                title=title,
                source_url=url,
                image_url=img.attributes.get("src") if img else None,
                attrs={"position": len(items)},
            ),
        )
    return list(items.values())


def parse_listing(html: str, url: str) -> Listing:
    tree = HTMLParser(html)
    docs = _page_json(tree)
    lists = _product_lists(docs)
    items: list[Item] = []
    if lists:
        best = max(lists, key=len)
        seen: set[str] = set()
        for position, raw in enumerate(best):
            item = _item(raw, url, position)
            if item and item.source_url not in seen:
                seen.add(item.source_url)
                items.append(item)
    title = _title(tree, docs)
    total = _number(_find_key(docs, "totalItems"))
    next_url = _next_url(tree, url)
    if not items:
        items = _anchor_items(tree, url)
    return Listing(
        title=title, items=items, total_items=int(total) if total else None, next_url=next_url
    )


# ---------------------------------------------------------------- product page


def parse_product(html: str, url: str) -> ProductPage:
    """Details from a product page's JSON-LD. `@type` is matched case-insensitively
    because joinfleek writes `"product"`, and `offers[].type` is accepted beside `@type`."""
    tree = HTMLParser(html)
    page = ProductPage()
    for doc in _page_json(tree):
        for node in _walk(doc):
            if not isinstance(node, dict):
                continue
            kind = str(node.get("@type") or node.get("type") or "").lower()
            if kind == "product" and page.title is None:
                page.title = clean_text(node.get("name"), 300)
                page.description = clean_text(node.get("description"), 1200)
                brand = node.get("brand")
                page.brand = brand.get("name") if isinstance(brand, dict) else brand
                offers = node.get("offers")
                offer = offers[0] if isinstance(offers, list) and offers else offers
                if isinstance(offer, dict):
                    page.price = _number(offer.get("price"))
                    page.currency = offer.get("priceCurrency")
                    availability = offer.get("availability")
                    if isinstance(availability, str):
                        page.in_stock = "instock" in availability.lower()
            elif kind == "breadcrumblist" and not page.breadcrumbs:
                for element in node.get("itemListElement") or []:
                    name = element.get("name") or (element.get("item") or {}).get("name")
                    if isinstance(name, str) and name.strip():
                        page.breadcrumbs.append(name.strip())
    return page
