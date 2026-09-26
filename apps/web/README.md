# apps/web

The Eden Matrix website (Next.js App Router). Deployed at `https://go.edenmatrix.xyz`, with the Eden API at `/v1`
on the same host.

| Route | What it does |
| --- | --- |
| `/` | What Eden Matrix is, plus a box to paste a store URL |
| `/<store-url>` | The prefix route: signs the visitor in (anonymously if new), `POST /v1/sessions`, then goes to `/s/<code>` |
| `/s/<code>` | Live status and category tree while the scrape runs, then **Continue in Grok** and the cheapest items |

```sh
npm install
npm run dev      # http://localhost:3000
npm run lint && npm run build
```

Settings (`.env.local` locally; GitHub variables in production, compiled in at build time):
`NEXT_PUBLIC_API_URL` (`http://localhost:8000/v1` locally), `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_ANON_KEY` (the publishable key, never a secret key).

Guests need anonymous sign-ins enabled in Supabase. See `docs/LOCAL_DEV.md` and `docs/DEPLOYMENT.md`.
