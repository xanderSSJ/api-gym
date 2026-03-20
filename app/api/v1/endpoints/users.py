from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models.enums import FeatureKey
from app.db.models.usage import UserFeatureCounter
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.common import MessageResponse
from app.schemas.user import (
    LimitsFeatureItem,
    OnboardingDataRequest,
    UserLimitsResponse,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserStateResponse,
)
from app.services.membership_service import get_entitlements_for_tier, get_membership_context
from app.services.user_service import complete_onboarding, update_profile, user_state

router = APIRouter(prefix="/users", tags=["users"])


def _serialize_profile(user: User) -> UserProfileResponse:
    return UserProfileResponse(
        user_id=user.id,
        full_name=user.full_name,
        email=user.email,
        email_verified_at=user.email_verified_at,
        physical_profile=user.physical_profile,
        training_preferences=user.training_preferences,
        nutrition_preferences=user.nutrition_preferences,
        safety_profile=user.safety_profile,
    )


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> UserProfileResponse:
    return _serialize_profile(current_user)


@router.patch("/me", response_model=UserProfileResponse)
async def patch_me(
    payload: UserProfileUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    user = await update_profile(session, current_user, payload)
    await session.commit()
    return _serialize_profile(user)


@router.post("/me/onboarding", response_model=UserProfileResponse)
async def onboarding(
    payload: OnboardingDataRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    user = await complete_onboarding(session, current_user, payload)
    await session.commit()
    return _serialize_profile(user)


@router.get("/me/state", response_model=UserStateResponse)
async def me_state(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> UserStateResponse:
    state = await user_state(session, current_user)
    return UserStateResponse(**state)


@router.get("/me/limits", response_model=UserLimitsResponse)
async def me_limits(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> UserLimitsResponse:
    membership = await get_membership_context(session, current_user.id)
    entitlements = await get_entitlements_for_tier(session, membership.tier)
    features: list[LimitsFeatureItem] = []
    for feature_key, entitlement in entitlements.items():
        counter_stmt = (
            select(UserFeatureCounter)
            .where(
                and_(
                    UserFeatureCounter.user_id == current_user.id,
                    UserFeatureCounter.feature_key == feature_key,
                )
            )
            .order_by(UserFeatureCounter.window_end.desc())
            .limit(1)
        )
        counter = (await session.execute(counter_stmt)).scalar_one_or_none()
        used = counter.used_units if counter else 0
        features.append(
            LimitsFeatureItem(
                feature_key=feature_key.value,
                quota=entitlement.quota,
                used=used,
                remaining=max(entitlement.quota - used, 0),
                window=f"{entitlement.window_size}_{entitlement.window_unit.value}",
                cooldown_days=entitlement.cooldown_days,
                next_available_at=counter.window_end if counter else None,
            )
        )
    return UserLimitsResponse(tier=membership.tier, features=features)


@router.get("/me/history", response_model=dict)
async def me_history(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    return {
        "data": {
            "routines": f"/v1/routines/history?user_id={current_user.id}",
            "nutrition": f"/v1/nutrition/plans/history?user_id={current_user.id}",
            "progress": f"/v1/progress/summary?user_id={current_user.id}",
        }
    }


@router.get("/me/disclaimer", response_model=MessageResponse)
async def disclaimer() -> MessageResponse:
    return MessageResponse(
        message=(
            "Este sistema no sustituye atencion medica, nutricional ni entrenamiento profesional. "
            "Si tienes lesiones o condiciones especiales, consulta un especialista."
        )
    )
