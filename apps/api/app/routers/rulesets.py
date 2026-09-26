"""Saved rulesets (any signed-in user, anonymous included) and plain-language rule parsing."""

from fastapi import APIRouter, Depends, Response
from supabase import AsyncClient

from app.auth import User
from app.config import Settings
from app.deps import current_user, get_db, get_settings
from app.errors import EdenError
from app.models import Rules, RulesetIn, RulesetOut, RulesetPatch, RulesParseIn
from app.services import grok
from app.services.rules import parse_text

router = APIRouter(tags=["rulesets"])


def _out(row: dict) -> RulesetOut:
    return RulesetOut(
        id=row["id"],
        name=row["name"],
        rules=Rules.model_validate(row["rules"] or {}),
        is_default=row["is_default"],
        created_at=row["created_at"],
    )


async def _clear_default(db: AsyncClient, user_id: str) -> None:
    """Only one default per user (enforced by an index too): unset the old one first."""
    await (
        db.table("rulesets")
        .update({"is_default": False})
        .eq("user_id", user_id)
        .eq("is_default", True)
        .execute()
    )


@router.get("/rulesets", response_model=list[RulesetOut])
async def list_rulesets(
    user: User = Depends(current_user), db: AsyncClient = Depends(get_db)
) -> list[RulesetOut]:
    res = (
        await db.table("rulesets").select("*").eq("user_id", user.id).order("created_at").execute()
    )
    return [_out(row) for row in res.data]


@router.post("/rulesets", status_code=201, response_model=RulesetOut)
async def create_ruleset(
    body: RulesetIn, user: User = Depends(current_user), db: AsyncClient = Depends(get_db)
) -> RulesetOut:
    if body.is_default:
        await _clear_default(db, user.id)
    res = (
        await db.table("rulesets")
        .insert(
            {
                "user_id": user.id,
                "name": body.name,
                "rules": body.rules.model_dump(exclude_none=True),
                "is_default": body.is_default,
            }
        )
        .execute()
    )
    return _out(res.data[0])


@router.patch("/rulesets/{ruleset_id}", response_model=RulesetOut)
async def update_ruleset(
    ruleset_id: str,
    body: RulesetPatch,
    user: User = Depends(current_user),
    db: AsyncClient = Depends(get_db),
) -> RulesetOut:
    update = body.model_dump(exclude_unset=True)
    if "rules" in update and body.rules is not None:
        update["rules"] = body.rules.model_dump(exclude_none=True)
    if update.get("is_default"):
        await _clear_default(db, user.id)
    res = (
        await db.table("rulesets")
        .update(update)
        .eq("id", ruleset_id)
        .eq("user_id", user.id)
        .execute()
    )
    if not res.data:
        raise EdenError("ruleset_not_found", "That ruleset doesn't exist.", 404)
    return _out(res.data[0])


@router.delete("/rulesets/{ruleset_id}", status_code=204)
async def delete_ruleset(
    ruleset_id: str, user: User = Depends(current_user), db: AsyncClient = Depends(get_db)
) -> Response:
    await db.table("rulesets").delete().eq("id", ruleset_id).eq("user_id", user.id).execute()
    return Response(status_code=204)


@router.post("/rules/parse", response_model=Rules)
async def parse_rules(
    body: RulesParseIn,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> Rules:
    """Plain language → a rules object: the Grok API if configured, else a deterministic parser."""
    return await grok.parse_rules(settings, body.text) or parse_text(body.text)
