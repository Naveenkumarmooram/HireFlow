"""Shared recruitment projections, tenant lookups and resume processing."""

import hashlib
import re
import zipfile
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

import clamd
from cryptography.fernet import Fernet
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Application,
    AuditEvent,
    Candidate,
    Interview,
    Job,
    Offer,
    ResumeDocument,
    User,
)
from app.schemas import (
    CandidateView,
    InterviewView,
    JobView,
    OfferView,
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


def record_audit(
    db: Session,
    organization_id: str,
    actor_id: str | None,
    entity_type: str,
    entity_id: str,
    action: str,
    details: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            details=details or {},
        )
    )


def get_candidate(candidate_id: str, organization_id: str, db: Session) -> Candidate:
    candidate = db.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.organization_id == organization_id,
        )
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


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
        requirements=[
            {
                "skill": item.skill,
                "category": item.category,
                "weight": item.weight,
                "min_evidence_level": item.min_evidence_level,
            }
            for item in job.requirements
        ],
        applications_count=db.scalar(
            select(func.count(Application.id)).where(Application.job_id == job.id)
        )
        or 0,
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
                raise HTTPException(
                    status_code=413,
                    detail="Resume document expands beyond allowed limits",
                )
            xml_content = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml_content)
            paragraphs = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
            return " ".join(paragraphs)[:200_000]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Resume DOCX could not be parsed") from exc


def resume_profile_fields(filename: str, text_content: str) -> dict:
    taxonomy = [
        "Python",
        "Java",
        "JavaScript",
        "TypeScript",
        "React",
        "FastAPI",
        "Django",
        "Node.js",
        "PostgreSQL",
        "MySQL",
        "SQL",
        "AWS",
        "Azure",
        "Docker",
        "Kubernetes",
        "Machine Learning",
        "LLMs",
        "RAG",
        "LangChain",
        "REST API",
        "Git",
    ]
    skills = [
        skill
        for skill in taxonomy
        if re.search(r"(?<![\w])" + re.escape(skill) + r"(?![\w])", text_content, re.IGNORECASE)
    ]
    experience_match = re.search(
        r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+)?experience",
        text_content,
        re.IGNORECASE,
    )
    experience = (
        f"{experience_match.group(1)} years (resume text; unverified)" if experience_match else ""
    )
    email_match = re.search(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text_content, re.IGNORECASE
    )
    email = email_match.group(0).lower() if email_match else None
    excluded = {
        "resume",
        "curriculum vitae",
        "cv",
        "profile",
        "summary",
        "experience",
        "education",
    }
    lines = [
        re.sub(r"\s+", " ", line).strip(" -|\t")
        for line in text_content.splitlines()
        if line.strip()
    ]
    name = next(
        (
            line
            for line in lines[:8]
            if 1 < len(line.split()) <= 5
            and len(line) <= 100
            and not any(word in line.casefold() for word in excluded)
            and not re.search(r"[@\d]", line)
        ),
        "",
    )
    if not name:
        name = re.sub(r"[_-]+", " ", Path(filename).stem).strip().title()[:180]
    return {"name": name, "email": email, "skills": skills, "experience": experience}


def prepare_resume_file(filename: str, content: bytes) -> dict:
    if not filename or len(filename) > 255:
        raise HTTPException(status_code=422, detail="Resume filename must be 1 to 255 characters")
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Only PDF and DOCX resumes are accepted")
    if not content or len(content) > settings.max_resume_bytes:
        raise HTTPException(
            status_code=413, detail="Resume file is empty or exceeds the 3.5 MB limit"
        )
    media_type = (
        "application/pdf"
        if extension == ".pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    signature_valid = (
        content.startswith(b"%PDF-") if extension == ".pdf" else content.startswith(b"PK\x03\x04")
    )
    if not signature_valid:
        raise HTTPException(
            status_code=415,
            detail="File extension does not match a supported document signature",
        )
    if not settings.clamd_host:
        raise HTTPException(
            status_code=503,
            detail="Resume uploads are disabled until malware scanning is configured",
        )
    if not settings.resume_encryption_key:
        raise HTTPException(
            status_code=503,
            detail="Resume uploads are disabled until encryption at-rest key is configured",
        )
    try:
        scanner = clamd.ClamdNetworkSocket(
            host=settings.clamd_host, port=settings.clamd_port, timeout=8
        )
        scan_result = scanner.instream(BytesIO(content))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Malware scanner is unavailable; resume was not stored",
        ) from exc
    scan_status = scan_result.get("stream", ("ERROR", "Unknown scan result"))
    if scan_status[0] != "OK":
        raise HTTPException(
            status_code=422, detail="Resume failed malware scanning and was not stored"
        )
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


def add_resume_document(
    candidate: Candidate, user: User, filename: str, prepared: dict, db: Session
) -> ResumeDocument:
    existing = db.scalar(
        select(ResumeDocument).where(
            ResumeDocument.organization_id == user.organization_id,
            ResumeDocument.sha256 == prepared["sha256"],
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="This resume file already exists in the organisation",
        )
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
    if candidate.stage in {"New", "Applied", "Resume Parsed"}:
        candidate.stage = "Resume Parsed"
    db.add(resume)
    db.flush()
    record_audit(
        db,
        user.organization_id,
        user.id,
        "candidate",
        candidate.id,
        "resume_scanned_and_parsed",
        {
            "resume_id": resume.id,
            "size_bytes": resume.size_bytes,
            "extracted_skill_count": len(prepared["skills"]),
        },
    )
    return resume
