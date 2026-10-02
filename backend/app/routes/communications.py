from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import current_user, recruiter_user
from app.models import (
    EmailTemplate,
    OutboundMessage,
    User,
)
from app.schemas import (
    CommunicationDraftInput,
    CommunicationDraftView,
    EmailTemplateInput,
    EmailTemplateView,
)
from app.services import get_candidate, record_audit

router = APIRouter(tags=["communications"])


@router.get("/api/communications/outbox")
def list_outbox(user: User = Depends(recruiter_user), db: Session = Depends(get_db)) -> list[dict]:
    messages = db.scalars(
        select(OutboundMessage)
        .where(OutboundMessage.organization_id == user.organization_id)
        .order_by(OutboundMessage.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            "id": item.id,
            "recipient": item.recipient,
            "subject": item.subject,
            "status": item.status,
            "created_at": item.created_at,
        }
        for item in messages
    ]


@router.get("/api/communications/templates", response_model=list[EmailTemplateView])
def list_communication_templates(
    user: User = Depends(current_user), db: Session = Depends(get_db)
) -> list[EmailTemplateView]:
    templates = db.scalars(
        select(EmailTemplate)
        .where(EmailTemplate.organization_id == user.organization_id)
        .order_by(EmailTemplate.event_key)
    ).all()
    if not templates:
        templates = [
            EmailTemplate(
                organization_id=user.organization_id,
                name="Application received",
                event_key="application_received",
                subject="We received your application for {{role}}",
                body="Hello {{candidate}},\n\nThank you for applying for {{role}}. The hiring team will review your application.",
            ),
            EmailTemplate(
                organization_id=user.organization_id,
                name="Interview invitation",
                event_key="interview_invitation",
                subject="Interview invitation: {{role}}",
                body="Hello {{candidate}},\n\nWe would like to invite you to an interview for {{role}}.\nWhen: {{interview_time}}",
            ),
            EmailTemplate(
                organization_id=user.organization_id,
                name="Rejection",
                event_key="rejection",
                subject="Update on your {{role}} application",
                body="Hello {{candidate}},\n\nThank you for your time. We will not be progressing your application for {{role}} at this time.",
            ),
            EmailTemplate(
                organization_id=user.organization_id,
                name="Offer",
                event_key="offer",
                subject="Offer for {{role}}",
                body="Hello {{candidate}},\n\nWe are pleased to offer you the {{role}} position. Compensation: {{compensation}}.",
            ),
        ]
        db.add_all(templates)
        db.commit()
        for template in templates:
            db.refresh(template)
    return [
        EmailTemplateView(
            id=item.id,
            name=item.name,
            subject=item.subject,
            body=item.body,
            event_key=item.event_key,
        )
        for item in templates
    ]


@router.post(
    "/api/communications/templates",
    response_model=EmailTemplateView,
    status_code=status.HTTP_201_CREATED,
)
def create_communication_template(
    data: EmailTemplateInput,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> EmailTemplateView:
    template = EmailTemplate(organization_id=user.organization_id, **data.model_dump())
    db.add(template)
    db.flush()
    record_audit(
        db,
        user.organization_id,
        user.id,
        "email_template",
        template.id,
        "created",
        {"event_key": template.event_key},
    )
    db.commit()
    db.refresh(template)
    return EmailTemplateView(
        id=template.id,
        name=template.name,
        subject=template.subject,
        body=template.body,
        event_key=template.event_key,
    )


@router.put("/api/communications/templates/{template_id}", response_model=EmailTemplateView)
def update_communication_template(
    template_id: str,
    data: EmailTemplateInput,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> EmailTemplateView:
    template = db.scalar(
        select(EmailTemplate).where(
            EmailTemplate.id == template_id,
            EmailTemplate.organization_id == user.organization_id,
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Communication template not found")
    for field, value in data.model_dump().items():
        setattr(template, field, value)
    record_audit(
        db,
        user.organization_id,
        user.id,
        "email_template",
        template.id,
        "updated",
        {"event_key": template.event_key},
    )
    db.commit()
    db.refresh(template)
    return EmailTemplateView(
        id=template.id,
        name=template.name,
        subject=template.subject,
        body=template.body,
        event_key=template.event_key,
    )


@router.post(
    "/api/communications/drafts",
    response_model=CommunicationDraftView,
    status_code=status.HTTP_201_CREATED,
)
def create_communication_draft(
    data: CommunicationDraftInput,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> CommunicationDraftView:
    candidate = get_candidate(data.candidate_id, user.organization_id, db)
    if not candidate.email:
        raise HTTPException(
            status_code=422,
            detail="Add a verified candidate email before creating a communication draft",
        )
    template = db.scalar(
        select(EmailTemplate).where(
            EmailTemplate.id == data.template_id,
            EmailTemplate.organization_id == user.organization_id,
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Communication template not found")
    variables = {
        "candidate": candidate.name,
        "role": candidate.role_title,
        "compensation": candidate.expected_ctc,
    }
    subject = data.subject if data.subject is not None else template.subject
    body = data.body if data.body is not None else template.body
    for key, value in variables.items():
        subject = subject.replace("{{" + key + "}}", value)
        body = body.replace("{{" + key + "}}", value)
    message = OutboundMessage(
        organization_id=user.organization_id,
        candidate_id=candidate.id,
        recipient=candidate.email,
        subject=subject,
        body=body,
        status="draft",
    )
    db.add(message)
    db.flush()
    record_audit(
        db,
        user.organization_id,
        user.id,
        "communication",
        message.id,
        "draft_created",
        {"candidate_id": candidate.id},
    )
    db.commit()
    db.refresh(message)
    return CommunicationDraftView(
        id=message.id,
        recipient=message.recipient,
        subject=message.subject,
        body=message.body,
        status=message.status,
        created_at=message.created_at,
    )
