# Eden Matrix

**Put our domain in front of any store URL and it becomes agent-ready.**

```
https://www.joinfleek.com/collections/nike
        ↓ prefix it
https://www.edenmatrix.com/https://www.joinfleek.com/collections/nike
```

Eden Matrix scrapes the page, classifies every product into a category tree, and exposes it through a public API that Grok Bot uses to recommend — and, for signed-in users with a linked agent card, buy — against the user's own rules.

Built for the Cursor Commerce London Hackathon (Fleek HQ).

## How it works

1. **Prefix a store URL.** Eden starts a session and scrapes the page in the background (Bright Data / Machine Transpiler), streaming a live category tree to the page.
2. **Set your rules.** e.g. "Premium only, under $14/piece, no shorts". Guests' rules persist on their device; signed-in users can save rulesets.
3. **Continue to Grok.** One click hands the session to Grok Bot. Grok queries the Eden API and recommends items that match your rules.
4. **Buy (signed-in only).** Ask Grok to buy → it returns a confirmation link → you confirm on Eden → a single-use agent card is issued, locked to the amount and merchant → checkout runs.

| | Guest | Signed in |
|---|---|---|
| Prefix any store URL | ✅ | ✅ |
| Rules on the continue page | ✅ (this device) | ✅ |
| Recommendations via Grok | ✅ | ✅ |
| Saved rulesets | — | ✅ |
| Past sessions | — | ✅ |
| Linked agent card + purchasing | — | ✅ |

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js (App Router), Tailwind, shadcn/ui, on the team VPS via Cloudflare Tunnel |
| API | FastAPI (Python) & Next.js Routes, on the team VPS via Cloudflare Tunnel |
| Data & auth | Supabase — Postgres, anonymous + email auth, RLS, Realtime, Vault |
| Scraping | Universal Machine Transpiler & Bright Data Web Unlocker |
| Classification & ranking | Jev (TypeSafe AI) System-1 Fast Path |
| Agent | Grok Bot + Grok API (attribute extraction & deep compromise reasoning) |
| Payments (stretch) | Agent card provider, Playwright checkout |

## Repo layout

```
eden-matrix/
├── apps/
│   ├── web/          # Next.js frontend
│   └── api/          # FastAPI — public Eden API, scraping, Jev, Grok
├── supabase/
│   └── migrations/   # SQL schema + RLS
├── docs/
│   ├── ARCHITECTURE.md
│   └── API.md
├── CLAUDE.md         # context for AI coding assistants
└── .env.example
```

## Quick start

```bash
# 1. Env
cp .env.example apps/api/.env
cp .env.example apps/web/.env.local   # keep only NEXT_PUBLIC_* + API URL here

# 2. Database
supabase link --project-ref <ref>
supabase db push

# 3. API
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000     # docs at http://localhost:8000/docs

# 4. Web
cd apps/web
npm install && npm run dev                    # http://localhost:3000
```

Try it: `http://localhost:3000/https://www.joinfleek.com/collections/nike`

## Docs

- [Architecture](docs/ARCHITECTURE.md) — components, data flow, key decisions
- [API reference](docs/API.md) — the public Eden API
- [Grok Bot](docs/GROK_BOT.md): handing sessions to Grok Bot, its memory, MCP, and buying with the demo agent card
- [Local development](docs/LOCAL_DEV.md): local Supabase (`make db`), env files, running things
- [Database](docs/DATABASE.md): migration rules and what each migration added
- [Deployment](docs/DEPLOYMENT.md): the VPS, Cloudflare Tunnel at `go.edenmatrix.xyz`, CI/CD, runbook
- [Secrets](docs/SECRETS.md): every GitHub secret and variable, and how to set or rotate one
- [Roadmap](.planning/ROADMAP.md) — build phases and progress

## Team

<!-- names + roles -->
