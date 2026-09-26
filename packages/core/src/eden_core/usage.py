"""Monthly spend counters: the enforcement point for the scrape and Jev caps.

One row per (month, key) in `usage_counters`, incremented atomically. Reads are
a single primary-key lookup, cheap enough to do before every paid call.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from psycopg import AsyncConnection

SCRAPES = "scrapes"  # every page fetch that goes through Bright Data
UNLOCKER = "unlocker"  # the paid-per-success strategy, a subset of SCRAPES
JEV_USD = "jev_usd"  # OpenRouter's reported cost for Jev decisions


def period_of(today: date | None = None) -> date:
    today = today or datetime.now(UTC).date()
    return today.replace(day=1)


async def add(
    conn: AsyncConnection, key: str, amount: float | Decimal = 1, *, today: date | None = None
) -> Decimal:
    """Add to this month's counter and return the new total."""
    cur = await conn.execute(
        """
        insert into public.usage_counters (period, key, amount) values (%s, %s, %s)
        on conflict (period, key) do update
          set amount = public.usage_counters.amount + excluded.amount
        returning amount
        """,
        (period_of(today), key, Decimal(str(amount))),
    )
    row = await cur.fetchone()
    assert row is not None
    return Decimal(row["amount"])


async def total(conn: AsyncConnection, key: str, *, today: date | None = None) -> Decimal:
    cur = await conn.execute(
        "select amount from public.usage_counters where period = %s and key = %s",
        (period_of(today), key),
    )
    row = await cur.fetchone()
    return Decimal(row["amount"]) if row else Decimal(0)


async def scrapes_left(conn: AsyncConnection, monthly_max: int) -> int:
    return max(0, monthly_max - int(await total(conn, SCRAPES)))


async def jev_budget_left(conn: AsyncConnection, monthly_usd: float) -> Decimal:
    return max(Decimal(0), Decimal(str(monthly_usd)) - await total(conn, JEV_USD))
