"""Authentication and account lifecycle endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import admin_user, current_user
from app.models import AuditEvent, Organization, User
from app.rate_limit import check_login_rate
from app.schemas import (
    LoginInput,
    PasswordChange,
    TokenView,
    UserAdminView,
    UserUpdate,
    UserView,
)
from app.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api", tags=["accounts"])


def user_view(user: User) -> UserView:
    return UserView(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        organization_name=user.organization.name,
    )


def audit(db, user, target, action):
    db.add(
        AuditEvent(
            organization_id=user.organization_id,
            actor_id=user.id,
            entity_type="user",
            entity_id=target,
            action=action,
            details={},
        )
    )


@router.post("/auth/login", response_model=TokenView)
def login(data: LoginInput, db: Session = Depends(get_db)):
    email = str(data.email).lower()
    check_login_rate(db, email)
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(data.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if user is None or not user.active or not valid:
        raise HTTPException(
            status_code=401,
            detail="Email or password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )
    audit(db, user, user.id, "signed_in")
    db.commit()
    return TokenView(
        access_token=create_access_token(user.id, user.organization_id, user.token_version),
        user=user_view(user),
    )


@router.get("/auth/me", response_model=UserView)
def me(user: User = Depends(current_user)):
    return user_view(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(update(User).where(User.id == user.id).values(token_version=User.token_version + 1))
    audit(db, user, user.id, "all_sessions_revoked")
    db.commit()


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: PasswordChange,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    check_login_rate(db, str(user.email))
    db.refresh(user, with_for_update=True)
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if data.current_password == data.new_password:
        raise HTTPException(status_code=422, detail="Choose a different password")
    user.password_hash = hash_password(data.new_password)
    user.token_version += 1
    audit(db, user, user.id, "password_changed")
    db.commit()


@router.patch("/users/{user_id}", response_model=UserAdminView)
def update_user(
    user_id: str,
    data: UserUpdate,
    actor: User = Depends(admin_user),
    db: Session = Depends(get_db),
):
    # Serialize administrator changes for a tenant, preserving at least one active admin.
    db.execute(
        select(Organization.id).where(Organization.id == actor.organization_id).with_for_update()
    )
    user = db.scalar(
        select(User)
        .where(User.id == user_id, User.organization_id == actor.organization_id)
        .with_for_update()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if (
        user.role == "admin"
        and user.active
        and (data.active is False or (data.role and data.role != "admin"))
    ):
        remaining = db.scalar(
            select(func.count(User.id)).where(
                User.organization_id == actor.organization_id,
                User.active.is_(True),
                User.role == "admin",
                User.id != user.id,
            )
        )
        if not remaining:
            raise HTTPException(
                status_code=409,
                detail="An organisation must retain an active administrator",
            )
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    user.token_version += 1
    audit(db, actor, user.id, "access_updated")
    db.commit()
    return UserAdminView(
        id=user.id, name=user.name, email=user.email, role=user.role, active=user.active
    )
