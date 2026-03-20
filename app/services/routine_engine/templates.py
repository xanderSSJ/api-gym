from __future__ import annotations

from app.db.models.enums import MainGoal


def split_for_frequency(frequency_per_week: int) -> list[str]:
    if frequency_per_week <= 3:
        return ["full_body", "full_body", "full_body"][:frequency_per_week]
    if frequency_per_week == 4:
        return ["upper_push", "lower", "upper_pull", "lower"]
    if frequency_per_week == 5:
        return ["push", "pull", "legs", "upper", "lower"]
    return ["push", "pull", "legs", "upper", "lower", "full_body"][:frequency_per_week]


def volume_target(goal: MainGoal) -> int:
    if goal == MainGoal.STRENGTH:
        return 12
    if goal == MainGoal.ENDURANCE:
        return 14
    if goal == MainGoal.FAT_LOSS:
        return 12
    return 16
