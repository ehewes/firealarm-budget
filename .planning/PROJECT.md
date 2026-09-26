# Eden Matrix

## What This Is

Prefix any store URL (`edenmatrix.com/<store-url>`) and Eden Matrix scrapes the page, classifies every product into a category tree, and exposes it through a public REST API. Grok Bot calls that API to recommend products within the user's own rules and, for signed-in users with a linked agent card, to buy them after explicit confirmation on Eden. Built in one day for the Cursor Commerce London Hackathon (Fleek HQ); demo store is `joinfleek.com`.

## Core Value

Prefixing a store URL produces a live category tree and a rules-filtered, ranked product list that Grok Bot can query over HTTP. If everything else fails, this must work.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Prefix route turns `edenmatrix.com/<url>` into a session and starts a background scrape
- [ ] Scrape fetches collection + product pages via Bright Data, extracts attributes, places products in a tree
- [ ] Live tree renders on the page as products arrive (Supabase Realtime)
- [ ] Public products endpoint returns compact, ranked items with a `why` per item
- [ ] Rules (plain language → structured) are applied server-side
- [ ] "Continue to Grok" hands the session code to Grok Bot, which calls the Eden API as tools
- [ ] Session page shows Grok's picks as preview cards rendered from the DB
- [ ] Anonymous auth for guests; sign-up keeps data; saved rulesets and past sessions
- [ ] (Stretch) Purchase intent → confirm on Eden → single-use card → checkout on dev store

### Out of Scope

- Multi-page collection crawling — page 1 only for the demo
- Arbitrary domains — allowlist only (`ALLOWED_DOMAINS`), SSRF risk
- Real-money purchases on Fleek — use Shopify dev store unless Fleek provides a test account
- MCP-first API — REST + OpenAPI first; wrap with `fastapi-mcp` only if Grok Bot requires it
- New infrastructure (Redis, Celery, queues) — one-day build

## Context

- Specs already written: `docs/ARCHITECTURE.md`, `docs/API.md`, `supabase/migrations/0001_init.sql`. `docs/PLAN.md` is currently a duplicate of ARCHITECTURE.md — day plan and demo script are missing.
- No application code yet: `apps/api` and `apps/web` do not exist.
- Team split: a teammate's agent is setting up infra in parallel — Cloudflare Tunnel (public URL for the local API so Grok Bot can reach it) and the Bright Data Web Unlocker zone. Code under `apps/` must not depend on that infra to make progress: fetching goes behind one `fetch(url) -> html` interface with a fixture fallback.
- Sponsors / services: Bright Data (fetching), Jev (typed Choice/Score classification + ranking), Grok API (extraction, rule parsing), Grok Bot (conversational agent), agent card provider (stretch).

## Constraints

- **Timeline**: One day — favour working and simple over clever; work priorities top-down, no level started until the one above works end-to-end.
- **Tech stack**: Next.js App Router + TS + Tailwind + shadcn/ui (`apps/web`); FastAPI + Pydantic v2, async httpx (`apps/api`); Supabase Postgres/Auth/Realtime/Vault.
- **Security**: Card data never in any LLM prompt/response; nothing purchased without a confirmed intent from the signed-in owner; session code can never spend money; secrets only in `apps/api`.
- **Data integrity**: Prices, titles, images shown to users come from the DB, never model text; re-check price/stock before issuing a card (`409 price_changed`).
- **Scraping**: Allowlisted domains only; cache every page in `page_cache`.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Public REST API, not MCP-first | Simpler to build/debug; auto OpenAPI for Grok | — Pending |
| Scrape is rule-independent | Scrape once per URL, rules are cheap query-time filters | — Pending |
| Rules applied server-side | Grok can't forget a rule; deterministic | — Pending |
| Supabase anonymous auth for guests | One code path; `is_anonymous` gates purchasing | — Pending |
| Session code = read-only capability | Codes appear in chat; never authorise spending | — Pending |
| Purchases confirmed on Eden, not in chat | LLM never interprets chat as payment authorisation | — Pending |
| Fetcher behind interface with fixture fallback | Unblocks API work while Bright Data/tunnel infra is set up by teammate | — Pending |
| Lean GSD: no research agents, coarse phases | Specs already exist; hackathon time budget | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-26 after initialization*
