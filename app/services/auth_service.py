from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import bad_request, conflict, unauthorized
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    get_password_hash,
    refresh_token_expiry,
    refresh_token_hash,
    verify_password,
)
from app.db.models.user import (
    AuthSession,
    EmailVerificationToken,
    PasswordResetToken,
    User,
    UserConsent,
    UserNutritionPreference,
    UserPhysicalProfile,
    UserSafetyProfile,
    UserTrainingPreference,
)
from app.utils.security_utils import stable_hash


def _new_random_token() -> str:
    return secrets.token_urlsafe(48)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = (
        select(User)
        .options(
            selectinload(User.physical_profile),
            selectinload(User.training_preferences),
            selectinload(User.nutrition_preferences),
            selectinload(User.safety_profile),
        )
        .where(User.email == email.lower())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def register_user(
    session: AsyncSession,
    full_name: str,
    email: str,
    password: str,
    phone: str | None,
    terms_accepted: bool,
    privacy_accepted: bool,
    ip: str | None,
) -> tuple[User, str | None]:
    existing = await get_user_by_email(session, email)
    if existing:
        raise conflict("Email already exists.")
    if not terms_accepted or not privacy_accepted:
        raise bad_request("Terms and privacy acceptance are required.")

    normalized_phone = phone.strip() if phone and phone.strip() else None
    user = User(
        full_name=full_name,
        email=email.lower(),
        phone=normalized_phone,
        password_hash=get_password_hash(password),
    )
    session.add(user)
    await session.flush()

    # Create empty profile records at registration for consistency.
    session.add_all(
        [
            UserPhysicalProfile(user_id=user.id),
            UserTrainingPreference(user_id=user.id),
            UserNutritionPreference(user_id=user.id),
            UserSafetyProfile(user_id=user.id),
            UserConsent(user_id=user.id, document_type="terms", version="1.0", ip_hash=stable_hash(ip)),
            UserConsent(user_id=user.id, document_type="privacy", version="1.0", ip_hash=stable_hash(ip)),
        ]
    )

    raw_email_verification_token: str | None = None
    if settings.enable_email_verification:
        raw_email_verification_token = _new_random_token()
        session.add(
            EmailVerificationToken(
                user_id=user.id,
                token_hash=refresh_token_hash(raw_email_verification_token),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )
    else:
        user.email_verified_at = datetime.now(UTC)
    await session.flush()
    return user, raw_email_verification_token


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
    device_id: str | None,
    user_agent: str | None,
    ip: str | None,
) -> tuple[str, str]:
    user = await get_user_by_email(session, email)
    if not user or not verify_password(password, user.password_hash):
        raise unauthorized("Invalid email or password.")
    if settings.enable_email_verification and not user.email_verified_at:
        raise unauthorized("Email verification is required before login.")

    raw_refresh = generate_refresh_token()
    family_id = uuid4().hex
    session.add(
        AuthSession(
            user_id=user.id,
            device_id=device_id,
            user_agent_hash=stable_hash(user_agent),
            ip_hash=stable_hash(ip),
            refresh_token_hash=refresh_token_hash(raw_refresh),
            family_id=family_id,
            expires_at=refresh_token_expiry(),
        )
    )
    user.last_login_at = datetime.now(UTC)
    access = create_access_token(subject=user.id, extra_claims={"tier": "unknown"})
    await session.flush()
    return access, raw_refresh


async def rotate_refresh_token(
    session: AsyncSession,
    provided_refresh_token: str,
    user_agent: str | None,
    ip: str | None,
) -> tuple[str, str]:
    token_hash = refresh_token_hash(provided_refresh_token)
    now = datetime.now(UTC)
    stmt = select(AuthSession).where(
        and_(
            AuthSession.refresh_token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at >= now,
        )
    )
    db_session = (await session.execute(stmt)).scalar_one_or_none()
    if db_session is None:
        raise unauthorized("Invalid refresh token.")

    db_session.revoked_at = now
    db_session.revoke_reason = "rotated"
    new_refresh = generate_refresh_token()
    session.add(
        AuthSession(
            user_id=db_session.user_id,
            device_id=db_session.device_id,
            user_agent_hash=stable_hash(user_agent),
            ip_hash=stable_hash(ip),
            refresh_token_hash=refresh_token_hash(new_refresh),
            family_id=db_session.family_id,
            expires_at=refresh_token_expiry(),
        )
    )
    access = create_access_token(subject=db_session.user_id, extra_claims={"tier": "unknown"})
    await session.flush()
    return access, new_refresh


async def logout_by_refresh_token(session: AsyncSession, provided_refresh_token: str) -> None:
    token_hash = refresh_token_hash(provided_refresh_token)
    stmt = select(AuthSession).where(
        and_(AuthSession.refresh_token_hash == token_hash, AuthSession.revoked_at.is_(None))
    )
    db_session = (await session.execute(stmt)).scalar_one_or_none()
    if db_session:
        db_session.revoked_at = datetime.now(UTC)
        db_session.revoke_reason = "logout"
        await session.flush()


async def issue_password_reset_token(session: AsyncSession, email: str) -> str | None:
    user = await get_user_by_email(session, email)
    if not user:
        return None
    raw_token = _new_random_token()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=refresh_token_hash(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
    )
    await session.flush()
    return raw_token


async def reset_password(session: AsyncSession, token: str, new_password: str) -> None:
    token_hash = refresh_token_hash(token)
    stmt = select(PasswordResetToken).where(
        and_(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at >= datetime.now(UTC),
        )
    )
    reset_obj = (await session.execute(stmt)).scalar_one_or_none()
    if reset_obj is None:
        raise bad_request("Invalid or expired reset token.")
    user_stmt = select(User).where(User.id == reset_obj.user_id).limit(1)
    user = (await session.execute(user_stmt)).scalar_one()
    user.password_hash = get_password_hash(new_password)
    reset_obj.used_at = datetime.now(UTC)
    await session.flush()


async def verify_email_with_token(session: AsyncSession, token: str) -> None:
    token_hash = refresh_token_hash(token)
    stmt = select(EmailVerificationToken).where(
        and_(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.used_at.is_(None),
            EmailVerificationToken.expires_at >= datetime.now(UTC),
        )
    )
    token_obj = (await session.execute(stmt)).scalar_one_or_none()
    if token_obj is None:
        raise bad_request("Invalid or expired verification token.")
    user_stmt = select(User).where(User.id == token_obj.user_id).limit(1)
    user = (await session.execute(user_stmt)).scalar_one()
    user.email_verified_at = datetime.now(UTC)
    token_obj.used_at = datetime.now(UTC)
    await session.flush()


async def get_user_from_access_token(session: AsyncSession, token: str) -> User:
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise unauthorized("Invalid access token.") from exc
    if payload.get("type") != "access":
        raise unauthorized("Invalid access token.")
    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized("Invalid token payload.")
    stmt = (
        select(User)
        .options(
            selectinload(User.physical_profile),
            selectinload(User.training_preferences),
            selectinload(User.nutrition_preferences),
            selectinload(User.safety_profile),
        )
        .where(User.id == user_id)
        .limit(1)
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise unauthorized("User not found.")
    return user
