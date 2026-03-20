from __future__ import annotations

import random
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import PlanStatus, TrainingEnvironment
from app.db.models.enums import ExperienceLevel
from app.db.models.training import Exercise, TrainingDayExercise, TrainingPlan, TrainingPlanDay
from app.schemas.routines import RoutineGenerationRequest
from app.services.routine_engine.progression import rep_range_for_goal, rest_for_goal, sets_for_level
from app.services.routine_engine.rules import validate_request
from app.services.routine_engine.templates import split_for_frequency

FOCUS_PATTERNS = {
    "full_body": ["squat", "hinge", "horizontal_push", "horizontal_pull", "core"],
    "upper_push": ["horizontal_push", "vertical_push", "triceps", "core"],
    "upper_pull": ["horizontal_pull", "vertical_pull", "biceps", "core"],
    "lower": ["squat", "hinge", "lunge", "calves", "core"],
    "push": ["horizontal_push", "vertical_push", "triceps", "shoulders"],
    "pull": ["horizontal_pull", "vertical_pull", "biceps", "rear_delts"],
    "legs": ["squat", "hinge", "lunge", "hamstrings", "calves"],
    "upper": ["horizontal_push", "horizontal_pull", "vertical_push", "vertical_pull"],
}


ENV_TO_EQUIPMENT = {
    TrainingEnvironment.GYM_FULL: {"barbell", "machine", "cable", "bodyweight", "dumbbell", "kettlebell"},
    TrainingEnvironment.HOME_DUMBBELLS: {"dumbbell", "bodyweight", "band"},
    TrainingEnvironment.HOME_NO_EQUIPMENT: {"bodyweight", "band"},
}


def _goal_label(goal: str) -> str:
    return goal.replace("_", " ").title()


async def _latest_plan_version(session: AsyncSession, user_id: str) -> int:
    stmt = select(func.max(TrainingPlan.version)).where(TrainingPlan.user_id == user_id)
    value = (await session.execute(stmt)).scalar_one()
    return int(value or 0)


async def _fetch_recent_exercise_ids(session: AsyncSession, user_id: str) -> set[str]:
    stmt = (
        select(TrainingPlan.id)
        .where(TrainingPlan.user_id == user_id)
        .order_by(TrainingPlan.created_at.desc())
        .limit(1)
    )
    plan_id = (await session.execute(stmt)).scalar_one_or_none()
    if not plan_id:
        return set()
    rows = (
        await session.execute(
            select(TrainingDayExercise.exercise_id)
            .join(TrainingPlanDay, TrainingPlanDay.id == TrainingDayExercise.training_plan_day_id)
            .where(TrainingPlanDay.training_plan_id == plan_id)
        )
    ).scalars()
    return set(rows)


def _exercise_count(minutes_per_session: int) -> int:
    if minutes_per_session <= 45:
        return 5
    if minutes_per_session <= 75:
        return 6
    return 7


async def _candidate_exercises(
    session: AsyncSession,
    payload: RoutineGenerationRequest,
) -> list[Exercise]:
    allowed_equipment = ENV_TO_EQUIPMENT.get(payload.training_environment, set())
    stmt = select(Exercise).where(Exercise.is_active.is_(True))
    exercises = list((await session.execute(stmt)).scalars())
    if not exercises:
        return []
    if payload.training_environment == TrainingEnvironment.GYM_FULL:
        return exercises
    filtered = [e for e in exercises if e.equipment_type in allowed_equipment]
    return filtered or exercises


def _pick_exercises(
    rng: random.Random,
    all_exercises: list[Exercise],
    focus: str,
    count: int,
    recently_used_ids: set[str],
) -> list[Exercise]:
    target_patterns = FOCUS_PATTERNS.get(focus, ["full_body"])
    by_pattern = {}
    for pattern in target_patterns:
        by_pattern[pattern] = [e for e in all_exercises if e.movement_pattern == pattern]

    selected: list[Exercise] = []
    for pattern in target_patterns:
        candidates = by_pattern.get(pattern, [])
        if not candidates:
            continue
        fresh = [c for c in candidates if c.id not in recently_used_ids and c not in selected]
        source = fresh if fresh else [c for c in candidates if c not in selected]
        if source:
            selected.append(rng.choice(source))

    if len(selected) < count:
        remaining = [e for e in all_exercises if e not in selected]
        rng.shuffle(remaining)
        selected.extend(remaining[: count - len(selected)])
    return selected[:count]


async def generate_training_plan(
    session: AsyncSession,
    user_id: str,
    payload: RoutineGenerationRequest,
    regeneration_reason: str | None = None,
) -> TrainingPlan:
    validate_request(payload)

    await session.execute(
        update(TrainingPlan)
        .where(TrainingPlan.user_id == user_id, TrainingPlan.is_current.is_(True))
        .values(is_current=False, status=PlanStatus.SUPERSEDED)
    )

    next_version = (await _latest_plan_version(session, user_id)) + 1
    recently_used = await _fetch_recent_exercise_ids(session, user_id)
    candidates = await _candidate_exercises(session, payload)

    seed = int(datetime.now(UTC).timestamp()) + next_version
    rng = random.Random(seed)
    plan_name = f"{_goal_label(payload.goal.value)} Plan V{next_version}"
    plan = TrainingPlan(
        user_id=user_id,
        name=plan_name,
        version=next_version,
        status=PlanStatus.ACTIVE,
        goal=payload.goal,
        level=payload.level,
        weeks=payload.weeks,
        is_current=True,
        generator_version="routine_engine_v1",
        input_snapshot=payload.model_dump(mode="json"),
        recommendations=[
            "Mantener tecnica correcta en cada repeticion.",
            "Aumentar carga de forma progresiva semanal.",
            "Priorizar descanso y recuperacion.",
        ],
        notes=regeneration_reason,
    )
    session.add(plan)
    await session.flush()

    split = split_for_frequency(payload.frequency_per_week)
    rep_min, rep_max = rep_range_for_goal(payload.goal)
    sets = sets_for_level(payload.level)
    rest = rest_for_goal(payload.goal)
    ex_count = _exercise_count(payload.minutes_per_session)

    for day_index, focus in enumerate(split, start=1):
        day = TrainingPlanDay(training_plan_id=plan.id, day_number=day_index, focus=focus.replace("_", " ").title())
        session.add(day)
        await session.flush()
        exercises = _pick_exercises(rng, candidates, focus, ex_count, recently_used)
        for order_no, exercise in enumerate(exercises, start=1):
            session.add(
                TrainingDayExercise(
                    training_plan_day_id=day.id,
                    exercise_id=exercise.id,
                    order_no=order_no,
                    sets=sets,
                    reps_min=rep_min,
                    reps_max=rep_max,
                    rest_seconds=rest,
                    rir=2 if payload.level != ExperienceLevel.BEGINNER else 3,
                )
            )

    await session.flush()
    return plan
