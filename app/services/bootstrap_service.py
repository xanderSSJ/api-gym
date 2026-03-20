from __future__ import annotations

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    BillingPeriod,
    BudgetLevel,
    ExperienceLevel,
    FeatureKey,
    MainGoal,
    WindowUnit,
)
from app.db.models.membership import MembershipEntitlement, MembershipPlan
from app.db.models.nutrition import Food, FoodCategory
from app.db.models.training import Exercise, MuscleGroup


async def _ensure_plan(
    session: AsyncSession,
    code: str,
    name: str,
    billing_period: BillingPeriod,
    price: float,
) -> MembershipPlan:
    plan = (await session.execute(select(MembershipPlan).where(MembershipPlan.code == code))).scalar_one_or_none()
    if plan:
        return plan
    plan = MembershipPlan(
        code=code,
        name=name,
        billing_period=billing_period,
        price=price,
        currency="USD",
        is_active=True,
    )
    session.add(plan)
    await session.flush()
    return plan


async def _ensure_entitlement(
    session: AsyncSession,
    plan_id: str,
    feature_key: FeatureKey,
    quota: int,
    window_unit: WindowUnit,
    window_size: int,
    cooldown_days: int,
) -> None:
    stmt = select(MembershipEntitlement).where(
        and_(MembershipEntitlement.plan_id == plan_id, MembershipEntitlement.feature_key == feature_key)
    )
    current = (await session.execute(stmt)).scalar_one_or_none()
    if current:
        current.quota = quota
        current.window_unit = window_unit
        current.window_size = window_size
        current.cooldown_days = cooldown_days
        return
    session.add(
        MembershipEntitlement(
            plan_id=plan_id,
            feature_key=feature_key,
            quota=quota,
            window_unit=window_unit,
            window_size=window_size,
            cooldown_days=cooldown_days,
        )
    )


async def _ensure_muscle_group(session: AsyncSession, name: str) -> MuscleGroup:
    current = (await session.execute(select(MuscleGroup).where(MuscleGroup.name == name))).scalar_one_or_none()
    if current:
        return current
    obj = MuscleGroup(name=name)
    session.add(obj)
    await session.flush()
    return obj


async def _ensure_exercise(
    session: AsyncSession,
    name: str,
    movement_pattern: str,
    equipment_type: str,
    difficulty: ExperienceLevel = ExperienceLevel.BEGINNER,
) -> None:
    existing = (await session.execute(select(Exercise).where(Exercise.name == name))).scalar_one_or_none()
    if existing:
        return
    session.add(
        Exercise(
            name=name,
            movement_pattern=movement_pattern,
            equipment_type=equipment_type,
            difficulty=difficulty,
            contraindications={},
            instructions="",
        )
    )


async def _ensure_food_category(session: AsyncSession, name: str) -> FoodCategory:
    current = (await session.execute(select(FoodCategory).where(FoodCategory.name == name))).scalar_one_or_none()
    if current:
        return current
    obj = FoodCategory(name=name)
    session.add(obj)
    await session.flush()
    return obj


async def _ensure_food(
    session: AsyncSession,
    category: FoodCategory,
    name: str,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    cost_level: BudgetLevel,
    allergens: list[str] | None = None,
) -> None:
    existing = (await session.execute(select(Food).where(Food.name == name))).scalar_one_or_none()
    if existing:
        return
    session.add(
        Food(
            name=name,
            category_id=category.id,
            calories_per_100g=calories,
            protein_per_100g=protein,
            carbs_per_100g=carbs,
            fat_per_100g=fat,
            fiber_per_100g=0,
            cost_level=cost_level,
            allergens=allergens or [],
            is_active=True,
        )
    )


async def seed_core_data(session: AsyncSession) -> None:
    free_plan = await _ensure_plan(session, "free", "Free", BillingPeriod.MONTHLY, 0)
    premium_plan = await _ensure_plan(session, "premium_monthly", "Premium Monthly", BillingPeriod.MONTHLY, 19.99)

    # Free entitlements: strict windows and cooldown.
    await _ensure_entitlement(
        session,
        free_plan.id,
        FeatureKey.ROUTINE_GENERATION,
        quota=1,
        window_unit=WindowUnit.ROLLING_DAYS,
        window_size=15,
        cooldown_days=15,
    )
    await _ensure_entitlement(
        session,
        free_plan.id,
        FeatureKey.NUTRITION_GENERATION,
        quota=1,
        window_unit=WindowUnit.ROLLING_DAYS,
        window_size=15,
        cooldown_days=15,
    )
    await _ensure_entitlement(
        session,
        free_plan.id,
        FeatureKey.PHOTO_UPLOAD,
        quota=12,
        window_unit=WindowUnit.MONTH,
        window_size=1,
        cooldown_days=0,
    )
    await _ensure_entitlement(
        session,
        free_plan.id,
        FeatureKey.HISTORY_ACCESS,
        quota=3,
        window_unit=WindowUnit.MONTH,
        window_size=1,
        cooldown_days=0,
    )

    # Premium entitlements.
    await _ensure_entitlement(
        session,
        premium_plan.id,
        FeatureKey.ROUTINE_GENERATION,
        quota=10,
        window_unit=WindowUnit.MONTH,
        window_size=1,
        cooldown_days=0,
    )
    await _ensure_entitlement(
        session,
        premium_plan.id,
        FeatureKey.ROUTINE_REGENERATION,
        quota=2,
        window_unit=WindowUnit.MONTH,
        window_size=1,
        cooldown_days=0,
    )
    await _ensure_entitlement(
        session,
        premium_plan.id,
        FeatureKey.NUTRITION_GENERATION,
        quota=10,
        window_unit=WindowUnit.MONTH,
        window_size=1,
        cooldown_days=0,
    )
    await _ensure_entitlement(
        session,
        premium_plan.id,
        FeatureKey.NUTRITION_ADJUSTMENT,
        quota=2,
        window_unit=WindowUnit.MONTH,
        window_size=1,
        cooldown_days=0,
    )
    await _ensure_entitlement(
        session,
        premium_plan.id,
        FeatureKey.PHOTO_UPLOAD,
        quota=60,
        window_unit=WindowUnit.MONTH,
        window_size=1,
        cooldown_days=0,
    )
    await _ensure_entitlement(
        session,
        premium_plan.id,
        FeatureKey.HISTORY_ACCESS,
        quota=9999,
        window_unit=WindowUnit.MONTH,
        window_size=1,
        cooldown_days=0,
    )

    for mg in ["Pecho", "Espalda", "Pierna", "Hombro", "Biceps", "Triceps", "Core"]:
        await _ensure_muscle_group(session, mg)

    exercise_rows = [
        ("Back Squat", "squat", "barbell", ExperienceLevel.INTERMEDIATE),
        ("Goblet Squat", "squat", "dumbbell", ExperienceLevel.BEGINNER),
        ("Romanian Deadlift", "hinge", "barbell", ExperienceLevel.INTERMEDIATE),
        ("Hip Hinge Band", "hinge", "band", ExperienceLevel.BEGINNER),
        ("Bench Press", "horizontal_push", "barbell", ExperienceLevel.INTERMEDIATE),
        ("Push Up", "horizontal_push", "bodyweight", ExperienceLevel.BEGINNER),
        ("Overhead Press", "vertical_push", "dumbbell", ExperienceLevel.INTERMEDIATE),
        ("Dumbbell Shoulder Press", "shoulders", "dumbbell", ExperienceLevel.BEGINNER),
        ("Bent Over Row", "horizontal_pull", "barbell", ExperienceLevel.INTERMEDIATE),
        ("One Arm Dumbbell Row", "horizontal_pull", "dumbbell", ExperienceLevel.BEGINNER),
        ("Lat Pulldown", "vertical_pull", "machine", ExperienceLevel.BEGINNER),
        ("Pull Up Assisted", "vertical_pull", "machine", ExperienceLevel.INTERMEDIATE),
        ("Walking Lunge", "lunge", "dumbbell", ExperienceLevel.BEGINNER),
        ("Leg Curl", "hamstrings", "machine", ExperienceLevel.BEGINNER),
        ("Standing Calf Raise", "calves", "bodyweight", ExperienceLevel.BEGINNER),
        ("Plank", "core", "bodyweight", ExperienceLevel.BEGINNER),
        ("Cable Triceps Pushdown", "triceps", "cable", ExperienceLevel.BEGINNER),
        ("Dumbbell Curl", "biceps", "dumbbell", ExperienceLevel.BEGINNER),
        ("Rear Delt Fly", "rear_delts", "dumbbell", ExperienceLevel.BEGINNER),
    ]
    for row in exercise_rows:
        await _ensure_exercise(session, *row)

    proteins = await _ensure_food_category(session, "Proteinas")
    carbs = await _ensure_food_category(session, "Carbohidratos")
    fats = await _ensure_food_category(session, "Grasas")
    fruits = await _ensure_food_category(session, "Frutas")
    veggies = await _ensure_food_category(session, "Verduras")

    foods = [
        (proteins, "Pechuga de pollo", 165, 31, 0, 3.6, BudgetLevel.MEDIUM, []),
        (proteins, "Atun en agua", 132, 28, 0, 1.3, BudgetLevel.MEDIUM, ["fish"]),
        (proteins, "Huevo", 155, 13, 1.1, 11, BudgetLevel.LOW, ["egg"]),
        (proteins, "Pavo", 135, 29, 0, 1, BudgetLevel.HIGH, []),
        (carbs, "Arroz cocido", 130, 2.7, 28, 0.3, BudgetLevel.LOW, []),
        (carbs, "Avena", 389, 17, 66, 7, BudgetLevel.LOW, ["gluten"]),
        (carbs, "Papa cocida", 87, 1.9, 20, 0.1, BudgetLevel.LOW, []),
        (carbs, "Pasta", 131, 5, 25, 1.1, BudgetLevel.MEDIUM, ["gluten"]),
        (fats, "Aceite de oliva", 884, 0, 0, 100, BudgetLevel.HIGH, []),
        (fats, "Aguacate", 160, 2, 9, 15, BudgetLevel.MEDIUM, []),
        (fruits, "Platano", 89, 1.1, 23, 0.3, BudgetLevel.LOW, []),
        (fruits, "Manzana", 52, 0.3, 14, 0.2, BudgetLevel.LOW, []),
        (veggies, "Brocoli", 34, 2.8, 7, 0.4, BudgetLevel.LOW, []),
        (veggies, "Espinaca", 23, 2.9, 3.6, 0.4, BudgetLevel.LOW, []),
    ]
    for food in foods:
        await _ensure_food(session, *food)
