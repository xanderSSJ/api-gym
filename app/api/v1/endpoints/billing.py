from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import unauthorized
from app.db.models.enums import MembershipStatus, PaymentStatus
from app.db.models.membership import PaymentTransaction, PaymentWebhookEvent, UserMembership
from app.db.session import get_db_session
from app.schemas.billing import WebhookAck

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/webhooks/stripe", response_model=WebhookAck)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    session: AsyncSession = Depends(get_db_session),
) -> WebhookAck:
    if settings.payment_webhook_secret and stripe_signature != settings.payment_webhook_secret:
        raise unauthorized("Invalid webhook signature.")

    payload = await request.json()
    event_id = str(payload.get("id", ""))
    event_type = str(payload.get("type", "unknown"))

    existing = (
        await session.execute(
            select(PaymentWebhookEvent).where(
                PaymentWebhookEvent.provider == "stripe",
                PaymentWebhookEvent.provider_event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return WebhookAck(received=True)

    event = PaymentWebhookEvent(
        provider="stripe",
        provider_event_id=event_id,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    await session.flush()

    if event_type == "invoice.paid":
        data = payload.get("data", {}).get("object", {})
        membership_id = data.get("metadata", {}).get("membership_id")
        amount_paid = (data.get("amount_paid") or 0) / 100
        currency = str(data.get("currency", "usd")).upper()
        if membership_id:
            membership = (
                await session.execute(select(UserMembership).where(UserMembership.id == membership_id))
            ).scalar_one_or_none()
            if membership:
                membership.status = MembershipStatus.ACTIVE
                session.add(
                    PaymentTransaction(
                        user_membership_id=membership.id,
                        provider="stripe",
                        provider_payment_id=str(data.get("payment_intent") or event_id),
                        amount=amount_paid,
                        currency=currency,
                        status=PaymentStatus.SUCCEEDED,
                        paid_at=datetime.now(UTC),
                        invoice_url=data.get("hosted_invoice_url"),
                        metadata_json={"event_id": event_id},
                    )
                )

    event.processed_at = datetime.now(UTC)
    await session.commit()
    return WebhookAck(received=True)
