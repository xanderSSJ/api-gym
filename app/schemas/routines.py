from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.enums import ExperienceLevel, MainGoal, PlanStatus, TrainingEnvironment


class RoutineGenerationRequest(BaseModel):
    goal: MainGoal
    level: ExperienceLevel
    frequency_per_week: int = Field(ge=2, le=7)
    minutes_per_session: int = Field(ge=20, le=180)
    training_environment: TrainingEnvironment
    available_equipment: list[str] = Field(default_factory=list)
    weeks: int = Field(default=6, ge=2, le=16)


class DayExerciseResponse(BaseModel):
    exercise_name: str
    sets: int
    reps_min: int
    reps_max: int
    rest_seconds: int
    notes: str | None = None


class RoutineDayResponse(BaseModel):
    day_number: int
    focus: str
    exercises: list[DayExerciseResponse]
    notes: str | None = None


class RoutinePlanResponse(BaseModel):
    plan_id: str
    name: str
    goal: MainGoal
    level: ExperienceLevel
    weeks: int
    status: PlanStatus
    created_at: datetime
    recommendations: list[str]
    days: list[RoutineDayResponse]


class RoutineHistoryItem(BaseModel):
    plan_id: str
    name: str
    status: PlanStatus
    goal: MainGoal
    level: ExperienceLevel
    weeks: int
    created_at: datetime
    is_current: bool


class GenerationJobResponse(BaseModel):
    job_id: str
    status: str
    estimated_wait_seconds: int = 5


class RegenerateRoutineRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)
