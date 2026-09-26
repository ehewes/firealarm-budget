# Local development

## Prerequisites

- Python 3.13 via [uv](https://docs.astral.sh/uv/) (uv downloads the interpreter if you do not have it)
- Node 22+ and npm
- Docker (local Supabase runs in it)
- Nothing else: the Supabase CLI runs through `npx`

## First run

```sh
cp .env.example .env
make install         # uv sync + npm install
make db              # starts local Supabase and applies supabase/migrations
make db-status       # copy the publishable (anon) key into SUPABASE_PUBLISHABLE_KEY in .env
make dev             # api on :8000, scraper worker, web on :3000
```

Open `http://localhost:3000/joinfleek.com/collections/april-eom-rl-drop`. You should land on a session
page that turns ready within a few seconds, with a working **Continue in Grok** link and a "View what Grok
sees" link to the Markdown context.

Grok itself cannot reach `localhost`, so the Grok button is only meaningful in production. Everything up to
it works locally.

## Offline by default

`.env.example` sets `SCRAPER_FIXTURES=apps/scraper/tests/fixtures/pages`. In that mode the scraper never
calls Bright Data: it serves saved HTML (a joinfleek-shaped collection page and product pages), so the
whole flow runs with no keys and no spend. Without `OPENROUTER_API_KEY`, link choice uses URL heuristics and
rules use keyword matching, which is also how production degrades when Jev is over budget.

To scrape for real, unset `SCRAPER_FIXTURES` and set `BRIGHTDATA_API_KEY` + `BRIGHTDATA_UNLOCKER_ZONE`
(and optionally `BRIGHTDATA_PROXY`). Add `OPENROUTER_API_KEY` to let Jev decide. Real calls count against the
monthly caps in your local database just as they do in production.

## Signing in locally

Local Supabase catches magic-link emails in Mailpit: open `http://127.0.0.1:54324`, click the link, and you
are signed in at `http://localhost:3000`. Then set a rule on `/account` (for example "only pants") and open a
new session: only matching items appear in the context.

## Everyday commands

| Command | Does |
| --- | --- |
| `make test` | Python unit tests and web tests, no database needed |
| `make test-db` | Database tests against local Supabase (after `make db`) |
| `make lint` / `make fmt` | ruff, eslint, tsc / format and autofix Python |
| `make db-reset` | Rebuild the local database from the migrations |
| `make widget` | Rebuild `widget.js`; then try it at `http://localhost:3000/widget-demo` |
| `make up-local` | The production topology (Caddy + all services in Docker) on `http://localhost:8080` |

## Adding a migration

```sh
npx supabase@2 migration new <what_it_adds>   # then rename to the next 000N_ number
make db-reset                                 # prove it applies from scratch
```

Never edit an applied migration. See [database.md](database.md).

## Environment variables

Every variable is described in `.env.example`, and [secrets.md](secrets.md) says which ones are secret in
production and how they get there. The web app reads the same root `.env` in development (see
`apps/web/next.config.ts`); in production each container gets only the variables it needs from compose.
