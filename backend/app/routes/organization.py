from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import admin_user, coordinator_user, current_user
from app.models import (
    AuditEvent,
    Candidate,
    Interview,
    Job,
    Offer,
    OrganizationSettings,
    RecruiterTask,
    User,
)
from app.schemas import (
    AuditEventView,
    OrganizationSettingsInput,
    OrganizationSettingsView,
    UserAdminView,
    UserCreate,
)
from app.security import hash_password
from app.services import record_audit

router = APIRouter(tags=["organization"])


@router.get("/api/users", response_model=list[UserAdminView])
def list_users(
    user: User = Depends(admin_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[UserAdminView]:
    users = db.scalars(
        select(User)
        .where(User.organization_id == user.organization_id)
        .order_by(User.name, User.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        UserAdminView(
            id=item.id,
            name=item.name,
            email=item.email,
            role=item.role,
            active=item.active,
        )
        for item in users
    ]


@router.get("/api/team/directory", response_model=list[UserAdminView])
def team_directory(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[UserAdminView]:
    users = db.scalars(
        select(User)
        .where(User.organization_id == user.organization_id, User.active.is_(True))
        .order_by(User.name, User.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        UserAdminView(
            id=item.id,
            name=item.name,
            email=item.email,
            role=item.role,
            active=item.active,
        )
        for item in users
    ]


@router.post("/api/users", response_model=UserAdminView, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate, user: User = Depends(admin_user), db: Session = Depends(get_db)
) -> UserAdminView:
    email = str(data.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    teammate = User(
        organization_id=user.organization_id,
        email=email,
        name=data.name.strip(),
        role=data.role,
        password_hash=hash_password(data.password),
    )
    db.add(teammate)
    db.flush()
    record_audit(
        db,
        user.organization_id,
        user.id,
        "user",
        teammate.id,
        "created",
        {"role": teammate.role},
    )
    db.commit()
    db.refresh(teammate)
    return UserAdminView(
        id=teammate.id,
        name=teammate.name,
        email=teammate.email,
        role=teammate.role,
        active=teammate.active,
    )


@router.get("/api/settings", response_model=OrganizationSettingsView)
def get_organization_settings(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> OrganizationSettingsView:
    settings_row = db.get(OrganizationSettings, user.organization_id)
    if settings_row is None:
        settings_row = OrganizationSettings(organization_id=user.organization_id)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return OrganizationSettingsView(
        organization_id=user.organization_id,
        timezone=settings_row.timezone,
        careers_intro=settings_row.careers_intro,
        retention_days=settings_row.retention_days,
        require_candidate_consent=settings_row.require_candidate_consent,
    )


@router.put("/api/settings", response_model=OrganizationSettingsView)
def update_organization_settings(
    data: OrganizationSettingsInput,
    user: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> OrganizationSettingsView:
    settings_row = db.get(OrganizationSettings, user.organization_id)
    if settings_row is None:
        settings_row = OrganizationSettings(organization_id=user.organization_id)
        db.add(settings_row)
    for field, value in data.model_dump().items():
        setattr(settings_row, field, value)
    record_audit(
        db,
        user.organization_id,
        user.id,
        "organization",
        user.organization_id,
        "settings_updated",
    )
    db.commit()
    db.refresh(settings_row)
    return OrganizationSettingsView(
        organization_id=user.organization_id,
        timezone=settings_row.timezone,
        careers_intro=settings_row.careers_intro,
        retention_days=settings_row.retention_days,
        require_candidate_consent=settings_row.require_candidate_consent,
    )


@router.get("/api/audit-events", response_model=list[AuditEventView])
def list_audit_events(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[AuditEventView]:
    if user.role not in {"admin", "recruiter", "hiring_manager"}:
        raise HTTPException(status_code=403, detail="Audit access required")
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.organization_id == user.organization_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(200)
    ).all()
    return [
        AuditEventView(
            id=item.id,
            actor_id=item.actor_id,
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            action=item.action,
            details=item.details,
            created_at=item.created_at,
        )
        for item in events
    ]


@router.get("/api/dashboard/summary")
def dashboard_summary(
    user: User = Depends(coordinator_user), db: Session = Depends(get_db)
) -> dict:
    org_id = user.organization_id
    stage_counts = dict(
        db.execute(
            select(Candidate.stage, func.count(Candidate.id))
            .where(Candidate.organization_id == org_id)
            .group_by(Candidate.stage)
        ).all()
    )
    return {
        "active_candidates": sum(
            count
            for stage, count in stage_counts.items()
            if stage not in {"Hired", "Rejected", "Closed", "Candidate Withdrew"}
        ),
        "candidates_by_stage": stage_counts,
        "open_jobs": db.scalar(
            select(func.count(Job.id)).where(
                Job.organization_id == org_id, Job.status == "published"
            )
        )
        or 0,
        "upcoming_interviews": db.scalar(
            select(func.count(Interview.id)).where(
                Interview.organization_id == org_id,
                Interview.status == "scheduled",
                Interview.scheduled_for >= datetime.now(timezone.utc),
            )
        )
        or 0,
        "pending_offers": db.scalar(
            select(func.count(Offer.id)).where(
                Offer.organization_id == org_id,
                Offer.status.in_(["draft", "approved", "sent"]),
            )
        )
        or 0,
        "open_tasks": db.scalar(
            select(func.count(RecruiterTask.id)).where(
                RecruiterTask.organization_id == org_id, RecruiterTask.status == "open"
            )
        )
        or 0,
    }
