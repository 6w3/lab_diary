"""empty message

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("locale", sa.String(8), nullable=False, server_default="cs"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "markers",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name_cs", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("default_unit", sa.String(64), nullable=False),
        sa.Column("tip_ref_low", sa.Float(), nullable=True),
        sa.Column("tip_ref_high", sa.Float(), nullable=True),
    )

    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),
    )

    op.create_table(
        "email_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_email_tokens_token", "email_tokens", ["token"], unique=True)

    op.create_table(
        "custom_markers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("unit", sa.String(64), nullable=False, server_default=""),
        sa.UniqueConstraint("user_id", "name", name="uq_custom_marker_user_name"),
    )
    op.create_index("ix_custom_markers_user_id", "custom_markers", ["user_id"])

    op.create_table(
        "blood_draws",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("drawn_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lab_name", sa.String(255), nullable=False),
        sa.Column("workplace", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_blood_draws_user_id", "blood_draws", ["user_id"])

    op.create_table(
        "draw_conditions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("blood_draw_id", sa.Integer(), sa.ForeignKey("blood_draws.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("fasting", sa.Boolean(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("last_hard_training", sa.String(255), nullable=True),
        sa.Column("sleep_score", sa.Integer(), nullable=True),
        sa.Column("cycle_day", sa.String(64), nullable=True),
        sa.Column("contraception", sa.Boolean(), nullable=True),
        sa.Column("illness_14d", sa.Boolean(), nullable=True),
        sa.Column("supplements", sa.String(512), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("blood_draw_id", sa.Integer(), sa.ForeignKey("blood_draws.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("ocr_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("ocr_raw_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_attachments_blood_draw_id", "attachments", ["blood_draw_id"])

    op.create_table(
        "result_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("blood_draw_id", sa.Integer(), sa.ForeignKey("blood_draws.id", ondelete="CASCADE"), nullable=False),
        sa.Column("marker_code", sa.String(64), sa.ForeignKey("markers.code"), nullable=True),
        sa.Column("custom_marker_id", sa.Integer(), sa.ForeignKey("custom_markers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(64), nullable=False),
        sa.Column("lab_ref_low", sa.Float(), nullable=True),
        sa.Column("lab_ref_high", sa.Float(), nullable=True),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("label", sa.String(255), nullable=True),
    )
    op.create_index("ix_result_values_blood_draw_id", "result_values", ["blood_draw_id"])


def downgrade() -> None:
    op.drop_table("result_values")
    op.drop_table("attachments")
    op.drop_table("draw_conditions")
    op.drop_table("blood_draws")
    op.drop_table("custom_markers")
    op.drop_table("email_tokens")
    op.drop_table("oauth_accounts")
    op.drop_table("markers")
    op.drop_table("users")
