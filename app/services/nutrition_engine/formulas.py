from __future__ import annotations

from app.db.models.enums import ActivityLevel, MainGoal, SexForCalculation


ACTIVITY_FACTORS = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.55,
    ActivityLevel.VERY_ACTIVE: 1.725,
    ActivityLevel.ATHLETE: 1.9,
}


def mifflin_st_jeor_bmr(
    sex: SexForCalculation,
    weight_kg: float,
    height_cm: int,
    age_years: int,
) -> float:
    base = (10 * weight_kg) + (6.25 * height_cm) - (5 * age_years)
    if sex == SexForCalculation.MALE:
        return base + 5
    if sex == SexForCalculation.FEMALE:
        return base - 161
    return base - 78


def tdee_from_bmr(bmr: float, activity: ActivityLevel) -> float:
    return bmr * ACTIVITY_FACTORS.get(activity, 1.375)


def target_calories_for_goal(tdee: float, goal: MainGoal) -> int:
    if goal == MainGoal.FAT_LOSS:
        return int(tdee * 0.82)
    if goal == MainGoal.MUSCLE_GAIN:
        return int(tdee * 1.1)
    if goal == MainGoal.RECOMP:
        return int(tdee * 0.95)
    if goal == MainGoal.ENDURANCE:
        return int(tdee * 1.05)
    return int(tdee)


def macro_distribution(
    weight_kg: float,
    target_calories: int,
    goal: MainGoal,
) -> tuple[float, float, float]:
    if goal == MainGoal.MUSCLE_GAIN:
        protein = 2.0 * weight_kg
    elif goal == MainGoal.FAT_LOSS:
        protein = 2.2 * weight_kg
    else:
        protein = 1.8 * weight_kg

    fat = 0.8 * weight_kg
    remaining_cals = max(target_calories - ((protein * 4) + (fat * 9)), 0)
    carbs = remaining_cals / 4
    return round(protein, 1), round(carbs, 1), round(fat, 1)
