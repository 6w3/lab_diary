"""Add import_jobs and nullable attachment.blood_draw_id

Revision ID: 0005_import_jobs
Revises: 0004_proposed_drawn_on
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_import_jobs"
down_revision: Union[str, None] = "0004_proposed_drawn_on"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="review"),
        sa.Column("extract_mode", sa.String(32), nullable=False, server_default="smart"),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("ocr_raw_text", sa.Text(), nullable=True),
        sa.Column("proposals_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Make blood_draw_id nullable for import-first attachments
    with op.batch_alter_table("attachments") as batch:
        batch.alter_column("blood_draw_id", existing_type=sa.Integer(), nullable=True)
        batch.add_column(sa.Column("import_job_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_attachments_import_job_id",
        "attachments",
        "import_jobs",
        ["import_job_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_attachments_import_job_id", "attachments", ["import_job_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_import_job_id", table_name="attachments")
    op.drop_constraint("fk_attachments_import_job_id", "attachments", type_="foreignkey")
    with op.batch_alter_table("attachments") as batch:
        batch.drop_column("import_job_id")
        batch.alter_column("blood_draw_id", existing_type=sa.Integer(), nullable=False)
    op.drop_table("import_jobs")
