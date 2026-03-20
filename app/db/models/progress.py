from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WeightLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "weight_logs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class BodyMeasurement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "body_measurements"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    waist_cm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    chest_cm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    arm_cm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    thigh_cm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    hip_cm: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    body_fat_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class StrengthLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "strength_logs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False)
    weight_kg: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_1rm: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ProgressPhoto(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "progress_photos"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    photo_type: Mapped[str] = mapped_column(String(40), default="front", nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private", nullable=False)


class WeeklyCheckin(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "weekly_checkins"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hunger: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adherence_training: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adherence_nutrition: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class GoalHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "goal_history"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    old_goal: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_goal: Mapped[str] = mapped_column(String(40), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class HealthMetricSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "health_metric_snapshots"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    bmi: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    bmr: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    tdee: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    snapshot_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
