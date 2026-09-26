# Database

Hosted Supabase (Postgres 17). The data model is described in [ARCHITECTURE.md](ARCHITECTURE.md) (Data model); this page is
about how the schema changes and what each migration added.

## Migrations

`supabase/migrations/` is the only source of truth, applied in filename order:

| Migration | What it holds |
| --- | --- |
| `0001_init.sql` | The core schema: scrapes, products, page cache, sessions, session picks, rulesets, card links, purchase intents, RLS, Realtime for the live tree |
| `0002_entry_and_limits.sql` | Session entry gate and abuse fields, one default ruleset per user, monthly spend counters |
| `0003_scrape_title_and_usage_fn.sql` | `scrapes.title` and `scrapes.updated_at`, and the `increment_usage` function |
| `0004_agents_and_demo_cards.sql` | Agent tokens, Grok Bot webhooks, and the card and purchase fields the demo card flow shows |

Rules:

- **Additive only.** Never edit or rename an applied migration. Add the next number (`0004_…`).
- **Stay compatible with the running version.** Deploys migrate before new images start, so for a few seconds
  the old API runs against the new schema. Add columns with defaults; drop things in a later release.
- **Prove it applies from scratch** with `make db-reset` before opening the PR.
- In production, the deploy workflow runs `supabase db push` (see [DEPLOYMENT.md](DEPLOYMENT.md)).
- If a migration was ever applied by hand in the Supabase SQL editor, tell the CLI before the next push, or
  it will try to apply it again: `npx supabase@2 migration repair --status applied 0001`.

## What 0002 added

**`sessions.entry`** (`prefix` or `widget`): which way the shopper came in. `prefix` is our domain in front of a
store URL. `widget` is a vendor's embedded "Continue in Eden Matrix" button, which sends the shopper to us with
the page they were on.

**`sessions.referrer_origin` / `origin_verified`**: for widget sessions, the origin the browser reported and
whether it matches the store URL. This is recorded, not enforced. A browser sends the Referer, but anything else
can forge it, so `origin_verified` means "the Referer matched", not "proven".

**`sessions.requester_ip_hash`**: a keyed hash of the requester's IP (never the address), indexed with
`created_at` so the API can count a requester's recent sessions for the rate limit on `POST /v1/sessions`.

**`rulesets_one_default`**: at most one `is_default` ruleset per user, so "the user's rules" is unambiguous.

**`usage_counters`**: monthly spend, one row per `(period, key)`:

| Key | Counts | Cap |
| --- | --- | --- |
| `scrapes` | Bright Data page fetches | `SCRAPE_MONTHLY_MAX` (5000) |
| `jev_usd` | Jev cost as reported by the provider | `JEV_MONTHLY_BUDGET_USD` (5) |

Increment atomically with an upsert, and check before every paid call:

```sql
insert into public.usage_counters (period, key, amount)
values (date_trunc('month', now())::date, 'scrapes', 1)
on conflict (period, key) do update set amount = public.usage_counters.amount + excluded.amount
returning amount;
```

RLS is on with no policies, so only the API (service role) can read or write it.

## What 0003 added

**`scrapes.title`**: the listing page's title ("Nike Vintage Wholesale"), returned as `collection` by
`GET /v1/sessions/{code}`.

**`scrapes.updated_at`**: bumped at every pipeline step. Scrapes run inside the API process, so a restart kills
any in flight. On startup the API marks scrapes still `pending`, `crawling` or `classifying` with no progress
for 10 minutes as `failed`, so no session page waits forever.

**`increment_usage(key, amount)`**: adds to this month's counter and returns the new total in one statement,
callable over the REST API by the service role only. The API calls it before every Bright Data fetch and after
every Jev decision.

## What 0004 added

**`agent_links`**: the tokens a shopper's agent (Grok Bot) sends to `/v1/mcp`. Only the token's SHA-256
(`token_hash`) and its last four characters (`token_hint`) are stored; the token itself is shown once. Revoking
sets `revoked_at`. The owner can read their own rows; everything else goes through the API.

**`bot_webhooks`**: one per user, the URL and key of their Grok Bot automation ("When a webhook fires"), where
Send to Grok Bot posts a session. The key is a credential for the shopper's bot, so the table has RLS on and no
policies: only the service role can read it.

**`card_links.label`, `last4`, `currency`, `updated_at`**: what the dashboard and confirm page show. Card numbers
are never stored. The demo provider holds no credentials, so its `credential_ref` points at no Vault secret.

**`purchase_intents.merchant`, `currency`, `agent_link_id`, `card_limit`, `order_ref`, `completed_at`,
`updated_at`**: the store, which agent asked, the issued card's limit, and the demo checkout's outcome. Statuses
are 0001's: `pending`, then `price_changed` or `executing` (card issued), then `completed`, `failed` or
`cancelled`.
