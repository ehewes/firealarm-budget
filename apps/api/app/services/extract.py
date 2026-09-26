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

import contextlib
import html as htmllib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

from selectolax.parser import HTMLParser

from app.services.urls import canonical, same_site

_NAME_KEYS = ("title", "name", "productName", "family")
_PRICE_KEYS = (
    "totalPrice",
    "price",
    "pricePerUnit",
    "offers",
    "priceRange",
    "salePrice",
    "variants",
    "prices",
    "displayPrice",
)
_ID_KEYS = ("id", "slug", "handle", "url", "redirectUrl", "sku", "productId", "seo", "link")
_PIECE_UNITS = {None, "", "piece", "pieces", "pcs", "pc", "unit", "units", "item", "items"}
# Product URL shapes across common stores, checked on the path only:
#   /products/<slug> (Shopify, Fleek), /p/, /item/, /dp/ (Amazon), /prd/<id> (ASOS),
#   /itm/ (eBay), /listing/<id> (Etsy), /t/<slug>/<code> (Nike),
#   <slug>-p<digits>.html (Zara), productpage.<id>.html (H&M), <slug>-<6+ digits>(.html).
_PRODUCT_PATH = re.compile(
    r"/(?:products?|p|item|items|dp|pd|goods|prd|pdp|sku|itm|listing|product-detail)"
    r"/[^/?#]+(?:/[^/?#]+)?/?$"
    r"|-[pP]\d+(?:\.html)?/?$"
    r"|productpage\.\d+\.html$"
    r"|/t/[^/?#]+/[A-Za-z0-9-]+/?$"
    r"|/[a-z0-9][a-z0-9-]*-\d{6,}(?:\.html?)?/?$",
    re.IGNORECASE,
)
# Links that are never products, whatever their shape: the chrome around every store.
_NOT_PRODUCT = re.compile(
    r"/(?:cart|basket|bag|checkout|account|login|log-in|signin|sign-in|register|signup|wishlist|"
    r"help|faq|contact|about|stores?|store-locator|careers|legal|terms|privacy|cookies?|returns|"
    r"shipping|delivery|gift-?cards?|blog|news|press)(?:/|$|\.)",
    re.IGNORECASE,
)
_MONEY = re.compile(
    r"([£$€])\s?(\d[\d,]*(?:\.\d{1,2})?)|(\d[\d,]*(?:\.\d{1,2})?)\s?(GBP|EUR|USD)\b"
)
_SYMBOL_CURRENCY = {"£": "GBP", "$": "USD", "€": "EUR"}
# Inline scripts that hand the page its data: window.x = {...}, var x = [...], and so on.
_ASSIGNMENT = re.compile(r"(?:window\.[\w.$]+|(?:var|let|const)\s+[\w$]+)\s*=\s*(?=[{\[])")
_MAX_SCRIPT = 8_000_000
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
    image: str | None = None
    in_stock: bool | None = None
    description: str | None = None
    brand: str | None = None
    breadcrumbs: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- page JSON


def _page_json(tree: HTMLParser) -> list[Any]:
    """Every JSON document embedded in the page.

    JSON script tags (__NEXT_DATA__, JSON-LD, application/json state), plus objects that
    inline scripts assign (`window.zara.appConfig = {...}`, `var __STATE__ = {...}`),
    which is where stores that aren't built on Next.js tend to keep their data.
    """
    docs: list[Any] = []
    decoder = json.JSONDecoder()
    for node in tree.css("script"):
        text = node.text() or ""
        if not text.strip() or len(text) > _MAX_SCRIPT:
            continue
        kind = (node.attributes.get("type") or "").lower()
        if "json" in kind:
            with contextlib.suppress(json.JSONDecodeError):
                docs.append(json.loads(text))
            continue
        if kind and "javascript" not in kind:
            continue
        for found, match in enumerate(_ASSIGNMENT.finditer(text)):
            if found >= 5:
                break
            try:
                docs.append(decoder.raw_decode(text, match.end())[0])
            except (json.JSONDecodeError, ValueError):
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
            if isinstance(node, list) and len(node) >= 2:
                unwrapped = []
                for x in node:
                    if isinstance(x, dict) and "item" in x and isinstance(x["item"], dict):
                        unwrapped.append(x["item"])
                    else:
                        unwrapped.append(x)
                likes = [x for x in unwrapped if _product_like(x)]
                if len(likes) >= 0.5 * len(unwrapped):
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
        # A bare path is usually relative to a CDN we can't see (Zara's is), so only a full URL.
        path = value.get("path")
        if isinstance(path, str) and path.startswith(("https://", "http://", "//")):
            return path
    return None


def clean_text(value: Any, limit: int = 600) -> str | None:
    if not isinstance(value, str):
        return None
    text = _WS.sub(" ", _TAGS.sub(" ", htmllib.unescape(htmllib.unescape(value)))).strip()
    return text[:limit] or None


_ID_KEY = re.compile(r"(^id$|id$|sku|ref|code|keyword|slug|handle)", re.IGNORECASE)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _identifiers(d: dict[str, Any], title: str, depth: int = 0) -> set[str]:
    """Values that a store's own product link is likely to contain: ids, references, SEO
    keywords, slugs (one level of nesting deep, e.g. Zara's seo.seoProductId)."""
    found: set[str] = set()
    for key, value in d.items():
        if isinstance(value, dict) and depth < 1:
            found |= _identifiers(value, title, depth + 1)
        elif isinstance(value, str | int) and not isinstance(value, bool) and _ID_KEY.search(key):
            text = str(value).strip().lower()
            if len(text) >= 5:
                found.add(text)
            # References like "06085001-I2026" hold the code the URL uses; plain words don't
            # (splitting a slug would let "shirt" match every shirt on the page).
            for part in re.split(r"[-_/ ]", text):
                if len(part) >= 5 and re.search(r"\d", part):
                    found.add(part)
    if depth == 0:
        found.add(_slug(title))
    return found


def _match_link(ids: set[str], title: str, links: list[Item]) -> Item | None:
    """The page link for a product: one containing an identifier, else one whose slug holds
    every word of the title (Zara reorders words between its name and its URL)."""
    for link in links:
        path = urlsplit(link.source_url).path.lower()
        if any(i and i in path for i in ids):
            return link
    words = {w for w in re.findall(r"[a-z0-9]+", title.lower()) if len(w) >= 3}
    if len(words) >= 3:
        for link in links:
            if words <= set(re.findall(r"[a-z0-9]+", urlsplit(link.source_url).path.lower())):
                return link
    return None


def _item(
    d: dict[str, Any],
    base: str,
    position: int,
    links: list[Item] | None = None,
    divisor: int = 1,
) -> tuple[Item, Item | None] | None:
    """One product from page data, and the page link it matched (so it isn't listed twice)."""
    title = next((d[k] for k in _NAME_KEYS if isinstance(d.get(k), str) and d[k].strip()), None)
    if not title:
        return None
    links = links or []
    match = _match_link(_identifiers(d, title), title, links)
    href = next(
        (d[k] for k in ("redirectUrl", "url", "href", "link") if isinstance(d.get(k), str)), None
    )
    slug = d.get("slug") or d.get("handle")
    if not href and slug:
        href = f"/products/{slug}"
    if not href and match:
        href = match.source_url
    if not href and d.get("id") is not None and any("/products/" in x.source_url for x in links):
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
    raw_price = next(
        (d[k] for k in ("totalPrice", "price", "salePrice") if d.get(k) not in (None, "")), None
    )
    variants = d.get("variants")
    if raw_price is None and isinstance(variants, list) and variants:
        raw_price = variants[0].get("price") if isinstance(variants[0], dict) else None
    price = _number(raw_price)
    if price is None and isinstance(offer, dict):
        price = _number(offer.get("price")) or _number(offer.get("lowPrice"))
    if price is None:
        price = _number(d.get("priceRange")) or _number(d.get("displayPrice"))
    if price is not None and divisor > 1 and isinstance(raw_price, int):
        # Minor units (pence, cents), as Zara ships them with currencyDecimals -2.
        price = round(price / divisor, 2)

    unit = d.get("measurementUnit")
    unit = unit.strip().lower() if isinstance(unit, str) else unit
    units = _number(d.get("units") or d.get("pieces") or d.get("quantity") or d.get("pieceCount"))
    pieces = int(units) if units and unit in _PIECE_UNITS else None
    if pieces is None:
        in_title = _PIECES_IN_TEXT.search(title)
        pieces = int(in_title.group(1)) if in_title else None
    per_piece = _number(d.get("pricePerUnit"))
    if per_piece is None and price is not None:
        # A bundle's price split by its pieces; an ordinary retail item is one piece.
        per_piece = price / pieces if pieces else price
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
    if stock is None and isinstance(d.get("availability"), str):
        flag = d["availability"].lower().replace("_", "").replace("-", "")
        stock = flag in ("instock", "available") or None if "out" not in flag else False

    brand = d.get("brand")
    attrs = {
        "position": position,
        "slug": slug,
        "units": units,
        "measurement_unit": unit,
        "discount_pct": discount,
        "brand": brand.get("name") if isinstance(brand, dict) else brand,
        "category": d.get("familyName") or d.get("category") or d.get("productType"),
        "description": clean_text(d.get("body") or d.get("description")),
    }
    item = Item(
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
        attrs={k: v for k, v in attrs.items() if v not in (None, "") and not isinstance(v, dict)},
    )
    if item.image_url is None and match is not None:
        item.image_url = match.image_url
    return item, match


def _page_currency(docs: list[Any]) -> str | None:
    """The currency the page declares anywhere (JSON-LD offers, store config)."""
    for key in ("priceCurrency", "currencyCode"):
        value = _find_key(docs, key)
        if isinstance(value, str) and len(value) == 3:
            return value.upper()
    return None


def _price_divisor(docs: list[Any]) -> int:
    """100 when the page declares two-decimal minor units (Zara: currencyDecimals -2)."""
    value = _find_key(docs, "currencyDecimals")
    return 100 if isinstance(value, int) and abs(value) == 2 else 1


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


def humanize(title: str) -> str:
    """`textured-checks-shirt` -> `Textured checks shirt`. Real titles pass through untouched."""
    if " " in title.strip() or not re.search(r"[-_]", title):
        return title
    words = re.sub(r"[-_]+", " ", title).strip()
    return words[:1].upper() + words[1:]


def _link_title(a: Any) -> str | None:
    """A link's product name: its image's alt text, its label, a heading in it, or its text."""
    img = a.css_first("img")
    title = (img.attributes.get("alt") if img else None) or a.attributes.get("aria-label")
    if not title:
        for heading in a.css("h1, h2, h3, h4, [class*='title'], [class*='name']"):
            text = heading.text(separator=" ").strip()
            if len(text) > 3:
                title = text
                break
    title = clean_text(title or a.text(separator=" "), 300)
    return humanize(title) if title else None


def _img_src(img: Any) -> str | None:
    """The picture an <img> shows, including lazy-loaded ones that keep it in data-* or srcset
    behind a data: placeholder."""
    if img is None:
        return None
    for key in ("src", "data-src", "data-original", "data-lazy-src"):
        value = img.attributes.get(key)
        if value and not value.startswith("data:"):
            return value
    srcset = (img.attributes.get("srcset") or img.attributes.get("data-srcset") or "").strip()
    first = srcset.split(",")[0].split()
    return first[0] if first else None


def _product_url(a: Any, base: str, cache: dict[str, str | None]) -> str | None:
    """The canonical product URL a link opens, or None when it isn't a product link."""
    raw = a.attributes.get("href") or ""
    if raw not in cache:
        href = urljoin(base, raw)
        path = urlsplit(href).path
        url = None
        if _PRODUCT_PATH.search(path) and not _NOT_PRODUCT.search(path) and same_site(href, base):
            with contextlib.suppress(Exception):
                url = canonical(href)
        cache[raw] = url
    return cache[raw]


def _tile(a: Any, url: str, base: str, cache: dict[str, str | None]) -> Any:
    """The product's own card: the link, or the largest ancestor (three levels at most) that
    holds no other product. Above that is the grid, where the first price is someone else's."""
    tile = a
    for _ in range(3):
        parent = tile.parent
        if parent is None or any(
            _product_url(x, base, cache) not in (None, url) for x in parent.css("a[href]")
        ):
            break
        tile = parent
    return tile


def _price_in(node: Any) -> tuple[float | None, str | None]:
    match = _MONEY.search((node.text(separator=" ") or "")[:600])
    if not match:
        return None, None
    if match.group(1):
        return _number(match.group(2)), _SYMBOL_CURRENCY.get(match.group(1))
    return _number(match.group(3)), match.group(4).upper()


def _clean_tree(html: str) -> HTMLParser:
    tree = HTMLParser(html)
    for noisy in tree.css("style, script, noscript, template"):
        noisy.decompose()
    return tree


def _anchor_items(tree: HTMLParser, base: str) -> list[Item]:
    """Product-looking links, titled from alt text or headings, priced from their own tile."""
    items: dict[str, Item] = {}
    cache: dict[str, str | None] = {}
    for a in tree.css("a[href]"):
        url = _product_url(a, base, cache)
        if url is None or url in items:
            continue
        title = _link_title(a)
        if not title:
            continue
        tile = _tile(a, url, base, cache)
        price, currency = _price_in(tile)
        in_title = _PIECES_IN_TEXT.search(title)
        pieces = int(in_title.group(1)) if in_title else None
        image = _img_src(a.css_first("img") or tile.css_first("img"))
        items[url] = Item(
            title=title,
            source_url=url,
            price=price,
            per_piece=round(price / pieces, 2) if price is not None and pieces else price,
            pieces=pieces,
            currency=currency,
            image_url=urljoin(base, image) if image else None,
            attrs={"position": len(items)},
        )
    return list(items.values())


def candidate_links(html: str, base: str, limit: int = 60) -> list[tuple[str, str]]:
    """Same-site links with readable text that might be products, for Jev to judge.

    Used when a store's product URLs match none of the known shapes: the store chrome
    (cart, account, help, policies) is dropped here so Jev only sees plausible links.
    """
    tree = _clean_tree(html)
    seen: dict[str, str] = {}
    for a in tree.css("a[href]"):
        href = urljoin(base, a.attributes.get("href") or "")
        path = urlsplit(href).path
        if not same_site(href, base) or _NOT_PRODUCT.search(path) or path in ("", "/"):
            continue
        title = _link_title(a)
        if not title or len(title) < 4:
            continue
        try:
            url = canonical(href)
        except Exception:
            continue
        if url != canonical(base):
            seen.setdefault(url, title)
        if len(seen) >= limit:
            break
    return list(seen.items())


def parse_listing(html: str, url: str) -> Listing:
    """Products from the page's own data where it has any, plus every product-looking link
    it didn't cover. Data gives names and prices; links catch what the data left out."""
    tree = HTMLParser(html)
    docs = _page_json(tree)
    links = _anchor_items(_clean_tree(html), url)
    divisor = _price_divisor(docs)
    lists = _product_lists(docs)
    items: list[Item] = []
    seen: set[str] = set()
    used: set[str] = set()
    if lists:
        best = max(lists, key=len)
        for position, raw in enumerate(best):
            built = _item(raw, url, position, links, divisor)
            if built is None:
                continue
            item, match = built
            if match is not None:
                used.add(match.source_url)
            if item.source_url not in seen:
                seen.add(item.source_url)
                items.append(item)
    for link in links:
        if link.source_url not in seen and link.source_url not in used:
            link.attrs["position"] = len(items)
            seen.add(link.source_url)
            items.append(link)
    currency = _page_currency(docs)
    for item in items:
        if item.price is not None and item.currency is None:
            item.currency = currency
    title = _title(tree, docs)
    total = _number(_find_key(docs, "totalItems"))
    next_url = _next_url(tree, url)
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
                page.image = _image(node.get("image"))
                if isinstance(offer, dict):
                    spec = offer.get("priceSpecification")
                    page.price = (
                        _number(offer.get("price"))
                        or _number(offer.get("lowPrice"))
                        or (_number(spec.get("price")) if isinstance(spec, dict) else None)
                    )
                    page.currency = offer.get("priceCurrency")
                    availability = offer.get("availability")
                    if isinstance(availability, str):
                        page.in_stock = "instock" in availability.lower()
            elif kind == "breadcrumblist" and not page.breadcrumbs:
                for element in node.get("itemListElement") or []:
                    name = element.get("name") or (element.get("item") or {}).get("name")
                    if isinstance(name, str) and name.strip():
                        page.breadcrumbs.append(name.strip())
    # Open Graph product tags: many stores set these even without JSON-LD.
    if page.price is None:
        tag = tree.css_first(
            'meta[property="product:price:amount"], meta[property="og:price:amount"]'
        )
        page.price = _number(tag.attributes.get("content")) if tag else None
    if page.currency is None:
        tag = tree.css_first(
            'meta[property="product:price:currency"], meta[property="og:price:currency"]'
        )
        page.currency = tag.attributes.get("content") if tag else None
    if page.title is None:
        og = tree.css_first('meta[property="og:title"]')
        page.title = clean_text(og.attributes.get("content"), 300) if og else None
    return page
