from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.nutrition import Food, FoodSubstitution


async def substitutions_for_food(session: AsyncSession, food_id: str, limit: int = 5) -> list[Food]:
    sub_rows = (
        await session.execute(
            select(FoodSubstitution)
            .where(FoodSubstitution.food_id == food_id)
            .order_by(FoodSubstitution.priority.asc())
            .limit(limit)
        )
    ).scalars()
    substitute_ids = [row.substitute_food_id for row in sub_rows]
    if not substitute_ids:
        return []
    foods = (await session.execute(select(Food).where(Food.id.in_(substitute_ids)))).scalars()
    return list(foods)
