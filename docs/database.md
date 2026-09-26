# Database

Hosted Supabase (Postgres 17). The schema lives only in `supabase/migrations/`, applied in filename order:

| Migration | What it holds |
| --- | --- |
| `0001_init.sql` | D1K03's original schema: scrapes, products, page cache, sessions, picks, rulesets, card links, purchase intents, RLS, Realtime |
| `0002_go_pipeline.sql` | The job queue, crawl progress, pages visited, session entry gate and abuse fields, spend counters |

## Tables

| Table | Holds | Written by |
| --- | --- | --- |
| `scrapes` | One fetch of a requested URL: status, product count, title, summary, crawl progress | api (creates), scraper (fills) |
| `scrape_pages` | Every page a scrape visited, with depth, who chose it, and its classified links | scraper |
| `products` | Items extracted from a scrape's pages: title, price, image, external id, category path | scraper |
| `page_cache` | Raw HTML by URL, so a recent page is not fetched twice | scraper |
| `sessions` | A shopper's public view of a scrape: code, rule snapshot, entry gate, expiry (24 h) | api |
| `session_picks` | Products that passed a session's rule, ranked, with the reason | scraper |
| `rulesets` | A signed-in user's rules; the account page edits the one marked `is_default` | api |
| `usage_counters` | Monthly spend: `scrapes`, `unlocker`, `jev_usd` | scraper, api (reads) |
| `card_links`, `purchase_intents` | Agent-card payments and purchases: designed, not used yet | nobody yet |

### Status fields

`scrapes.status` moves `pending → crawling → classifying → ready`, or to `failed` if the requested page
cannot be fetched. Children that fail do not fail the scrape. `root_fetched_at` is set as soon as the
requested page is parsed; the session page enables Continue in Grok from then on, while the crawl finishes.

A session's rule is applied incrementally: root products are tested first (then `sessions.classified_at` is
set), and products from followed pages are tested as each page lands. A session without a rule gets
`classified_at` at once, and its context shows every product.

### Rules

`rulesets.rules` is JSON. Today the only key the code reads is `text`, the rule in the shopper's words:

```json
{"text": "only pants"}
```

Sessions snapshot this into `sessions.rules` when they are created, so editing a rule never changes a
session someone already shared.

## Row level security

RLS is on for every table. From 0001: `scrapes` and `products` are readable by anyone (public catalogue
data), and users can see only their own sessions, picks, rulesets, card links and purchases. 0002 makes
`scrape_pages` publicly readable too, and gives `usage_counters` no policies at all.

The browser never queries tables directly today; it only uses Supabase Auth. The API and scraper connect as
the `postgres` role (see below), which bypasses RLS, and they enforce ownership in code (a user can only edit
their own ruleset because the API only ever uses the user id from their verified token).

## Connections

The Python services connect with psycopg to `SUPABASE_DB_URL`. In production that is the **Supavisor
session pooler** string from the Supabase dashboard (Connect > Session pooler), which works over IPv4 and keeps
session semantics. Prepared statements are disabled in the pool, so switching to the transaction pooler later
is safe. A dedicated least-privilege role is on the [roadmap](roadmap.md).

## The queue

`pgmq` (Supabase Queues), one queue called `scrape`. Messages are JSON:

```json
{"v": 1, "kind": "page",     "scrape_id": "…", "url": "https://…", "depth": 0, "parent_url": null, "reason": "root"}
{"v": 1, "kind": "classify", "session_id": "…"}
```

`page` fetches and parses one page (and, at depth 0, plans the crawl). `classify` applies a new session's
rule to a scrape that already finished, which happens when a second shopper reuses a fresh scrape.

The worker reads with a visibility timeout. It deletes a message when the job succeeds. It leaves it to
reappear on failure, and archives it after three reads (`pgmq.a_scrape` keeps the history).

## Migrations

- **Additive only.** Never edit or rename an applied file. Add the next number (`0003_…`).
- Locally: `make db-reset` rebuilds from scratch and proves a migration applies.
- In CI: the database tests run against `supabase db start`, which applies every migration first.
- In production: the deploy workflow runs `supabase db push` before rolling out new images.
- If a migration was ever applied by hand in the Supabase SQL editor, tell the CLI before the next push, or
  it will try to apply it again: `npx supabase@2 migration repair --status applied 0001`.
