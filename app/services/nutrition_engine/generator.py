from __future__ import annotations

import random
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import bad_request
from app.db.models.enums import PlanStatus
from app.db.models.nutrition import (
    Food,
    NutritionMeal,
    NutritionMealItem,
    NutritionPlan,
    NutritionPlanDay,
    ShoppingList,
    ShoppingListItem,
)
from app.db.models.user import User
from app.schemas.nutrition import NutritionGenerationRequest
from app.services.nutrition_engine.formulas import (
    macro_distribution,
    mifflin_st_jeor_bmr,
    target_calories_for_goal,
    tdee_from_bmr,
)
from app.services.user_service import age_from_birth_date


def _validate_nutrition_input(user: User) -> None:
    profile = user.physical_profile
    pref = user.nutrition_preferences
    if not profile or not pref:
        raise bad_request("Usuario sin perfil suficiente para nutricion.")
    required = [profile.birth_date, profile.sex_for_calculation, profile.height_cm, profile.current_weight_kg]
    if any(item is None for item in required):
        raise bad_request("Faltan datos fisicos obligatorios para generar nutricion.")
    if pref.activity_level is None or pref.meals_per_day is None:
        raise bad_request("Faltan preferencias de actividad o numero de comidas.")


async def _latest_plan_version(session: AsyncSession, user_id: str) -> int:
    stmt = select(func.max(NutritionPlan.version)).where(NutritionPlan.user_id == user_id)
    value = (await session.execute(stmt)).scalar_one()
    return int(value or 0)


async def _eligible_foods(session: AsyncSession, user: User) -> list[Food]:
    pref = user.nutrition_preferences
    assert pref is not None
    excluded_tokens = {x.strip().lower() for x in pref.excluded_foods}
    allergy_tokens = {x.strip().lower() for x in pref.allergies}
    stmt = select(Food).where(Food.is_active.is_(True))
    foods = list((await session.execute(stmt)).scalars())
    filtered: list[Food] = []
    for food in foods:
        if food.name.lower() in excluded_tokens:
            continue
        food_allergens = {x.lower() for x in (food.allergens or [])}
        if food_allergens.intersection(allergy_tokens):
            continue
        filtered.append(food)
    if not filtered:
        raise bad_request("No hay alimentos elegibles con las restricciones actuales.")
    return filtered


def _meal_name(meal_number: int) -> str:
    names = {1: "Desayuno", 2: "Comida", 3: "Cena", 4: "Snack 1", 5: "Snack 2", 6: "Snack 3"}
    return names.get(meal_number, f"Comida {meal_number}")


async def generate_nutrition_plan(
    session: AsyncSession,
    user: User,
    payload: NutritionGenerationRequest,
    reason: str | None = None,
) -> NutritionPlan:
    _validate_nutrition_input(user)
    profile = user.physical_profile
    pref = user.nutrition_preferences
    assert profile and pref

    await session.execute(
        update(NutritionPlan)
        .where(NutritionPlan.user_id == user.id, NutritionPlan.is_current.is_(True))
        .values(is_current=False, status=PlanStatus.SUPERSEDED)
    )

    age = age_from_birth_date(profile.birth_date)
    if age is None:
        raise bad_request("No se pudo calcular edad para nutricion.")

    bmr = mifflin_st_jeor_bmr(
        sex=profile.sex_for_calculation,
        weight_kg=float(profile.current_weight_kg),
        height_cm=int(profile.height_cm),
        age_years=age,
    )
    tdee = tdee_from_bmr(bmr, pref.activity_level)
    target_cals = target_calories_for_goal(tdee, payload.goal)
    protein_g, carbs_g, fat_g = macro_distribution(float(profile.current_weight_kg), target_cals, payload.goal)

    next_version = (await _latest_plan_version(session, user.id)) + 1
    plan = NutritionPlan(
        user_id=user.id,
        name=f"Plan Nutricional {payload.goal.value.replace('_', ' ').title()} V{next_version}",
        version=next_version,
        status=PlanStatus.ACTIVE,
        goal=payload.goal,
        days_count=payload.days_count,
        target_calories=target_cals,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        is_current=True,
        generator_version="nutrition_engine_v1",
        input_snapshot=payload.model_dump(mode="json"),
        recommendations=[
            "Distribuir hidratacion durante todo el dia.",
            "Priorizar alimentos frescos y no ultraprocesados.",
            "Ajustar porciones segun saciedad y adherencia semanal.",
        ],
        notes=reason,
    )
    session.add(plan)
    await session.flush()

    foods = await _eligible_foods(session, user)
    rng = random.Random(int(datetime.now(UTC).timestamp()) + next_version)
    meals_per_day = pref.meals_per_day or 3
    calories_per_meal = max(int(target_cals / meals_per_day), 100)
    grams_per_item = 120

    shopping_aggregate: defaultdict[str, float] = defaultdict(float)

    for day_number in range(1, payload.days_count + 1):
        day = NutritionPlanDay(
            nutrition_plan_id=plan.id,
            day_number=day_number,
            target_calories=target_cals,
        )
        session.add(day)
        await session.flush()

        for meal_number in range(1, meals_per_day + 1):
            meal = NutritionMeal(
                nutrition_plan_day_id=day.id,
                meal_number=meal_number,
                meal_name=_meal_name(meal_number),
            )
            session.add(meal)
            await session.flush()

            selected_foods = rng.sample(foods, k=min(3, len(foods)))
            for food in selected_foods:
                item_grams = float(grams_per_item / len(selected_foods))
                session.add(
                    NutritionMealItem(
                        nutrition_meal_id=meal.id,
                        food_id=food.id,
                        quantity=1,
                        grams=item_grams,
                        notes=f"Aprox. {int(calories_per_meal / len(selected_foods))} kcal",
                    )
                )
                shopping_aggregate[food.id] += item_grams

    shopping = ShoppingList(nutrition_plan_id=plan.id, period="weekly")
    session.add(shopping)
    await session.flush()
    for food_id, total_grams in shopping_aggregate.items():
        session.add(
            ShoppingListItem(
                shopping_list_id=shopping.id,
                food_id=food_id,
                total_grams=round(total_grams / max(payload.days_count / 7, 1), 2),
                display_unit="g",
            )
        )

    await session.flush()
    return plan
