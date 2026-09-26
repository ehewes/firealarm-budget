"""Purchase intents, as the Eden confirm page sees them. Agents create them over MCP.

Only the signed-in owner can see, confirm or cancel an intent, and confirming needs a
real account (rule 2). No session code or agent token can reach these.
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from supabase import AsyncClient

from app.auth import User
from app.config import Settings
from app.deps import account_user, current_user, get_db, get_settings
from app.models import PurchaseOut
from app.services import purchases

router = APIRouter(prefix="/purchase-intents", tags=["purchases"], include_in_schema=False)


@router.get("/{intent_id}", response_model=PurchaseOut)
async def get_intent(
    intent_id: UUID,
    user: User = Depends(current_user),
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PurchaseOut:
    intent = await purchases.load_intent(db, str(intent_id), user.id)
    return await purchases.view(db, settings, intent)


@router.post("/{intent_id}/confirm", response_model=PurchaseOut)
async def confirm_intent(
    intent_id: UUID,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(account_user),
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PurchaseOut:
    """Re-check prices and stock, then issue the card and check out. 409 price_changed on change."""
    return await purchases.confirm(
        db, settings, request.app.state.fetcher, user, str(intent_id), background
    )


@router.post("/{intent_id}/cancel", response_model=PurchaseOut)
async def cancel_intent(
    intent_id: UUID,
    user: User = Depends(current_user),
    db: AsyncClient = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> PurchaseOut:
    return await purchases.cancel(db, settings, user, str(intent_id))
