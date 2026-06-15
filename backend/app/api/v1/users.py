"""Admin users router. All endpoints are org_admin-only and org-scoped."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.models import User
from app.schemas.user import UserCreateInOrg, UserResponse, UserUpdate
from app.services.audit import write_audit_log
from app.utils.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])

# Every endpoint in this router is restricted to organisation admins. Building
# the dependency once (rather than per-route) keeps the signatures clean.
require_org_admin = require_roles("org_admin")


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _get_org_user(db: AsyncSession, user_id: UUID, organisation_id: UUID) -> User:
    """Fetch a user by id within an organisation, or raise 404.

    Scoping the lookup by organisation_id ensures one org can never read or
    mutate another org's users (returns 404, not 403, to avoid leaking
    existence across tenants).
    """
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.organisation_id == organisation_id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.get("/", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    """List every user in the caller's organisation."""
    result = await db.execute(
        select(User)
        .where(User.organisation_id == current_user.organisation_id)
        .order_by(User.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateInOrg,
    request: Request,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Create a new user inside the caller's organisation."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = User(
        organisation_id=current_user.organisation_id,
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    await db.flush()

    await write_audit_log(
        db,
        organisation_id=current_user.organisation_id,
        action="user.create",
        user_id=current_user.id,
        resource_type="user",
        resource_id=user.id,
        payload={"email": user.email, "role": user.role},
        ip_address=_client_ip(request),
    )

    await db.commit()
    await db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Fetch a single user from the caller's organisation."""
    return await _get_org_user(db, user_id, current_user.organisation_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    request: Request,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Update a user's full_name, role, and/or active status."""
    user = await _get_org_user(db, user_id, current_user.organisation_id)

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)

    await write_audit_log(
        db,
        organisation_id=current_user.organisation_id,
        action="user.update",
        user_id=current_user.id,
        resource_type="user",
        resource_id=user.id,
        payload=updates,
        ip_address=_client_ip(request),
    )

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: UUID,
    request: Request,
    current_user: User = Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Soft-delete a user by deactivating the account."""
    user = await _get_org_user(db, user_id, current_user.organisation_id)
    user.is_active = False

    await write_audit_log(
        db,
        organisation_id=current_user.organisation_id,
        action="user.delete",
        user_id=current_user.id,
        resource_type="user",
        resource_id=user.id,
        ip_address=_client_ip(request),
    )

    await db.commit()
    await db.refresh(user)
    return user
