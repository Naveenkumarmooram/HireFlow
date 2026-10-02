import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import coordinator_user, current_user, recruiter_user
from app.models import (
    Offer,
    User,
)
from app.schemas import (
    OfferCreatedView,
    OfferInput,
    OfferView,
)
from app.services import get_candidate, offer_view, record_audit

router = APIRouter(tags=["offers"])


@router.get("/api/offers", response_model=list[OfferView])
def list_offers(
    user: User = Depends(coordinator_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[OfferView]:
    offers = db.scalars(
        select(Offer)
        .where(Offer.organization_id == user.organization_id)
        .order_by(Offer.created_at.desc(), Offer.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [offer_view(item) for item in offers]


@router.post("/api/offers", response_model=OfferCreatedView, status_code=status.HTTP_201_CREATED)
def create_offer(
    data: OfferInput,
    user: User = Depends(recruiter_user),
    db: Session = Depends(get_db),
) -> OfferCreatedView:
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
        expires_at=data.expires_at or datetime.now(timezone.utc) + timedelta(days=14),
    )
    candidate.stage = "Offer Approval"
    db.add(offer)
    db.flush()
    record_audit(
        db,
        user.organization_id,
        user.id,
        "offer",
        offer.id,
        "draft_created",
        {"candidate_id": candidate.id},
    )
    db.commit()
    db.refresh(offer)
    return OfferCreatedView(
        **offer_view(offer).model_dump(), acceptance_url=f"/offer/{acceptance_token}"
    )


@router.post("/api/offers/{offer_id}/approve", response_model=OfferView)
def approve_offer(
    offer_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> OfferView:
    if user.role not in {"admin", "hiring_manager"}:
        raise HTTPException(status_code=403, detail="Offer approval access required")
    offer = db.scalar(
        select(Offer)
        .where(Offer.id == offer_id, Offer.organization_id == user.organization_id)
        .with_for_update()
    )
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft offers can be approved")
    offer.status = "approved"
    offer.approved_by_id = user.id
    offer.candidate.stage = "Offer Sent"
    record_audit(
        db,
        user.organization_id,
        user.id,
        "offer",
        offer.id,
        "approved",
        {"candidate_id": offer.candidate_id},
    )
    db.commit()
    db.refresh(offer)
    return offer_view(offer)
