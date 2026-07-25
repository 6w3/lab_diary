"""Widen proposals_json / ocr_raw_text to MEDIUMTEXT

Revision ID: 0009_mediumtext_payload
Revises: 0008_orig_filename
Create Date: 2026-07-25
"""

from __future__ import annotations

from alembic import op

revision = "0009_mediumtext_payload"
down_revision = "0008_orig_filename"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL TEXT = 64KiB; multi-file Smart payloads exceed that.
    op.execute(
        "ALTER TABLE import_jobs "
        "MODIFY proposals_json MEDIUMTEXT NULL, "
        "MODIFY ocr_raw_text MEDIUMTEXT NULL"
    )
    op.execute(
        "ALTER TABLE attachments MODIFY ocr_raw_text MEDIUMTEXT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE import_jobs "
        "MODIFY proposals_json TEXT NULL, "
        "MODIFY ocr_raw_text TEXT NULL"
    )
    op.execute(
        "ALTER TABLE attachments MODIFY ocr_raw_text TEXT NULL"
    )
