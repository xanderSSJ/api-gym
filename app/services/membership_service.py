from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import BillingPeriod, FeatureKey, MembershipStatus
from app.db.models.membership import MembershipEntitlement, MembershipPlan, UserMembership


@dataclass
class MembershipContext:
    tier: str
    is_premium: bool
    status: str
    plan_code: str
    plan_name: str
    membership_id: str | None


async def get_or_create_free_membership(session: AsyncSession, user_id: str) -> UserMembership:
    stmt = (
        select(UserMembership, MembershipPlan)
        .join(MembershipPlan, MembershipPlan.id == UserMembership.plan_id)
        .where(UserMembership.user_id == user_id)
        .order_by(UserMembership.ends_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row:
        membership, _plan = row
        return membership

    free_plan = await ensure_plan_exists(
        session,
        code="free",
        name="Free",
        price=0,
        billing_period=BillingPeriod.MONTHLY,
    )
    starts_at = datetime.now(UTC)
    membership = UserMembership(
        user_id=user_id,
        plan_id=free_plan.id,
        status=MembershipStatus.ACTIVE,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(days=3650),
        auto_renew=True,
        provider="internal",
    )
    session.add(membership)
    await session.flush()
    return membership


async def get_membership_context(session: AsyncSession, user_id: str) -> MembershipContext:
    stmt = (
        select(UserMembership, MembershipPlan)
        .join(MembershipPlan, MembershipPlan.id == UserMembership.plan_id)
        .where(UserMembership.user_id == user_id)
        .order_by(UserMembership.ends_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        membership = await get_or_create_free_membership(session, user_id)
        stmt = select(MembershipPlan).where(MembershipPlan.id == membership.plan_id)
        plan = (await session.execute(stmt)).scalar_one()
        return MembershipContext(
            tier=plan.code,
            is_premium=plan.code != "free" and membership.status == MembershipStatus.ACTIVE,
            status=membership.status.value,
            plan_code=plan.code,
            plan_name=plan.name,
            membership_id=membership.id,
        )

    membership, plan = row
    is_active = membership.status == MembershipStatus.ACTIVE and membership.ends_at >= datetime.now(UTC)
    tier = plan.code if is_active else "free"
    return MembershipContext(
        tier=tier,
        is_premium=tier != "free",
        status=membership.status.value,
        plan_code=plan.code,
        plan_name=plan.name,
        membership_id=membership.id,
    )


async def get_current_membership_record(
    session: AsyncSession, user_id: str
) -> tuple[UserMembership, MembershipPlan]:
    stmt = (
        select(UserMembership, MembershipPlan)
        .join(MembershipPlan, MembershipPlan.id == UserMembership.plan_id)
        .where(UserMembership.user_id == user_id)
        .order_by(UserMembership.ends_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row:
        return row
    membership = await get_or_create_free_membership(session, user_id)
    plan = (await session.execute(select(MembershipPlan).where(MembershipPlan.id == membership.plan_id))).scalar_one()
    return membership, plan


async def get_entitlements_for_tier(
    session: AsyncSession, tier: str
) -> dict[FeatureKey, MembershipEntitlement]:
    stmt = select(MembershipPlan).where(MembershipPlan.code == tier).limit(1)
    plan = (await session.execute(stmt)).scalar_one_or_none()
    if plan is None and tier != "free":
        stmt = select(MembershipPlan).where(MembershipPlan.code == "free").limit(1)
        plan = (await session.execute(stmt)).scalar_one_or_none()
    if plan is None:
        return {}
    rows = (
        await session.execute(select(MembershipEntitlement).where(MembershipEntitlement.plan_id == plan.id))
    ).scalars()
    return {row.feature_key: row for row in rows}


async def ensure_plan_exists(
    session: AsyncSession,
    code: str,
    name: str,
    price: float,
    billing_period: BillingPeriod = BillingPeriod.MONTHLY,
) -> MembershipPlan:
    stmt = select(MembershipPlan).where(MembershipPlan.code == code).limit(1)
    plan = (await session.execute(stmt)).scalar_one_or_none()
    if plan:
        return plan
    plan = MembershipPlan(
        code=code,
        name=name,
        price=price,
        billing_period=billing_period,
        currency="USD",
        is_active=True,
    )
    session.add(plan)
    await session.flush()
    return plan


async def create_or_replace_membership(
    session: AsyncSession,
    user_id: str,
    plan_code: str,
    provider: str,
) -> tuple[UserMembership, MembershipPlan]:
    stmt = select(MembershipPlan).where(and_(MembershipPlan.code == plan_code, MembershipPlan.is_active.is_(True)))
    plan = (await session.execute(stmt)).scalar_one_or_none()
    if plan is None:
        raise ValueError("Invalid plan_code")

    current_stmt = select(UserMembership).where(UserMembership.user_id == user_id).order_by(UserMembership.ends_at.desc())
    current = (await session.execute(current_stmt)).scalars().first()
    now = datetime.now(UTC)
    if current:
        current.status = MembershipStatus.CANCELED
        current.canceled_at = now

    duration_days = 30
    if plan.billing_period == BillingPeriod.QUARTERLY:
        duration_days = 90
    elif plan.billing_period == BillingPeriod.YEARLY:
        duration_days = 365

    membership = UserMembership(
        user_id=user_id,
        plan_id=plan.id,
        status=MembershipStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=duration_days),
        provider=provider,
        auto_renew=True,
    )
    session.add(membership)
    await session.flush()
    return membership, plan
