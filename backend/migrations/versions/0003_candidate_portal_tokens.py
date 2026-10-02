"""Add hashed candidate portal tokens and organisation-level candidate uniqueness."""

import hashlib

import sqlalchemy as sa
from alembic import op

revision = "0003_candidate_portal_tokens"
down_revision = "0002_ats_workflows"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    application_columns = {column["name"] for column in inspector.get_columns("applications")}
    if "portal_token_hash" not in application_columns:
        op.add_column(
            "applications",
            sa.Column("portal_token_hash", sa.String(length=64), nullable=True),
        )
        rows = connection.execute(
            sa.text("SELECT id FROM applications WHERE portal_token_hash IS NULL")
        ).all()
        for (application_id,) in rows:
            digest = hashlib.sha256(f"legacy-portal-token:{application_id}".encode()).hexdigest()
            connection.execute(
                sa.text(
                    "UPDATE applications SET portal_token_hash = :digest WHERE id = :application_id"
                ),
                {"digest": digest, "application_id": application_id},
            )
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("applications", recreate="always") as batch:
            batch.alter_column(
                "portal_token_hash", existing_type=sa.String(length=64), nullable=False
            )
    else:
        op.alter_column(
            "applications",
            "portal_token_hash",
            existing_type=sa.String(length=64),
            nullable=False,
        )
    application_constraints = inspector.get_unique_constraints("applications")
    has_portal_unique = any(
        constraint.get("column_names") == ["portal_token_hash"]
        for constraint in application_constraints
    )
    if not has_portal_unique:
        if connection.dialect.name == "sqlite":
            with op.batch_alter_table("applications", recreate="always") as batch:
                batch.create_unique_constraint(
                    "uq_applications_portal_token_hash", ["portal_token_hash"]
                )
        else:
            op.create_unique_constraint(
                "uq_applications_portal_token_hash",
                "applications",
                ["portal_token_hash"],
            )
    candidate_constraints = inspector.get_unique_constraints("candidates")
    has_org_email_unique = any(
        constraint.get("column_names") == ["organization_id", "email"]
        for constraint in candidate_constraints
    )
    if not has_org_email_unique:
        if connection.dialect.name == "sqlite":
            with op.batch_alter_table("candidates", recreate="always") as batch:
                batch.create_unique_constraint(
                    "uq_candidates_org_email", ["organization_id", "email"]
                )
        else:
            op.create_unique_constraint(
                "uq_candidates_org_email", "candidates", ["organization_id", "email"]
            )


def downgrade() -> None:
    op.drop_constraint("uq_candidates_org_email", "candidates", type_="unique")
    op.drop_constraint("uq_applications_portal_token_hash", "applications", type_="unique")
    op.drop_column("applications", "portal_token_hash")
