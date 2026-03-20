from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import ExperienceLevel, GenerationJobStatus, MainGoal, PlanStatus, TrainingEnvironment


class MuscleGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "muscle_groups"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("muscle_groups.id"), nullable=True)


class Exercise(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exercises"

    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    movement_pattern: Mapped[str] = mapped_column(String(80), nullable=False)
    difficulty: Mapped[ExperienceLevel] = mapped_column(Enum(ExperienceLevel), nullable=False)
    equipment_type: Mapped[str] = mapped_column(String(80), nullable=False)
    contraindications: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ExerciseMuscleGroup(TimestampMixin, Base):
    __tablename__ = "exercise_muscle_groups"
    __table_args__ = (UniqueConstraint("exercise_id", "muscle_group_id", name="uq_exercise_muscle"),)

    exercise_id: Mapped[str] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), primary_key=True
    )
    muscle_group_id: Mapped[str] = mapped_column(
        ForeignKey("muscle_groups.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), default="primary", nullable=False)


class RoutineTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "routine_templates"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    goal: Mapped[MainGoal] = mapped_column(Enum(MainGoal), nullable=False, index=True)
    level: Mapped[ExperienceLevel] = mapped_column(Enum(ExperienceLevel), nullable=False, index=True)
    frequency_per_week: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    environment: Mapped[TrainingEnvironment] = mapped_column(Enum(TrainingEnvironment), nullable=False)
    template_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TrainingPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_plans"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus), default=PlanStatus.ACTIVE, nullable=False)
    goal: Mapped[MainGoal] = mapped_column(Enum(MainGoal), nullable=False)
    level: Mapped[ExperienceLevel] = mapped_column(Enum(ExperienceLevel), nullable=False)
    weeks: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    replaces_plan_id: Mapped[str | None] = mapped_column(ForeignKey("training_plans.id"), nullable=True)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(40), default="v1", nullable=False)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrainingPlanDay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_plan_days"
    __table_args__ = (UniqueConstraint("training_plan_id", "day_number", name="uq_plan_day"),)

    training_plan_id: Mapped[str] = mapped_column(
        ForeignKey("training_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    focus: Mapped[str] = mapped_column(String(120), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrainingDayExercise(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_day_exercises"
    __table_args__ = (UniqueConstraint("training_plan_day_id", "order_no", name="uq_day_ex_order"),)

    training_plan_day_id: Mapped[str] = mapped_column(
        ForeignKey("training_plan_days.id", ondelete="CASCADE"), index=True, nullable=False
    )
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id", ondelete="RESTRICT"), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sets: Mapped[int] = mapped_column(Integer, nullable=False)
    reps_min: Mapped[int] = mapped_column(Integer, nullable=False)
    reps_max: Mapped[int] = mapped_column(Integer, nullable=False)
    rest_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    rir: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class TrainingGenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "training_generation_jobs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[GenerationJobStatus] = mapped_column(
        Enum(GenerationJobStatus), default=GenerationJobStatus.QUEUED, nullable=False
    )
    request_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result_plan_id: Mapped[str | None] = mapped_column(ForeignKey("training_plans.id"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
