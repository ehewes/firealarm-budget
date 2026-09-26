"""The signed-in shopper's own rule. One default ruleset per user for now."""

from fastapi import APIRouter, Depends, Response
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from api.deps import get_pool, required_user
from api.models import RulesetIn, RulesetOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/ruleset", response_model=RulesetOut)
async def get_ruleset(
    user_id: str = Depends(required_user), pool: AsyncConnectionPool = Depends(get_pool)
) -> RulesetOut:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "select rules from public.rulesets where user_id = %s and is_default", (user_id,)
        )
        row = await cur.fetchone()
    text = (row["rules"] or {}).get("text") if row else None
    return RulesetOut(rule=text if isinstance(text, str) and text.strip() else None)


@router.put("/ruleset", response_model=RulesetOut)
async def put_ruleset(
    body: RulesetIn,
    user_id: str = Depends(required_user),
    pool: AsyncConnectionPool = Depends(get_pool),
) -> RulesetOut:
    rule = body.rule.strip()
    async with pool.connection() as conn:
        await conn.execute(
            """
            insert into public.rulesets (user_id, name, rules, is_default)
            values (%s, 'Default', %s, true)
            on conflict (user_id) where is_default do update set rules = excluded.rules
            """,
            (user_id, Jsonb({"text": rule})),
        )
    return RulesetOut(rule=rule)


@router.delete("/ruleset", status_code=204)
async def delete_ruleset(
    user_id: str = Depends(required_user), pool: AsyncConnectionPool = Depends(get_pool)
) -> Response:
    async with pool.connection() as conn:
        await conn.execute(
            "delete from public.rulesets where user_id = %s and is_default", (user_id,)
        )
    return Response(status_code=204)
