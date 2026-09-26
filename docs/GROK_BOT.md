# Grok Bot: handoff, memory and buying

How a session gets from Eden Matrix to the shopper's Grok Bot, how the bot remembers sessions, and how it buys
with the shopper's agent card. The card is a demo card for now.

## What Grok Bot's app can and can't do

This was read from the installed app (v0.59.1, its `Info.plist` and `app.asar`) because the docs don't cover it:

- It registers the link schemes `grokbot://` and `sand://`. The routes are `app/v1/open`, `app/v1/agent?id=`,
  `app/v1/bot-template?id=`, marketplace, plugins and settings. **No route carries a prompt**, so a link can open
  the app but can't start a task.
- Automations can be triggered **"When a webhook fires"**. The automation gets a webhook URL and key, and the
  sender adds `Authorization: Bearer <key>`. This is how Eden hands over a session with nothing to paste.
- It connects to remote **MCP servers** from a JSON config with `url` and `headers` (as in Cursor), or over OAuth
  (`grokbot://mcp/oauth/callback`). Connectors are account-wide, not per bot.
- Each bot's computer keeps `/workspace` between tasks ([docs](https://docs.x.ai/grok-bot/computer-and-apps)).
  That is where the bot keeps its log of the shopper's sessions.

## Four ways to hand over a session

On the session page (`/s/<code>`), once the page has been read:

| Button | Needs | What happens |
| --- | --- | --- |
| **Send to Grok Bot** | a Grok Bot automation connected on `/dashboard` | Eden posts the session to the automation's webhook and the bot starts on it |
| **Copy prompt & open Grok Bot** | a desktop with Grok Bot | copies the prompt, opens `grokbot://app/v1/open`; the shopper presses ⌘V in a new task |
| **Continue in Grok** | nothing | opens `grok.com/?q=<prompt>`, prefilled |
| (just ask) | the Eden MCP connected | "What have I been shopping for on Eden?" The bot calls `list_my_sessions` |

The Grok Bot prompt (`bot_prompt` from `GET /v1/sessions/{code}/grok`) is the normal prompt plus memory. It tells
the bot to add the session to `/workspace/eden-matrix/sessions.md` (code, store, collection, date, link), to read
that file whenever the shopper mentions an earlier session, and to use `list_my_sessions` when the MCP is
connected.

## Setting it up (shopper, once)

1. **Create an account** on `/dashboard`. A guest is upgraded in place (`supabase.auth.updateUser`), so the
   sessions they started as a guest stay theirs.
2. **Add the demo agent card** with a limit per purchase. No real card is issued and nothing is charged. The
   card link stores a label, the last four digits and the limit, never a number.
3. **Connect Grok Bot (MCP).** Eden makes a token (shown once; only its SHA-256 is stored) and shows the JSON to
   paste into Grok Bot's MCP servers:

   ```json
   { "mcpServers": { "eden-matrix": {
       "url": "https://go.edenmatrix.xyz/v1/mcp",
       "headers": { "Authorization": "Bearer em_agent_…" } } } }
   ```

4. **Optional: Send to Grok Bot.** In Grok Bot, create an automation triggered "When a webhook fires", give it
   the instructions the dashboard shows, and paste its webhook URL and key into the dashboard. The key is stored
   in `bot_webhooks`, which has no RLS policies, so only the API can read it.

## The MCP tools (`POST /v1/mcp`)

Streamable HTTP with JSON responses. `GET` returns 405 because there is no server-sent stream. Every call acts
for the account that owns the token.

| Tool | Does |
| --- | --- |
| `list_my_sessions` | the shopper's sessions, newest first: the bot's memory on Eden's side |
| `start_session` | reads a new store page (optionally with rules in plain words) into a session |
| `get_session` | status, store, collection, rules |
| `find_products` | the ranked shortlist, rules applied server-side, each item with a `why` |
| `create_purchase_intent` | asks to buy; returns a `confirm_url` for the shopper. Nothing is charged |
| `get_purchase_status` | `pending`, `price_changed`, `executing` (card ready), `completed` (order ref), `failed`, `cancelled` |

## Buying

1. The bot calls `create_purchase_intent` with ids from `find_products`. Eden checks the card, the limit, stock
   and currency. It prices the intent from the database, stores it as `pending` for 30 minutes and returns
   `confirm_url` (`/confirm/<id>`).
2. The shopper opens the link, signed in as the same account, and presses Confirm. Agent tokens, guests and
   other accounts can't confirm (CLAUDE.md rule 2).
3. Eden re-reads every product page on the store (rule 4). If a price moved or an item went out of stock, the
   intent becomes `price_changed` with the new total and the shopper confirms again.
4. Eden issues the (demo) card: the confirmed total plus 5%, never above the limit. The intent is now
   `executing`, and the bot sees `card_ready` with the last four digits, never a card number (rule 1).
5. The demo checkout marks it `completed` with an `EDEN-DEMO-…` order reference after `DEMO_CHECKOUT_SECONDS`.
   Nothing is sent to the store.

To make it real, swap the demo provider in `services/purchases.py` for a card issuer (for example Stripe
Issuing, which Cloudflare's agentic payments work supports through MPP), keep its credentials in Vault as
`card_links.credential_ref` intends, and replace `demo_checkout` with the store's checkout.

## Demo checklist

- Supabase **Confirm email** is on in production, and Supabase's built-in mailer sends only a few emails an hour.
  For a live demo, switch it off (Authentication → Sign In / Providers → Email). Sign-up then completes instantly.
- A team demo account exists in production: username `admin` (`admin@edenmatrix.xyz`, which has no mailbox; the
  sign-in box turns a bare username into `<name>@edenmatrix.xyz`). Its password was set through the Supabase admin
  API from inside the API container with a bcrypt `password_hash`, because it is shorter than the project's
  minimum. Anyone who knows the password can approve that account's purchases, so change it before a real card
  is ever linked.
- Grok Bot must be able to reach `https://go.edenmatrix.xyz/v1/mcp`. The Cloudflare WAF skip rule covers
  `/v1/mcp` as well as `/v1/sessions/*` (see [DEPLOYMENT.md](DEPLOYMENT.md)), so the zone's AI-bot blocking
  doesn't stop it.
