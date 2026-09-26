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
