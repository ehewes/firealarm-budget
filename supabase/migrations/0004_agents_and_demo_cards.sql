-- Additions for accounts that buy through their own agent. 0001-0003 are unchanged.
--
-- A signed-in shopper links a card (a demo card for now) and connects an agent such as
-- Grok Bot to our MCP endpoint with a personal token. The agent can then ask to buy. It
-- only ever creates a pending purchase_intent; the shopper confirms it on Eden, and the
-- agent learns "card_ready" and the last four digits, never a card number.

-- ---------- agent links: the token an agent sends to /v1/mcp ----------
-- The token is shown once when it is made. Only its SHA-256 is kept, so a database
-- leak doesn't hand anyone a working token.
create table if not exists public.agent_links (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  name         text not null default 'Grok Bot' check (char_length(name) between 1 and 60),
  token_hash   text not null unique,
  token_hint   text not null,              -- the token's last 4 characters, to tell tokens apart
  created_at   timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at   timestamptz
);
create index if not exists agent_links_by_user on public.agent_links (user_id, created_at desc);

alter table public.agent_links enable row level security;
create policy "own agent links" on public.agent_links
  for select using (auth.uid() = user_id);

-- ---------- card links: what the account page may show ----------
-- The demo provider issues nothing real, so its credential_ref points at no Vault
-- secret. A real provider keeps its credentials in Vault, as 0001 intended.
alter table public.card_links
  add column if not exists label      text,
  add column if not exists last4      text check (last4 ~ '^[0-9]{4}$'),
  add column if not exists currency   text not null default 'GBP',
  add column if not exists updated_at timestamptz not null default now();

-- ---------- purchase intents: store, agent, currency, and the checkout's outcome ----------
alter table public.purchase_intents
  add column if not exists merchant      text,
  add column if not exists currency      text,
  add column if not exists agent_link_id uuid references public.agent_links(id) on delete set null,
  add column if not exists card_limit    numeric(12,2),
  add column if not exists order_ref     text,
  add column if not exists completed_at  timestamptz,
  add column if not exists updated_at    timestamptz not null default now();

create index if not exists purchase_intents_by_user
  on public.purchase_intents (user_id, created_at desc);

-- ---------- Grok Bot automations: where "Send to Grok Bot" posts a session ----------
-- A Grok Bot automation triggered "When a webhook fires" has a URL and a key; the sender
-- authenticates with `Authorization: Bearer <key>`. The key is a credential for the
-- shopper's bot, so the table has no policies: only the API (service role) can read it.
create table if not exists public.bot_webhooks (
  user_id      uuid primary key references auth.users(id) on delete cascade,
  url          text not null check (url like 'https://%'),
  secret       text not null,
  created_at   timestamptz not null default now(),
  last_sent_at timestamptz
);

alter table public.bot_webhooks enable row level security;
