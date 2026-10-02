"""Add jobs, candidate applications, interviews, offers and recruiter operations."""

from alembic import op

from migrations.legacy_schema import Base

revision = "0002_ats_workflows"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    workflow_tables = [
        table for table in Base.metadata.sorted_tables if table.name != "resume_documents"
    ]
    Base.metadata.create_all(bind=op.get_bind(), tables=workflow_tables)


def downgrade() -> None:
    for table in (
        "audit_events",
        "organization_settings",
        "outbound_messages",
        "email_templates",
        "recruiter_tasks",
        "offers",
        "interview_feedback",
        "interviews",
        "candidate_scores",
        "applications",
        "job_requirements",
    ):
        op.drop_table(table)
