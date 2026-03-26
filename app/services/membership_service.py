from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import bad_request
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


def _is_membership_active(membership: UserMembership, now: datetime) -> bool:
    return (
        membership.status == MembershipStatus.ACTIVE
        and membership.starts_at <= now
        and membership.ends_at >= now
    )


async def _membership_rows(
    session: AsyncSession, user_id: str
) -> list[tuple[UserMembership, MembershipPlan]]:
    rows = (
        await session.execute(
            select(UserMembership, MembershipPlan)
            .join(MembershipPlan, MembershipPlan.id == UserMembership.plan_id)
            .where(UserMembership.user_id == user_id)
            .order_by(UserMembership.starts_at.desc(), UserMembership.created_at.desc())
        )
    ).all()
    return list(rows)


def _pick_active_membership_row(
    rows: list[tuple[UserMembership, MembershipPlan]],
) -> tuple[UserMembership, MembershipPlan] | None:
    now = datetime.now(UTC)
    active_rows = [row for row in rows if _is_membership_active(row[0], now)]
    if not active_rows:
        return None
    return max(
        active_rows,
        key=lambda row: (
            row[0].starts_at,
            row[0].created_at or row[0].starts_at,
            row[0].ends_at,
        ),
    )


async def get_or_create_free_membership(session: AsyncSession, user_id: str) -> UserMembership:
    rows = await _membership_rows(session, user_id)
    active = _pick_active_membership_row(rows)
    if active:
        membership, _plan = active
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


async def replace_with_free_membership(
    session: AsyncSession,
    user_id: str,
    provider: str = "internal",
) -> UserMembership:
    free_plan = await ensure_plan_exists(
        session,
        code="free",
        name="Free",
        price=0,
        billing_period=BillingPeriod.MONTHLY,
    )

    now = datetime.now(UTC)
    replaceable_statuses = [
        MembershipStatus.ACTIVE,
        MembershipStatus.PENDING_PAYMENT,
        MembershipStatus.PAST_DUE,
        MembershipStatus.SUSPENDED,
    ]
    await session.execute(
        update(UserMembership)
        .where(UserMembership.user_id == user_id, UserMembership.status.in_(replaceable_statuses))
        .values(
            status=MembershipStatus.CANCELED,
            canceled_at=now,
            auto_renew=False,
        )
    )

    membership = UserMembership(
        user_id=user_id,
        plan_id=free_plan.id,
        status=MembershipStatus.ACTIVE,
        starts_at=now,
        ends_at=now + timedelta(days=3650),
        auto_renew=True,
        provider=provider,
    )
    session.add(membership)
    await session.flush()
    return membership


async def get_membership_context(session: AsyncSession, user_id: str) -> MembershipContext:
    membership, plan = await get_current_membership_record(session, user_id)
    is_active = _is_membership_active(membership, datetime.now(UTC))
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
    rows = await _membership_rows(session, user_id)
    active = _pick_active_membership_row(rows)
    if active:
        return active
    membership = await get_or_create_free_membership(session, user_id)
    plan = (await session.execute(select(MembershipPlan).where(MembershipPlan.id == membership.plan_id))).scalar_one()
    return membership, plan


async def get_entitlements_for_tier(
    session: AsyncSession, tier: str
) -> dict[FeatureKey, MembershipEntitlement]:
    candidate_codes = [tier]
    if tier.startswith("premium_"):
        candidate_codes.append("premium_monthly")
    if tier != "free":
        candidate_codes.append("free")

    seen: set[str] = set()
    for code in candidate_codes:
        if code in seen:
            continue
        seen.add(code)
        plan = (
            await session.execute(select(MembershipPlan).where(MembershipPlan.code == code).limit(1))
        ).scalar_one_or_none()
        if plan is None:
            continue
        rows = (
            await session.execute(select(MembershipEntitlement).where(MembershipEntitlement.plan_id == plan.id))
        ).scalars()
        entitlements = {row.feature_key: row for row in rows}
        if entitlements:
            return entitlements
    return {}


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
        raise bad_request("Invalid plan_code.")

    now = datetime.now(UTC)
    replaceable_statuses = [
        MembershipStatus.ACTIVE,
        MembershipStatus.PENDING_PAYMENT,
        MembershipStatus.PAST_DUE,
        MembershipStatus.SUSPENDED,
    ]
    await session.execute(
        update(UserMembership)
        .where(UserMembership.user_id == user_id, UserMembership.status.in_(replaceable_statuses))
        .values(
            status=MembershipStatus.CANCELED,
            canceled_at=now,
            auto_renew=False,
        )
    )

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
