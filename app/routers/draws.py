from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.deps import DbDep, LocaleDep, UserDep, redirect, template_context
from app.models import Attachment, BloodDraw, DrawConditions, Marker, ResultValue, User
from app.services.draw_organize import (
    apply_draw_conditions,
    attachments_for_draw,
    create_draw as create_blood_draw,
)
from app.services.multi_date import unique_drawn_dates
from app.services.ocr_tables import date_to_datetime, parse_iso_date
from app.services.result_bind import bind_marker_and_units
from app.services.smart_extract import smart_enabled
from app.services.units import UNIT_CHOICES, unit_options_for_marker

router = APIRouter(prefix="/draws", tags=["draws"])
templates = Jinja2Templates(directory="app/templates")


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value in {"1", "true", "on", "yes"}


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _parse_drawn_at(raw: str) -> datetime:
    """Accept date-only (YYYY-MM-DD) or datetime-local; store as midnight when no time."""
    value = (raw or "").strip()
    if not value:
        raise ValueError("drawn_at required")
    if "T" in value:
        return datetime.fromisoformat(value)
    return datetime.combine(date.fromisoformat(value), datetime.min.time())


def _get_owned_draw(db, user_id: int, draw_id: int) -> BloodDraw | None:
    return (
        db.query(BloodDraw)
        .filter(BloodDraw.id == draw_id, BloodDraw.user_id == user_id)
        .first()
    )


def _apply_conditions(draw: BloodDraw, form: dict) -> DrawConditions:
    return apply_draw_conditions(draw, form)


def _display_results(draw: BloodDraw, locale: str):
    rows = []
    for r in draw.results:
        if not r.confirmed:
            continue
        tip_low = tip_high = None
        if r.marker:
            tip_low, tip_high = r.marker.tip_ref_low, r.marker.tip_ref_high
            name = r.marker.name_cs if locale == "cs" else r.marker.name_en
        elif r.custom_marker:
            name = r.custom_marker.name
        else:
            name = r.label or "?"
        rows.append(
            SimpleNamespace(
                id=r.id,
                display_name=name,
                value=r.value,
                unit=r.unit,
                lab_ref_low=r.lab_ref_low,
                lab_ref_high=r.lab_ref_high,
                tip_low=tip_low,
                tip_high=tip_high,
                notes=r.notes,
            )
        )
    return rows


@router.get("", response_class=HTMLResponse)
def list_draws(request: Request, db: DbDep, locale: LocaleDep, user: UserDep):
    draws = (
        db.query(BloodDraw)
        .filter(BloodDraw.user_id == user.id)
        .order_by(BloodDraw.drawn_at.desc())
        .all()
    )
    draw_rows = [
        SimpleNamespace(
            id=d.id,
            drawn_at=d.drawn_at,
            lab_name=d.lab_name,
            missing_conditions=d.conditions is None,
        )
        for d in draws
    ]
    return templates.TemplateResponse(
        request,
        "draws/list.html",
        template_context(request, locale, draws=draw_rows),
    )


@router.get("/new", response_class=HTMLResponse)
def new_draw_form(request: Request, locale: LocaleDep, user: UserDep):
    return templates.TemplateResponse(
        request,
        "draws/form.html",
        template_context(
            request,
            locale,
            draw=None,
            c=None,
            action="/draws/new",
            drawn_at_value="",
        ),
    )


@router.post("/new")
async def create_draw(request: Request, db: DbDep, user: UserDep):
    form = dict(await request.form())
    drawn_at = _parse_drawn_at(form["drawn_at"])
    lab_name = (form.get("lab_name") or "").strip()
    if not lab_name:
        return redirect("/draws/new")
    draw = BloodDraw(
        user_id=user.id,
        drawn_at=drawn_at,
        lab_name=lab_name,
        workplace=(form.get("workplace") or "").strip() or None,
    )
    db.add(draw)
    db.flush()
    conditions = _apply_conditions(draw, form)
    db.add(conditions)
    db.commit()
    return redirect(f"/draws/{draw.id}")


@router.get("/{draw_id}", response_class=HTMLResponse)
def draw_detail(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, draw_id: int):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    markers = db.query(Marker).order_by(Marker.code).all()
    return templates.TemplateResponse(
        request,
        "draws/detail.html",
        template_context(
            request,
            locale,
            draw=draw,
            markers=markers,
            confirmed_results=_display_results(draw, locale),
            linked_attachments=attachments_for_draw(draw),
            smart_available=smart_enabled(),
        ),
    )


@router.get("/{draw_id}/edit", response_class=HTMLResponse)
def edit_draw_form(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, draw_id: int):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    drawn_at_value = draw.drawn_at.strftime("%Y-%m-%d")
    return templates.TemplateResponse(
        request,
        "draws/form.html",
        template_context(
            request,
            locale,
            draw=draw,
            c=draw.conditions,
            action=f"/draws/{draw.id}/edit",
            drawn_at_value=drawn_at_value,
        ),
    )


@router.post("/{draw_id}/edit")
async def edit_draw(request: Request, db: DbDep, user: UserDep, draw_id: int):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    form = dict(await request.form())
    draw.drawn_at = _parse_drawn_at(form["drawn_at"])
    draw.lab_name = (form.get("lab_name") or "").strip()
    draw.workplace = (form.get("workplace") or "").strip() or None
    conditions = _apply_conditions(draw, form)
    if draw.conditions is None:
        db.add(conditions)
    db.commit()
    return redirect(f"/draws/{draw.id}")


@router.post("/{draw_id}/delete")
def delete_draw(db: DbDep, user: UserDep, draw_id: int):
    draw = _get_owned_draw(db, user.id, draw_id)
    if draw:
        db.delete(draw)
        db.commit()
    return redirect("/draws")


@router.post("/{draw_id}/upload")
async def upload_files(
    request: Request,
    db: DbDep,
    user: UserDep,
    draw_id: int,
):
    """Deprecated: uploads are import-first and organize into draws automatically."""
    _ = (db, user, draw_id, request)
    return redirect("/import")


@router.post("/{draw_id}/split")
async def split_results(request: Request, db: DbDep, user: UserDep, draw_id: int):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    form = await request.form()
    selected = set(form.getlist("split_ids"))
    if not selected:
        request.session["flash"] = "Vyber výsledky k oddělení."
        return redirect(f"/draws/{draw_id}")

    new_draw = create_blood_draw(
        db,
        user.id,
        drawn_at=draw.drawn_at,
        lab_name=draw.lab_name,
        workplace=draw.workplace,
    )
    moved = 0
    for raw_id in selected:
        try:
            rid = int(raw_id)
        except (TypeError, ValueError):
            continue
        row = db.get(ResultValue, rid)
        if row and row.blood_draw_id == draw.id and row.confirmed:
            row.blood_draw_id = new_draw.id
            moved += 1
    if moved == 0:
        db.delete(new_draw)
        db.commit()
        request.session["flash"] = "Nic k oddělení."
        return redirect(f"/draws/{draw_id}")
    db.commit()
    request.session["flash"] = f"Odděleno {moved} výsledků do nového odběru."
    request.session["conditions_queue"] = [{"id": new_draw.id, "is_new": True}]
    return redirect("/import/conditions")


@router.get("/{draw_id}/ocr/{attachment_id}", response_class=HTMLResponse)
def ocr_review(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, draw_id: int, attachment_id: int):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    att = db.get(Attachment, attachment_id)
    if not att or att.blood_draw_id != draw.id:
        return redirect(f"/draws/{draw_id}")
    proposals = []
    for r in draw.results:
        if r.confirmed or r.attachment_id != att.id:
            continue
        unit_opts = unit_options_for_marker(
            r.marker.default_unit if r.marker else (r.unit or "")
        )
        if r.unit and r.unit not in unit_opts:
            unit_opts = [r.unit] + unit_opts
        proposals.append(
            {
                "label": r.label or "",
                "value": r.value,
                "unit": r.unit,
                "unit_options": unit_opts,
                "lab_ref_low": r.lab_ref_low,
                "lab_ref_high": r.lab_ref_high,
                "notes": r.notes or "",
                "id": r.id,
                "marker_code": r.marker_code or "",
                "proposed_drawn_on": r.proposed_drawn_on.strftime("%Y-%m-%d") if r.proposed_drawn_on else "",
            }
        )
    multi_date = len(unique_drawn_dates(proposals)) > 1
    catalog = db.query(Marker).order_by(Marker.name_cs).all()
    return templates.TemplateResponse(
        request,
        "draws/ocr_review.html",
        template_context(
            request,
            locale,
            draw=draw,
            attachment=att,
            proposals=proposals,
            multi_date=multi_date,
            detected_dates=unique_drawn_dates(proposals),
            unit_choices=UNIT_CHOICES,
            markers=catalog,
            default_date=draw.drawn_at.strftime("%Y-%m-%d") if draw.drawn_at else "",
        ),
    )


def _resolve_target_draw(
    db,
    user: User,
    source: BloodDraw,
    proposed: datetime | None,
) -> BloodDraw:
    """Keep on source draw if same calendar day / no proposal; else find/create draw."""
    if proposed is None:
        return source
    src_day = source.drawn_at.date() if source.drawn_at else None
    prop_day = proposed.date()
    if src_day == prop_day:
        return source
    existing = (
        db.query(BloodDraw)
        .filter(BloodDraw.user_id == user.id, BloodDraw.lab_name == source.lab_name)
        .all()
    )
    for cand in existing:
        if cand.drawn_at and cand.drawn_at.date() == prop_day:
            return cand
    new_draw = BloodDraw(
        user_id=user.id,
        drawn_at=proposed,
        lab_name=source.lab_name,
        workplace=source.workplace,
    )
    db.add(new_draw)
    db.flush()
    return new_draw


@router.post("/{draw_id}/ocr/{attachment_id}/confirm")
async def ocr_confirm(request: Request, db: DbDep, user: UserDep, draw_id: int, attachment_id: int):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    form = await request.form()
    selected = set(form.getlist("selected"))
    count = int(form.get("count") or 0)
    pending = [r for r in draw.results if not r.confirmed and r.attachment_id == attachment_id]
    catalog = db.query(Marker).all()
    kept_ids: set[int] = set()
    for idx in range(count):
        if str(idx) not in selected:
            continue
        value_raw = form.get(f"value_{idx}")
        if value_raw in (None, ""):
            continue
        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            continue
        label = (form.get(f"label_{idx}") or "").strip()
        unit = form.get(f"unit_{idx}") or ""
        low = form.get(f"low_{idx}")
        high = form.get(f"high_{idx}")
        lab_low = float(low) if low not in (None, "") else None
        lab_high = float(high) if high not in (None, "") else None
        notes = (form.get(f"notes_{idx}") or "").strip() or None
        code_raw = form.get(f"marker_code_{idx}")
        if code_raw is None:
            code_hint = None
            allow_fuzzy = True
        else:
            code_hint = (code_raw or "").strip() or None
            allow_fuzzy = bool(code_hint)
        date_raw = (form.get(f"date_{idx}") or "").strip()
        proposed = None
        if date_raw:
            d = parse_iso_date(date_raw)
            proposed = date_to_datetime(d) if d else None

        marker_code, custom_id, result_label, value, unit, lab_low, lab_high = bind_marker_and_units(
            db,
            user.id,
            label=label,
            value=value,
            unit=unit,
            lab_low=lab_low,
            lab_high=lab_high,
            catalog=catalog,
            code_hint=code_hint,
            allow_fuzzy=allow_fuzzy,
        )
        target = _resolve_target_draw(db, user, draw, proposed)

        if idx < len(pending):
            row = pending[idx]
            kept_ids.add(row.id)
        else:
            row = ResultValue(blood_draw_id=target.id, attachment_id=attachment_id)
            db.add(row)

        row.blood_draw_id = target.id
        row.marker_code = marker_code
        row.custom_marker_id = custom_id
        row.label = result_label
        row.value = value
        row.unit = unit
        row.lab_ref_low = lab_low
        row.lab_ref_high = lab_high
        row.notes = notes
        row.confirmed = True
        row.proposed_drawn_on = None

    for row in pending:
        if row.id not in kept_ids:
            db.delete(row)
    db.commit()
    return redirect(f"/draws/{draw.id}")


@router.post("/{draw_id}/results")
def add_result(
    db: DbDep,
    user: UserDep,
    draw_id: int,
    marker_code: str = Form(""),
    custom_name: str = Form(""),
    value: float = Form(...),
    unit: str = Form(""),
    lab_ref_low: str = Form(""),
    lab_ref_high: str = Form(""),
    notes: str = Form(""),
):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    code = marker_code or None
    label = None
    if code:
        marker = db.get(Marker, code)
        if not marker:
            return redirect(f"/draws/{draw_id}")
        if not unit:
            unit = marker.default_unit
        label = marker.name_cs
    elif custom_name.strip():
        label = custom_name.strip()
    else:
        return redirect(f"/draws/{draw_id}")

    bound_code, custom_id, bound_label, value, unit, lab_low, lab_high = bind_marker_and_units(
        db,
        user.id,
        label=label,
        value=value,
        unit=unit,
        lab_low=_parse_float(lab_ref_low),
        lab_high=_parse_float(lab_ref_high),
        catalog=db.query(Marker).all(),
        code_hint=code,
    )
    db.add(
        ResultValue(
            blood_draw_id=draw.id,
            marker_code=bound_code,
            custom_marker_id=custom_id,
            value=value,
            unit=unit,
            lab_ref_low=lab_low,
            lab_ref_high=lab_high,
            confirmed=True,
            label=bound_label,
            notes=notes.strip() or None,
        )
    )
    db.commit()
    return redirect(f"/draws/{draw_id}")


@router.post("/{draw_id}/results/{result_id}/notes")
def update_result_notes(
    db: DbDep,
    user: UserDep,
    draw_id: int,
    result_id: int,
    notes: str = Form(""),
):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    row = db.get(ResultValue, result_id)
    if row and row.blood_draw_id == draw.id:
        row.notes = notes.strip() or None
        db.commit()
    return redirect(f"/draws/{draw_id}")


@router.post("/{draw_id}/results/{result_id}/delete")
def delete_result(db: DbDep, user: UserDep, draw_id: int, result_id: int):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    row = db.get(ResultValue, result_id)
    if row and row.blood_draw_id == draw.id:
        db.delete(row)
        db.commit()
    return redirect(f"/draws/{draw_id}")
