# Local development

## Prerequisites

- Docker (local Supabase runs in it)
- Python 3.11+ and Node 22+
- Nothing else: the Supabase CLI runs through `npx` (the Makefile wraps it)

## Local Supabase

`supabase/config.toml` configures a local Supabase that matches production: anonymous sign-ins on, email
confirmation off, and sign-in redirects for `http://localhost:3000`.

```sh
make db          # start it (Docker) and apply supabase/migrations
make db-status   # URLs and keys to copy into your env files
make db-reset    # rebuild from the migrations, e.g. after adding one
make db-stop
```

| What | Where |
| --- | --- |
| API (PostgREST, Auth, Realtime) | `http://127.0.0.1:54321` |
| Postgres | `postgresql://postgres:postgres@127.0.0.1:54322/postgres` |
| Studio (table browser) | `http://127.0.0.1:54323` |
| Mailpit (catches auth emails) | `http://127.0.0.1:54324` |

The local keys `make db-status` prints are fixed development keys, safe to put in local env files and useless
anywhere else.

`make db-reset` re-applies migrations but does not reload `supabase/config.toml`. After changing the config
(auth settings, for example), run `make db-stop && make db`.

## Env files

As in the README quick start: copy `env.example` to `apps/api/.env` and `apps/web/.env.local`, then fill in the
local Supabase values. Keep only the `NEXT_PUBLIC_*` values and the API URL in the web file; server keys never go
near the web app.

For scraping locally, set `BRIGHTDATA_API_KEY` and `BRIGHTDATA_UNLOCKER_ZONE`, and keep `ALLOWED_DOMAINS` short.
Real fetches cost money and count against `SCRAPE_MONTHLY_MAX` in whatever database you point at.

## Running

```sh
make api-install  # apps/api/.venv with requirements-dev.txt
make api          # uvicorn app.main:app --reload --port 8000   (docs at http://localhost:8000/docs)
make api-offline  # same, but scrapes the saved fixtures: no Bright Data key, no spend
make web          # cd apps/web && npm run dev                  (http://localhost:3000)
make api-test     # unit tests, no database
make api-test-db  # everything, against local Supabase (after make db)
make web-check    # lint + build
```

`apps/api/.env` for local Supabase needs `SUPABASE_URL=http://127.0.0.1:54321` and the local
`SERVICE_ROLE_KEY` from `make db-status` as `SUPABASE_SERVICE_ROLE_KEY`. Locally signed tokens are verified
through the local JWKS automatically.

**Offline mode** (`make api-offline`, or `FIXTURES_DIR=tests/fixtures`) serves
`apps/api/tests/fixtures/collection.html` for listing pages and `product.html` for product pages. These are
synthetic pages built to the same shape as joinfleek's real markup, so the whole pipeline (extraction, the
tree, rules) runs with no keys. Without `OPENROUTER_API_KEY`, Jev is skipped and keyword placement is used.

**The web app** (`apps/web`) needs `apps/web/.env.local`:

```sh
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<the local publishable key from make db-status>
```

The API's `WEB_ORIGIN` must be `http://localhost:3000` (its CORS allowlist). Local Supabase already allows anonymous
sign-ins, which is how the prefix route signs guests in.

Then try `http://localhost:3000/https://www.joinfleek.com/collections/nike`.

## Adding a migration

Create the next numbered file in `supabase/migrations/` (for example `0004_what_it_adds.sql`). Never edit an
applied one. Prove it applies from scratch with `make db-reset`, then update [DATABASE.md](DATABASE.md).
