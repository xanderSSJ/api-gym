from __future__ import annotations

from app.db.models.enums import ExperienceLevel, MainGoal


def rep_range_for_goal(goal: MainGoal) -> tuple[int, int]:
    if goal == MainGoal.STRENGTH:
        return 3, 6
    if goal == MainGoal.ENDURANCE:
        return 12, 20
    if goal == MainGoal.MUSCLE_GAIN:
        return 6, 12
    return 8, 15


def sets_for_level(level: ExperienceLevel) -> int:
    if level == ExperienceLevel.BEGINNER:
        return 3
    if level == ExperienceLevel.INTERMEDIATE:
        return 4
    return 5


def rest_for_goal(goal: MainGoal) -> int:
    if goal == MainGoal.STRENGTH:
        return 150
    if goal == MainGoal.ENDURANCE:
        return 45
    return 90
