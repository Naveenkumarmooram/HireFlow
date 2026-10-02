from contextlib import asynccontextmanager
from datetime import datetime, timezone
import hashlib
from io import BytesIO
from pathlib import Path
import re
import secrets
import zipfile
from xml.etree import ElementTree

from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
import clamd
from pypdf import PdfReader

from app.config import settings
from app.database import engine, get_db
from app.deps import admin_user, coordinator_user, current_user, recruiter_user
from app.models import (
    Application, AuditEvent, Candidate, CandidateScore, EmailTemplate, Interview, InterviewFeedback,
    Job, JobRequirement, Offer, Organization, OrganizationSettings, OutboundMessage, RecruiterTask,
    ResumeDocument, Screening, User,
)
from app.schemas import (
    ApplicationReceipt, AuditEventView, CandidateInput, CandidatePortalView, CandidateUpdate, CandidateView, CommunicationDraftInput, CommunicationDraftView, EmailTemplateInput, EmailTemplateView, FeedbackInput, InterviewInput,
    InterviewView, JobInput, JobView, LoginInput, MatchCriterion, MatchView, OfferCreatedView,
    OfferInput, OfferView, OrganizationSettingsInput, OrganizationSettingsView, PublicApplicationInput,
    PublicJobView, PublicOfferView, RecruiterTaskInput, ResumeDocumentView, ResumeIntakeView, ScreeningInput, ScreeningView, TaskUpdate,
    TaskView, TokenView, UserAdminView, UserCreate, UserView,
)
from app.security import create_access_token, hash_password, verify_password


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_migrate_on_startup:
        alembic_config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        alembic_config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "migrations"))
        alembic_config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
        command.upgrade(alembic_config, "head")
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == settings.bootstrap_admin_email.lower()))
        if user is None:
            organization = Organization(name=settings.bootstrap_org_name)
            db.add(organization)
            db.flush()
            db.add(User(
                organization_id=organization.id,
                email=settings.bootstrap_admin_email.lower(),
                name="HireFlow Admin",
                role="admin",
                password_hash=hash_password(settings.bootstrap_admin_password),
            ))
            db.add(OrganizationSettings(organization_id=organization.id))
            db.commit()
    yield


app = FastAPI(title="HireFlow API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def candidate_view(candidate: Candidate) -> CandidateView:
    latest_score = max(candidate.scores, key=lambda score: score.created_at, default=None)
    return CandidateView(
        id=candidate.id,
        name=candidate.name,
        email=candidate.email,
        role_title=candidate.role_title,
        stage=candidate.stage,
        experience=candidate.experience,
        skills=[skill for skill in candidate.skills.split(",") if skill],
        current_ctc=candidate.current_ctc,
        expected_ctc=candidate.expected_ctc,
        availability=candidate.availability,
        job_id=candidate.job_id,
        created_at=candidate.created_at,
        score=latest_score.score if latest_score else None,
    )


def record_audit(db: Session, organization_id: str, actor_id: str | None, entity_type: str, entity_id: str, action: str, details: dict | None = None) -> None:
    db.add(AuditEvent(
        organization_id=organization_id,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        details=details or {},
    ))


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database unavailable") from exc
    return {"status": "ok", "service": "hireflow-api"}


@app.post("/api/auth/login", response_model=TokenView)
def login(data: LoginInput, db: Session = Depends(get_db)) -> TokenView:
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if user is None or not user.active or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email or password is incorrect")
    return TokenView(
        access_token=create_access_token(user.id, user.organization_id),
        user=UserView(id=user.id, email=user.email, name=user.name, role=user.role, organization_name=user.organization.name),
    )


@app.get("/api/auth/me", response_model=UserView)
def me(user: User = Depends(current_user)) -> UserView:
    return UserView(id=user.id, email=user.email, name=user.name, role=user.role, organization_name=user.organization.name)


@app.get("/api/candidates", response_model=list[CandidateView])
def list_candidates(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[CandidateView]:
    if user.role not in {"admin", "recruiter", "hiring_manager", "interviewer"}:
        raise HTTPException(status_code=403, detail="Candidate access required")
    query = select(Candidate).where(Candidate.organization_id == user.organization_id)
    if user.role == "interviewer":
        query = query.join(Interview, Interview.candidate_id == Candidate.id).where(Interview.interviewer_id == user.id).distinct()
    candidates = db.scalars(query.order_by(Candidate.created_at.desc())).all()
    results = [candidate_view(candidate) for candidate in candidates]
    if user.role in {"hiring_manager", "interviewer"}:
        for item in results:
            item.current_ctc = ""
            item.expected_ctc = ""
    return results


@app.post("/api/candidates", response_model=CandidateView, status_code=status.HTTP_201_CREATED)
def create_candidate(data: CandidateInput, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> CandidateView:
    if data.job_id and db.scalar(select(Job.id).where(Job.id == data.job_id, Job.organization_id == user.organization_id)) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    duplicate = db.scalar(select(Candidate.id).where(
        Candidate.organization_id == user.organization_id,
        func.lower(Candidate.email) == str(data.email).lower(),
    ))
    if duplicate:
        raise HTTPException(status_code=409, detail="Candidate with this email already exists in your organisation")
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
    db.commit()
    db.refresh(candidate)
    record_audit(db, user.organization_id, user.id, "candidate", candidate.id, "created", {"stage": candidate.stage})
    db.commit()
    return candidate_view(candidate)


def get_candidate(candidate_id: str, organization_id: str, db: Session) -> Candidate:
    candidate = db.scalar(select(Candidate).where(
        Candidate.id == candidate_id,
        Candidate.organization_id == organization_id,
    ))
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@app.patch("/api/candidates/{candidate_id}", response_model=CandidateView)
def update_candidate(candidate_id: str, data: CandidateUpdate, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> CandidateView:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    if "email" in data.model_fields_set and data.email:
        duplicate = db.scalar(select(Candidate.id).where(
            Candidate.organization_id == user.organization_id,
            func.lower(Candidate.email) == str(data.email).lower(),
            Candidate.id != candidate.id,
        ))
        if duplicate:
            raise HTTPException(status_code=409, detail="Another candidate in this organisation already uses that email")
    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "email" and value:
            value = str(value).lower()
        setattr(candidate, field, ",".join(skill.strip() for skill in value if skill.strip()) if field == "skills" and value is not None else value)
    updated_fields = set(data.model_fields_set) - {"current_ctc", "expected_ctc", "email"}
    record_audit(db, user.organization_id, user.id, "candidate", candidate.id, "updated", {"fields": sorted(updated_fields), "contact_email_updated": "email" in data.model_fields_set})
    db.commit()
    db.refresh(candidate)
    return candidate_view(candidate)


@app.delete("/api/candidates/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(candidate_id: str, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> None:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    db.delete(candidate)
    record_audit(db, user.organization_id, user.id, "candidate", candidate_id, "deleted")
    db.commit()


@app.get("/api/candidates/{candidate_id}/screenings", response_model=list[ScreeningView])
def list_screenings(candidate_id: str, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> list[Screening]:
    get_candidate(candidate_id, user.organization_id, db)
    return list(db.scalars(select(Screening).where(
        Screening.candidate_id == candidate_id,
        Screening.organization_id == user.organization_id,
    ).order_by(Screening.created_at.desc())).all())


@app.post("/api/candidates/{candidate_id}/screenings", response_model=ScreeningView, status_code=status.HTTP_201_CREATED)
def create_screening(candidate_id: str, data: ScreeningInput, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> Screening:
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
    candidate.stage = {"Shortlist": "Tech round 1", "Hold": "Screening", "Reject": "Rejected"}[data.decision]
    record_audit(db, user.organization_id, user.id, "candidate", candidate.id, "screening_recorded", {"decision": data.decision})
    db.add(screening)
    db.commit()
    db.refresh(screening)
    return screening


def get_job(job_id: str, organization_id: str, db: Session) -> Job:
    job = db.scalar(select(Job).where(Job.id == job_id, Job.organization_id == organization_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def job_view(job: Job, db: Session) -> JobView:
    return JobView(
        id=job.id,
        title=job.title,
        location=job.location,
        employment_type=job.employment_type,
        status=job.status,
        description=job.description,
        created_at=job.created_at,
        requirements=[{"skill": item.skill, "category": item.category, "weight": item.weight, "min_evidence_level": item.min_evidence_level} for item in job.requirements],
        applications_count=db.scalar(select(func.count(Application.id)).where(Application.job_id == job.id)) or 0,
    )


@app.get("/api/jobs", response_model=list[JobView])
def list_jobs(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[JobView]:
    jobs = db.scalars(select(Job).where(Job.organization_id == user.organization_id).order_by(Job.created_at.desc())).all()
    return [job_view(job, db) for job in jobs]


@app.post("/api/jobs", response_model=JobView, status_code=status.HTTP_201_CREATED)
def create_job(data: JobInput, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> JobView:
    job = Job(
        organization_id=user.organization_id,
        title=data.title.strip(),
        location=data.location.strip(),
        employment_type=data.employment_type,
        status=data.status,
        description=data.description.strip(),
    )
    job.requirements = [JobRequirement(
        organization_id=user.organization_id,
        skill=item.skill.strip(),
        category=item.category,
        weight=item.weight,
        min_evidence_level=item.min_evidence_level,
    ) for item in data.requirements]
    db.add(job)
    db.flush()
    record_audit(db, user.organization_id, user.id, "job", job.id, "created", {"status": job.status})
    db.commit()
    db.refresh(job)
    return job_view(job, db)


@app.patch("/api/jobs/{job_id}/status", response_model=JobView)
def set_job_status(job_id: str, status_value: str, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> JobView:
    if status_value not in {"draft", "published", "closed"}:
        raise HTTPException(status_code=422, detail="Status must be draft, published, or closed")
    job = get_job(job_id, user.organization_id, db)
    job.status = status_value
    record_audit(db, user.organization_id, user.id, "job", job.id, "status_changed", {"status": status_value})
    db.commit()
    db.refresh(job)
    return job_view(job, db)


@app.get("/api/public/jobs", response_model=list[PublicJobView])
def public_jobs(db: Session = Depends(get_db)) -> list[PublicJobView]:
    jobs = db.scalars(select(Job).where(Job.status == "published").order_by(Job.created_at.desc())).all()
    return [PublicJobView(
        id=job.id,
        title=job.title,
        location=job.location,
        employment_type=job.employment_type,
        description=job.description,
        organization_name=job.organization.name,
        requirements=[item.skill for item in job.requirements if item.category == "must_have"],
    ) for job in jobs]


@app.post("/api/public/jobs/{job_id}/applications", response_model=ApplicationReceipt, status_code=status.HTTP_201_CREATED)
def apply_to_job(job_id: str, data: PublicApplicationInput, db: Session = Depends(get_db)) -> ApplicationReceipt:
    if not data.consent:
        raise HTTPException(status_code=400, detail="Candidate data-processing consent is required")
    job = db.scalar(select(Job).where(Job.id == job_id, Job.status == "published"))
    if job is None:
        raise HTTPException(status_code=404, detail="Published job not found")
    email = str(data.email).lower()
    if db.scalar(select(Application.id).where(Application.job_id == job.id, Application.email == email)):
        raise HTTPException(status_code=409, detail="An application for this role already exists")
    candidate = db.scalar(select(Candidate).where(
        Candidate.organization_id == job.organization_id,
        func.lower(Candidate.email) == email,
    ))
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
            source=data.source,
        )
        db.add(candidate)
        db.flush()
    portal_token = secrets.token_urlsafe(32)
    db.add(Application(
        organization_id=job.organization_id,
        job_id=job.id,
        candidate_id=candidate.id,
        email=email,
        source=data.source,
        consent_text="I consent to this organisation processing my application data for recruitment.",
        portal_token_hash=hashlib.sha256(portal_token.encode()).hexdigest(),
    ))
    record_audit(db, job.organization_id, None, "application", candidate.id, "submitted", {"job_id": job.id, "source": data.source})
    db.commit()
    return ApplicationReceipt(status="received", message="Application received. Save this private link to view your application status or withdraw.", portal_url=f"/candidate/{portal_token}")


@app.get("/api/public/candidates/{token}", response_model=CandidatePortalView)
def candidate_portal(token: str, db: Session = Depends(get_db)) -> CandidatePortalView:
    application = db.scalar(select(Application).where(Application.portal_token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if application is None:
        raise HTTPException(status_code=404, detail="Candidate portal link not found")
    candidate = application.candidate
    interviews = db.scalars(select(Interview).where(
        Interview.organization_id == application.organization_id,
        Interview.candidate_id == candidate.id,
    ).order_by(Interview.scheduled_for.asc())).all()
    offer = db.scalar(select(Offer).where(Offer.organization_id == application.organization_id, Offer.candidate_id == candidate.id).order_by(Offer.created_at.desc()))
    return CandidatePortalView(
        candidate_name=candidate.name,
        job_title=get_job(application.job_id, application.organization_id, db).title,
        application_status=candidate.stage,
        last_updated=candidate.updated_at,
        interviews=[{"title": item.title, "scheduled_for": item.scheduled_for, "timezone": item.timezone, "status": item.status} for item in interviews],
        offer_status=offer.status if offer else None,
    )


@app.post("/api/public/candidates/{token}/withdraw")
def withdraw_application(token: str, db: Session = Depends(get_db)) -> dict[str, str]:
    application = db.scalar(select(Application).where(Application.portal_token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if application is None:
        raise HTTPException(status_code=404, detail="Candidate portal link not found")
    application.candidate.stage = "Candidate Withdrew"
    record_audit(db, application.organization_id, None, "application", application.candidate_id, "withdrawn", {"job_id": application.job_id})
    db.commit()
    return {"status": "withdrawn"}


@app.post("/api/candidates/{candidate_id}/match", response_model=MatchView)
def score_candidate(candidate_id: str, job_id: str, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> MatchView:
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
            criteria.append(MatchCriterion(
                skill=requirement.skill,
                category=requirement.category,
                weight=requirement.weight,
                matched=matched,
                evidence_level=1 if matched else 0,
                evidence="Self-reported profile skill; verify manually. Flag only, never an automatic rejection.",
            ))
            continue
        available_weight += requirement.weight
        credit = 0.5 if matched and requirement.category == "trainable" else 1.0 if matched else 0.0
        achieved_weight += requirement.weight * credit
        criteria.append(MatchCriterion(
            skill=requirement.skill,
            category=requirement.category,
            weight=requirement.weight,
            matched=matched,
            evidence_level=1 if matched else 0,
            evidence="Self-reported profile skill; resume/project evidence has not been verified." if matched else "No matching skill recorded in the candidate profile.",
        ))
    score = round(achieved_weight / available_weight * 100) if available_weight else 0
    existing = db.scalar(select(CandidateScore).where(
        CandidateScore.organization_id == user.organization_id,
        CandidateScore.candidate_id == candidate.id,
        CandidateScore.job_id == job.id,
    ))
    if existing:
        existing.score = score
        existing.criteria = [item.model_dump() for item in criteria]
        existing.created_at = datetime.now(timezone.utc)
    else:
        db.add(CandidateScore(
            organization_id=user.organization_id,
            candidate_id=candidate.id,
            job_id=job.id,
            score=score,
            criteria=[item.model_dump() for item in criteria],
        ))
    record_audit(db, user.organization_id, user.id, "candidate", candidate.id, "match_calculated", {"job_id": job.id, "score": score})
    db.commit()
    return MatchView(
        candidate_id=candidate.id,
        job_id=job.id,
        score=score,
        methodology="deterministic-v1",
        decision_note="Profile-only comparison. This is not AI and does not verify resume claims or make a hiring decision.",
        criteria=criteria,
    )


def interview_view(interview: Interview) -> InterviewView:
    return InterviewView(
        id=interview.id,
        candidate_id=interview.candidate_id,
        candidate_name=interview.candidate.name,
        candidate_email=interview.candidate.email,
        interviewer_id=interview.interviewer_id,
        title=interview.title,
        scheduled_for=interview.scheduled_for,
        duration_minutes=interview.duration_minutes,
        timezone=interview.timezone,
        meeting_method=interview.meeting_method,
        location_or_link=interview.location_or_link,
        status=interview.status,
        feedback_submitted=bool(interview.feedback),
    )


@app.get("/api/interviews", response_model=list[InterviewView])
def list_interviews(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[InterviewView]:
    query = select(Interview).where(Interview.organization_id == user.organization_id)
    if user.role == "interviewer":
        query = query.where(Interview.interviewer_id == user.id)
    interviews = db.scalars(query.order_by(Interview.scheduled_for.asc())).all()
    return [interview_view(item) for item in interviews]


@app.post("/api/interviews", response_model=InterviewView, status_code=status.HTTP_201_CREATED)
def create_interview(data: InterviewInput, user: User = Depends(coordinator_user), db: Session = Depends(get_db)) -> InterviewView:
    candidate = get_candidate(data.candidate_id, user.organization_id, db)
    if data.interviewer_id:
        interviewer = db.scalar(select(User).where(
            User.id == data.interviewer_id,
            User.organization_id == user.organization_id,
            User.active.is_(True),
            User.role.in_(["interviewer", "hiring_manager", "admin"]),
        ))
        if interviewer is None:
            raise HTTPException(status_code=404, detail="Interviewer not found")
    interview = Interview(
        organization_id=user.organization_id,
        candidate_id=candidate.id,
        interviewer_id=data.interviewer_id,
        title=data.title.strip(),
        scheduled_for=data.scheduled_for,
        duration_minutes=data.duration_minutes,
        timezone=data.timezone,
        meeting_method=data.meeting_method,
        location_or_link=data.location_or_link.strip(),
    )
    db.add(interview)
    db.flush()
    record_audit(db, user.organization_id, user.id, "interview", interview.id, "scheduled", {"candidate_id": candidate.id})
    db.commit()
    db.refresh(interview)
    return interview_view(interview)


@app.post("/api/interviews/{interview_id}/feedback", status_code=status.HTTP_201_CREATED)
def submit_interview_feedback(interview_id: str, data: FeedbackInput, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict[str, str]:
    interview = db.scalar(select(Interview).where(
        Interview.id == interview_id,
        Interview.organization_id == user.organization_id,
    ))
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if user.role == "interviewer" and interview.interviewer_id != user.id:
        raise HTTPException(status_code=403, detail="Feedback is limited to your assigned interviews")
    if user.role not in {"admin", "recruiter", "hiring_manager", "interviewer"}:
        raise HTTPException(status_code=403, detail="Interview feedback access required")
    if db.scalar(select(InterviewFeedback.id).where(
        InterviewFeedback.interview_id == interview.id,
        InterviewFeedback.interviewer_id == user.id,
    )):
        raise HTTPException(status_code=409, detail="You already submitted feedback for this interview")
    db.add(InterviewFeedback(organization_id=user.organization_id, interview_id=interview.id, interviewer_id=user.id, **data.model_dump()))
    interview.status = "completed"
    record_audit(db, user.organization_id, user.id, "interview", interview.id, "feedback_submitted", {"recommendation": data.recommendation})
    db.commit()
    return {"status": "submitted"}


def offer_view(offer: Offer) -> OfferView:
    return OfferView(
        id=offer.id,
        candidate_id=offer.candidate_id,
        candidate_name=offer.candidate.name,
        title=offer.title,
        compensation=offer.compensation,
        employment_type=offer.employment_type,
        joining_date=offer.joining_date,
        status=offer.status,
        expires_at=offer.expires_at,
        accepted_at=offer.accepted_at,
        created_at=offer.created_at,
    )


@app.get("/api/offers", response_model=list[OfferView])
def list_offers(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[OfferView]:
    offers = db.scalars(select(Offer).where(Offer.organization_id == user.organization_id).order_by(Offer.created_at.desc())).all()
    return [offer_view(item) for item in offers]


@app.post("/api/offers", response_model=OfferCreatedView, status_code=status.HTTP_201_CREATED)
def create_offer(data: OfferInput, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> OfferCreatedView:
    candidate = get_candidate(data.candidate_id, user.organization_id, db)
    acceptance_token = secrets.token_urlsafe(32)
    offer = Offer(
        organization_id=user.organization_id,
        candidate_id=candidate.id,
        created_by_id=user.id,
        title=data.title.strip(),
        compensation=data.compensation.strip(),
        employment_type=data.employment_type,
        joining_date=data.joining_date,
        acceptance_token_hash=hashlib.sha256(acceptance_token.encode()).hexdigest(),
        expires_at=data.expires_at,
    )
    candidate.stage = "Offer Approval"
    db.add(offer)
    db.flush()
    record_audit(db, user.organization_id, user.id, "offer", offer.id, "draft_created", {"candidate_id": candidate.id})
    db.commit()
    db.refresh(offer)
    return OfferCreatedView(**offer_view(offer).model_dump(), acceptance_url=f"/offer/{acceptance_token}")


@app.post("/api/offers/{offer_id}/approve", response_model=OfferView)
def approve_offer(offer_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> OfferView:
    if user.role not in {"admin", "hiring_manager"}:
        raise HTTPException(status_code=403, detail="Offer approval access required")
    offer = db.scalar(select(Offer).where(Offer.id == offer_id, Offer.organization_id == user.organization_id))
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft offers can be approved")
    offer.status = "approved"
    offer.approved_by_id = user.id
    offer.candidate.stage = "Offer Sent"
    record_audit(db, user.organization_id, user.id, "offer", offer.id, "approved", {"compensation": offer.compensation})
    db.commit()
    db.refresh(offer)
    return offer_view(offer)


@app.get("/api/public/offers/{token}", response_model=PublicOfferView)
def public_offer(token: str, db: Session = Depends(get_db)) -> PublicOfferView:
    offer = db.scalar(select(Offer).where(Offer.acceptance_token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if offer is None or offer.status not in {"approved", "sent"}:
        raise HTTPException(status_code=404, detail="Offer link is invalid or unavailable")
    return PublicOfferView(
        candidate_name=offer.candidate.name,
        title=offer.title,
        compensation=offer.compensation,
        employment_type=offer.employment_type,
        joining_date=offer.joining_date,
        status=offer.status,
        expires_at=offer.expires_at,
    )


@app.post("/api/public/offers/{token}/decision")
def offer_decision(token: str, decision: str, db: Session = Depends(get_db)) -> dict[str, str]:
    if decision not in {"accept", "decline"}:
        raise HTTPException(status_code=422, detail="Decision must be accept or decline")
    offer = db.scalar(select(Offer).where(Offer.acceptance_token_hash == hashlib.sha256(token.encode()).hexdigest()))
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
    record_audit(db, offer.organization_id, None, "offer", offer.id, decision, {"candidate_id": offer.candidate_id})
    db.commit()
    return {"status": offer.status}


@app.get("/api/tasks", response_model=list[TaskView])
def list_tasks(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[TaskView]:
    query = select(RecruiterTask).where(RecruiterTask.organization_id == user.organization_id)
    if user.role == "interviewer":
        query = query.where(RecruiterTask.assigned_to_id == user.id)
    tasks = db.scalars(query.order_by(RecruiterTask.due_at.asc().nulls_last())).all()
    return [TaskView(
        id=task.id,
        candidate_id=task.candidate_id,
        candidate_name=task.candidate.name if task.candidate else None,
        assigned_to_id=task.assigned_to_id,
        title=task.title,
        due_at=task.due_at,
        status=task.status,
        created_at=task.created_at,
    ) for task in tasks]


@app.post("/api/tasks", response_model=TaskView, status_code=status.HTTP_201_CREATED)
def create_task(data: RecruiterTaskInput, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> TaskView:
    candidate = get_candidate(data.candidate_id, user.organization_id, db) if data.candidate_id else None
    if data.assigned_to_id and db.scalar(select(User.id).where(User.id == data.assigned_to_id, User.organization_id == user.organization_id, User.active.is_(True))) is None:
        raise HTTPException(status_code=404, detail="Assigned team member not found")
    task = RecruiterTask(organization_id=user.organization_id, candidate_id=candidate.id if candidate else None, **data.model_dump(exclude={"candidate_id"}))
    db.add(task)
    db.flush()
    record_audit(db, user.organization_id, user.id, "task", task.id, "created")
    db.commit()
    db.refresh(task)
    return TaskView(id=task.id, candidate_id=task.candidate_id, candidate_name=candidate.name if candidate else None, assigned_to_id=task.assigned_to_id, title=task.title, due_at=task.due_at, status=task.status, created_at=task.created_at)


@app.patch("/api/tasks/{task_id}", response_model=TaskView)
def update_task(task_id: str, data: TaskUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> TaskView:
    task = db.scalar(select(RecruiterTask).where(RecruiterTask.id == task_id, RecruiterTask.organization_id == user.organization_id))
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if user.role == "interviewer" and task.assigned_to_id != user.id:
        raise HTTPException(status_code=403, detail="Task is not assigned to you")
    task.status = data.status
    record_audit(db, user.organization_id, user.id, "task", task.id, "status_changed", {"status": task.status})
    db.commit()
    db.refresh(task)
    return TaskView(id=task.id, candidate_id=task.candidate_id, candidate_name=task.candidate.name if task.candidate else None, assigned_to_id=task.assigned_to_id, title=task.title, due_at=task.due_at, status=task.status, created_at=task.created_at)


@app.get("/api/users", response_model=list[UserAdminView])
def list_users(user: User = Depends(admin_user), db: Session = Depends(get_db)) -> list[UserAdminView]:
    users = db.scalars(select(User).where(User.organization_id == user.organization_id).order_by(User.name)).all()
    return [UserAdminView(id=item.id, name=item.name, email=item.email, role=item.role, active=item.active) for item in users]


@app.get("/api/team/directory", response_model=list[UserAdminView])
def team_directory(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[UserAdminView]:
    users = db.scalars(select(User).where(User.organization_id == user.organization_id, User.active.is_(True)).order_by(User.name)).all()
    return [UserAdminView(id=item.id, name=item.name, email=item.email, role=item.role, active=item.active) for item in users]


@app.post("/api/users", response_model=UserAdminView, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, user: User = Depends(admin_user), db: Session = Depends(get_db)) -> UserAdminView:
    email = str(data.email).lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    teammate = User(organization_id=user.organization_id, email=email, name=data.name.strip(), role=data.role, password_hash=hash_password(data.password))
    db.add(teammate)
    db.flush()
    record_audit(db, user.organization_id, user.id, "user", teammate.id, "created", {"role": teammate.role})
    db.commit()
    db.refresh(teammate)
    return UserAdminView(id=teammate.id, name=teammate.name, email=teammate.email, role=teammate.role, active=teammate.active)


@app.get("/api/settings", response_model=OrganizationSettingsView)
def get_organization_settings(user: User = Depends(current_user), db: Session = Depends(get_db)) -> OrganizationSettingsView:
    settings_row = db.get(OrganizationSettings, user.organization_id)
    if settings_row is None:
        settings_row = OrganizationSettings(organization_id=user.organization_id)
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return OrganizationSettingsView(organization_id=user.organization_id, timezone=settings_row.timezone, careers_intro=settings_row.careers_intro, retention_days=settings_row.retention_days, require_candidate_consent=settings_row.require_candidate_consent)


@app.put("/api/settings", response_model=OrganizationSettingsView)
def update_organization_settings(data: OrganizationSettingsInput, user: User = Depends(admin_user), db: Session = Depends(get_db)) -> OrganizationSettingsView:
    settings_row = db.get(OrganizationSettings, user.organization_id)
    if settings_row is None:
        settings_row = OrganizationSettings(organization_id=user.organization_id)
        db.add(settings_row)
    for field, value in data.model_dump().items():
        setattr(settings_row, field, value)
    record_audit(db, user.organization_id, user.id, "organization", user.organization_id, "settings_updated")
    db.commit()
    db.refresh(settings_row)
    return OrganizationSettingsView(organization_id=user.organization_id, timezone=settings_row.timezone, careers_intro=settings_row.careers_intro, retention_days=settings_row.retention_days, require_candidate_consent=settings_row.require_candidate_consent)


@app.get("/api/audit-events", response_model=list[AuditEventView])
def list_audit_events(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[AuditEventView]:
    if user.role not in {"admin", "recruiter", "hiring_manager"}:
        raise HTTPException(status_code=403, detail="Audit access required")
    events = db.scalars(select(AuditEvent).where(AuditEvent.organization_id == user.organization_id).order_by(AuditEvent.created_at.desc()).limit(200)).all()
    return [AuditEventView(id=item.id, actor_id=item.actor_id, entity_type=item.entity_type, entity_id=item.entity_id, action=item.action, details=item.details, created_at=item.created_at) for item in events]


@app.get("/api/dashboard/summary")
def dashboard_summary(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    org_id = user.organization_id
    candidates = db.scalars(select(Candidate).where(Candidate.organization_id == org_id)).all()
    jobs = db.scalars(select(Job).where(Job.organization_id == org_id)).all()
    return {
        "active_candidates": sum(candidate.stage not in {"Hired", "Rejected", "Closed", "Candidate Withdrew"} for candidate in candidates),
        "candidates_by_stage": {stage: sum(candidate.stage == stage for candidate in candidates) for stage in sorted({candidate.stage for candidate in candidates})},
        "open_jobs": sum(job.status == "published" for job in jobs),
        "upcoming_interviews": db.scalar(select(func.count(Interview.id)).where(Interview.organization_id == org_id, Interview.status == "scheduled", Interview.scheduled_for >= datetime.now(timezone.utc))) or 0,
        "pending_offers": db.scalar(select(func.count(Offer.id)).where(Offer.organization_id == org_id, Offer.status.in_(["draft", "approved", "sent"]))) or 0,
        "open_tasks": db.scalar(select(func.count(RecruiterTask.id)).where(RecruiterTask.organization_id == org_id, RecruiterTask.status == "open")) or 0,
    }


@app.get("/api/communications/outbox")
def list_outbox(user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> list[dict]:
    messages = db.scalars(select(OutboundMessage).where(OutboundMessage.organization_id == user.organization_id).order_by(OutboundMessage.created_at.desc()).limit(100)).all()
    return [{"id": item.id, "recipient": item.recipient, "subject": item.subject, "status": item.status, "created_at": item.created_at} for item in messages]


@app.get("/api/candidates/{candidate_id}/activity", response_model=list[AuditEventView])
def candidate_activity(candidate_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[AuditEventView]:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    if user.role == "interviewer":
        assigned = db.scalar(select(Interview.id).where(
            Interview.organization_id == user.organization_id,
            Interview.candidate_id == candidate.id,
            Interview.interviewer_id == user.id,
        ))
        if not assigned:
            raise HTTPException(status_code=403, detail="Candidate is not assigned to you")
    events = db.scalars(select(AuditEvent).where(
        AuditEvent.organization_id == user.organization_id,
        AuditEvent.entity_id == candidate.id,
        AuditEvent.entity_type.in_(["candidate", "application"]),
    ).order_by(AuditEvent.created_at.desc()).limit(100)).all()
    return [AuditEventView(id=item.id, actor_id=item.actor_id, entity_type=item.entity_type, entity_id=item.entity_id, action=item.action, details=item.details, created_at=item.created_at) for item in events]


def extract_resume_text(filename: str, content: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if len(reader.pages) > 30:
                raise HTTPException(status_code=413, detail="Resume PDF exceeds 30 pages")
            return "\n".join(page.extract_text() or "" for page in reader.pages)[:200_000]
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Resume PDF could not be parsed") from exc
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 500 or sum(entry.file_size for entry in entries) > 20_000_000:
                raise HTTPException(status_code=413, detail="Resume document expands beyond allowed limits")
            xml_content = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml_content)
            paragraphs = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
            return " ".join(paragraphs)[:200_000]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Resume DOCX could not be parsed") from exc


def resume_profile_fields(filename: str, text_content: str) -> dict:
    taxonomy = ["Python", "Java", "JavaScript", "TypeScript", "React", "FastAPI", "Django", "Node.js", "PostgreSQL", "MySQL", "SQL", "AWS", "Azure", "Docker", "Kubernetes", "Machine Learning", "LLMs", "RAG", "LangChain", "REST API", "Git"]
    skills = [skill for skill in taxonomy if re.search(r"(?<![\w])" + re.escape(skill) + r"(?![\w])", text_content, re.IGNORECASE)]
    experience_match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+)?experience", text_content, re.IGNORECASE)
    experience = f"{experience_match.group(1)} years (resume text; unverified)" if experience_match else ""
    email_match = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text_content, re.IGNORECASE)
    email = email_match.group(0).lower() if email_match else None
    excluded = {"resume", "curriculum vitae", "cv", "profile", "summary", "experience", "education"}
    lines = [re.sub(r"\s+", " ", line).strip(" -|\t") for line in text_content.splitlines() if line.strip()]
    name = next((line for line in lines[:8] if 1 < len(line.split()) <= 5 and len(line) <= 100 and not any(word in line.casefold() for word in excluded) and not re.search(r"[@\d]", line)), "")
    if not name:
        name = re.sub(r"[_-]+", " ", Path(filename).stem).strip().title()[:180]
    return {"name": name, "email": email, "skills": skills, "experience": experience}


def prepare_resume_file(filename: str, content: bytes) -> dict:
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX resumes are accepted")
    if not content or len(content) > 10_000_000:
        raise HTTPException(status_code=413, detail="Resume file must be between 1 byte and 10 MB")
    media_type = "application/pdf" if extension == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    signature_valid = content.startswith(b"%PDF-") if extension == ".pdf" else content.startswith(b"PK\x03\x04")
    if not signature_valid:
        raise HTTPException(status_code=415, detail="File extension does not match a supported document signature")
    if not settings.clamd_host:
        raise HTTPException(status_code=503, detail="Resume uploads are disabled until malware scanning is configured")
    if not settings.resume_encryption_key:
        raise HTTPException(status_code=503, detail="Resume uploads are disabled until encryption at-rest key is configured")
    try:
        scanner = clamd.ClamdNetworkSocket(host=settings.clamd_host, port=settings.clamd_port, timeout=8)
        scan_result = scanner.instream(BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Malware scanner is unavailable; resume was not stored") from exc
    scan_status = scan_result.get("stream", ("ERROR", "Unknown scan result"))
    if scan_status[0] != "OK":
        raise HTTPException(status_code=422, detail="Resume failed malware scanning and was not stored")
    try:
        encrypted = Fernet(settings.resume_encryption_key.encode()).encrypt(content)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=503, detail="Resume encryption key is invalid") from exc
    text_content = extract_resume_text(filename, content)
    return {
        "media_type": media_type,
        "encrypted_content": encrypted,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
        **resume_profile_fields(filename, text_content),
    }


def add_resume_document(candidate: Candidate, user: User, filename: str, prepared: dict, db: Session) -> ResumeDocument:
    existing = db.scalar(select(ResumeDocument).where(ResumeDocument.organization_id == user.organization_id, ResumeDocument.sha256 == prepared["sha256"]))
    if existing:
        raise HTTPException(status_code=409, detail="This resume file already exists in the organisation")
    resume = ResumeDocument(
        organization_id=user.organization_id,
        candidate_id=candidate.id,
        original_name=filename,
        media_type=prepared["media_type"],
        size_bytes=prepared["size_bytes"],
        sha256=prepared["sha256"],
        encrypted_content=prepared["encrypted_content"],
    )
    existing_skills = {skill.strip() for skill in candidate.skills.split(",") if skill.strip()}
    candidate.skills = ",".join(sorted(existing_skills | set(prepared["skills"])))
    if prepared["experience"] and not candidate.experience:
        candidate.experience = prepared["experience"]
    candidate.stage = "Resume Parsed"
    db.add(resume)
    db.flush()
    record_audit(db, user.organization_id, user.id, "candidate", candidate.id, "resume_scanned_and_parsed", {"resume_id": resume.id, "size_bytes": resume.size_bytes, "extracted_skill_count": len(prepared["skills"])})
    return resume


@app.post("/api/candidates/{candidate_id}/resumes", response_model=ResumeDocumentView, status_code=status.HTTP_201_CREATED)
async def upload_resume(candidate_id: str, file: UploadFile = File(...), user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> ResumeDocumentView:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    filename = Path((file.filename or "resume").replace("\\", "/")).name
    content = await file.read(10_000_001)
    prepared = prepare_resume_file(filename, content)
    resume = add_resume_document(candidate, user, filename, prepared, db)
    db.commit()
    db.refresh(resume)
    return ResumeDocumentView(id=resume.id, candidate_id=candidate.id, original_name=resume.original_name, media_type=resume.media_type, size_bytes=resume.size_bytes, created_at=resume.created_at, extracted_skills=prepared["skills"], extracted_experience=prepared["experience"])


@app.post("/api/resume-intake", response_model=ResumeIntakeView, status_code=status.HTTP_201_CREATED)
async def intake_resume(
    file: UploadFile = File(...),
    job_id: str | None = Form(default=None),
    role_title: str = Form(default=""),
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> ResumeIntakeView:
    filename = Path((file.filename or "resume").replace("\\", "/")).name
    content = await file.read(10_000_001)
    prepared = prepare_resume_file(filename, content)
    job = get_job(job_id, user.organization_id, db) if job_id else None
    resolved_role = job.title if job else role_title.strip()
    if not resolved_role:
        raise HTTPException(status_code=422, detail="Choose a role or enter a role title for this resume")
    candidate = None
    matched_existing = False
    if prepared["email"]:
        candidate = db.scalar(select(Candidate).where(
            Candidate.organization_id == user.organization_id,
            func.lower(Candidate.email) == prepared["email"],
        ))
        matched_existing = candidate is not None
    if candidate is None:
        candidate = Candidate(
            organization_id=user.organization_id,
            job_id=job.id if job else None,
            name=prepared["name"],
            email=prepared["email"],
            role_title=resolved_role,
            stage="Resume Parsed",
            experience=prepared["experience"],
            skills=",".join(prepared["skills"]),
            current_ctc="",
            expected_ctc="",
            availability="",
            source="resume_upload",
        )
        db.add(candidate)
        db.flush()
        record_audit(db, user.organization_id, user.id, "candidate", candidate.id, "created_from_resume", {"role_title": resolved_role})
    elif job and candidate.job_id is None:
        candidate.job_id = job.id
    resume = add_resume_document(candidate, user, filename, prepared, db)
    db.commit()
    db.refresh(candidate)
    db.refresh(resume)
    review_fields = []
    if not candidate.email:
        review_fields.append("email")
    if not prepared["skills"]:
        review_fields.append("skills")
    if not prepared["experience"]:
        review_fields.append("experience")
    return ResumeIntakeView(
        candidate=candidate_view(candidate),
        resume=ResumeDocumentView(id=resume.id, candidate_id=resume.candidate_id, original_name=resume.original_name, media_type=resume.media_type, size_bytes=resume.size_bytes, created_at=resume.created_at, extracted_skills=prepared["skills"], extracted_experience=prepared["experience"]),
        fields_needing_review=review_fields,
        matched_existing_candidate=matched_existing,
        review_note="Resume extraction is unverified. Confirm candidate name, contact details, skills, and experience before making decisions.",
    )


@app.get("/api/candidates/{candidate_id}/resumes", response_model=list[ResumeDocumentView])
def list_candidate_resumes(candidate_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[ResumeDocumentView]:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    if user.role == "interviewer":
        assigned = db.scalar(select(Interview.id).where(Interview.organization_id == user.organization_id, Interview.candidate_id == candidate.id, Interview.interviewer_id == user.id))
        if not assigned:
            raise HTTPException(status_code=403, detail="Candidate is not assigned to you")
    documents = db.scalars(select(ResumeDocument).where(ResumeDocument.organization_id == user.organization_id, ResumeDocument.candidate_id == candidate.id).order_by(ResumeDocument.created_at.desc())).all()
    return [ResumeDocumentView(id=item.id, candidate_id=item.candidate_id, original_name=item.original_name, media_type=item.media_type, size_bytes=item.size_bytes, created_at=item.created_at, extracted_skills=[], extracted_experience="") for item in documents]


@app.get("/api/candidates/{candidate_id}/resumes/{resume_id}/download")
def download_resume(candidate_id: str, resume_id: str, user: User = Depends(recruiter_user), db: Session = Depends(get_db)):
    from fastapi.responses import Response

    candidate = get_candidate(candidate_id, user.organization_id, db)
    resume = db.scalar(select(ResumeDocument).where(ResumeDocument.id == resume_id, ResumeDocument.organization_id == user.organization_id, ResumeDocument.candidate_id == candidate.id))
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    if not settings.resume_encryption_key:
        raise HTTPException(status_code=503, detail="Resume encryption key is not configured")
    try:
        content = Fernet(settings.resume_encryption_key.encode()).decrypt(resume.encrypted_content)
    except (InvalidToken, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="Resume cannot be decrypted with the active key") from exc
    record_audit(db, user.organization_id, user.id, "resume", resume.id, "downloaded", {"candidate_id": candidate.id})
    db.commit()
    safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", resume.original_name)
    return Response(content=content, media_type=resume.media_type, headers={"Content-Disposition": f'attachment; filename="{safe_filename}"', "Cache-Control": "no-store"})


@app.get("/api/communications/templates", response_model=list[EmailTemplateView])
def list_communication_templates(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[EmailTemplateView]:
    templates = db.scalars(select(EmailTemplate).where(EmailTemplate.organization_id == user.organization_id).order_by(EmailTemplate.event_key)).all()
    if not templates:
        templates = [
            EmailTemplate(organization_id=user.organization_id, name="Application received", event_key="application_received", subject="We received your application for {{role}}", body="Hello {{candidate}},\n\nThank you for applying for {{role}}. The hiring team will review your application."),
            EmailTemplate(organization_id=user.organization_id, name="Interview invitation", event_key="interview_invitation", subject="Interview invitation: {{role}}", body="Hello {{candidate}},\n\nWe would like to invite you to an interview for {{role}}.\nWhen: {{interview_time}}"),
            EmailTemplate(organization_id=user.organization_id, name="Rejection", event_key="rejection", subject="Update on your {{role}} application", body="Hello {{candidate}},\n\nThank you for your time. We will not be progressing your application for {{role}} at this time."),
            EmailTemplate(organization_id=user.organization_id, name="Offer", event_key="offer", subject="Offer for {{role}}", body="Hello {{candidate}},\n\nWe are pleased to offer you the {{role}} position. Compensation: {{compensation}}."),
        ]
        db.add_all(templates)
        db.commit()
        for template in templates:
            db.refresh(template)
    return [EmailTemplateView(id=item.id, name=item.name, subject=item.subject, body=item.body, event_key=item.event_key) for item in templates]


@app.post("/api/communications/templates", response_model=EmailTemplateView, status_code=status.HTTP_201_CREATED)
def create_communication_template(data: EmailTemplateInput, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> EmailTemplateView:
    template = EmailTemplate(organization_id=user.organization_id, **data.model_dump())
    db.add(template)
    db.flush()
    record_audit(db, user.organization_id, user.id, "email_template", template.id, "created", {"event_key": template.event_key})
    db.commit()
    db.refresh(template)
    return EmailTemplateView(id=template.id, name=template.name, subject=template.subject, body=template.body, event_key=template.event_key)


@app.put("/api/communications/templates/{template_id}", response_model=EmailTemplateView)
def update_communication_template(template_id: str, data: EmailTemplateInput, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> EmailTemplateView:
    template = db.scalar(select(EmailTemplate).where(EmailTemplate.id == template_id, EmailTemplate.organization_id == user.organization_id))
    if template is None:
        raise HTTPException(status_code=404, detail="Communication template not found")
    for field, value in data.model_dump().items():
        setattr(template, field, value)
    record_audit(db, user.organization_id, user.id, "email_template", template.id, "updated", {"event_key": template.event_key})
    db.commit()
    db.refresh(template)
    return EmailTemplateView(id=template.id, name=template.name, subject=template.subject, body=template.body, event_key=template.event_key)


@app.post("/api/communications/drafts", response_model=CommunicationDraftView, status_code=status.HTTP_201_CREATED)
def create_communication_draft(data: CommunicationDraftInput, user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> CommunicationDraftView:
    candidate = get_candidate(data.candidate_id, user.organization_id, db)
    if not candidate.email:
        raise HTTPException(status_code=422, detail="Add a verified candidate email before creating a communication draft")
    template = db.scalar(select(EmailTemplate).where(EmailTemplate.id == data.template_id, EmailTemplate.organization_id == user.organization_id))
    if template is None:
        raise HTTPException(status_code=404, detail="Communication template not found")
    variables = {"candidate": candidate.name, "role": candidate.role_title, "compensation": candidate.expected_ctc}
    subject = data.subject if data.subject is not None else template.subject
    body = data.body if data.body is not None else template.body
    for key, value in variables.items():
        subject = subject.replace("{{" + key + "}}", value)
        body = body.replace("{{" + key + "}}", value)
    message = OutboundMessage(organization_id=user.organization_id, candidate_id=candidate.id, recipient=candidate.email, subject=subject, body=body, status="draft")
    db.add(message)
    db.flush()
    record_audit(db, user.organization_id, user.id, "communication", message.id, "draft_created", {"candidate_id": candidate.id})
    db.commit()
    db.refresh(message)
    return CommunicationDraftView(id=message.id, recipient=message.recipient, subject=message.subject, body=message.body, status=message.status, created_at=message.created_at)