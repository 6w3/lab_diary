from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    locale: Mapped[str] = mapped_column(String(8), default="cs")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    oauth_accounts: Mapped[list["OAuthAccount"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    blood_draws: Mapped[list["BloodDraw"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    custom_markers: Mapped[list["CustomMarker"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    label_aliases: Mapped[list["LabelAlias"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    email_tokens: Mapped[list["EmailToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    import_jobs: Mapped[list["ImportJob"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class OAuthAccount(Base):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id", name="uq_oauth_provider_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32))
    provider_user_id: Mapped[str] = mapped_column(String(255))

    user: Mapped[User] = relationship(back_populates="oauth_accounts")


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(32))  # verify | reset
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="email_tokens")


class BloodDraw(Base):
    __tablename__ = "blood_draws"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    drawn_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lab_name: Mapped[str] = mapped_column(String(255))
    workplace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="blood_draws")
    conditions: Mapped["DrawConditions | None"] = relationship(
        back_populates="blood_draw", uselist=False, cascade="all, delete-orphan"
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="blood_draw", cascade="all, delete-orphan"
    )
    draw_attachments: Mapped[list["DrawAttachment"]] = relationship(
        back_populates="blood_draw", cascade="all, delete-orphan"
    )
    results: Mapped[list["ResultValue"]] = relationship(
        back_populates="blood_draw", cascade="all, delete-orphan"
    )


class DrawConditions(Base):
    __tablename__ = "draw_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blood_draw_id: Mapped[int] = mapped_column(ForeignKey("blood_draws.id", ondelete="CASCADE"), unique=True)
    fasting: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_hard_training: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sleep_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cycle_day: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contraception: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    illness_14d: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    supplements: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    blood_draw: Mapped[BloodDraw] = relationship(back_populates="conditions")


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="review")  # review|confirmed|failed|cancelled
    extract_mode: Mapped[str] = mapped_column(String(32), default="smart")
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    storage_path: Mapped[str] = mapped_column(String(512))
    ocr_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposals_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="import_jobs")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="import_job")


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blood_draw_id: Mapped[int | None] = mapped_column(
        ForeignKey("blood_draws.id", ondelete="CASCADE"), nullable=True, index=True
    )
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_jobs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    storage_path: Mapped[str] = mapped_column(String(512))
    ocr_status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|done|failed|skipped
    ocr_raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    blood_draw: Mapped[BloodDraw | None] = relationship(back_populates="attachments")
    import_job: Mapped[ImportJob | None] = relationship(back_populates="attachments")
    draw_links: Mapped[list["DrawAttachment"]] = relationship(
        back_populates="attachment", cascade="all, delete-orphan"
    )


class DrawAttachment(Base):
    """Many-to-many: one file can belong to many draws; one draw can have many files."""

    __tablename__ = "draw_attachments"
    __table_args__ = (UniqueConstraint("blood_draw_id", "attachment_id", name="uq_draw_attachment_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blood_draw_id: Mapped[int] = mapped_column(
        ForeignKey("blood_draws.id", ondelete="CASCADE"), index=True
    )
    attachment_id: Mapped[int] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE"), index=True
    )

    blood_draw: Mapped[BloodDraw] = relationship(back_populates="draw_attachments")
    attachment: Mapped[Attachment] = relationship(back_populates="draw_links")


class Marker(Base):
    __tablename__ = "markers"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name_cs: Mapped[str] = mapped_column(String(255))
    name_en: Mapped[str] = mapped_column(String(255))
    default_unit: Mapped[str] = mapped_column(String(64))
    tip_ref_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    tip_ref_high: Mapped[float | None] = mapped_column(Float, nullable=True)


class CustomMarker(Base):
    __tablename__ = "custom_markers"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_custom_marker_user_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(64), default="")

    user: Mapped[User] = relationship(back_populates="custom_markers")
    results: Mapped[list["ResultValue"]] = relationship(back_populates="custom_marker")


class LabelAlias(Base):
    """User-learned OCR/custom label → catalog marker mapping."""

    __tablename__ = "label_aliases"
    __table_args__ = (UniqueConstraint("user_id", "label_norm", name="uq_label_alias_user_norm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label_raw: Mapped[str] = mapped_column(String(255))
    label_norm: Mapped[str] = mapped_column(String(255))
    marker_code: Mapped[str] = mapped_column(ForeignKey("markers.code", ondelete="CASCADE"))

    user: Mapped[User] = relationship(back_populates="label_aliases")
    marker: Mapped["Marker"] = relationship()


class ResultValue(Base):
    __tablename__ = "result_values"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blood_draw_id: Mapped[int] = mapped_column(ForeignKey("blood_draws.id", ondelete="CASCADE"), index=True)
    attachment_id: Mapped[int | None] = mapped_column(
        ForeignKey("attachments.id", ondelete="CASCADE"), nullable=True, index=True
    )
    marker_code: Mapped[str | None] = mapped_column(ForeignKey("markers.code"), nullable=True)
    custom_marker_id: Mapped[int | None] = mapped_column(
        ForeignKey("custom_markers.id", ondelete="SET NULL"), nullable=True
    )
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(64))
    lab_ref_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    lab_ref_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_drawn_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    blood_draw: Mapped[BloodDraw] = relationship(back_populates="results")
    attachment: Mapped[Attachment | None] = relationship()
    marker: Mapped[Marker | None] = relationship()
    custom_marker: Mapped[CustomMarker | None] = relationship(back_populates="results")
