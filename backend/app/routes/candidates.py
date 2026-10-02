from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import current_user, recruiter_user
from app.models import (
    AuditEvent,
    Candidate,
    CandidateScore,
    Interview,
    Job,
    Screening,
    User,
)
from app.schemas import (
    AuditEventView,
    CandidateInput,
    CandidateUpdate,
    CandidateView,
    MatchCriterion,
    MatchView,
    ScreeningInput,
    ScreeningView,
)
from app.services import candidate_view, get_candidate, get_job, record_audit

router = APIRouter(tags=["candidates"])


@router.get("/api/candidates", response_model=list[CandidateView])
def list_candidates(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[CandidateView]:
    if user.role not in {"admin", "recruiter", "hiring_manager", "interviewer"}:
        raise HTTPException(status_code=403, detail="Candidate access required")
    query = (
        select(Candidate)
        .options(selectinload(Candidate.scores))
        .where(Candidate.organization_id == user.organization_id)
    )
    if user.role == "interviewer":
        query = (
            query.join(Interview, Interview.candidate_id == Candidate.id)
            .where(Interview.interviewer_id == user.id)
            .distinct()
        )
    candidates = db.scalars(
        query.order_by(Candidate.created_at.desc(), Candidate.id).limit(limit).offset(offset)
    ).all()
    results = [candidate_view(candidate) for candidate in candidates]
    if user.role in {"hiring_manager", "interviewer"}:
        for item in results:
            item.current_ctc = ""
            item.expected_ctc = ""
    return results


@router.post("/api/candidates", response_model=CandidateView, status_code=status.HTTP_201_CREATED)
def create_candidate(
    data: CandidateInput,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> CandidateView:
    if (
        data.job_id
        and db.scalar(
            select(Job.id).where(Job.id == data.job_id, Job.organization_id == user.organization_id)
        )
        is None
    ):
        raise HTTPException(status_code=404, detail="Job not found")
    duplicate = db.scalar(
        select(Candidate.id).where(
            Candidate.organization_id == user.organization_id,
            func.lower(Candidate.email) == str(data.email).lower(),
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="Candidate with this email already exists in your organisation",
        )
    candidate = Candidate(
        organization_id=user.organization_id,
        job_id=data.job_id,
        name=data.name.strip(),
        email=str(data.email).lower(),
        role_title=data.role_title.strip(),
        stage=data.stage,
        experience=data.experience.strip(),
        skills=",".join(skill.strip() for skill in data.skills if skill.strip()),
        current_ctc=data.current_ctc.strip(),
        expected_ctc=data.expected_ctc.strip(),
        availability=data.availability.strip(),
    )
    db.add(candidate)
    db.flush()
    record_audit(
        db,
        user.organization_id,
        user.id,
        "candidate",
        candidate.id,
        "created",
        {"stage": candidate.stage},
    )
    db.commit()
    return candidate_view(candidate)


@router.patch("/api/candidates/{candidate_id}", response_model=CandidateView)
def update_candidate(
    candidate_id: str,
    data: CandidateUpdate,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> CandidateView:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    if "email" in data.model_fields_set and data.email:
        duplicate = db.scalar(
            select(Candidate.id).where(
                Candidate.organization_id == user.organization_id,
                func.lower(Candidate.email) == str(data.email).lower(),
                Candidate.id != candidate.id,
            )
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Another candidate in this organisation already uses that email",
            )
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "email" and value:
            value = str(value).lower()
        setattr(
            candidate,
            field,
            ",".join(skill.strip() for skill in value if skill.strip())
            if field == "skills" and value is not None
            else value,
        )
    updated_fields = set(data.model_fields_set) - {
        "current_ctc",
        "expected_ctc",
        "email",
    }
    record_audit(
        db,
        user.organization_id,
        user.id,
        "candidate",
        candidate.id,
        "updated",
        {
            "fields": sorted(updated_fields),
            "contact_email_updated": "email" in data.model_fields_set,
        },
    )
    db.commit()
    db.refresh(candidate)
    return candidate_view(candidate)


@router.delete("/api/candidates/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: str,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> None:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    db.delete(candidate)
    record_audit(db, user.organization_id, user.id, "candidate", candidate_id, "deleted")
    db.commit()


@router.get("/api/candidates/{candidate_id}/screenings", response_model=list[ScreeningView])
def list_screenings(
    candidate_id: str,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> list[Screening]:
    get_candidate(candidate_id, user.organization_id, db)
    return list(
        db.scalars(
            select(Screening)
            .where(
                Screening.candidate_id == candidate_id,
                Screening.organization_id == user.organization_id,
            )
            .order_by(Screening.created_at.desc())
        ).all()
    )


@router.post(
    "/api/candidates/{candidate_id}/screenings",
    response_model=ScreeningView,
    status_code=status.HTTP_201_CREATED,
)
def create_screening(
    candidate_id: str,
    data: ScreeningInput,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> Screening:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    screening = Screening(
        organization_id=user.organization_id,
        candidate_id=candidate.id,
        recruiter_id=user.id,
        **data.model_dump(),
    )
    candidate.current_ctc = data.current_ctc or candidate.current_ctc
    candidate.expected_ctc = data.expected_ctc or candidate.expected_ctc
    candidate.availability = data.notice_period or candidate.availability
    candidate.stage = {
        "Shortlist": "Tech round 1",
        "Hold": "Screening",
        "Reject": "Rejected",
    }[data.decision]
    record_audit(
        db,
        user.organization_id,
        user.id,
        "candidate",
        candidate.id,
        "screening_recorded",
        {"decision": data.decision},
    )
    db.add(screening)
    db.commit()
    db.refresh(screening)
    return screening


@router.post("/api/candidates/{candidate_id}/match", response_model=MatchView)
def score_candidate(
    candidate_id: str,
    job_id: str,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> MatchView:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    job = get_job(job_id, user.organization_id, db)
    requirements = list(job.requirements)
    skills = {skill.strip().casefold() for skill in candidate.skills.split(",") if skill.strip()}
    criteria: list[MatchCriterion] = []
    available_weight = 0
    achieved_weight = 0.0
    for requirement in requirements:
        matched = requirement.skill.casefold() in skills
        if requirement.category == "disqualifying":
            criteria.append(
                MatchCriterion(
                    skill=requirement.skill,
                    category=requirement.category,
                    weight=requirement.weight,
                    matched=matched,
                    evidence_level=1 if matched else 0,
                    evidence="Self-reported profile skill; verify manually. Flag only, never an automatic rejection.",
                )
            )
            continue
        available_weight += requirement.weight
        credit = 0.5 if matched and requirement.category == "trainable" else 1.0 if matched else 0.0
        achieved_weight += requirement.weight * credit
        criteria.append(
            MatchCriterion(
                skill=requirement.skill,
                category=requirement.category,
                weight=requirement.weight,
                matched=matched,
                evidence_level=1 if matched else 0,
                evidence="Self-reported profile skill; resume/project evidence has not been verified."
                if matched
                else "No matching skill recorded in the candidate profile.",
            )
        )
    score = round(achieved_weight / available_weight * 100) if available_weight else 0
    existing = db.scalar(
        select(CandidateScore).where(
            CandidateScore.organization_id == user.organization_id,
            CandidateScore.candidate_id == candidate.id,
            CandidateScore.job_id == job.id,
        )
    )
    if existing:
        existing.score = score
        existing.criteria = [item.model_dump() for item in criteria]
        existing.created_at = datetime.now(timezone.utc)
    else:
        db.add(
            CandidateScore(
                organization_id=user.organization_id,
                candidate_id=candidate.id,
                job_id=job.id,
                score=score,
                criteria=[item.model_dump() for item in criteria],
            )
        )
    record_audit(
        db,
        user.organization_id,
        user.id,
        "candidate",
        candidate.id,
        "match_calculated",
        {"job_id": job.id, "score": score},
    )
    db.commit()
    return MatchView(
        candidate_id=candidate.id,
        job_id=job.id,
        score=score,
        methodology="deterministic-v1",
        decision_note="Profile-only comparison. This is not AI and does not verify resume claims or make a hiring decision.",
        criteria=criteria,
    )


@router.get("/api/candidates/{candidate_id}/activity", response_model=list[AuditEventView])
def candidate_activity(
    candidate_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[AuditEventView]:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    if user.role == "interviewer":
        assigned = db.scalar(
            select(Interview.id).where(
                Interview.organization_id == user.organization_id,
                Interview.candidate_id == candidate.id,
                Interview.interviewer_id == user.id,
            )
        )
        if not assigned:
            raise HTTPException(status_code=403, detail="Candidate is not assigned to you")
    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.organization_id == user.organization_id,
            AuditEvent.entity_id == candidate.id,
            AuditEvent.entity_type.in_(["candidate", "application"]),
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
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
