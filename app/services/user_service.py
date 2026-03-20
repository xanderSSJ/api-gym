from __future__ import annotations

from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import (
    User,
    UserNutritionPreference,
    UserPhysicalProfile,
    UserSafetyProfile,
    UserTrainingPreference,
)
from app.db.models.enums import MeasurementRiskLevel
from app.schemas.user import (
    OnboardingDataRequest,
    UserNutritionPreferenceIn,
    UserPhysicalProfileIn,
    UserProfileUpdateRequest,
    UserSafetyProfileIn,
    UserTrainingPreferenceIn,
)
from app.services.membership_service import get_membership_context


def _apply_physical_profile(model: UserPhysicalProfile, payload: UserPhysicalProfileIn) -> None:
    model.birth_date = payload.birth_date
    model.sex_for_calculation = payload.sex_for_calculation
    model.height_cm = payload.height_cm
    model.current_weight_kg = payload.current_weight_kg
    model.target_weight_kg = payload.target_weight_kg


def _apply_training_preferences(model: UserTrainingPreference, payload: UserTrainingPreferenceIn) -> None:
    model.main_goal = payload.main_goal
    model.experience_level = payload.experience_level
    model.frequency_per_week = payload.frequency_per_week
    model.minutes_per_session = payload.minutes_per_session
    model.training_environment = payload.training_environment
    model.available_equipment = payload.available_equipment


def _apply_nutrition_preferences(model: UserNutritionPreference, payload: UserNutritionPreferenceIn) -> None:
    model.activity_level = payload.activity_level
    model.meals_per_day = payload.meals_per_day
    model.budget_level = payload.budget_level
    model.allergies = payload.allergies
    model.dietary_restrictions = payload.dietary_restrictions
    model.excluded_foods = payload.excluded_foods
    model.training_schedule = payload.training_schedule


def _apply_safety_profile(model: UserSafetyProfile, payload: UserSafetyProfileIn) -> None:
    model.injuries = payload.injuries
    model.medical_conditions = payload.medical_conditions
    model.requires_professional_clearance = payload.requires_professional_clearance
    if payload.requires_professional_clearance or payload.medical_conditions:
        model.risk_level = MeasurementRiskLevel.NEEDS_CAUTION
    else:
        model.risk_level = MeasurementRiskLevel.NORMAL


async def get_user_full_profile(session: AsyncSession, user_id: str) -> User:
    stmt = select(User).where(User.id == user_id).limit(1)
    return (await session.execute(stmt)).scalar_one()


async def update_profile(
    session: AsyncSession,
    user: User,
    payload: UserProfileUpdateRequest,
) -> User:
    if payload.full_name:
        user.full_name = payload.full_name

    if payload.physical_profile:
        _apply_physical_profile(user.physical_profile, payload.physical_profile)
    if payload.training_preferences:
        _apply_training_preferences(user.training_preferences, payload.training_preferences)
    if payload.nutrition_preferences:
        _apply_nutrition_preferences(user.nutrition_preferences, payload.nutrition_preferences)
    if payload.safety_profile:
        _apply_safety_profile(user.safety_profile, payload.safety_profile)
    await session.flush()
    return user


async def complete_onboarding(session: AsyncSession, user: User, payload: OnboardingDataRequest) -> User:
    _apply_physical_profile(user.physical_profile, payload.physical_profile)
    _apply_training_preferences(user.training_preferences, payload.training_preferences)
    _apply_nutrition_preferences(user.nutrition_preferences, payload.nutrition_preferences)
    _apply_safety_profile(user.safety_profile, payload.safety_profile)
    await session.flush()
    return user


def calculate_profile_completion(user: User) -> int:
    points = 0
    max_points = 10
    profile = user.physical_profile
    training = user.training_preferences
    nutrition = user.nutrition_preferences
    safety = user.safety_profile

    if user.full_name:
        points += 1
    if user.email_verified_at:
        points += 1
    if profile.birth_date and profile.sex_for_calculation and profile.height_cm and profile.current_weight_kg:
        points += 2
    if training.main_goal and training.experience_level and training.frequency_per_week:
        points += 2
    if training.minutes_per_session and training.training_environment:
        points += 1
    if nutrition.activity_level and nutrition.meals_per_day:
        points += 1
    if isinstance(nutrition.allergies, list) and isinstance(nutrition.dietary_restrictions, list):
        points += 1
    if safety is not None:
        points += 1
    return int((points / max_points) * 100)


def age_from_birth_date(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


async def user_state(session: AsyncSession, user: User) -> dict[str, Any]:
    membership = await get_membership_context(session, user.id)
    warnings: list[str] = []
    if user.safety_profile and user.safety_profile.requires_professional_clearance:
        warnings.append("Usuario marcado con condiciones que requieren supervision profesional.")
    return {
        "membership_status": membership.status,
        "membership_plan_code": membership.plan_code,
        "is_premium": membership.is_premium,
        "profile_completion_pct": calculate_profile_completion(user),
        "warnings": warnings,
    }
