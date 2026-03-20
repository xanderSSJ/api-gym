from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import BillingPeriod, FeatureKey, MembershipStatus, PaymentStatus, WindowUnit


class MembershipPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "membership_plans"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    billing_period: Mapped[BillingPeriod] = mapped_column(Enum(BillingPeriod), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)


class MembershipEntitlement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "membership_entitlements"
    __table_args__ = (UniqueConstraint("plan_id", "feature_key", name="uq_entitlement_plan_feature"),)

    plan_id: Mapped[str] = mapped_column(
        ForeignKey("membership_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    feature_key: Mapped[FeatureKey] = mapped_column(Enum(FeatureKey), nullable=False)
    quota: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    window_unit: Mapped[WindowUnit] = mapped_column(Enum(WindowUnit), nullable=False)
    window_size: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cooldown_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requires_verified_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UserMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_memberships"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("membership_plans.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        Enum(MembershipStatus), default=MembershipStatus.PENDING_PAYMENT, nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider: Mapped[str] = mapped_column(String(60), default="stripe", nullable=False)
    provider_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class PaymentTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_transactions"

    user_membership_id: Mapped[str] = mapped_column(
        ForeignKey("user_memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invoice_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class PaymentWebhookEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_provider_event"),
    )

    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
