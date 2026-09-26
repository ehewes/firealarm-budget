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
- [ ] "Continue to Grok" opens a Grok prefill link carrying the session's `/brief` URL; Grok reads the Eden API over plain GETs
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

- Specs already written: `docs/ARCHITECTURE.md`, `docs/API.md`, `supabase/migrations/0001_init.sql`.
- `apps/api` exists (teammate, commit 263f9b6): most of the Phase 1 backend plus rules parsing/filtering. `apps/web` does not exist yet.
- Infra (teammate): team VPS behind Cloudflare Tunnel at `https://go.edenmatrix.xyz` (web at `/`, API at `/v1`), secrets in GitHub, deploy from `main` via CI. See `docs/DEPLOYMENT.md`, `docs/SECRETS.md`, `docs/LOCAL_DEV.md`.
- Sponsors / services: Bright Data (fetching), Jev (typed Choice/Score classification + ranking), Grok API (extraction, rule parsing), Grok Bot (conversational agent), agent card provider (stretch).

## Constraints

- **Timeline**: One day — favour working and simple over clever; work priorities top-down, no level started until the one above works end-to-end.
- **Tech stack**: Next.js App Router + TS + Tailwind + shadcn/ui (`apps/web`); FastAPI + Pydantic v2, async httpx (`apps/api`); Supabase Postgres/Auth/Realtime/Vault.
- **Security**: Card data never in any LLM prompt/response; nothing purchased without a confirmed intent from the signed-in owner; session code can never spend money; secrets only in `apps/api`.
- **Data integrity**: Prices, titles, images shown to users come from the DB, never model text; re-check price/stock before issuing a card (`409 price_changed`).
- **Scraping**: Allowlisted domains only; cache every page in `page_cache`.

## Key Decisions

Architecture decisions (REST not MCP, rules server-side, anonymous auth, session code as read-only key, purchases confirmed on Eden) live in `docs/ARCHITECTURE.md`. Decisions made during planning:

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Grok handoff via prefill link + GET-only `/brief` endpoint | Prefill only puts text in chat; Grok reads our data with its browsing tool, so reads must be unauthenticated GETs | — Pending |
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
