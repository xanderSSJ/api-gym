from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models.enums import MainGoal, PlanStatus


class NutritionGenerationRequest(BaseModel):
    goal: MainGoal
    days_count: int = Field(default=30, ge=7, le=30)


class NutritionPlanAdjustmentRequest(BaseModel):
    adjustment_reason: str = Field(min_length=3, max_length=300)


class NutritionMealItemResponse(BaseModel):
    food_name: str
    grams: float
    quantity: float
    notes: str | None = None


class NutritionMealResponse(BaseModel):
    meal_number: int
    meal_name: str
    items: list[NutritionMealItemResponse]


class NutritionDayResponse(BaseModel):
    day_number: int
    target_calories: int
    meals: list[NutritionMealResponse]


class NutritionPlanResponse(BaseModel):
    plan_id: str
    name: str
    goal: MainGoal
    days_count: int
    status: PlanStatus
    created_at: datetime
    target_calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    recommendations: list[str]
    days: list[NutritionDayResponse]


class NutritionHistoryItem(BaseModel):
    plan_id: str
    name: str
    goal: MainGoal
    status: PlanStatus
    days_count: int
    created_at: datetime
    is_current: bool


class ShoppingItemResponse(BaseModel):
    food_name: str
    total_grams: float
    display_unit: str


class ShoppingListResponse(BaseModel):
    shopping_list_id: str
    plan_id: str
    period: str
    items: list[ShoppingItemResponse]
