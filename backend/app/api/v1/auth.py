"""Authentication router: register, login, refresh, logout, and self-service."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Organisation, User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse, UserUpdate
from app.services.audit import write_audit_log
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    """Best-effort extraction of the client IP for audit logging."""
    return request.client.host if request.client else None


def _issue_tokens(user: User) -> TokenResponse:
    """Mint an access + refresh token pair for a user."""
    claims = {"sub": str(user.id), "org": str(user.organisation_id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(claims),
        refresh_token=create_refresh_token({"sub": str(user.id)}),
    )


@router.post("/register", response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Create a new organisation and its first user (an ``org_admin``)."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    organisation = Organisation(
        name=body.organisation_name,
        domain=body.domain,
        plan=body.plan,
    )
    db.add(organisation)
    await db.flush()

    user = User(
        organisation_id=organisation.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role="org_admin",
    )
    db.add(user)
    await db.flush()

    await write_audit_log(
        db,
        organisation_id=organisation.id,
        action="user.register",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        payload={"email": user.email},
        ip_address=_client_ip(request),
    )

    await db.commit()
    await db.refresh(user)
    return _issue_tokens(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate a user with email + password and issue tokens."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    user.last_login = datetime.now(UTC)
    await write_audit_log(
        db,
        organisation_id=user.organisation_id,
        action="user.login",
        user_id=user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=_client_ip(request),
    )

    await db.commit()
    await db.refresh(user)
    return _issue_tokens(user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Issue a new access token from a valid refresh token (no rotation)."""
    payload = decode_access_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    result = await db.execute(select(User).where(User.id == subject))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    claims = {"sub": str(user.id), "org": str(user.organisation_id), "role": user.role}
    return TokenResponse(
        access_token=create_access_token(claims),
        refresh_token=body.refresh_token,
    )


@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Log the user out. Token invalidation is client-side for now."""
    await write_audit_log(
        db,
        organisation_id=current_user.organisation_id,
        action="user.logout",
        user_id=current_user.id,
        resource_type="user",
        resource_id=current_user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user."""
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Update the current user's own profile (only ``full_name`` is allowed)."""
    if body.full_name is not None:
        current_user.full_name = body.full_name

    # Role and activation status are never self-mutable; those changes go
    # through the admin users router. Any such fields in the body are ignored.

    await db.commit()
    await db.refresh(current_user)
    return current_user
