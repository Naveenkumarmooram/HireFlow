"""Allow imported candidate profiles before a contact email is found."""

import sqlalchemy as sa
from alembic import op

revision = "0005_candidate_contact_optional"
down_revision = "0004_encrypted_resumes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    email_column = next(
        column
        for column in sa.inspect(connection).get_columns("candidates")
        if column["name"] == "email"
    )
    if email_column["nullable"]:
        return
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("candidates", recreate="always") as batch:
            batch.alter_column("email", existing_type=sa.String(length=254), nullable=True)
    else:
        op.alter_column("candidates", "email", existing_type=sa.String(length=254), nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM candidates WHERE email IS NULL")).scalar():
        raise RuntimeError(
            "Cannot require candidate email while resume imports without contact details exist"
        )
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("candidates", recreate="always") as batch:
            batch.alter_column("email", existing_type=sa.String(length=254), nullable=False)
    else:
        op.alter_column("candidates", "email", existing_type=sa.String(length=254), nullable=False)
