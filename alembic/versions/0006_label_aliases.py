"""Add label_aliases for user OCR→marker mappings

Revision ID: 0006_label_aliases
Revises: 0005_import_jobs
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_label_aliases"
down_revision: Union[str, None] = "0005_import_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "label_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("label_raw", sa.String(255), nullable=False),
        sa.Column("label_norm", sa.String(255), nullable=False),
        sa.Column("marker_code", sa.String(64), sa.ForeignKey("markers.code", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("user_id", "label_norm", name="uq_label_alias_user_norm"),
    )


def downgrade() -> None:
    op.drop_table("label_aliases")
