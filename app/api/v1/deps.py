from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import forbidden, unauthorized
from app.db.models.user import User
from app.db.session import get_db_session
from app.services.auth_service import get_user_from_access_token
from app.services.membership_service import get_membership_context

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if credentials is None:
        raise unauthorized("Authorization header is required.")
    return await get_user_from_access_token(session, credentials.credentials)


async def require_premium(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    membership = await get_membership_context(session, current_user.id)
    if not membership.is_premium:
        raise forbidden("Premium membership is required.")
    return current_user


def request_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
