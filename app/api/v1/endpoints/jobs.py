from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.exceptions import not_found
from app.db.models.nutrition import NutritionGenerationJob
from app.db.models.training import TrainingGenerationJob
from app.db.models.user import User
from app.db.session import get_db_session

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}")
async def get_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    training_job = (
        await session.execute(
            select(TrainingGenerationJob).where(
                TrainingGenerationJob.id == job_id,
                TrainingGenerationJob.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if training_job:
        return {
            "data": {
                "job_id": training_job.id,
                "type": "routine",
                "status": training_job.status.value,
                "result_id": training_job.result_plan_id,
            }
        }
    nutrition_job = (
        await session.execute(
            select(NutritionGenerationJob).where(
                NutritionGenerationJob.id == job_id,
                NutritionGenerationJob.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if nutrition_job:
        return {
            "data": {
                "job_id": nutrition_job.id,
                "type": "nutrition",
                "status": nutrition_job.status.value,
                "result_id": nutrition_job.result_plan_id,
            }
        }
    raise not_found("Job not found.")
