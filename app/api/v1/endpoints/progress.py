from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.exceptions import bad_request
from app.db.models.enums import FeatureKey
from app.db.models.progress import (
    BodyMeasurement,
    HealthMetricSnapshot,
    ProgressPhoto,
    StrengthLog,
    WeeklyCheckin,
    WeightLog,
)
from app.db.models.training import Exercise
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.common import MessageResponse
from app.schemas.progress import (
    MeasurementCreate,
    ProgressPhotoPresignRequest,
    ProgressPhotoPresignResponse,
    ProgressSummaryResponse,
    StrengthLogCreate,
    WeeklyCheckinCreate,
    WeightLogCreate,
)
from app.services.nutrition_engine.formulas import mifflin_st_jeor_bmr, tdee_from_bmr
from app.services.usage_service import enforce_and_consume_feature
from app.services.user_service import age_from_birth_date

router = APIRouter(prefix="/progress", tags=["progress"])


@router.post("/weights", response_model=MessageResponse)
async def add_weight(
    payload: WeightLogCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    session.add(
        WeightLog(
            user_id=current_user.id,
            weight_kg=payload.weight_kg,
            recorded_at=payload.recorded_at,
        )
    )
    await session.commit()
    return MessageResponse(message="Weight recorded.")


@router.post("/measurements", response_model=MessageResponse)
async def add_measurement(
    payload: MeasurementCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    session.add(
        BodyMeasurement(
            user_id=current_user.id,
            waist_cm=payload.waist_cm,
            chest_cm=payload.chest_cm,
            arm_cm=payload.arm_cm,
            thigh_cm=payload.thigh_cm,
            hip_cm=payload.hip_cm,
            body_fat_pct=payload.body_fat_pct,
            recorded_at=payload.recorded_at,
        )
    )
    await session.commit()
    return MessageResponse(message="Measurements recorded.")


@router.post("/strength", response_model=MessageResponse)
async def add_strength(
    payload: StrengthLogCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    exercise = (await session.execute(select(Exercise).where(Exercise.id == payload.exercise_id))).scalar_one_or_none()
    if exercise is None:
        raise bad_request("Invalid exercise id.")
    estimated_1rm = payload.weight_kg * (1 + (payload.reps / 30))
    session.add(
        StrengthLog(
            user_id=current_user.id,
            exercise_id=payload.exercise_id,
            weight_kg=payload.weight_kg,
            reps=payload.reps,
            estimated_1rm=round(estimated_1rm, 2),
            recorded_at=payload.recorded_at,
        )
    )
    await session.commit()
    return MessageResponse(message="Strength entry recorded.")


@router.post("/checkins", response_model=MessageResponse)
async def add_checkin(
    payload: WeeklyCheckinCreate,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    session.add(
        WeeklyCheckin(
            user_id=current_user.id,
            energy=payload.energy,
            sleep=payload.sleep,
            hunger=payload.hunger,
            adherence_training=payload.adherence_training,
            adherence_nutrition=payload.adherence_nutrition,
            notes=payload.notes,
            recorded_at=payload.recorded_at,
        )
    )
    await session.commit()
    return MessageResponse(message="Weekly check-in recorded.")


@router.post("/photos/presign", response_model=ProgressPhotoPresignResponse)
async def presign_progress_photo(
    payload: ProgressPhotoPresignRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProgressPhotoPresignResponse:
    await enforce_and_consume_feature(session, current_user.id, FeatureKey.PHOTO_UPLOAD)
    storage_key = f"progress/{current_user.id}/{int(datetime.now(UTC).timestamp())}.{payload.extension}"
    fake_upload_url = f"{settings.public_media_base_url}/upload/{storage_key}"
    session.add(
        ProgressPhoto(
            user_id=current_user.id,
            storage_key=storage_key,
            photo_type=payload.photo_type,
            captured_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return ProgressPhotoPresignResponse(upload_url=fake_upload_url, storage_key=storage_key)


@router.get("/summary", response_model=ProgressSummaryResponse)
async def progress_summary(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProgressSummaryResponse:
    weight_rows = (
        await session.execute(
            select(WeightLog)
            .where(WeightLog.user_id == current_user.id)
            .order_by(WeightLog.recorded_at.desc())
            .limit(2)
        )
    ).scalars()
    weight_list = list(weight_rows)
    latest_weight = float(weight_list[0].weight_kg) if weight_list else None
    weekly_delta = None
    if len(weight_list) >= 2:
        weekly_delta = float(weight_list[0].weight_kg) - float(weight_list[1].weight_kg)

    latest_bmi = None
    latest_bmr = None
    latest_tdee = None
    profile = current_user.physical_profile
    nutrition_pref = current_user.nutrition_preferences
    if (
        profile
        and profile.height_cm
        and latest_weight
        and profile.birth_date
        and profile.sex_for_calculation
        and nutrition_pref
        and nutrition_pref.activity_level
    ):
        height_m = profile.height_cm / 100
        latest_bmi = round(latest_weight / (height_m * height_m), 2)
        age = age_from_birth_date(profile.birth_date)
        if age:
            latest_bmr = round(
                mifflin_st_jeor_bmr(
                    profile.sex_for_calculation,
                    latest_weight,
                    profile.height_cm,
                    age,
                ),
                2,
            )
            latest_tdee = round(tdee_from_bmr(latest_bmr, nutrition_pref.activity_level), 2)
            session.add(
                HealthMetricSnapshot(
                    user_id=current_user.id,
                    bmi=latest_bmi,
                    bmr=latest_bmr,
                    tdee=latest_tdee,
                    snapshot_data={"source": "summary_endpoint"},
                    recorded_at=datetime.now(UTC),
                )
            )
            await session.commit()

    strength_rows = (
        await session.execute(
            select(StrengthLog, Exercise)
            .join(Exercise, Exercise.id == StrengthLog.exercise_id)
            .where(StrengthLog.user_id == current_user.id)
            .order_by(StrengthLog.recorded_at.desc())
            .limit(20)
        )
    ).all()
    prs: dict[str, float] = {}
    for row, exercise in strength_rows:
        current = prs.get(exercise.name, 0)
        prs[exercise.name] = max(current, float(row.estimated_1rm or 0))

    return ProgressSummaryResponse(
        latest_weight_kg=latest_weight,
        weekly_weight_delta_kg=weekly_delta,
        latest_bmi=latest_bmi,
        latest_bmr=latest_bmr,
        latest_tdee=latest_tdee,
        strength_prs=prs,
    )
