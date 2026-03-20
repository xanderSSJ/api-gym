from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models.enums import MembershipStatus
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.membership import (
    MembershipCancelResponse,
    MembershipCurrentResponse,
    MembershipSubscribeRequest,
    MembershipSubscribeResponse,
)
from app.services.membership_service import (
    create_or_replace_membership,
    get_current_membership_record,
    get_membership_context,
)

router = APIRouter(prefix="/memberships", tags=["memberships"])


@router.get("/current", response_model=MembershipCurrentResponse)
async def current_membership(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MembershipCurrentResponse:
    membership, plan = await get_current_membership_record(session, current_user.id)
    context = await get_membership_context(session, current_user.id)
    return MembershipCurrentResponse(
        membership_id=membership.id,
        plan_code=plan.code,
        plan_name=plan.name,
        status=membership.status,
        starts_at=membership.starts_at,
        ends_at=membership.ends_at,
        auto_renew=membership.auto_renew,
        is_premium=context.is_premium,
    )


@router.post("/subscribe", response_model=MembershipSubscribeResponse, status_code=status.HTTP_201_CREATED)
async def subscribe_membership(
    payload: MembershipSubscribeRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MembershipSubscribeResponse:
    membership, _plan = await create_or_replace_membership(
        session=session,
        user_id=current_user.id,
        plan_code=payload.plan_code,
        provider=payload.provider,
    )
    await session.commit()
    return MembershipSubscribeResponse(
        membership_id=membership.id,
        status=membership.status,
        checkout_reference=f"checkout_{membership.id}",
    )


@router.post("/cancel", response_model=MembershipCancelResponse)
async def cancel_membership(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MembershipCancelResponse:
    membership, _plan = await get_current_membership_record(session, current_user.id)
    membership.status = MembershipStatus.CANCELED
    membership.canceled_at = datetime.now(UTC)
    membership.auto_renew = False
    await session.commit()
    return MembershipCancelResponse(
        membership_id=membership.id,
        status=membership.status,
        canceled_at=membership.canceled_at,
    )
