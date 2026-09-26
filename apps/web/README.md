# apps/web

The Eden Matrix website (Next.js App Router). Deployed at `https://go.edenmatrix.xyz`, with the Eden API at `/v1`
on the same host.

| Route | What it does |
| --- | --- |
| `/` | What Eden Matrix is, plus a box to paste a store URL |
| `/<store-url>` | The prefix route: signs the visitor in (anonymously if new), `POST /v1/sessions`, then goes to `/s/<code>` |
| `/s/<code>` | Live status and category tree while the scrape runs, then the handoff and the cheapest items. **Send to Grok Bot** when the shopper has connected a Grok Bot automation; otherwise, on desktops, **Copy prompt & open Grok Bot** (`grokbot://app/v1/open` can't carry a prompt itself). **Continue in Grok** opens grok.com with the prompt filled in |
| `/dashboard` | The shopper's account: sign up (a guest is upgraded in place, keeping their sessions) or sign in, the demo agent card and its limit, **Connect Grok Bot** (a one-time MCP token and the JSON to paste), the Grok Bot automation webhook, past sessions |
| `/confirm/<id>` | Where the signed-in owner approves what their agent asked to buy. Prices are re-checked on the store first, then the demo card is issued and the demo checkout runs. See `docs/GROK_BOT.md` |

```sh
npm install
npm run dev      # http://localhost:3000
npm run lint && npm run build
```

Settings (`.env.local` locally; GitHub variables in production, compiled in at build time):
`NEXT_PUBLIC_API_URL` (`http://localhost:8000/v1` locally), `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` (the publishable key, never a secret key).

Guests need anonymous sign-ins enabled in Supabase. See `docs/LOCAL_DEV.md` and `docs/DEPLOYMENT.md`.
