from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.db.models.enums import MembershipStatus


class MembershipCurrentResponse(BaseModel):
    membership_id: str | None = None
    plan_code: str
    plan_name: str
    status: MembershipStatus | str
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    auto_renew: bool = False
    is_premium: bool


class MembershipSubscribeRequest(BaseModel):
    plan_code: str
    provider: str = "stripe"


class MembershipSubscribeResponse(BaseModel):
    membership_id: str
    status: MembershipStatus
    checkout_reference: str


class MembershipCancelResponse(BaseModel):
    membership_id: str
    status: MembershipStatus
    canceled_at: datetime
