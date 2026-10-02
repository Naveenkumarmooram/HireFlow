from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import current_user, recruiter_user
from app.models import (
    Job,
    JobRequirement,
    User,
)
from app.schemas import (
    JobInput,
    JobView,
)
from app.services import get_job, job_view, record_audit

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs", response_model=list[JobView])
def list_jobs(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[JobView]:
    jobs = db.scalars(
        select(Job)
        .options(selectinload(Job.requirements))
        .where(Job.organization_id == user.organization_id)
        .order_by(Job.created_at.desc(), Job.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [job_view(job, db) for job in jobs]


@router.post("/api/jobs", response_model=JobView, status_code=status.HTTP_201_CREATED)
def create_job(
    data: JobInput, user: User = Depends(recruiter_user), db: Session = Depends(get_db)
) -> JobView:
    job = Job(
        organization_id=user.organization_id,
        title=data.title.strip(),
        location=data.location.strip(),
        employment_type=data.employment_type,
        status=data.status,
        description=data.description.strip(),
    )
    job.requirements = [
        JobRequirement(
            organization_id=user.organization_id,
            skill=item.skill.strip(),
            category=item.category,
            weight=item.weight,
            min_evidence_level=item.min_evidence_level,
        )
        for item in data.requirements
    ]
    db.add(job)
    db.flush()
    record_audit(
        db,
        user.organization_id,
        user.id,
        "job",
        job.id,
        "created",
        {"status": job.status},
    )
    db.commit()
    db.refresh(job)
    return job_view(job, db)


@router.patch("/api/jobs/{job_id}/status", response_model=JobView)
def set_job_status(
    job_id: str,
    status_value: str,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> JobView:
    if status_value not in {"draft", "published", "closed"}:
        raise HTTPException(status_code=422, detail="Status must be draft, published, or closed")
    job = get_job(job_id, user.organization_id, db)
    job.status = status_value
    record_audit(
        db,
        user.organization_id,
        user.id,
        "job",
        job.id,
        "status_changed",
        {"status": status_value},
    )
    db.commit()
    db.refresh(job)
    return job_view(job, db)
