# firealarm-budget: EdenMatrix "go"

Put `go.edenmatrix.xyz/` in front of any shop page and continue the conversation in Grok.

```
https://www.joinfleek.com/collections/april-eom-rl-drop
https://go.edenmatrix.xyz/joinfleek.com/collections/april-eom-rl-drop
```

The service scrapes that page in the background (Bright Data), follows the links that matter (Jev decides
which), and stores the result as a **public session**. The shopper lands on a minimal page with a
**Continue in Grok** button that opens Grok already pointed at the session's plain-text context. Signed-in
shoppers can set a rule such as "only pants", and only matching items reach Grok. Vendors can embed a small
"Continue in EdenMatrix" button on their own site as a second way in.

## Layout

| Path | What it is |
| --- | --- |
| `apps/web` | Next.js (TypeScript): the entry gates, session page, sign-in, account |
| `apps/api` | FastAPI (Python): sessions, the public context Grok reads, rulesets |
| `apps/scraper` | Python worker: Bright Data fetches, extraction, Jev crawl and rule gating |
| `apps/widget` | The embeddable vendor button (`widget.js`) |
| `packages/core` | Small shared Python package used by the API and the scraper |
| `supabase` | Database migrations and local Supabase config |
| `deploy` | Docker Compose, Caddy and Cloudflare Tunnel config for the VPS |
| `docs` | Everything below, in more depth |

## Quick start

```sh
cp .env.example .env
make install
make db          # local Supabase in Docker, applies the migrations
make dev         # api :8000, scraper, web :3000
open http://localhost:3000/joinfleek.com/collections/april-eom-rl-drop
```

The default `.env` runs fully offline: pages come from saved fixtures and no API keys are needed.

## Docs

Start at [docs/README.md](docs/README.md): architecture, local development, deployment, secrets, database,
scraper and Jev, the widget, the API and the Grok context format, and the roadmap.
