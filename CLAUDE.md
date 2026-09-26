# CLAUDE.md

Context for AI coding assistants working in this repo. Read this before making changes.

## What this is

Eden Matrix: prefix any store URL (`edenmatrix.com/<store-url>`) → we scrape it, classify products into a tree, and expose it through a public REST API that Grok Bot calls to recommend and (for signed-in users) buy within the user's rules. One-day hackathon build — favour working and simple over clever.

Full detail: `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/PLAN.md`.

## Layout

- `apps/web` — Next.js App Router, TypeScript, Tailwind, shadcn/ui
- `apps/api` — FastAPI, Python 3.11+, Pydantic v2
- `supabase/migrations` — SQL schema + RLS (source of truth for the data model)

## Commands

```bash
# api
cd apps/api && uvicorn app.main:app --reload --port 8000
cd apps/api && pytest

# web
cd apps/web && npm run dev
cd apps/web && npm run lint && npm run build

# db
supabase db push
```

## Non-negotiable rules

1. **Never put card numbers or card-provider credentials in any LLM prompt or response.** Code fetches and fills card details; Grok only sees "card_ready".
2. **Nothing is purchased without a confirmed `purchase_intent`**, confirmed by the signed-in owner (`is_anonymous = false`) via the Eden confirm page. No endpoint callable with just a session code may spend money.
3. **Prices, titles and images shown to users come from the database**, never from model-generated text.
4. **Re-check price and stock before issuing a card.** On change → `409 price_changed`, require re-confirmation.
5. **Only scrape allowlisted domains** (`ALLOWED_DOMAINS`). Never fetch arbitrary user-supplied URLs.
6. **Service role key, Bright Data, Jev, Grok and card keys live only in `apps/api`.** The web app uses the anon key and `NEXT_PUBLIC_*` vars only.
7. **Rules are applied server-side** in the products endpoint, not left to Grok.

## Conventions

**API (Python)**
- Routers in `app/routers/`, services in `app/services/` (`scraper.py`, `extract.py`, `jev.py`, `rules.py`, `purchases.py`).
- Pydantic models for every request/response; they generate the OpenAPI spec that Grok consumes, so keep field names and descriptions clear.
- Async everywhere; `httpx.AsyncClient`; concurrency via `asyncio.Semaphore`.
- Long work (scrapes) in `BackgroundTasks`; write progress to `scrapes.status`.
- Errors: raise `EdenError(code, message, status)` → `{"error": {"code", "message"}}`. Codes listed in `docs/API.md`.
- Cache every fetched page in `page_cache`; don't re-fetch within a session unless `/refresh` is called.
- Keep agent-facing responses compact: default `limit=10`, include a `why` per product and `session_url`.

**Web (TypeScript)**
- Catch-all prefix route: `app/[...url]/page.tsx`. Normalise `https:/` → `https://` before calling the API.
- Session page `app/s/[code]/page.tsx`; confirm page `app/confirm/[id]/page.tsx`; dashboard under `app/dashboard/`.
- Supabase client: anonymous sign-in on first visit if no session; `linkIdentity`/`updateUser` on sign-up to keep data.
- Subscribe to Realtime on `products` filtered by `scrape_id` for the live tree.
- Server components by default; client components only for interactivity.

**Both**
- Small, focused commits. Don't add dependencies without a clear need.
- No new infrastructure (no Redis, Celery, queues) — it's a one-day build.

## Current priority

Work top-down; don't start a level until the one above works end-to-end.
1. Prefix → scrape → tree → products endpoint
2. Rules + Grok Bot handoff + recommendations
3. Session page, anonymous auth, saved rulesets, past sessions
4. Purchase intents → confirm → card → checkout (dev store)
