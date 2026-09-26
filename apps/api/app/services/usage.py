"""The monthly spend caps: 5,000 Bright Data scrapes and $5 of Jev by default.

Counted in `usage_counters` through the `increment_usage` function, which adds and
returns the new total in one statement.
"""

from datetime import UTC, datetime
from decimal import Decimal

from supabase import AsyncClient

SCRAPES = "scrapes"
JEV_USD = "jev_usd"


def _period() -> str:
    return datetime.now(UTC).date().replace(day=1).isoformat()


async def add(db: AsyncClient, key: str, amount: float = 1) -> Decimal:
    res = await db.rpc("increment_usage", {"p_key": key, "p_amount": amount}).execute()
    return Decimal(str(res.data))


async def total(db: AsyncClient, key: str) -> Decimal:
    res = (
        await db.table("usage_counters")
        .select("amount")
        .eq("period", _period())
        .eq("key", key)
        .limit(1)
        .execute()
    )
    return Decimal(str(res.data[0]["amount"])) if res.data else Decimal(0)


async def scrapes_left(db: AsyncClient, monthly_max: int) -> int:
    return max(0, monthly_max - int(await total(db, SCRAPES)))


async def jev_budget_left(db: AsyncClient, monthly_usd: float) -> Decimal:
    return max(Decimal(0), Decimal(str(monthly_usd)) - await total(db, JEV_USD))
