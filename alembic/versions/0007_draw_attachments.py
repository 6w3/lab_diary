"""Add draw_attachments M2M between blood draws and files

Revision ID: 0007_draw_attachments
Revises: 0006_label_aliases
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_draw_attachments"
down_revision: Union[str, None] = "0006_label_aliases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "draw_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "blood_draw_id",
            sa.Integer(),
            sa.ForeignKey("blood_draws.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "attachment_id",
            sa.Integer(),
            sa.ForeignKey("attachments.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.UniqueConstraint("blood_draw_id", "attachment_id", name="uq_draw_attachment_pair"),
    )
    # Backfill from legacy attachments.blood_draw_id
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, blood_draw_id FROM attachments WHERE blood_draw_id IS NOT NULL"
        )
    ).fetchall()
    for att_id, draw_id in rows:
        conn.execute(
            sa.text(
                "INSERT INTO draw_attachments (blood_draw_id, attachment_id) "
                "VALUES (:draw_id, :att_id)"
            ),
            {"draw_id": draw_id, "att_id": att_id},
        )


def downgrade() -> None:
    op.drop_table("draw_attachments")
