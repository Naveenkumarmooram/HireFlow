import re
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import current_user, recruiter_user
from app.models import (
    Candidate,
    Interview,
    ResumeDocument,
    User,
)
from app.schemas import (
    ResumeDocumentView,
    ResumeIntakeView,
)
from app.services import (
    add_resume_document,
    candidate_view,
    get_candidate,
    get_job,
    prepare_resume_file,
    record_audit,
)

router = APIRouter(tags=["resumes"])


@router.post(
    "/api/candidates/{candidate_id}/resumes",
    response_model=ResumeDocumentView,
    status_code=status.HTTP_201_CREATED,
)
def upload_resume(
    candidate_id: str,
    file: UploadFile = File(...),
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> ResumeDocumentView:
    candidate = get_candidate(candidate_id, user.organization_id, db)
    filename = Path((file.filename or "resume").replace("\\", "/")).name
    content = file.file.read(settings.max_resume_bytes + 1)
    prepared = prepare_resume_file(filename, content)
    resume = add_resume_document(candidate, user, filename, prepared, db)
    db.commit()
    db.refresh(resume)
    return ResumeDocumentView(
        id=resume.id,
        candidate_id=candidate.id,
        original_name=resume.original_name,
        media_type=resume.media_type,
        size_bytes=resume.size_bytes,
        created_at=resume.created_at,
        extracted_skills=prepared["skills"],
        extracted_experience=prepared["experience"],
    )


@router.post(
    "/api/resume-intake",
    response_model=ResumeIntakeView,
    status_code=status.HTTP_201_CREATED,
)
def intake_resume(
    file: UploadFile = File(...),
    job_id: str | None = Form(default=None),
    role_title: str = Form(default="", max_length=180),
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> ResumeIntakeView:
    filename = Path((file.filename or "resume").replace("\\", "/")).name
    content = file.file.read(settings.max_resume_bytes + 1)
    prepared = prepare_resume_file(filename, content)
    job = get_job(job_id, user.organization_id, db) if job_id else None
    resolved_role = job.title if job else role_title.strip()
    if not resolved_role:
        raise HTTPException(
            status_code=422,
            detail="Choose a role or enter a role title for this resume",
        )
    candidate = None
    matched_existing = False
    if prepared["email"]:
        candidate = db.scalar(
            select(Candidate).where(
                Candidate.organization_id == user.organization_id,
                func.lower(Candidate.email) == prepared["email"],
            )
        )
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
        record_audit(
            db,
            user.organization_id,
            user.id,
            "candidate",
            candidate.id,
            "created_from_resume",
            {"role_title": resolved_role},
        )
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
        resume=ResumeDocumentView(
            id=resume.id,
            candidate_id=resume.candidate_id,
            original_name=resume.original_name,
            media_type=resume.media_type,
            size_bytes=resume.size_bytes,
            created_at=resume.created_at,
            extracted_skills=prepared["skills"],
            extracted_experience=prepared["experience"],
        ),
        fields_needing_review=review_fields,
        matched_existing_candidate=matched_existing,
        review_note="Resume extraction is unverified. Confirm candidate name, contact details, skills, and experience before making decisions.",
    )


@router.get("/api/candidates/{candidate_id}/resumes", response_model=list[ResumeDocumentView])
def list_candidate_resumes(
    candidate_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[ResumeDocumentView]:
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
    documents = db.scalars(
        select(ResumeDocument)
        .where(
            ResumeDocument.organization_id == user.organization_id,
            ResumeDocument.candidate_id == candidate.id,
        )
        .order_by(ResumeDocument.created_at.desc())
    ).all()
    return [
        ResumeDocumentView(
            id=item.id,
            candidate_id=item.candidate_id,
            original_name=item.original_name,
            media_type=item.media_type,
            size_bytes=item.size_bytes,
            created_at=item.created_at,
            extracted_skills=[],
            extracted_experience="",
        )
        for item in documents
    ]


@router.get("/api/candidates/{candidate_id}/resumes/{resume_id}/download")
def download_resume(
    candidate_id: str,
    resume_id: str,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response

    candidate = get_candidate(candidate_id, user.organization_id, db)
    resume = db.scalar(
        select(ResumeDocument).where(
            ResumeDocument.id == resume_id,
            ResumeDocument.organization_id == user.organization_id,
            ResumeDocument.candidate_id == candidate.id,
        )
    )
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found")
    if not settings.resume_encryption_key:
        raise HTTPException(status_code=503, detail="Resume encryption key is not configured")
    try:
        content = Fernet(settings.resume_encryption_key.encode()).decrypt(resume.encrypted_content)
    except (InvalidToken, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=500, detail="Resume cannot be decrypted with the active key"
        ) from exc
    record_audit(
        db,
        user.organization_id,
        user.id,
        "resume",
        resume.id,
        "downloaded",
        {"candidate_id": candidate.id},
    )
    db.commit()
    safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", resume.original_name)
    return Response(
        content=content,
        media_type=resume.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "Cache-Control": "no-store",
        },
    )
