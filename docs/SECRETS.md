# Secrets

**Every secret lives in GitHub repository secrets** (Settings > Secrets and variables > Actions), and every
non-secret setting in repository variables. Nothing secret is committed, and nothing secret is pasted into chat
or an issue. The deploy workflow renders `/opt/firealarm-budget/.env` on the VPS from these on every deploy,
so the box never drifts from the repo settings and nothing is hand-edited there.

Locally, the same names go in `apps/api/.env` and `apps/web/.env.local` (see [LOCAL_DEV.md](LOCAL_DEV.md) and
`env.example`).

## Setting one

```sh
gh secret set NAME -R ehewes/firealarm-budget              # prompts; the value is not echoed
gh secret set NAME -R ehewes/firealarm-budget < file       # from a file, e.g. a private key
gh variable set NAME -R ehewes/firealarm-budget --body value
gh secret list -R ehewes/firealarm-budget                  # names only, never values
```

After changing a runtime secret, redeploy (re-run the latest deploy workflow) so the box picks it up.

## Secrets

| Name | Used by | What it is |
| --- | --- | --- |
| `SUPABASE_SERVICE_ROLE_KEY` | api | Server key; bypasses RLS. Never in the web app |
| `SUPABASE_JWT_SECRET` | api | Only if the project still signs tokens with the legacy HS256 secret; otherwise tokens are verified via the project's JWKS |
| `SUPABASE_DB_URL` | CI migrate job | Session pooler connection string, used only by `supabase db push`. Never rendered to the box. The password part must be percent-encoded |
| `BRIGHTDATA_API_KEY` | api | Web Unlocker API key |
| `OPENROUTER_API_KEY` or `JEV_API_KEY` | api | Access to Jev (`typesafe/jev-1.13`). Through OpenRouter today; `JEV_API_KEY` if we go to TypeSafe directly |
| `GROK_API_KEY` | api | xAI API: attribute extraction and rule parsing |
| `IP_HASH_SALT` | api | Keys the hash of requester IPs for rate limiting. Random, never reused |
| `AGENT_CARD_API_KEY` | api | Stretch goal: the agent card provider |
| `CLOUDFLARE_TUNNEL_TOKEN` | cloudflared | This project's tunnel |
| `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET` | CI | Tailscale OAuth client (tag `tag:ci`); lets the runner reach the VPS |
| `TS_AUTHKEY` | CI | Fallback only if there is no OAuth client: a reusable, ephemeral `tag:ci` auth key (it expires) |
| `VPS_SSH_KEY` | CI | Private half of the dedicated deploy key, usable only from the tailnet |

## Variables (not secret)

| Name | Value / example | Used by |
| --- | --- | --- |
| `DEPLOY_ENABLED` | `false` until setup is complete, then `true` | CI |
| `VPS_HOST`, `VPS_USER`, `VPS_APP_DIR` | `100.102.111.88`, `deploy`, `/opt/firealarm-budget` | CI |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | api |
| `WEB_ORIGIN` | `https://go.edenmatrix.xyz` | api (links, CORS) |
| `ALLOWED_DOMAINS` | `*` | api: which stores it will scrape; `*` means any store, or give a comma-separated list |
| `BRIGHTDATA_UNLOCKER_ZONE` | the zone name | api |
| `SESSION_TTL_HOURS` | `24` | api |
| `SCRAPE_CONCURRENCY` | `8` | api |
| `MAX_PRODUCT_PAGES` | `10` | api: product pages fetched per scrape (each one counts as a scrape) |
| `GROK_BOT_URL` | `https://grok.com/` | api: where Continue to Grok links point |
| `SCRAPE_MONTHLY_MAX` | `5000` | api: Bright Data fetches per month, then scraping stops |
| `JEV_MONTHLY_BUDGET_USD` | `5` | api: Jev spend per month, then it falls back to heuristics |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` | web, at build time |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the anon / publishable key | web, at build time (safe to expose) |
| `NEXT_PUBLIC_API_URL` | `https://go.edenmatrix.xyz/v1` | web, at build time |
| `NEXT_PUBLIC_GROK_BOT_URL` | the Grok Bot link | web, at build time |

`NEXT_PUBLIC_*` values are compiled into the web image, so they are variables (public by design), passed as
build arguments, and changing one needs a rebuild, not just a redeploy.

## Adding a new one

1. Add it to `env.example` (placeholder only) and to the settings code that reads it.
2. Add it to the `.env` render step in the deploy workflow, and to the service's `environment:` in the compose
   file. Each container gets only the variables it needs.
3. Add a row here.
4. Set it with `gh secret set` / `gh variable set`.

## Rotating

Set the new value with `gh secret set`, redeploy, then revoke the old value at the provider. If a secret was
ever pasted into a chat, an issue or a log, treat it as leaked: rotate it.
