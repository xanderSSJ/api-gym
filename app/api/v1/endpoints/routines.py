from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_premium
from app.core.exceptions import bad_request, not_found
from app.db.models.enums import FeatureKey, GenerationJobStatus
from app.db.models.training import (
    Exercise,
    TrainingDayExercise,
    TrainingGenerationJob,
    TrainingPlan,
    TrainingPlanDay,
)
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.routines import (
    GenerationJobResponse,
    RegenerateRoutineRequest,
    RoutineDayResponse,
    RoutineGenerationRequest,
    RoutineHistoryItem,
    RoutinePlanResponse,
)
from app.services.routine_engine.generator import generate_training_plan
from app.services.usage_service import enforce_and_consume_feature

router = APIRouter(prefix="/routines", tags=["routines"])


async def _serialize_training_plan(session: AsyncSession, plan: TrainingPlan) -> RoutinePlanResponse:
    day_rows = (
        await session.execute(
            select(TrainingPlanDay).where(TrainingPlanDay.training_plan_id == plan.id).order_by(TrainingPlanDay.day_number)
        )
    ).scalars()
    days_payload: list[RoutineDayResponse] = []
    for day in day_rows:
        exercises_rows = (
            await session.execute(
                select(TrainingDayExercise, Exercise)
                .join(Exercise, Exercise.id == TrainingDayExercise.exercise_id)
                .where(TrainingDayExercise.training_plan_day_id == day.id)
                .order_by(TrainingDayExercise.order_no)
            )
        ).all()
        ex_payload = [
            {
                "exercise_name": ex.name,
                "sets": row.sets,
                "reps_min": row.reps_min,
                "reps_max": row.reps_max,
                "rest_seconds": row.rest_seconds,
                "notes": row.notes,
            }
            for row, ex in exercises_rows
        ]
        days_payload.append(
            RoutineDayResponse(
                day_number=day.day_number,
                focus=day.focus,
                exercises=ex_payload,
                notes=day.notes,
            )
        )
    return RoutinePlanResponse(
        plan_id=plan.id,
        name=plan.name,
        goal=plan.goal,
        level=plan.level,
        weeks=plan.weeks,
        status=plan.status,
        created_at=plan.created_at,
        recommendations=[str(item) for item in plan.recommendations],
        days=days_payload,
    )


@router.post("/generations", response_model=GenerationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def generate_routine(
    payload: RoutineGenerationRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> GenerationJobResponse:
    if current_user.safety_profile and current_user.safety_profile.requires_professional_clearance:
        raise bad_request("No se puede generar rutina automatica sin alta profesional para este perfil.")

    await enforce_and_consume_feature(session, current_user.id, FeatureKey.ROUTINE_GENERATION)
    job = TrainingGenerationJob(
        user_id=current_user.id,
        status=GenerationJobStatus.PROCESSING,
        request_snapshot=payload.model_dump(mode="json"),
    )
    session.add(job)
    await session.flush()

    plan = await generate_training_plan(session, user_id=current_user.id, payload=payload)
    job.status = GenerationJobStatus.SUCCEEDED
    job.result_plan_id = plan.id
    await session.commit()
    return GenerationJobResponse(job_id=job.id, status=job.status.value, estimated_wait_seconds=1)


@router.post("/{plan_id}/regenerate", response_model=GenerationJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def regenerate_routine(
    plan_id: str,
    payload: RegenerateRoutineRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(require_premium),
) -> GenerationJobResponse:
    original = (
        await session.execute(
            select(TrainingPlan).where(TrainingPlan.id == plan_id, TrainingPlan.user_id == current_user.id).limit(1)
        )
    ).scalar_one_or_none()
    if original is None:
        raise not_found("Routine plan not found.")

    await enforce_and_consume_feature(session, current_user.id, FeatureKey.ROUTINE_REGENERATION)
    job = TrainingGenerationJob(
        user_id=current_user.id,
        status=GenerationJobStatus.PROCESSING,
        request_snapshot=original.input_snapshot,
    )
    session.add(job)
    await session.flush()

    request_payload = RoutineGenerationRequest(**original.input_snapshot)
    plan = await generate_training_plan(
        session,
        user_id=current_user.id,
        payload=request_payload,
        regeneration_reason=payload.reason,
    )
    job.status = GenerationJobStatus.SUCCEEDED
    job.result_plan_id = plan.id
    await session.commit()
    return GenerationJobResponse(job_id=job.id, status=job.status.value, estimated_wait_seconds=1)


@router.get("/current", response_model=RoutinePlanResponse)
async def current_routine(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> RoutinePlanResponse:
    plan = (
        await session.execute(
            select(TrainingPlan)
            .where(TrainingPlan.user_id == current_user.id, TrainingPlan.is_current.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    if plan is None:
        raise not_found("No active routine plan found.")
    return await _serialize_training_plan(session, plan)


@router.get("/history", response_model=list[RoutineHistoryItem])
async def routine_history(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[RoutineHistoryItem]:
    await enforce_and_consume_feature(session, current_user.id, FeatureKey.HISTORY_ACCESS)
    rows = (
        await session.execute(
            select(TrainingPlan)
            .where(TrainingPlan.user_id == current_user.id)
            .order_by(TrainingPlan.created_at.desc())
            .limit(30)
        )
    ).scalars()
    await session.commit()
    return [
        RoutineHistoryItem(
            plan_id=row.id,
            name=row.name,
            status=row.status,
            goal=row.goal,
            level=row.level,
            weeks=row.weeks,
            created_at=row.created_at,
            is_current=row.is_current,
        )
        for row in rows
    ]


@router.get("/jobs/{job_id}", response_model=GenerationJobResponse)
async def routine_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> GenerationJobResponse:
    job = (
        await session.execute(
            select(TrainingGenerationJob)
            .where(TrainingGenerationJob.id == job_id, TrainingGenerationJob.user_id == current_user.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is None:
        raise not_found("Job not found.")
    return GenerationJobResponse(job_id=job.id, status=job.status.value, estimated_wait_seconds=0)
