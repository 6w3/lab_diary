"""Add original_filename to attachments

Revision ID: 0008_attachment_original_filename
Revises: 0007_draw_attachments
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_attachment_original_filename"
down_revision = "0007_draw_attachments"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(col["name"] == column for col in inspector.get_columns(table))


def upgrade() -> None:
    if _has_column("attachments", "original_filename"):
        return
    with op.batch_alter_table("attachments") as batch:
        batch.add_column(sa.Column("original_filename", sa.String(length=255), nullable=True))


def downgrade() -> None:
    if not _has_column("attachments", "original_filename"):
        return
    with op.batch_alter_table("attachments") as batch:
        batch.drop_column("original_filename")
