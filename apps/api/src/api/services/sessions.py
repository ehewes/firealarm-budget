"""Creating a session: the one write path both entry gates share.

Order matters and is cheapest-first: validate the address, return an existing
session on a refresh, apply the rate limit, then (only if nothing fresh can be
shared) check the monthly scrape budget and enqueue a job. The session row and
its job are written in one transaction, so a session never exists without the
work that fills it.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from api.client_ip import ip_hash
from api.errors import ApiError
from api.settings import ApiSettings
from eden_core import queue, reachable, usage
from eden_core.codes import new_session_code
from eden_core.jobs import ClassifyJob, PageJob
from eden_core.urls import BadUrl, canonical, host_of, origin_of, same_site, site_of

OWN_ZONE = "edenmatrix.xyz"


@dataclass(frozen=True, slots=True)
class Created:
    code: str
    status: str
    reused: bool


async def validate_target(url: str, settings: ApiSettings) -> str:
    """The canonical form of an address we are willing to scrape, or ApiError."""
    try:
        target = canonical(url)
    except BadUrl as exc:
        raise ApiError(422, "bad_url", str(exc)) from exc

    site = site_of(host_of(target))
    own = site_of(host_of(settings.public_base_url))
    if any(site == zone or site.endswith("." + zone) for zone in (own, OWN_ZONE)):
        raise ApiError(422, "self", "That is already an EdenMatrix address.")

    allowed = settings.allowed_sites
    if allowed and not any(site == a or site.endswith("." + a) for a in allowed):
        raise ApiError(403, "site_not_supported", "EdenMatrix does not support that site yet.")

    if settings.gate_resolve_dns:
        try:
            await reachable.check(target)
        except reachable.NotReachable as exc:
            raise ApiError(422, "unreachable", "We could not find that site.") from exc
    return target


async def create_session(
    pool: AsyncConnectionPool,
    settings: ApiSettings,
    *,
    url: str,
    entry: str,
    referrer_origin: str | None,
    ip: str,
    user_id: str | None,
) -> Created:
    target = await validate_target(url, settings)
    requester = ip_hash(ip, settings.ip_hash_salt)
    referrer = origin_of(referrer_origin) if referrer_origin else None
    # A browser assertion, not proof: anything other than a browser can send any
    # Referer it likes. Real verification is the future Web Bot Auth layer.
    origin_verified = entry == "widget" and referrer is not None and same_site(referrer, target)

    async with pool.connection() as conn:
        rules = await _rules_for(conn, user_id)
        existing = await _recent_session(conn, target, user_id, requester, rules, settings)
        if existing is not None:
            return existing
        await _check_rate(conn, user_id, requester, settings)

        async with conn.transaction():
            scrape_id, status = await _fresh_scrape(conn, target, settings.scrape_fresh_minutes)
            new_scrape = scrape_id is None
            if new_scrape:
                if await usage.scrapes_left(conn, settings.scrape_monthly_max) <= 0:
                    raise ApiError(
                        503,
                        "budget_exhausted",
                        "EdenMatrix has used this month's scraping budget. Please try again later.",
                    )
                cur = await conn.execute(
                    "insert into public.scrapes (url, domain) values (%s, %s) returning id",
                    (target, site_of(host_of(target))),
                )
                row = await cur.fetchone()
                assert row is not None
                scrape_id, status = row["id"], "pending"

            assert scrape_id is not None
            session_id, code = await _insert_session(
                conn,
                scrape_id=scrape_id,
                user_id=user_id,
                rules=rules,
                entry=entry,
                referrer=referrer,
                origin_verified=origin_verified,
                requester=requester,
            )
            if new_scrape:
                job = PageJob(scrape_id=scrape_id, url=target)
                await queue.send(conn, job.model_dump(mode="json"))
            elif rules:
                # The shared scrape's products predate this session, so its rule
                # has to be applied to them separately.
                await queue.send(conn, ClassifyJob(session_id=session_id).model_dump(mode="json"))
    return Created(code=code, status=status, reused=False)


async def _rules_for(conn: AsyncConnection, user_id: str | None) -> dict[str, Any]:
    if user_id is None:
        return {}
    cur = await conn.execute(
        "select rules from public.rulesets where user_id = %s and is_default", (user_id,)
    )
    row = await cur.fetchone()
    text = (row["rules"] or {}).get("text") if row else None
    if isinstance(text, str) and text.strip():
        return {"text": text.strip()}
    return {}


async def _recent_session(
    conn: AsyncConnection,
    target: str,
    user_id: str | None,
    requester: str,
    rules: dict[str, Any],
    settings: ApiSettings,
) -> Created | None:
    """The same shopper asking for the same page with the same rule, moments ago.

    Refreshing the gate, or a browser retrying it, would otherwise mint a new
    session (and count against the rate limit) every time.
    """
    who = "s.user_id = %s" if user_id else "s.user_id is null and s.requester_ip_hash = %s"
    cur = await conn.execute(
        f"""
        select s.code, sc.status
          from public.sessions s join public.scrapes sc on sc.id = s.scrape_id
         where sc.url = %s and {who}
           and s.rules = %s and sc.status <> 'failed'
           and s.expires_at > now()
           and s.created_at > now() - make_interval(mins => %s)
         order by s.created_at desc
         limit 1
        """,
        (target, user_id or requester, Jsonb(rules), settings.session_reuse_minutes),
    )
    row = await cur.fetchone()
    return Created(code=row["code"], status=row["status"], reused=True) if row else None


async def _check_rate(
    conn: AsyncConnection, user_id: str | None, requester: str, settings: ApiSettings
) -> None:
    if user_id:
        column, key = "user_id", user_id
        per_hour, per_day = settings.user_sessions_per_hour, None
    else:
        column, key = "requester_ip_hash", requester
        per_hour, per_day = settings.guest_sessions_per_hour, settings.guest_sessions_per_day
    cur = await conn.execute(
        f"""
        select count(*) filter (where created_at > now() - interval '1 hour') as hour,
               count(*) as day,
               extract(epoch from (
                 min(created_at) filter (where created_at > now() - interval '1 hour')
                 + interval '1 hour' - now()))::int as retry_after
          from public.sessions
         where {column} = %s and created_at > now() - interval '1 day'
        """,
        (key,),
    )
    row = await cur.fetchone()
    assert row is not None
    over_day = per_day is not None and row["day"] >= per_day
    if row["hour"] >= per_hour or over_day:
        retry = 3600 if over_day else max(1, int(row["retry_after"] or 60))
        raise ApiError(
            429,
            "rate_limited",
            "That is a lot of pages in a short time. Please wait a little and try again.",
            headers={"Retry-After": str(retry)},
        )


async def _fresh_scrape(
    conn: AsyncConnection, target: str, fresh_minutes: int
) -> tuple[UUID | None, str]:
    """A recent scrape of the same page (finished or still running) to share."""
    cur = await conn.execute(
        """
        select id, status from public.scrapes
         where url = %s and status <> 'failed'
           and scraped_at > now() - make_interval(mins => %s)
         order by scraped_at desc
         limit 1
        """,
        (target, fresh_minutes),
    )
    row = await cur.fetchone()
    return (row["id"], row["status"]) if row else (None, "pending")


async def _insert_session(
    conn: AsyncConnection,
    *,
    scrape_id: UUID,
    user_id: str | None,
    rules: dict[str, Any],
    entry: str,
    referrer: str | None,
    origin_verified: bool,
    requester: str,
) -> tuple[UUID, str]:
    for _ in range(5):
        code = new_session_code()
        try:
            # A savepoint, so a code collision rolls back only this insert.
            async with conn.transaction():
                cur = await conn.execute(
                    """
                    insert into public.sessions
                      (code, user_id, scrape_id, rules, entry, referrer_origin,
                       origin_verified, requester_ip_hash, classified_at)
                    values (%s, %s, %s, %s, %s, %s, %s, %s,
                            case when %s then now() end)
                    returning id
                    """,
                    (
                        code,
                        user_id,
                        scrape_id,
                        Jsonb(rules),
                        entry,
                        referrer,
                        origin_verified,
                        requester,
                        not rules,
                    ),
                )
                row = await cur.fetchone()
                assert row is not None
                return row["id"], code
        except UniqueViolation:
            continue
    raise RuntimeError("could not find a free session code")
