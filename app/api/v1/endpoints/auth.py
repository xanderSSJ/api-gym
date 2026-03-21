from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, request_ip
from app.core.config import settings
from app.core.exceptions import too_many_requests
from app.core.rate_limit import rate_limit_hit
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPairResponse,
    VerifyEmailRequest,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import (
    authenticate_user,
    issue_password_reset_token,
    logout_by_refresh_token,
    register_user,
    reset_password,
    rotate_refresh_token,
    verify_email_with_token,
)
from app.services.membership_service import get_or_create_free_membership

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    ip = request_ip(request)
    allowed, _ = await rate_limit_hit(
        key=f"rate:register:{ip}",
        limit=settings.max_register_attempts_per_hour,
        window_seconds=3600,
    )
    if not allowed:
        raise too_many_requests("Too many registration attempts. Please try later.")

    user, verification_token = await register_user(
        session=session,
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        phone=payload.phone,
        terms_accepted=payload.terms_accepted,
        privacy_accepted=payload.privacy_accepted,
        ip=ip,
    )
    await get_or_create_free_membership(session, user.id)
    await session.commit()

    response = {
        "data": {
            "user_id": user.id,
            "email": user.email,
            "email_verification_required": settings.enable_email_verification,
        }
    }
    if settings.app_env != "production" and verification_token:
        response["data"]["verification_token_dev"] = verification_token
    return response


@router.post("/login", response_model=TokenPairResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPairResponse:
    ip = request_ip(request)
    allowed, _ = await rate_limit_hit(
        key=f"rate:login:{ip}:{payload.email.lower()}",
        limit=settings.max_login_attempts_per_15_min,
        window_seconds=900,
    )
    if not allowed:
        raise too_many_requests("Too many login attempts. Please try later.")

    access_token, refresh_token = await authenticate_user(
        session=session,
        email=payload.email,
        password=payload.password,
        device_id=payload.device_id,
        user_agent=request.headers.get("user-agent"),
        ip=ip,
    )
    await session.commit()
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_token(
    payload: RefreshTokenRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPairResponse:
    access_token, refresh_token = await rotate_refresh_token(
        session=session,
        provided_refresh_token=payload.refresh_token,
        user_agent=request.headers.get("user-agent"),
        ip=request_ip(request),
    )
    await session.commit()
    return TokenPairResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: RefreshTokenRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    await logout_by_refresh_token(session, payload.refresh_token)
    await session.commit()
    return MessageResponse(message="Session closed.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    token = await issue_password_reset_token(session, payload.email)
    await session.commit()
    # In production, token must be emailed instead of returned.
    if settings.app_env != "production" and token:
        return MessageResponse(message=f"Reset token (dev only): {token}")
    return MessageResponse(message="If the email exists, password reset instructions were sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password_endpoint(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    await reset_password(session, payload.token, payload.new_password)
    await session.commit()
    return MessageResponse(message="Password updated successfully.")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    payload: VerifyEmailRequest,
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    await verify_email_with_token(session, payload.token)
    await session.commit()
    return MessageResponse(message="Email verified successfully.")
