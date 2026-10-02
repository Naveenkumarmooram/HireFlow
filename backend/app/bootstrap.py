"""Explicit one-time bootstrap: python -m app.bootstrap. Never runs on web startup."""

from email_validator import validate_email
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine
from app.models import AuditEvent, Organization, OrganizationSettings, User
from app.security import hash_password


def main():
    email = validate_email(
        settings.bootstrap_admin_email, check_deliverability=False
    ).normalized.lower()
    if not settings.bootstrap_org_name.strip():
        raise RuntimeError("BOOTSTRAP_ORG_NAME is required")
    password = settings.bootstrap_admin_password
    if len(password) < 16 or any(
        value in password.lower() for value in ("change-this", "replace-with")
    ):
        raise RuntimeError("Set a unique BOOTSTRAP_ADMIN_PASSWORD of at least 16 characters")
    with Session(engine) as db, db.begin():
        if engine.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(739146820)"))
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            print("Bootstrap account already exists; no changes made.")
            return
        if db.scalar(select(User.id).limit(1)):
            raise RuntimeError(
                "Database is already provisioned. Use an existing administrator to create accounts."
            )
        organization = Organization(name=settings.bootstrap_org_name.strip())
        db.add(organization)
        db.flush()
        user = User(
            organization_id=organization.id,
            email=email,
            name="Administrator",
            role="admin",
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
        db.add(OrganizationSettings(organization_id=organization.id))
        db.add(
            AuditEvent(
                organization_id=organization.id,
                actor_id=user.id,
                entity_type="user",
                entity_id=user.id,
                action="bootstrap_admin_created",
                details={},
            )
        )
    print("Initial administrator created. Remove bootstrap credentials from the environment.")


if __name__ == "__main__":
    main()
