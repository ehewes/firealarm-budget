-- What the API needs on top of 0002: the collection's name for GET /v1/sessions/{code},
-- when a scrape last made progress, and an atomic way to add to the monthly spend
-- counters over the REST API.

-- The listing page's title ("Nike Vintage Wholesale"), shown as `collection`.
alter table public.scrapes add column if not exists title text;

-- Bumped at every pipeline step. A scrape whose last progress is old was killed by a
-- restart (scrapes run inside the API process), and startup marks it failed.
alter table public.scrapes add column if not exists updated_at timestamptz not null default now();

-- Adds to this month's counter and returns the new total. One statement, so two
-- concurrent scrapes can never both read 4999 and both decide there is room.
-- Callable only by the service role (the API): spend is not the browser's business.
create or replace function public.increment_usage(p_key text, p_amount numeric default 1)
returns numeric
language sql
set search_path = ''
as $$
  insert into public.usage_counters (period, key, amount)
  values (date_trunc('month', now())::date, p_key, p_amount)
  on conflict (period, key) do update
    set amount = public.usage_counters.amount + excluded.amount
  returning amount;
$$;

revoke execute on function public.increment_usage(text, numeric) from public, anon, authenticated;
grant execute on function public.increment_usage(text, numeric) to service_role;
