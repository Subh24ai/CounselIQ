"""Password hashing and JWT token utilities.

Passwords are hashed with bcrypt via passlib. Access and refresh tokens are
signed JWTs using the application's ``JWT_SECRET_KEY`` / ``JWT_ALGORITHM``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Refresh tokens are long-lived; access tokens use JWT_EXPIRE_MINUTES.
REFRESH_TOKEN_EXPIRE_DAYS = 7


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of ``plain``."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if ``plain`` matches the bcrypt ``hashed`` value."""
    try:
        return pwd_context.verify(plain, hashed)
    except (ValueError, TypeError):
        # Malformed hash or input — treat as a failed verification, never raise.
        return False


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed access-token JWT.

    ``data`` is copied into the payload. An ``exp`` claim is added using
    ``expires_delta`` when given, otherwise ``JWT_EXPIRE_MINUTES`` from settings.
    """
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(data: dict[str, Any]) -> str:
    """Create a signed refresh-token JWT (7-day expiry, ``type='refresh'``)."""
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT, returning its payload or ``None`` on any error."""
    try:
        return jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
    except JWTError:
        return None
