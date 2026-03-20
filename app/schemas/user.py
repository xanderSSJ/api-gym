from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.db.models.enums import (
    ActivityLevel,
    BudgetLevel,
    ExperienceLevel,
    MainGoal,
    MembershipStatus,
    SexForCalculation,
    TrainingEnvironment,
)


class UserPhysicalProfileIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    birth_date: date | None = None
    sex_for_calculation: SexForCalculation | None = None
    height_cm: int | None = Field(default=None, ge=120, le=230)
    current_weight_kg: float | None = Field(default=None, ge=30, le=350)
    target_weight_kg: float | None = Field(default=None, ge=30, le=350)


class UserTrainingPreferenceIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    main_goal: MainGoal | None = None
    experience_level: ExperienceLevel | None = None
    frequency_per_week: int | None = Field(default=None, ge=2, le=7)
    minutes_per_session: int | None = Field(default=None, ge=20, le=180)
    training_environment: TrainingEnvironment | None = None
    available_equipment: list[str] = Field(default_factory=list)


class UserNutritionPreferenceIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    activity_level: ActivityLevel | None = None
    meals_per_day: int | None = Field(default=None, ge=2, le=6)
    budget_level: BudgetLevel | None = None
    allergies: list[str] = Field(default_factory=list)
    dietary_restrictions: list[str] = Field(default_factory=list)
    excluded_foods: list[str] = Field(default_factory=list)
    training_schedule: dict[str, Any] = Field(default_factory=dict)


class UserSafetyProfileIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    injuries: list[str] = Field(default_factory=list)
    medical_conditions: list[str] = Field(default_factory=list)
    requires_professional_clearance: bool = False


class UserProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    physical_profile: UserPhysicalProfileIn | None = None
    training_preferences: UserTrainingPreferenceIn | None = None
    nutrition_preferences: UserNutritionPreferenceIn | None = None
    safety_profile: UserSafetyProfileIn | None = None


class UserProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: str
    full_name: str
    email: EmailStr
    email_verified_at: datetime | None
    physical_profile: UserPhysicalProfileIn | None
    training_preferences: UserTrainingPreferenceIn | None
    nutrition_preferences: UserNutritionPreferenceIn | None
    safety_profile: UserSafetyProfileIn | None


class UserStateResponse(BaseModel):
    membership_status: MembershipStatus | str
    membership_plan_code: str | None = None
    is_premium: bool
    profile_completion_pct: int = Field(ge=0, le=100)
    warnings: list[str] = Field(default_factory=list)


class LimitsFeatureItem(BaseModel):
    feature_key: str
    quota: int
    used: int
    remaining: int
    window: str
    cooldown_days: int = 0
    next_available_at: datetime | None = None


class UserLimitsResponse(BaseModel):
    tier: str
    features: list[LimitsFeatureItem]


def _clean_list_strings(values: list[str]) -> list[str]:
    return [value.strip().lower() for value in values if value and value.strip()]


class OnboardingDataRequest(BaseModel):
    physical_profile: UserPhysicalProfileIn
    training_preferences: UserTrainingPreferenceIn
    nutrition_preferences: UserNutritionPreferenceIn
    safety_profile: UserSafetyProfileIn

    @field_validator("safety_profile")
    @classmethod
    def ensure_safety_lists(cls, value: UserSafetyProfileIn) -> UserSafetyProfileIn:
        value.injuries = _clean_list_strings(value.injuries)
        value.medical_conditions = _clean_list_strings(value.medical_conditions)
        return value
