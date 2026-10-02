"""Store scanned resumes encrypted and attached to organisation candidates."""

import sqlalchemy as sa
from alembic import op

revision = "0004_encrypted_resumes"
down_revision = "0003_candidate_portal_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "resume_documents" not in inspector.get_table_names():
        op.create_table(
            "resume_documents",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(length=36),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "candidate_id",
                sa.String(length=36),
                sa.ForeignKey("candidates.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("original_name", sa.String(length=255), nullable=False),
            sa.Column("media_type", sa.String(length=120), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("encrypted_content", sa.LargeBinary(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("organization_id", "sha256", name="uq_resume_org_sha256"),
        )
    index_names = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("resume_documents")
    }
    if "ix_resume_documents_organization_id" not in index_names:
        op.create_index(
            "ix_resume_documents_organization_id",
            "resume_documents",
            ["organization_id"],
        )
    if "ix_resume_documents_candidate_id" not in index_names:
        op.create_index("ix_resume_documents_candidate_id", "resume_documents", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_resume_documents_candidate_id", table_name="resume_documents")
    op.drop_index("ix_resume_documents_organization_id", table_name="resume_documents")
    op.drop_table("resume_documents")
