"""Add proposed_drawn_on for multi-date OCR imports

Revision ID: 0004_proposed_drawn_on
Revises: 0003_result_notes
Create Date: 2026-07-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_proposed_drawn_on"
down_revision: Union[str, None] = "0003_result_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "result_values",
        sa.Column("proposed_drawn_on", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("result_values", "proposed_drawn_on")
