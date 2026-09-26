-- Eden Matrix initial schema
-- FastAPI uses the service role (bypasses RLS). Browser uses anon key.

create extension if not exists pgcrypto;

-- ---------- scraping ----------
create table public.scrapes (
  id            uuid primary key default gen_random_uuid(),
  url           text not null,
  domain        text not null,
  status        text not null default 'pending'
                check (status in ('pending','crawling','classifying','ready','failed')),
  product_count int  not null default 0,
  error         text,
  scraped_at    timestamptz not null default now()
);
create index on public.scrapes (url, scraped_at desc);

create table public.products (
  id               uuid primary key default gen_random_uuid(),
  scrape_id        uuid not null references public.scrapes(id) on delete cascade,
  source_url       text not null,
  external_id      text,
  title            text not null,
  image_url        text,
  price            numeric(12,2),
  compare_at_price numeric(12,2),
  per_piece        numeric(12,2),
  pieces           int,
  currency         text default 'USD',
  tree_path        text[] not null default '{}',
  attrs            jsonb  not null default '{}',
  in_stock         boolean,
  updated_at       timestamptz not null default now(),
  unique (scrape_id, source_url)
);
create index on public.products (scrape_id);

create table public.page_cache (
  url        text primary key,
  html       text not null,
  fetched_at timestamptz not null default now()
);

-- ---------- sessions ----------
create table public.sessions (
  id         uuid primary key default gen_random_uuid(),
  code       text not null unique,          -- e.g. EM-7K2Q9X4M, random, read-only capability
  user_id    uuid references auth.users(id) on delete set null,
  scrape_id  uuid not null references public.scrapes(id),
  rules      jsonb not null default '{}',   -- snapshot of rules for this session
  expires_at timestamptz not null default now() + interval '24 hours',
  created_at timestamptz not null default now()
);
create index on public.sessions (user_id, created_at desc);

create table public.session_picks (
  session_id uuid not null references public.sessions(id) on delete cascade,
  product_id uuid not null references public.products(id) on delete cascade,
  rank       int  not null,
  why        text,
  created_at timestamptz not null default now(),
  primary key (session_id, product_id)
);

-- ---------- rules ----------
create table public.rulesets (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users(id) on delete cascade,
  name       text not null,
  rules      jsonb not null default '{}',
  is_default boolean not null default false,
  created_at timestamptz not null default now()
);

-- ---------- payments ----------
create table public.card_links (
  user_id        uuid primary key references auth.users(id) on delete cascade,
  provider       text not null,
  credential_ref uuid not null,             -- Supabase Vault secret id, never the key itself
  spend_cap      numeric(12,2),
  created_at     timestamptz not null default now()
);

create table public.purchase_intents (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  session_id   uuid not null references public.sessions(id),
  product_ids  uuid[] not null,
  quoted_total numeric(12,2) not null,
  status       text not null default 'pending'
               check (status in ('pending','confirmed','executing','completed','failed','cancelled','price_changed')),
  card_last4   text,
  error        text,
  expires_at   timestamptz not null default now() + interval '30 minutes',
  created_at   timestamptz not null default now(),
  confirmed_at timestamptz
);

-- ---------- RLS ----------
alter table public.scrapes          enable row level security;
alter table public.products         enable row level security;
alter table public.page_cache       enable row level security;
alter table public.sessions         enable row level security;
alter table public.session_picks    enable row level security;
alter table public.rulesets         enable row level security;
alter table public.card_links       enable row level security;
alter table public.purchase_intents enable row level security;

-- public catalogue data
create policy "scrapes readable"  on public.scrapes  for select using (true);
create policy "products readable" on public.products for select using (true);
-- page_cache: no policies → service role only

create policy "own sessions" on public.sessions
  for select using (auth.uid() = user_id);

create policy "own session picks" on public.session_picks
  for select using (exists (
    select 1 from public.sessions s where s.id = session_id and s.user_id = auth.uid()
  ));

create policy "own rulesets" on public.rulesets
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own card link" on public.card_links
  for select using (auth.uid() = user_id);

create policy "own purchases" on public.purchase_intents
  for select using (auth.uid() = user_id);

-- ---------- Realtime (live tree) ----------
alter publication supabase_realtime add table public.scrapes, public.products;
