import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import (
    Application,
    Candidate,
    Job,
    Offer,
)
from app.schemas import (
    ApplicationReceipt,
    CandidatePortalView,
    PublicApplicationInput,
    PublicJobView,
    PublicOfferView,
)
from app.services import get_job, record_audit

router = APIRouter(tags=["public"])


@router.get("/api/public/jobs", response_model=list[PublicJobView])
def public_jobs(
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[PublicJobView]:
    jobs = db.scalars(
        select(Job)
        .options(selectinload(Job.requirements), selectinload(Job.organization))
        .where(Job.status == "published")
        .order_by(Job.created_at.desc(), Job.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        PublicJobView(
            id=job.id,
            title=job.title,
            location=job.location,
            employment_type=job.employment_type,
            description=job.description,
            organization_name=job.organization.name,
            requirements=[item.skill for item in job.requirements if item.category == "must_have"],
        )
        for job in jobs
    ]


@router.post(
    "/api/public/jobs/{job_id}/applications",
    response_model=ApplicationReceipt,
    status_code=status.HTTP_201_CREATED,
)
def apply_to_job(
    job_id: str, data: PublicApplicationInput, db: Session = Depends(get_db)
) -> ApplicationReceipt:
    if not data.consent:
        raise HTTPException(status_code=400, detail="Candidate data-processing consent is required")
    job = db.scalar(select(Job).where(Job.id == job_id, Job.status == "published"))
    if job is None:
        raise HTTPException(status_code=404, detail="Published job not found")
    email = str(data.email).lower()
    if db.scalar(
        select(Application.id).where(Application.job_id == job.id, Application.email == email)
    ):
        raise HTTPException(status_code=409, detail="An application for this role already exists")
    candidate = db.scalar(
        select(Candidate).where(
            Candidate.organization_id == job.organization_id,
            func.lower(Candidate.email) == email,
        )
    )
    if candidate is None:
        candidate = Candidate(
            organization_id=job.organization_id,
            job_id=job.id,
            name=data.name.strip(),
            email=email,
            role_title=job.title,
            stage="Applied",
            experience=data.experience.strip(),
            skills=",".join(skill.strip() for skill in data.skills if skill.strip()),
            availability=data.availability.strip(),
            source="careers_page",
        )
        db.add(candidate)
        db.flush()
    portal_token = secrets.token_urlsafe(32)
    db.add(
        Application(
            organization_id=job.organization_id,
            job_id=job.id,
            candidate_id=candidate.id,
            email=email,
            source="careers_page",
            consent_text="I consent to this organisation processing my application data for recruitment.",
            portal_token_hash=hashlib.sha256(portal_token.encode()).hexdigest(),
            answers={"submitted_name": data.name, "withdrawn": False},
        )
    )
    record_audit(
        db,
        job.organization_id,
        None,
        "application",
        candidate.id,
        "submitted",
        {"job_id": job.id, "source": data.source},
    )
    db.commit()
    return ApplicationReceipt(
        status="received",
        message="Application received. Save this private link to view your application status or withdraw.",
        portal_url=f"/candidate/{portal_token}",
    )


@router.get("/api/public/candidates/{token}", response_model=CandidatePortalView)
def candidate_portal(token: str, db: Session = Depends(get_db)) -> CandidatePortalView:
    application = db.scalar(
        select(Application).where(
            Application.portal_token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Candidate portal link not found")
    # A supplied email is not verified identity. Expose only this submission,
    # never existing candidate records, interviews, or unrelated offers.
    return CandidatePortalView(
        candidate_name=application.answers.get("submitted_name", "Applicant"),
        job_title=get_job(application.job_id, application.organization_id, db).title,
        application_status="Candidate Withdrew"
        if application.answers.get("withdrawn")
        else "Applied",
        last_updated=application.consented_at,
        interviews=[],
        offer_status=None,
    )


@router.post("/api/public/candidates/{token}/withdraw")
def withdraw_application(token: str, db: Session = Depends(get_db)) -> dict[str, str]:
    application = db.scalar(
        select(Application).where(
            Application.portal_token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Candidate portal link not found")
    if application.answers.get("withdrawn"):
        return {"status": "withdrawn"}
    application.answers = {**application.answers, "withdrawn": True}
    count = db.scalar(
        select(func.count(Application.id)).where(
            Application.candidate_id == application.candidate_id
        )
    )
    if (
        count == 1
        and application.candidate.source == "careers_page"
        and application.candidate.job_id == application.job_id
    ):
        application.candidate.stage = "Candidate Withdrew"
    record_audit(
        db,
        application.organization_id,
        None,
        "application",
        application.candidate_id,
        "withdrawn",
        {"job_id": application.job_id},
    )
    db.commit()
    return {"status": "withdrawn"}


@router.get("/api/public/offers/{token}", response_model=PublicOfferView)
def public_offer(token: str, db: Session = Depends(get_db)) -> PublicOfferView:
    offer = db.scalar(
        select(Offer).where(
            Offer.acceptance_token_hash == hashlib.sha256(token.encode()).hexdigest()
        )
    )
    if offer is None or offer.status not in {"approved", "sent"}:
        raise HTTPException(status_code=404, detail="Offer link is invalid or unavailable")
    expiry = offer.expires_at
    if expiry and (
        expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry
    ) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Offer has expired")
    return PublicOfferView(
        candidate_name=offer.candidate.name,
        title=offer.title,
        compensation=offer.compensation,
        employment_type=offer.employment_type,
        joining_date=offer.joining_date,
        status=offer.status,
        expires_at=offer.expires_at,
    )


@router.post("/api/public/offers/{token}/decision")
def offer_decision(token: str, decision: str, db: Session = Depends(get_db)) -> dict[str, str]:
    if decision not in {"accept", "decline"}:
        raise HTTPException(status_code=422, detail="Decision must be accept or decline")
    offer = db.scalar(
        select(Offer)
        .where(Offer.acceptance_token_hash == hashlib.sha256(token.encode()).hexdigest())
        .with_for_update()
    )
    if offer is None or offer.status not in {"approved", "sent"}:
        raise HTTPException(status_code=404, detail="Offer link is invalid or unavailable")
    expires_at = offer.expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Offer has expired")
    offer.status = "accepted" if decision == "accept" else "declined"
    if decision == "accept":
        offer.accepted_at = datetime.now(timezone.utc)
        offer.candidate.stage = "Offer Accepted"
    else:
        offer.candidate.stage = "Offer Declined"
    record_audit(
        db,
        offer.organization_id,
        None,
        "offer",
        offer.id,
        decision,
        {"candidate_id": offer.candidate_id},
    )
    db.commit()
    return {"status": offer.status}
