"""Revocable authentication, login throttling and Supabase API isolation."""

import sqlalchemy as sa
from alembic import op

revision = "0006_auth_hardening"
down_revision = "0005_candidate_contact_optional"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    # Fail without changing data if existing identities need operator reconciliation.
    if connection.execute(
        sa.text("SELECT lower(email) FROM users GROUP BY lower(email) HAVING COUNT(*) > 1")
    ).first():
        raise RuntimeError("Duplicate user emails must be reconciled before upgrading")
    connection.execute(sa.text("UPDATE users SET email = lower(email)"))
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0")
        )
        batch.alter_column("email", existing_type=sa.String(254), nullable=False)
        batch.create_unique_constraint("uq_users_email", ["email"])
    op.create_table(
        "login_attempts",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index("ix_login_attempts_window_start", "login_attempts", ["window_start"])
    if connection.dialect.name == "postgresql":
        # FastAPI owns authorization. Browser Supabase REST roles must never read these tables.
        names = [
            "organizations",
            "users",
            "jobs",
            "candidates",
            "screenings",
            "job_requirements",
            "applications",
            "candidate_scores",
            "interviews",
            "interview_feedback",
            "offers",
            "recruiter_tasks",
            "email_templates",
            "outbound_messages",
            "audit_events",
            "organization_settings",
            "resume_documents",
            "login_attempts",
            "alembic_version",
        ]
        roles = (
            connection.execute(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
            )
            .scalars()
            .all()
        )
        for name in names:
            op.execute(sa.text(f'ALTER TABLE "{name}" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text(f'REVOKE ALL ON TABLE "{name}" FROM PUBLIC'))
            for role in roles:
                op.execute(sa.text(f'REVOKE ALL ON TABLE "{name}" FROM "{role}"'))


def downgrade():
    raise RuntimeError("Security migration is forward-only. Restore a tested backup to roll back.")
