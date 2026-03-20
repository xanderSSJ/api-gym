from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import forbidden, too_many_requests
from app.db.models.enums import FeatureKey
from app.db.models.membership import MembershipEntitlement
from app.db.models.usage import UsageEvent, UserFeatureCounter
from app.services.membership_service import get_entitlements_for_tier, get_membership_context


def _window_bounds(window_unit: str, window_size: int) -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    if window_unit == "day":
        end = now + timedelta(days=window_size)
    elif window_unit == "week":
        end = now + timedelta(weeks=window_size)
    elif window_unit == "month":
        end = now + timedelta(days=30 * window_size)
    else:
        end = now + timedelta(days=window_size)
    return now, end


async def get_feature_counter(
    session: AsyncSession,
    user_id: str,
    feature_key: FeatureKey,
    entitlement: MembershipEntitlement,
) -> UserFeatureCounter:
    now = datetime.now(UTC)
    stmt = (
        select(UserFeatureCounter)
        .where(
            and_(
                UserFeatureCounter.user_id == user_id,
                UserFeatureCounter.feature_key == feature_key,
                UserFeatureCounter.window_end >= now,
            )
        )
        .order_by(UserFeatureCounter.window_end.desc())
        .limit(1)
    )
    counter = (await session.execute(stmt)).scalar_one_or_none()
    if counter:
        return counter

    window_start, window_end = _window_bounds(entitlement.window_unit.value, entitlement.window_size)
    counter = UserFeatureCounter(
        user_id=user_id,
        feature_key=feature_key,
        window_start=window_start,
        window_end=window_end,
        used_units=0,
    )
    session.add(counter)
    await session.flush()
    return counter


async def enforce_and_consume_feature(
    session: AsyncSession,
    user_id: str,
    feature_key: FeatureKey,
    consumed_units: int = 1,
    ip_hash: str | None = None,
    device_id: str | None = None,
) -> None:
    membership = await get_membership_context(session, user_id)
    entitlements = await get_entitlements_for_tier(session, membership.tier)
    entitlement = entitlements.get(feature_key)
    if entitlement is None:
        raise forbidden("This feature is not available for your membership tier.")

    counter = await get_feature_counter(session, user_id, feature_key, entitlement)
    if counter.used_units + consumed_units > entitlement.quota:
        raise too_many_requests("Feature quota exceeded for current window.")

    counter.used_units += consumed_units
    session.add(
        UsageEvent(
            user_id=user_id,
            feature_key=feature_key,
            membership_tier=membership.tier,
            status="consumed",
            consumed_units=consumed_units,
            ip_hash=ip_hash,
            device_id=device_id,
            metadata_json={
                "window_start": counter.window_start.isoformat(),
                "window_end": counter.window_end.isoformat(),
            },
        )
    )


async def list_counters(session: AsyncSession, user_id: str) -> tuple[str, list[UserFeatureCounter]]:
    membership = await get_membership_context(session, user_id)
    rows = (
        await session.execute(
            select(UserFeatureCounter)
            .where(UserFeatureCounter.user_id == user_id)
            .order_by(UserFeatureCounter.window_end.desc())
            .limit(50)
        )
    ).scalars()
    return membership.tier, list(rows)
