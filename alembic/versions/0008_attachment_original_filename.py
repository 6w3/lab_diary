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


def upgrade() -> None:
    with op.batch_alter_table("attachments") as batch:
        batch.add_column(sa.Column("original_filename", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attachments") as batch:
        batch.drop_column("original_filename")
