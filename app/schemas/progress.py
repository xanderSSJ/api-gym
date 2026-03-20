from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class WeightLogCreate(BaseModel):
    weight_kg: float = Field(ge=30, le=350)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MeasurementCreate(BaseModel):
    waist_cm: float | None = Field(default=None, ge=20, le=250)
    chest_cm: float | None = Field(default=None, ge=20, le=250)
    arm_cm: float | None = Field(default=None, ge=10, le=100)
    thigh_cm: float | None = Field(default=None, ge=20, le=120)
    hip_cm: float | None = Field(default=None, ge=20, le=250)
    body_fat_pct: float | None = Field(default=None, ge=2, le=70)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StrengthLogCreate(BaseModel):
    exercise_id: str
    weight_kg: float = Field(ge=0, le=800)
    reps: int = Field(ge=1, le=60)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WeeklyCheckinCreate(BaseModel):
    energy: int | None = Field(default=None, ge=1, le=10)
    sleep: int | None = Field(default=None, ge=1, le=10)
    hunger: int | None = Field(default=None, ge=1, le=10)
    adherence_training: int | None = Field(default=None, ge=1, le=10)
    adherence_nutrition: int | None = Field(default=None, ge=1, le=10)
    notes: str | None = Field(default=None, max_length=400)
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProgressPhotoPresignRequest(BaseModel):
    photo_type: str = Field(default="front", max_length=40)
    extension: str = Field(default="jpg", pattern="^(jpg|jpeg|png|webp)$")


class ProgressPhotoPresignResponse(BaseModel):
    upload_url: str
    storage_key: str
    expires_in_seconds: int = 600


class ProgressSummaryResponse(BaseModel):
    latest_weight_kg: float | None
    weekly_weight_delta_kg: float | None
    latest_bmi: float | None
    latest_bmr: float | None
    latest_tdee: float | None
    strength_prs: dict[str, float]
