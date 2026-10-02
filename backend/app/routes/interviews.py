from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import coordinator_user, current_user
from app.models import (
    Interview,
    InterviewFeedback,
    User,
)
from app.schemas import (
    FeedbackInput,
    InterviewInput,
    InterviewView,
)
from app.services import get_candidate, interview_view, record_audit

router = APIRouter(tags=["interviews"])


@router.get("/api/interviews", response_model=list[InterviewView])
def list_interviews(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[InterviewView]:
    query = select(Interview).where(Interview.organization_id == user.organization_id)
    if user.role == "interviewer":
        query = query.where(Interview.interviewer_id == user.id)
    interviews = db.scalars(
        query.order_by(Interview.scheduled_for.asc(), Interview.id).limit(limit).offset(offset)
    ).all()
    return [interview_view(item) for item in interviews]


@router.post("/api/interviews", response_model=InterviewView, status_code=status.HTTP_201_CREATED)
def create_interview(
    data: InterviewInput,
    user: User = Depends(coordinator_user),
    db: Session = Depends(get_db),
) -> InterviewView:
    candidate = get_candidate(data.candidate_id, user.organization_id, db)
    if data.interviewer_id:
        interviewer = db.scalar(
            select(User).where(
                User.id == data.interviewer_id,
                User.organization_id == user.organization_id,
                User.active.is_(True),
                User.role.in_(["interviewer", "hiring_manager", "admin"]),
            )
        )
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
    record_audit(
        db,
        user.organization_id,
        user.id,
        "interview",
        interview.id,
        "scheduled",
        {"candidate_id": candidate.id},
    )
    db.commit()
    db.refresh(interview)
    return interview_view(interview)


@router.post("/api/interviews/{interview_id}/feedback", status_code=status.HTTP_201_CREATED)
def submit_interview_feedback(
    interview_id: str,
    data: FeedbackInput,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    interview = db.scalar(
        select(Interview).where(
            Interview.id == interview_id,
            Interview.organization_id == user.organization_id,
        )
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    if user.role == "interviewer" and interview.interviewer_id != user.id:
        raise HTTPException(
            status_code=403, detail="Feedback is limited to your assigned interviews"
        )
    if user.role not in {"admin", "recruiter", "hiring_manager", "interviewer"}:
        raise HTTPException(status_code=403, detail="Interview feedback access required")
    if db.scalar(
        select(InterviewFeedback.id).where(
            InterviewFeedback.interview_id == interview.id,
            InterviewFeedback.interviewer_id == user.id,
        )
    ):
        raise HTTPException(
            status_code=409, detail="You already submitted feedback for this interview"
        )
    db.add(
        InterviewFeedback(
            organization_id=user.organization_id,
            interview_id=interview.id,
            interviewer_id=user.id,
            **data.model_dump(),
        )
    )
    interview.status = "completed"
    record_audit(
        db,
        user.organization_id,
        user.id,
        "interview",
        interview.id,
        "feedback_submitted",
        {"recommendation": data.recommendation},
    )
    db.commit()
    return {"status": "submitted"}
