from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.usage import UsageCounterResponse, UsageSummaryResponse
from app.services.usage_service import list_counters

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/me", response_model=UsageSummaryResponse)
async def usage_me(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> UsageSummaryResponse:
    tier, counters = await list_counters(session, current_user.id)
    return UsageSummaryResponse(
        tier=tier,
        counters=[
            UsageCounterResponse(
                feature_key=row.feature_key.value,
                window_start=row.window_start,
                window_end=row.window_end,
                used_units=row.used_units,
            )
            for row in counters
        ],
    )
