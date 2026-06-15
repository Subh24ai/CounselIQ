"""Shared FastAPI dependencies for authentication and authorisation."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models import Organisation, User
from app.utils.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated :class:`User` from a bearer access token.

    Raises 401 when the token is invalid/expired or the user no longer exists,
    and 403 when the user exists but has been deactivated (authenticated but
    not permitted).
    """
    payload = decode_access_token(token)
    if payload is None:
        raise _CREDENTIALS_EXCEPTION

    subject = payload.get("sub")
    if subject is None:
        raise _CREDENTIALS_EXCEPTION

    try:
        user_id = UUID(str(subject))
    except (ValueError, TypeError):
        raise _CREDENTIALS_EXCEPTION from None

    result = await db.execute(
        select(User)
        .options(selectinload(User.organisation))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise _CREDENTIALS_EXCEPTION

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Return the current user, ensuring the account is active (403 if not)."""
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    return current_user


def require_roles(
    *roles: str,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    """Build a dependency that allows only users whose role is in ``roles``."""

    async def _role_checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {current_user.role} not permitted for this action",
            )
        return current_user

    return _role_checker


async def get_current_org(
    current_user: User = Depends(get_current_user),
) -> Organisation:
    """Return the organisation the current user belongs to."""
    return current_user.organisation
