-- Additions on top of 0001_init.sql, which is unchanged: where a session came from,
-- what we need to rate limit session creation, one default ruleset per user, and the
-- monthly spend counters behind the scrape and Jev budgets.

-- ---------- sessions: entry gate and abuse control ----------
alter table public.sessions
  -- 'prefix': someone put our domain in front of a store URL.
  -- 'widget': a vendor's embedded "Continue in Eden Matrix" button sent them.
  add column if not exists entry             text not null default 'prefix'
                                             check (entry in ('prefix','widget')),
  -- Widget sessions only: the origin the browser reported, and whether it matches
  -- the store URL it claims. Recorded, not enforced: a non-browser client can send
  -- any Referer it likes.
  add column if not exists referrer_origin   text,
  add column if not exists origin_verified   boolean not null default false,
  -- A salted hash of the requester's IP, never the address itself. Used only for
  -- the per-IP limit on POST /v1/sessions.
  add column if not exists requester_ip_hash text;

create index if not exists sessions_requester_recent
  on public.sessions (requester_ip_hash, created_at desc);
create index if not exists sessions_by_scrape
  on public.sessions (scrape_id);

-- ---------- rulesets: at most one default per user ----------
create unique index if not exists rulesets_one_default
  on public.rulesets (user_id) where is_default;

-- ---------- monthly spend counters ----------
-- Keys: 'scrapes' (Bright Data page fetches) and 'jev_usd' (Jev's reported cost).
-- `period` is the first day of the month the spend belongs to. The API checks these
-- before every paid call and stops at SCRAPE_MONTHLY_MAX / JEV_MONTHLY_BUDGET_USD.
create table if not exists public.usage_counters (
  period date          not null,
  key    text          not null,
  amount numeric(14,6) not null default 0,
  primary key (period, key)
);

alter table public.usage_counters enable row level security;
-- No policies: only the API (service role) reads or writes spend.
