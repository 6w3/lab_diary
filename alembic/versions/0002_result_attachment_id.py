"""Link OCR proposals to source attachment

Revision ID: 0002_result_attachment
Revises: 0001_initial
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_result_attachment"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "result_values",
        sa.Column("attachment_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_result_values_attachment_id", "result_values", ["attachment_id"])
    op.create_foreign_key(
        "fk_result_values_attachment_id",
        "result_values",
        "attachments",
        ["attachment_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_result_values_attachment_id", "result_values", type_="foreignkey")
    op.drop_index("ix_result_values_attachment_id", table_name="result_values")
    op.drop_column("result_values", "attachment_id")
