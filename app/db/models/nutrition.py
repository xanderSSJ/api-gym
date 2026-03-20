from __future__ import annotations

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import BudgetLevel, GenerationJobStatus, MainGoal, PlanStatus


class FoodCategory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "food_categories"

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("food_categories.id"), nullable=True)


class Food(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "foods"

    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    category_id: Mapped[str] = mapped_column(
        ForeignKey("food_categories.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    calories_per_100g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    protein_per_100g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    carbs_per_100g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    fat_per_100g: Mapped[float] = mapped_column(Numeric(7, 2), nullable=False)
    fiber_per_100g: Mapped[float | None] = mapped_column(Numeric(7, 2), nullable=True)
    cost_level: Mapped[BudgetLevel] = mapped_column(Enum(BudgetLevel), default=BudgetLevel.MEDIUM, nullable=False)
    allergens: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class FoodPortion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "food_portions"

    food_id: Mapped[str] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"), index=True, nullable=False)
    portion_name: Mapped[str] = mapped_column(String(80), nullable=False)
    grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    household_measure: Mapped[str | None] = mapped_column(String(80), nullable=True)


class FoodSubstitution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "food_substitutions"
    __table_args__ = (
        UniqueConstraint("food_id", "substitute_food_id", name="uq_food_substitute"),
    )

    food_id: Mapped[str] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"), index=True, nullable=False)
    substitute_food_id: Mapped[str] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), index=True, nullable=False
    )
    equivalence_ratio: Mapped[float] = mapped_column(Numeric(8, 3), default=1.0, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(250), nullable=True)


class MealTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "meal_templates"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    goal: Mapped[MainGoal] = mapped_column(Enum(MainGoal), nullable=False, index=True)
    meal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    budget_level: Mapped[BudgetLevel] = mapped_column(Enum(BudgetLevel), nullable=False)
    template_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NutritionPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "nutrition_plans"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[PlanStatus] = mapped_column(Enum(PlanStatus), default=PlanStatus.ACTIVE, nullable=False)
    goal: Mapped[MainGoal] = mapped_column(Enum(MainGoal), nullable=False)
    days_count: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    target_calories: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    carbs_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    fat_g: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    replaces_plan_id: Mapped[str | None] = mapped_column(ForeignKey("nutrition_plans.id"), nullable=True)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(40), default="v1", nullable=False)
    recommendations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class NutritionPlanDay(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "nutrition_plan_days"
    __table_args__ = (UniqueConstraint("nutrition_plan_id", "day_number", name="uq_nutrition_day"),)

    nutrition_plan_id: Mapped[str] = mapped_column(
        ForeignKey("nutrition_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    target_calories: Mapped[int] = mapped_column(Integer, nullable=False)


class NutritionMeal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "nutrition_meals"
    __table_args__ = (
        UniqueConstraint("nutrition_plan_day_id", "meal_number", name="uq_day_meal_number"),
    )

    nutrition_plan_day_id: Mapped[str] = mapped_column(
        ForeignKey("nutrition_plan_days.id", ondelete="CASCADE"), index=True, nullable=False
    )
    meal_number: Mapped[int] = mapped_column(Integer, nullable=False)
    meal_name: Mapped[str] = mapped_column(String(100), nullable=False)
    scheduled_time: Mapped[str | None] = mapped_column(String(20), nullable=True)


class NutritionMealItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "nutrition_meal_items"

    nutrition_meal_id: Mapped[str] = mapped_column(
        ForeignKey("nutrition_meals.id", ondelete="CASCADE"), index=True, nullable=False
    )
    food_id: Mapped[str] = mapped_column(ForeignKey("foods.id", ondelete="RESTRICT"), nullable=False)
    portion_id: Mapped[str | None] = mapped_column(ForeignKey("food_portions.id"), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(8, 2), default=1, nullable=False)
    grams: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class ShoppingList(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shopping_lists"

    nutrition_plan_id: Mapped[str] = mapped_column(
        ForeignKey("nutrition_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    period: Mapped[str] = mapped_column(String(20), default="weekly", nullable=False)


class ShoppingListItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "shopping_list_items"

    shopping_list_id: Mapped[str] = mapped_column(
        ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True, nullable=False
    )
    food_id: Mapped[str] = mapped_column(ForeignKey("foods.id", ondelete="RESTRICT"), nullable=False)
    total_grams: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    display_unit: Mapped[str] = mapped_column(String(20), default="g", nullable=False)


class NutritionGenerationJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "nutrition_generation_jobs"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    status: Mapped[GenerationJobStatus] = mapped_column(
        Enum(GenerationJobStatus), default=GenerationJobStatus.QUEUED, nullable=False
    )
    request_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result_plan_id: Mapped[str | None] = mapped_column(ForeignKey("nutrition_plans.id"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
