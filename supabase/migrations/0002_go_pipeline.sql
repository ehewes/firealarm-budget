-- What the first working path needs on top of 0001_init.sql: the job queue, crawl
-- progress, the pages a scrape visited, where a session came from, and the
-- monthly spend counters. Additive only; nothing in 0001 is changed or dropped.

-- ---------- job queue (Supabase Queues) ----------
-- One queue for every scraper job. The API enqueues in the same transaction that
-- creates the session, so a session never exists without its job, and a worker
-- that dies mid-job gets its message back when the visibility timeout expires.
create extension if not exists pgmq;
select pgmq.create('scrape');

-- ---------- scrapes: what the page said, and crawl progress ----------
alter table public.scrapes
  add column if not exists title           text,
  add column if not exists description     text,
  -- Readable Markdown of the requested page, capped by the scraper.
  add column if not exists summary_md      text,
  -- Set once the requested page is fetched and parsed. The session page enables
  -- Continue in Grok from this moment, while the crawl carries on behind it.
  add column if not exists root_fetched_at timestamptz,
  -- The requested page counts as one planned page; followed links add to it.
  add column if not exists pages_planned   int not null default 1,
  add column if not exists pages_done      int not null default 0,
  add column if not exists updated_at      timestamptz not null default now();

-- ---------- pages a scrape visited ----------
-- The requested page (depth 0) plus each page the crawler chose to follow from
-- it (depth 1). `links` is the page's classified same-site links, which is what
-- lets the context tell Grok how to get from one page to another.
create table public.scrape_pages (
  scrape_id   uuid     not null references public.scrapes(id) on delete cascade,
  url         text     not null,
  depth       smallint not null default 0,
  parent_url  text,
  -- Why it was fetched: 'root', or who chose it: 'jev' or 'heuristic'.
  reason      text     not null default 'root',
  status      text     not null default 'pending'
              check (status in ('pending','fetched','failed')),
  strategy    text,
  http_status int,
  title       text,
  links       jsonb    not null default '[]',
  error       text,
  fetched_at  timestamptz,
  primary key (scrape_id, url)
);

alter table public.scrape_pages enable row level security;
-- Same visibility as scrapes and products in 0001: public catalogue data.
create policy "scrape pages readable" on public.scrape_pages for select using (true);

-- ---------- sessions: entry gate, abuse control, rule progress ----------
alter table public.sessions
  add column if not exists entry             text not null default 'url_rewrite'
                                             check (entry in ('url_rewrite','widget')),
  -- For widget sessions: the origin the browser said it came from, and whether
  -- it matches the page it claims to be. Recorded, not enforced, for now.
  add column if not exists referrer_origin   text,
  add column if not exists origin_verified   boolean not null default false,
  -- Salted hash, never the address itself. Only used for the per-hour limit.
  add column if not exists requester_ip_hash text,
  -- When this session's rule was first applied to the scrape's products. Null
  -- while pending; set immediately for sessions with no rule.
  add column if not exists classified_at     timestamptz;

create index if not exists sessions_requester_recent
  on public.sessions (requester_ip_hash, created_at desc);
create index if not exists sessions_by_scrape
  on public.sessions (scrape_id);

-- ---------- rulesets ----------
-- The account page edits one default ruleset per user; this keeps it to one.
create unique index if not exists rulesets_one_default
  on public.rulesets (user_id) where is_default;

-- ---------- monthly spend counters ----------
-- Keys: 'scrapes' (page fetches through Bright Data), 'unlocker' (the paid
-- strategy, a subset of scrapes) and 'jev_usd' (OpenRouter's reported cost).
-- `period` is the first day of the month the spend belongs to.
create table public.usage_counters (
  period date          not null,
  key    text          not null,
  amount numeric(14,6) not null default 0,
  primary key (period, key)
);

alter table public.usage_counters enable row level security;
-- No policies: only the backend (postgres role) reads or writes spend.
