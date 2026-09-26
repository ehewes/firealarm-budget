# Eden API reference (v1)

Base URL: `https://api.edenmatrix.com/v1` (local: `http://localhost:8000/v1`)
Interactive docs / OpenAPI: `/docs`, `/openapi.json`

Responses are deliberately compact — the main consumer is an LLM agent.

## Authentication

| Caller | How | Can do |
|---|---|---|
| Anyone with a session code | Code in the path | Read that session's data, create purchase intents (only succeeds if the owner is signed in with a card) |
| Eden web app | `Authorization: Bearer <Supabase JWT>` (anonymous or signed-in) | Create sessions, manage own rulesets |
| Signed-in user | Bearer JWT where `is_anonymous = false` | Link card, confirm purchases |

## Rules object

```json
{
  "max_per_piece": 14.0,
  "max_total": 600.0,
  "min_pieces": 20,
  "grades": ["premium"],
  "include_categories": ["bottoms"],
  "exclude_categories": ["shorts"],
  "notes": ["prefer baggy fits"]
}
```

All fields optional. `notes` are free-text preferences scored by Jev; everything else is a hard filter.

## Endpoints

### `POST /sessions`

Create a session and start scraping (returns before the scrape finishes).

**Auth:** Bearer JWT (anonymous OK). **Rate limited.**

```json
// request
{ "url": "https://www.joinfleek.com/collections/nike", "rules": { "max_per_piece": 14 }, "ruleset_id": null }

// 202
{
  "code": "EM-7K2Q9X4M",
  "status": "crawling",
  "session_url": "https://www.edenmatrix.com/s/EM-7K2Q9X4M",
  "grok_url": "https://…"
}
```

### `GET /sessions/{code}`

```json
{
  "code": "EM-7K2Q9X4M",
  "store": "joinfleek.com",
  "collection": "Nike Vintage Wholesale",
  "status": "ready",
  "product_count": 25,
  "snapshot_at": "2026-09-26T10:14:00Z",
  "rules": { "max_per_piece": 14, "grades": ["premium"] },
  "can_purchase": false
}
```

### `GET /sessions/{code}/brief`

Entry point for Grok. The "Continue to Grok" button opens a Grok prefill link whose message contains this URL, and Grok reads it with its browsing tool. Returns `text/markdown`: store, collection, rules, scrape status, the top picks with `why`, and links to filtered `/products` URLs for digging further. While the scrape is still `crawling`, it returns whatever products are ready plus a retry hint.

```
# Eden session EM-7K2Q9X4M — joinfleek.com / Nike Vintage Wholesale
Status: ready · 25 products · rules: max $14/pc, premium only

1. Premium Vintage Nike Baggy Pants — $128.00 (10 pcs, $12.78/pc)
   Why: Premium grade; $12.78/pc under your $14 cap
   https://www.joinfleek.com/products/…

More: https://api.edenmatrix.com/v1/sessions/EM-7K2Q9X4M/products?category=bottoms
Session page: https://www.edenmatrix.com/s/EM-7K2Q9X4M
```

All Grok-facing endpoints (`/brief`, `GET /sessions/{code}`, `/tree`, `/products`, `/products/{id}`) are plain `GET`s with the code in the path, need no auth header, and send `Cache-Control: no-store`, so a browsing tool can read them.

### `GET /sessions/{code}/tree`

```json
{ "tree": [ { "name": "bottoms", "count": 18, "children": [ { "name": "trackpants", "count": 9 } ] } ] }
```

### `GET /sessions/{code}/products`

Ranked products with session rules applied.

Query: `q`, `category`, `max_per_piece`, `limit` (default 10, max 25).

```json
{
  "items": [
    {
      "id": "b1c…",
      "title": "Premium Vintage Nike Baggy Pants",
      "price": 128.0,
      "per_piece": 12.78,
      "pieces": 10,
      "currency": "USD",
      "tree_path": ["bottoms", "baggy pants", "premium"],
      "image_url": "https://…",
      "source_url": "https://www.joinfleek.com/products/…",
      "why": "Premium grade; $12.78/pc under your $14 cap"
    }
  ],
  "session_url": "https://www.edenmatrix.com/s/EM-7K2Q9X4M"
}
```

Items returned here are recorded as the session's picks.

### `GET /sessions/{code}/products/{id}`

Full product detail including `attrs`.

### `POST /sessions/{code}/products/{id}/refresh`

Re-fetch price and stock. Returns the product plus `"changed": { "price": [129.0, 141.0] }` if anything moved.

### `POST /sessions/{code}/purchase-intents`

```json
// request
{ "product_ids": ["b1c…", "d4e…"] }

// 201
{ "intent_id": "…", "quoted_total": 256.0, "confirm_url": "https://www.edenmatrix.com/confirm/…" }
```

Never charges anything. Fails with `403 purchase_not_allowed` if the session owner is anonymous or has no linked card — Grok should tell the user to sign in on Eden.

### `POST /purchase-intents/{id}/confirm`

**Auth:** signed-in owner only. Re-checks prices; if changed, returns `409 price_changed` with the new total. Otherwise issues the single-use card and starts checkout.

```json
{ "status": "executing", "card": { "last4": "4417", "limit": 270.0, "merchant": "joinfleek.com", "expires_at": "…" } }
```

### `GET /purchase-intents/{id}`

Status: `pending | confirmed | executing | completed | failed | cancelled | price_changed`.

### Rulesets (signed-in or anonymous JWT)

`GET /rulesets` · `POST /rulesets` · `PATCH /rulesets/{id}` · `DELETE /rulesets/{id}`

`POST /rules/parse` — `{ "text": "premium only under 14 a piece" }` → rules object.

## Errors

```json
{ "error": { "code": "domain_not_allowed", "message": "…" } }
```

| Status | Code |
|---|---|
| 400 | `invalid_url`, `domain_not_allowed` |
| 401 | `unauthenticated` |
| 403 | `purchase_not_allowed`, `not_owner` |
| 404 | `session_not_found`, `session_expired` |
| 409 | `price_changed`, `out_of_stock` |
| 429 | `rate_limited` |
| 502 | `scrape_failed` |

## As implemented (`apps/api`)

Everything above is implemented except purchase intents (the stretch goal). This section records the
details the reference leaves open.

- **Base URL:** `https://go.edenmatrix.xyz/v1` in production (same host as the web app, see
  [DEPLOYMENT.md](DEPLOYMENT.md)); `http://localhost:8000/v1` locally. `GET /v1/health` (liveness) and
  `GET /v1/ready` (database reachable).
- **`POST /sessions`** also takes `entry` (`prefix` | `widget`) and `referrer_origin` (widget only), and returns
  `scrape_id` so the web app can subscribe to `products` over Realtime for the live tree. The URL may arrive with
  `https:/` (collapsed slashes) or without a scheme; tracking parameters such as joinfleek's `click_source` are
  stripped. A scrape of the same page from the last `SCRAPE_FRESH_MINUTES` is shared instead of re-fetched.
- **Scrape pipeline** (`services/scraper.py`, a `BackgroundTask`):
  1. `crawling`: fetch the listing through Bright Data Web Unlocker. Products are extracted from the page's own
     JSON (joinfleek's `__NEXT_DATA__` items, including `units` and `pricePerUnit`) and inserted at once with a
     keyword placement, so the live tree fills immediately.
  2. Up to `MAX_PRODUCT_PAGES` product pages add brand, breadcrumbs and stock.
  3. `classifying`: Jev places each product in the fixed tree, level by level: category, then type, then tier
     (`premium` or `standard`). When Jev is unsure, the keyword placement stays.
  4. `ready`.
- **Tree:** the fixed taxonomy lives in `services/taxonomy.py`: tops, bottoms, outerwear, dresses, footwear,
  accessories, mixed, each with its types.
- **Rules** (`services/rules.py`) are applied in code. A product that can't be checked against a hard filter
  (for example, no per-piece price under a `max_per_piece` rule) is excluded. `notes` rank the matches using Jev
  yes/no scores, cached per session; without Jev, matches are ordered cheapest per piece. `why` is built only
  from stored fields.
- **`POST /rules/parse`** uses the Grok API when `GROK_API_KEY` is set. Otherwise it uses a deterministic parser
  for phrasings like "premium only, under $14/piece, no shorts, at least 20 pieces".
- **Limits:**
  - `SESSIONS_PER_HOUR_PER_IP` / `SESSIONS_PER_HOUR_PER_USER` on `POST /sessions`, returning `429 rate_limited`.
  - Monthly `SCRAPE_MONTHLY_MAX` (Bright Data fetches, default 5000) and `JEV_MONTHLY_BUDGET_USD` (default $5),
    counted in `usage_counters`. Past the scrape cap, new scrapes get `503 budget_exhausted`; past the Jev budget,
    classification and ranking fall back to keywords and price.
- **Extra error codes:** `503 budget_exhausted`, `404 product_not_found`, `404 ruleset_not_found`.
- **Auth:** Supabase JWTs (anonymous included) are verified against the project's JWKS (ES256/RS256), or against
  `SUPABASE_JWT_SECRET` for legacy HS256 projects.
