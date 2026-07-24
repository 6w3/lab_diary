"""Link attachments to draws and resolve draw targets without silent merge."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from app.services.ocr_parse import normalize_unit
from app.services.units import to_canonical

if TYPE_CHECKING:
    from app.models import Attachment, BloodDraw, DrawConditions


def link_attachment_to_draw(db, draw_id: int, attachment_id: int) -> None:
    from app.models import DrawAttachment

    existing = (
        db.query(DrawAttachment)
        .filter(
            DrawAttachment.blood_draw_id == draw_id,
            DrawAttachment.attachment_id == attachment_id,
        )
        .first()
    )
    if existing:
        return
    db.add(DrawAttachment(blood_draw_id=draw_id, attachment_id=attachment_id))


def find_draw_candidates(
    db,
    user_id: int,
    day: date,
    lab_name: str,
) -> list:
    from app.models import BloodDraw

    lab = (lab_name or "").strip().casefold()
    rows = db.query(BloodDraw).filter(BloodDraw.user_id == user_id).all()
    out = []
    for d in rows:
        if not d.drawn_at or d.drawn_at.date() != day:
            continue
        if (d.lab_name or "").strip().casefold() != lab:
            continue
        out.append(d)
    out.sort(key=lambda d: d.id)
    return out


def create_draw(
    db,
    user_id: int,
    drawn_at: datetime,
    lab_name: str,
    workplace: str | None,
):
    from app.models import BloodDraw

    draw = BloodDraw(
        user_id=user_id,
        drawn_at=drawn_at,
        lab_name=lab_name,
        workplace=workplace,
    )
    db.add(draw)
    db.flush()
    return draw


def resolve_draw_for_group(
    db,
    user_id: int,
    *,
    drawn_at: datetime,
    lab_name: str,
    workplace: str | None,
    choice: str | None,
) -> tuple:
    """Return (draw, is_new).

    choice:
      - None / "" / "new" → always create new draw
      - "existing:{id}" → use that draw if owned
    """
    from app.models import BloodDraw

    raw = (choice or "new").strip()
    if raw.startswith("existing:"):
        try:
            draw_id = int(raw.split(":", 1)[1])
        except ValueError:
            draw_id = 0
        draw = (
            db.query(BloodDraw)
            .filter(BloodDraw.id == draw_id, BloodDraw.user_id == user_id)
            .first()
        )
        if draw:
            if workplace and not draw.workplace:
                draw.workplace = workplace
            return draw, False
    return create_draw(db, user_id, drawn_at, lab_name, workplace), True


def values_close(a: float, b: float, *, rel: float = 1e-6, abs_tol: float = 1e-9) -> bool:
    return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b)))


def result_is_duplicate(
    db,
    *,
    draw_id: int,
    marker_code: str | None,
    custom_marker_id: int | None,
    value: float,
    unit: str,
) -> bool:
    """True if an equivalent confirmed result already exists on the draw."""
    from app.models import Marker, ResultValue

    q = db.query(ResultValue).filter(
        ResultValue.blood_draw_id == draw_id,
        ResultValue.confirmed.is_(True),
    )
    if marker_code:
        q = q.filter(ResultValue.marker_code == marker_code)
    elif custom_marker_id:
        q = q.filter(ResultValue.custom_marker_id == custom_marker_id)
    else:
        return False

    unit_n = normalize_unit(unit or "")
    for row in q.all():
        row_unit = normalize_unit(row.unit or "")
        cmp_value, cmp_unit = value, unit_n
        row_value, row_u = row.value, row_unit
        if marker_code:
            marker = db.get(Marker, marker_code)
            if marker:
                cv, cu, ok = to_canonical(value, unit_n or unit, marker_code, marker.default_unit)
                if ok:
                    cmp_value, cmp_unit = cv, cu
                rv, ru, rok = to_canonical(
                    row.value, row_unit or row.unit, marker_code, marker.default_unit
                )
                if rok:
                    row_value, row_u = rv, ru
        if cmp_unit and row_u and cmp_unit.casefold() != row_u.casefold():
            continue
        if values_close(float(cmp_value), float(row_value)):
            return True
    return False


def attachments_for_draw(draw) -> list:
    """Prefer M2M links; fall back to legacy blood_draw_id."""
    linked = [link.attachment for link in (draw.draw_attachments or []) if link.attachment]
    if linked:
        seen: set[int] = set()
        out = []
        for a in linked:
            if a.id in seen:
                continue
            seen.add(a.id)
            out.append(a)
        return out
    return list(draw.attachments or [])


def apply_draw_conditions(draw, form: dict):
    from app.models import DrawConditions

    c = draw.conditions or DrawConditions(blood_draw_id=draw.id)

    def parse_bool(value: str | None) -> bool | None:
        if value is None:
            return None
        return value in {"1", "true", "on", "yes"}

    def parse_float(value: str | None) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

    def parse_int(value: str | None) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    c.fasting = parse_bool(form.get("fasting"))
    c.weight_kg = parse_float(form.get("weight_kg"))
    c.last_hard_training = form.get("last_hard_training") or None
    c.sleep_score = parse_int(form.get("sleep_score"))
    c.cycle_day = form.get("cycle_day") or None
    c.contraception = parse_bool(form.get("contraception"))
    c.illness_14d = parse_bool(form.get("illness_14d"))
    c.supplements = form.get("supplements") or None
    c.notes = form.get("notes") or None
    return c
