from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


Stage = Literal[
    "New", "Applied", "Resume Parsed", "AI Screened", "Recruiter Review", "Screening",
    "Telephone Discussion", "Tech round 1", "Tech round 2", "Final Discussion", "Offer Approval",
    "Offer", "Offer Sent", "Offer Accepted", "Joining Confirmed", "Hired", "Hold", "Rejected",
    "No Response", "Candidate Withdrew", "Offer Declined", "Closed",
]


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserView(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str
    organization_name: str


class TokenView(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserView


class CandidateInput(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: EmailStr
    role_title: str = Field(min_length=1, max_length=180)
    stage: Stage = "New"
    experience: str = Field(default="", max_length=60)
    skills: list[str] = Field(default_factory=list, max_length=30)
    current_ctc: str = Field(default="", max_length=60)
    expected_ctc: str = Field(default="", max_length=60)
    availability: str = Field(default="", max_length=80)
    job_id: str | None = None


class CandidateUpdate(BaseModel):
    email: EmailStr | None = None
    stage: Stage | None = None
    experience: str | None = Field(default=None, max_length=60)
    skills: list[str] | None = Field(default=None, max_length=30)
    current_ctc: str | None = Field(default=None, max_length=60)
    expected_ctc: str | None = Field(default=None, max_length=60)
    availability: str | None = Field(default=None, max_length=80)


class CandidateView(BaseModel):
    id: str
    name: str
    email: EmailStr | None
    role_title: str
    stage: Stage
    experience: str
    skills: list[str]
    current_ctc: str
    expected_ctc: str
    availability: str
    job_id: str | None
    created_at: datetime
    score: int | None = None
    model_config = ConfigDict(from_attributes=True)


class ScreeningInput(BaseModel):
    call_status: Literal["Connected", "No answer", "Call back requested"]
    current_ctc: str = Field(default="", max_length=60)
    expected_ctc: str = Field(default="", max_length=60)
    notice_period: str = Field(default="", max_length=80)
    relocation: Literal["Not discussed", "Yes", "No", "Needs discussion"] = "Not discussed"
    contract_preference: Literal["Not discussed", "Yes", "No", "Needs discussion"] = "Not discussed"
    notes: str = Field(default="", max_length=5000)
    decision: Literal["Shortlist", "Hold", "Reject"]


class ScreeningView(BaseModel):
    id: str
    candidate_id: str
    call_status: str
    current_ctc: str
    expected_ctc: str
    notice_period: str
    relocation: str
    contract_preference: str
    notes: str
    decision: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class JobRequirementInput(BaseModel):
    skill: str = Field(min_length=1, max_length=100)
    category: Literal["must_have", "nice_to_have", "trainable", "disqualifying"] = "must_have"
    weight: int = Field(default=1, ge=1, le=100)
    min_evidence_level: int = Field(default=1, ge=1, le=6)


class JobInput(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    location: str = Field(default="", max_length=180)
    employment_type: str = Field(default="Full time", max_length=80)
    status: Literal["draft", "published", "closed"] = "draft"
    description: str = Field(default="", max_length=12000)
    requirements: list[JobRequirementInput] = Field(default_factory=list, max_length=50)


class JobView(BaseModel):
    id: str
    title: str
    location: str
    employment_type: str
    status: str
    description: str
    created_at: datetime
    requirements: list[JobRequirementInput]
    applications_count: int = 0


class PublicJobView(BaseModel):
    id: str
    title: str
    location: str
    employment_type: str
    description: str
    organization_name: str
    requirements: list[str]


class PublicApplicationInput(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: EmailStr
    experience: str = Field(default="", max_length=60)
    skills: list[str] = Field(default_factory=list, max_length=30)
    availability: str = Field(default="", max_length=80)
    consent: bool
    source: str = Field(default="careers_page", max_length=80)


class MatchCriterion(BaseModel):
    skill: str
    category: str
    weight: int
    matched: bool
    evidence_level: int
    evidence: str


class MatchView(BaseModel):
    candidate_id: str
    job_id: str
    score: int
    methodology: str
    decision_note: str
    criteria: list[MatchCriterion]


class InterviewInput(BaseModel):
    candidate_id: str
    interviewer_id: str | None = None
    title: str = Field(min_length=2, max_length=120)
    scheduled_for: datetime
    duration_minutes: int = Field(default=60, ge=15, le=480)
    timezone: str = Field(default="UTC", max_length=80)
    meeting_method: Literal["Google Meet", "Microsoft Teams", "Phone", "In person"] = "In person"
    location_or_link: str = Field(default="", max_length=500)


class InterviewView(BaseModel):
    id: str
    candidate_id: str
    candidate_name: str
    candidate_email: EmailStr | None
    interviewer_id: str | None
    title: str
    scheduled_for: datetime
    duration_minutes: int
    timezone: str
    meeting_method: str
    location_or_link: str
    status: str
    feedback_submitted: bool


class FeedbackInput(BaseModel):
    technical_rating: int = Field(ge=1, le=5)
    problem_solving_rating: int = Field(ge=1, le=5)
    evidence: str = Field(min_length=10, max_length=5000)
    recommendation: Literal["Strong yes", "Yes", "Hold", "No"]


class OfferInput(BaseModel):
    candidate_id: str
    title: str = Field(min_length=2, max_length=180)
    compensation: str = Field(min_length=1, max_length=100)
    employment_type: str = Field(max_length=80)
    joining_date: str = Field(default="", max_length=20)
    expires_at: datetime | None = None


class OfferView(BaseModel):
    id: str
    candidate_id: str
    candidate_name: str
    title: str
    compensation: str
    employment_type: str
    joining_date: str
    status: str
    expires_at: datetime | None
    accepted_at: datetime | None
    created_at: datetime


class OfferCreatedView(OfferView):
    acceptance_url: str


class RecruiterTaskInput(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    candidate_id: str | None = None
    assigned_to_id: str | None = None
    due_at: datetime | None = None


class TaskView(BaseModel):
    id: str
    candidate_id: str | None
    candidate_name: str | None
    assigned_to_id: str | None
    title: str
    due_at: datetime | None
    status: str
    created_at: datetime


class TaskUpdate(BaseModel):
    status: Literal["open", "done", "cancelled"]


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "recruiter", "hiring_manager", "interviewer"] = "recruiter"


class UserAdminView(BaseModel):
    id: str
    name: str
    email: EmailStr
    role: str
    active: bool


class OrganizationSettingsInput(BaseModel):
    timezone: str = Field(default="UTC", max_length=80)
    careers_intro: str = Field(default="", max_length=500)
    retention_days: int = Field(default=365, ge=30, le=3650)
    require_candidate_consent: bool = True


class OrganizationSettingsView(OrganizationSettingsInput):
    organization_id: str


class AuditEventView(BaseModel):
    id: str
    actor_id: str | None
    entity_type: str
    entity_id: str
    action: str
    details: dict
    created_at: datetime


class PublicOfferView(BaseModel):
    candidate_name: str
    title: str
    compensation: str
    employment_type: str
    joining_date: str
    status: str
    expires_at: datetime | None


class CandidatePortalView(BaseModel):
    candidate_name: str
    job_title: str
    application_status: str
    last_updated: datetime
    interviews: list[dict]
    offer_status: str | None


class EmailTemplateInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    subject: str = Field(min_length=2, max_length=240)
    body: str = Field(min_length=2, max_length=10000)
    event_key: Literal["application_received", "interview_invitation", "rejection", "offer"]


class EmailTemplateView(BaseModel):
    id: str
    name: str
    subject: str
    body: str
    event_key: str


class CommunicationDraftInput(BaseModel):
    template_id: str
    candidate_id: str
    subject: str | None = Field(default=None, max_length=240)
    body: str | None = Field(default=None, max_length=10000)


class CommunicationDraftView(BaseModel):
    id: str
    recipient: EmailStr
    subject: str
    body: str
    status: str
    created_at: datetime


class ResumeDocumentView(BaseModel):
    id: str
    candidate_id: str
    original_name: str
    media_type: str
    size_bytes: int
    created_at: datetime
    extracted_skills: list[str]
    extracted_experience: str


class ResumeIntakeView(BaseModel):
    candidate: CandidateView
    resume: ResumeDocumentView
    fields_needing_review: list[str]
    matched_existing_candidate: bool
    review_note: str


class ApplicationReceipt(BaseModel):
    status: str
    message: str
    portal_url: str