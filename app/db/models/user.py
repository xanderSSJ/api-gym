from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import (
    ActivityLevel,
    BudgetLevel,
    ExperienceLevel,
    MainGoal,
    MeasurementRiskLevel,
    SexForCalculation,
    TrainingEnvironment,
    UserStatus,
)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.ACTIVE, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    physical_profile: Mapped["UserPhysicalProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    training_preferences: Mapped["UserTrainingPreference"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    nutrition_preferences: Mapped["UserNutritionPreference"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    safety_profile: Mapped["UserSafetyProfile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserPhysicalProfile(TimestampMixin, Base):
    __tablename__ = "user_physical_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    birth_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    sex_for_calculation: Mapped[SexForCalculation | None] = mapped_column(
        Enum(SexForCalculation), nullable=True
    )
    height_cm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_weight_kg: Mapped[float | None] = mapped_column(nullable=True)
    target_weight_kg: Mapped[float | None] = mapped_column(nullable=True)

    user: Mapped[User] = relationship(back_populates="physical_profile")


class UserTrainingPreference(TimestampMixin, Base):
    __tablename__ = "user_training_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    main_goal: Mapped[MainGoal | None] = mapped_column(Enum(MainGoal), nullable=True)
    experience_level: Mapped[ExperienceLevel | None] = mapped_column(Enum(ExperienceLevel), nullable=True)
    frequency_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minutes_per_session: Mapped[int | None] = mapped_column(Integer, nullable=True)
    training_environment: Mapped[TrainingEnvironment | None] = mapped_column(
        Enum(TrainingEnvironment), nullable=True
    )
    available_equipment: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)

    user: Mapped[User] = relationship(back_populates="training_preferences")


class UserNutritionPreference(TimestampMixin, Base):
    __tablename__ = "user_nutrition_preferences"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    activity_level: Mapped[ActivityLevel | None] = mapped_column(Enum(ActivityLevel), nullable=True)
    meals_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    budget_level: Mapped[BudgetLevel | None] = mapped_column(Enum(BudgetLevel), nullable=True)
    allergies: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    dietary_restrictions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    excluded_foods: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    training_schedule: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="nutrition_preferences")


class UserSafetyProfile(TimestampMixin, Base):
    __tablename__ = "user_safety_profiles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    injuries: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    medical_conditions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    risk_level: Mapped[MeasurementRiskLevel] = mapped_column(
        Enum(MeasurementRiskLevel), default=MeasurementRiskLevel.NORMAL, nullable=False
    )
    requires_professional_clearance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="safety_profile")


class UserConsent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_consents"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[str] = mapped_column(String(30), nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)


class AuthSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "auth_sessions"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)


class PasswordResetToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "password_reset_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailVerificationToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_verification_tokens"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserSecurityEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_security_events"

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_agent_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
