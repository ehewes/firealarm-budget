# Database

Hosted Supabase (Postgres 17). The data model is described in [PLAN.md](PLAN.md) (Data model); this page is
about how the schema changes and what each migration added.

## Migrations

`supabase/migrations/` is the only source of truth, applied in filename order:

| Migration | What it holds |
| --- | --- |
| `0001_init.sql` | The core schema: scrapes, products, page cache, sessions, session picks, rulesets, card links, purchase intents, RLS, Realtime for the live tree |
| `0002_entry_and_limits.sql` | Session entry gate and abuse fields, one default ruleset per user, monthly spend counters |

Rules:

- **Additive only.** Never edit or rename an applied migration. Add the next number (`0003_…`).
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
