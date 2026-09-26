# Requirements: Eden Matrix

**Defined:** 2026-09-26
**Core Value:** Prefixing a store URL produces a live category tree and a rules-filtered, ranked product list that Grok Bot can query over HTTP.

## v1 Requirements

### Scraping

- [ ] **SCRP-01**: API rejects any URL whose domain is not in `ALLOWED_DOMAINS` with `400 domain_not_allowed`
- [ ] **SCRP-02**: Scraper fetches pages through one `fetch(url) -> html` interface backed by Bright Data Web Unlocker, with a local fixture fallback when no key is configured
- [ ] **SCRP-03**: Every fetched page is cached in `page_cache` and not re-fetched within a session
- [ ] **SCRP-04**: Scraper parses product links from page 1 of a collection and fetches product pages concurrently (semaphore, `SCRAPE_CONCURRENCY`)
- [ ] **SCRP-05**: Each product has structured attributes (title, price, pieces, per-piece price, grade, sizes, image, source URL) extracted via the Grok API
- [ ] **SCRP-06**: Each product is placed in a category tree (category → type → tier) via Jev
- [ ] **SCRP-07**: Scrape progress is written to `scrapes.status` and products are upserted as they complete

### Public API

- [ ] **API-01**: `POST /v1/sessions` creates a session and returns `202` with `code`, `status`, `session_url` before the scrape finishes
- [ ] **API-02**: `GET /v1/sessions/{code}` returns store, collection, status, product count, rules, `can_purchase`
- [ ] **API-03**: `GET /v1/sessions/{code}/tree` returns the category tree with counts
- [ ] **API-04**: `GET /v1/sessions/{code}/products` returns ranked items (default `limit=10`, max 25) with a `why` per item and `session_url`, and records them as picks
- [ ] **API-05**: `GET /v1/sessions/{code}/products/{id}` returns full product detail including `attrs`
- [ ] **API-06**: Errors use `{"error": {"code", "message"}}` with codes from `docs/API.md`
- [ ] **API-07**: OpenAPI spec at `/openapi.json` has clear field names and descriptions for Grok to consume
- [ ] **API-08**: `GET /v1/sessions/{code}/brief` returns one plain-text/markdown summary (store, rules, scrape status, top picks with `why`, links to filtered `/products` URLs); while `crawling` it returns partial results plus a retry hint
- [ ] **API-09**: Every Grok-facing endpoint is a plain `GET` with the code in the path, no auth header, and `Cache-Control: no-store`, so Grok's browsing tool can read it from a prefill link

### Web

- [ ] **WEB-01**: Visiting `/<store-url>` normalises `https:/` → `https://`, creates a session, and shows the building tree
- [ ] **WEB-02**: Tree updates live via Supabase Realtime on `products` filtered by `scrape_id`

### Rules & Grok

- [ ] **RULE-01**: `POST /v1/rules/parse` turns plain-language text into a structured rules object
- [ ] **RULE-02**: Continue page lets the user add rules shown as removable chips; rules are stored on the session
- [ ] **RULE-03**: Products endpoint applies hard-filter rules server-side and scores `notes` via Jev
- [ ] **GROK-01**: "Continue to Grok" opens Grok Bot with the session code, and Grok can call the Eden API as tools
- [ ] **GROK-02**: Grok's recommendations match the user's rules end-to-end in a live demo

### Sessions & Accounts

- [ ] **SESS-01**: Session page `/s/{code}` shows picks as preview cards rendered from the DB
- [ ] **AUTH-01**: Guest gets anonymous Supabase auth on first visit; guest rules persist on the device
- [ ] **AUTH-02**: User can sign up and keep anonymous data (`linkIdentity` / `updateUser`)
- [ ] **SESS-02**: Signed-in user can save, edit, delete rulesets
- [ ] **SESS-03**: Signed-in user can view past sessions in the dashboard

### Purchasing (stretch)

- [ ] **BUY-01**: `POST /v1/sessions/{code}/purchase-intents` creates a pending intent with quoted total and `confirm_url`; returns `403 purchase_not_allowed` for anonymous owners or no linked card
- [ ] **BUY-02**: Confirm page `/confirm/{id}` shows items, total, merchant, card limit; only the signed-in owner can confirm
- [ ] **BUY-03**: Confirm re-checks price and stock; on change returns `409 price_changed` and requires re-confirmation
- [ ] **BUY-04**: Confirm issues a single-use card locked to amount + merchant; card details never enter any LLM context
- [ ] **BUY-05**: Playwright completes checkout on the dev store and the receipt is stored

## v2 Requirements

- **SCRP-08**: Multi-page collection crawling
- **API-10**: `POST /v1/sessions/{code}/products/{id}/refresh` exposed to Grok
- **API-11**: Rate limiting on `POST /v1/sessions` per IP / user
- **GROK-03**: MCP wrapper (`fastapi-mcp`) if Grok Bot requires MCP

## Out of Scope

| Feature | Reason |
|---------|--------|
| Arbitrary (non-allowlisted) domains | SSRF and abuse risk |
| Real-money checkout on Fleek | No test account yet; use Shopify dev store |
| Redis / Celery / queues | One-day build; `BackgroundTasks` is enough |
| Purchase authorisation in chat | LLM must never interpret chat as payment consent |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SCRP-01..07 | Phase 1 | Pending |
| API-01..09 | Phase 1 | Pending |
| WEB-01..02 | Phase 1 | Pending |
| RULE-01..03 | Phase 2 | Pending |
| GROK-01..02 | Phase 2 | Pending |
| SESS-01..03 | Phase 3 | Pending |
| AUTH-01..02 | Phase 3 | Pending |
| BUY-01..05 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0

---
*Requirements defined: 2026-09-26*
*Last updated: 2026-09-26 after adding Grok prefill handoff requirements (API-08, API-09)*
