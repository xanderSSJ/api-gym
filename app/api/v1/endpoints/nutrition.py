from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_premium
from app.core.exceptions import bad_request, not_found
from app.db.models.enums import FeatureKey, GenerationJobStatus
from app.db.models.nutrition import (
    Food,
    NutritionGenerationJob,
    NutritionMeal,
    NutritionMealItem,
    NutritionPlan,
    NutritionPlanDay,
    ShoppingList,
    ShoppingListItem,
)
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.nutrition import (
    NutritionDayResponse,
    NutritionGenerationRequest,
    NutritionHistoryItem,
    NutritionMealItemResponse,
    NutritionMealResponse,
    NutritionPlanAdjustmentRequest,
    NutritionPlanResponse,
    ShoppingItemResponse,
    ShoppingListResponse,
)
from app.schemas.routines import GenerationJobResponse
from app.services.nutrition_engine.generator import generate_nutrition_plan
from app.services.usage_service import enforce_and_consume_feature

router = APIRouter(prefix="/nutrition/plans", tags=["nutrition"])


async def _serialize_plan(session: AsyncSession, plan: NutritionPlan) -> NutritionPlanResponse:
    days_rows = (
        await session.execute(
            select(NutritionPlanDay)
            .where(NutritionPlanDay.nutrition_plan_id == plan.id)
            .order_by(NutritionPlanDay.day_number)
        )
    ).scalars()
    days_payload: list[NutritionDayResponse] = []
    for day in days_rows:
        meal_rows = (
            await session.execute(
                select(NutritionMeal)
                .where(NutritionMeal.nutrition_plan_day_id == day.id)
                .order_by(NutritionMeal.meal_number)
            )
        ).scalars()
        meal_payload: list[NutritionMealResponse] = []
        for meal in meal_rows:
            item_rows = (
                await session.execute(
                    select(NutritionMealItem, Food)
                    .join(Food, Food.id == NutritionMealItem.food_id)
                    .where(NutritionMealItem.nutrition_meal_id == meal.id)
                )
            ).all()
            items = [
                NutritionMealItemResponse(
                    food_name=food.name,
                    grams=float(item.grams),
                    quantity=float(item.quantity),
                    notes=item.notes,
                )
                for item, food in item_rows
            ]
            meal_payload.append(
                NutritionMealResponse(meal_number=meal.meal_number, meal_name=meal.meal_name, items=items)
            )
        days_payload.append(
            NutritionDayResponse(day_number=day.day_number, target_calories=day.target_calories, meals=meal_payload)
        )
    return NutritionPlanResponse(
        plan_id=plan.id,
        name=plan.name,
        goal=plan.goal,
        days_count=plan.days_count,
        status=plan.status,
        created_at=plan.created_at,
        target_calories=plan.target_calories,
        protein_g=float(plan.protein_g),
        carbs_g=float(plan.carbs_g),
        fat_g=float(plan.fat_g),
        recommendations=[str(item) for item in plan.recommendations],
        days=days_payload,
    )


@router.post("/generations", response_model=GenerationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_plan(
    payload: NutritionGenerationRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> GenerationJobResponse:
    if current_user.safety_profile and current_user.safety_profile.requires_professional_clearance:
        raise bad_request("No se puede generar plan sin revision profesional para este perfil.")
    await enforce_and_consume_feature(session, current_user.id, FeatureKey.NUTRITION_GENERATION)

    job = NutritionGenerationJob(
        user_id=current_user.id,
        status=GenerationJobStatus.PROCESSING,
        request_snapshot=payload.model_dump(mode="json"),
    )
    session.add(job)
    await session.flush()

    plan = await generate_nutrition_plan(session, current_user, payload)
    job.status = GenerationJobStatus.SUCCEEDED
    job.result_plan_id = plan.id
    await session.commit()
    return GenerationJobResponse(job_id=job.id, status=job.status.value, estimated_wait_seconds=1)


@router.post("/{plan_id}/adjust", response_model=GenerationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def adjust_plan(
    plan_id: str,
    payload: NutritionPlanAdjustmentRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_premium),
) -> GenerationJobResponse:
    original = (
        await session.execute(
            select(NutritionPlan).where(NutritionPlan.id == plan_id, NutritionPlan.user_id == current_user.id).limit(1)
        )
    ).scalar_one_or_none()
    if original is None:
        raise not_found("Nutrition plan not found.")
    await enforce_and_consume_feature(session, current_user.id, FeatureKey.NUTRITION_ADJUSTMENT)
    job = NutritionGenerationJob(
        user_id=current_user.id,
        status=GenerationJobStatus.PROCESSING,
        request_snapshot=original.input_snapshot,
    )
    session.add(job)
    await session.flush()

    req = NutritionGenerationRequest(
        goal=original.goal,
        days_count=original.days_count,
    )
    plan = await generate_nutrition_plan(session, current_user, req, reason=payload.adjustment_reason)
    job.status = GenerationJobStatus.SUCCEEDED
    job.result_plan_id = plan.id
    await session.commit()
    return GenerationJobResponse(job_id=job.id, status=job.status.value, estimated_wait_seconds=1)


@router.get("/current", response_model=NutritionPlanResponse)
async def current_plan(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> NutritionPlanResponse:
    plan = (
        await session.execute(
            select(NutritionPlan)
            .where(NutritionPlan.user_id == current_user.id, NutritionPlan.is_current.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if plan is None:
        raise not_found("No active nutrition plan found.")
    return await _serialize_plan(session, plan)


@router.get("/history", response_model=list[NutritionHistoryItem])
async def history(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[NutritionHistoryItem]:
    await enforce_and_consume_feature(session, current_user.id, FeatureKey.HISTORY_ACCESS)
    rows = (
        await session.execute(
            select(NutritionPlan)
            .where(NutritionPlan.user_id == current_user.id)
            .order_by(NutritionPlan.created_at.desc())
            .limit(30)
        )
    ).scalars()
    await session.commit()
    return [
        NutritionHistoryItem(
            plan_id=row.id,
            name=row.name,
            goal=row.goal,
            status=row.status,
            days_count=row.days_count,
            created_at=row.created_at,
            is_current=row.is_current,
        )
        for row in rows
    ]


@router.get("/{plan_id}/shopping-list", response_model=ShoppingListResponse)
async def shopping_list(
    plan_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_premium),
) -> ShoppingListResponse:
    shopping = (
        await session.execute(
            select(ShoppingList)
            .join(NutritionPlan, NutritionPlan.id == ShoppingList.nutrition_plan_id)
            .where(ShoppingList.nutrition_plan_id == plan_id, NutritionPlan.user_id == current_user.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if shopping is None:
        raise not_found("Shopping list not found.")
    rows = (
        await session.execute(
            select(ShoppingListItem, Food)
            .join(Food, Food.id == ShoppingListItem.food_id)
            .where(ShoppingListItem.shopping_list_id == shopping.id)
            .order_by(ShoppingListItem.total_grams.desc())
        )
    ).all()
    items = [
        ShoppingItemResponse(
            food_name=food.name,
            total_grams=float(item.total_grams),
            display_unit=item.display_unit,
        )
        for item, food in rows
    ]
    return ShoppingListResponse(
        shopping_list_id=shopping.id,
        plan_id=plan_id,
        period=shopping.period,
        items=items,
    )


@router.get("/jobs/{job_id}", response_model=GenerationJobResponse)
async def nutrition_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> GenerationJobResponse:
    job = (
        await session.execute(
            select(NutritionGenerationJob)
            .where(NutritionGenerationJob.id == job_id, NutritionGenerationJob.user_id == current_user.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        raise not_found("Job not found.")
    return GenerationJobResponse(job_id=job.id, status=job.status.value, estimated_wait_seconds=0)
