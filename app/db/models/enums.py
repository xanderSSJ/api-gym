from __future__ import annotations

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"


class SexForCalculation(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class ActivityLevel(StrEnum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    VERY_ACTIVE = "very_active"
    ATHLETE = "athlete"


class MainGoal(StrEnum):
    FAT_LOSS = "fat_loss"
    MUSCLE_GAIN = "muscle_gain"
    MAINTENANCE = "maintenance"
    STRENGTH = "strength"
    ENDURANCE = "endurance"
    RECOMP = "recomposition"


class ExperienceLevel(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class TrainingEnvironment(StrEnum):
    GYM_FULL = "gym_full"
    HOME_DUMBBELLS = "home_dumbbells"
    HOME_NO_EQUIPMENT = "home_no_equipment"


class BudgetLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MembershipStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


class BillingPeriod(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class PaymentStatus(StrEnum):
    REQUIRES_ACTION = "requires_action"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class PlanStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class GenerationJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class FeatureKey(StrEnum):
    ROUTINE_GENERATION = "routine_generation"
    NUTRITION_GENERATION = "nutrition_generation"
    ROUTINE_REGENERATION = "routine_regeneration"
    NUTRITION_ADJUSTMENT = "nutrition_adjustment"
    PHOTO_UPLOAD = "photo_upload"
    HISTORY_ACCESS = "history_access"


class WindowUnit(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    ROLLING_DAYS = "rolling_days"


class MeasurementRiskLevel(StrEnum):
    NORMAL = "normal"
    NEEDS_CAUTION = "needs_caution"
    RESTRICTED = "restricted"
