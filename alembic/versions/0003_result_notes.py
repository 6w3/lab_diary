"""Add optional notes on result values

Revision ID: 0003_result_notes
Revises: 0002_result_attachment
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_result_notes"
down_revision: Union[str, None] = "0002_result_attachment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("result_values", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("result_values", "notes")
