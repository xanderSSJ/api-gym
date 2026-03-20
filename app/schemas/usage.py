from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UsageCounterResponse(BaseModel):
    feature_key: str
    window_start: datetime
    window_end: datetime
    used_units: int


class UsageSummaryResponse(BaseModel):
    tier: str
    counters: list[UsageCounterResponse]
