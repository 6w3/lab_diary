from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.deps import DbDep, LocaleDep, UserDep, redirect, template_context
from app.models import Attachment, BloodDraw, CustomMarker, DrawConditions, Marker, ResultValue, User
from app.services.markers import match_marker
from app.services.ocr_extract import extract_document
from app.services.ocr_parse import normalize_unit
from app.services.ocr_tables import date_to_datetime, parse_iso_date
from app.services.smart_extract import run_smart_extract, smart_enabled
from app.services.storage import save_upload

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
    c = draw.conditions or DrawConditions(blood_draw_id=draw.id)
    c.fasting = _parse_bool(form.get("fasting"))
    c.weight_kg = _parse_float(form.get("weight_kg"))
    c.last_hard_training = form.get("last_hard_training") or None
    c.sleep_score = _parse_int(form.get("sleep_score"))
    c.cycle_day = form.get("cycle_day") or None
    c.contraception = _parse_bool(form.get("contraception"))
    c.illness_14d = _parse_bool(form.get("illness_14d"))
    c.supplements = form.get("supplements") or None
    c.notes = form.get("notes") or None
    return c


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
    return templates.TemplateResponse(
        request,
        "draws/list.html",
        template_context(request, locale, draws=draws),
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
    files: list[UploadFile] = File(...),
    extract_mode: str = Form("classic"),
    smart_consent: str = Form(""),
):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    mode = (extract_mode or "classic").lower()
    if mode == "smart":
        if not smart_enabled():
            request.session["flash"] = "Smart AI není nakonfigurované (NVIDIA_API_KEY)."
            return redirect(f"/draws/{draw_id}")
        if smart_consent not in {"1", "on", "true", "yes"}:
            request.session["flash"] = "Pro Smart AI je potřeba souhlas s odesláním reportu na NVIDIA."
            return redirect(f"/draws/{draw_id}")

    existing = len(draw.attachments)
    settings = get_settings()
    catalog = db.query(Marker).all()
    marker_hints = [m.name_cs for m in catalog] + [m.code for m in catalog]
    last_att_id = None

    def _proposal_dt(p: dict) -> datetime | None:
        raw = p.get("proposed_drawn_on")
        if not raw:
            return None
        d = parse_iso_date(str(raw))
        return date_to_datetime(d) if d else None

    for file in files:
        if existing >= settings.max_attachments_per_draw:
            break
        try:
            filename, content_type, storage_path = save_upload(file, user.id, draw.id)
        except ValueError:
            continue
        att = Attachment(
            blood_draw_id=draw.id,
            filename=filename,
            content_type=content_type,
            storage_path=storage_path,
            ocr_status="pending",
        )
        db.add(att)
        db.flush()
        last_att_id = att.id
        try:
            if mode == "smart":
                raw, proposals, _meta = run_smart_extract(storage_path, marker_hints=marker_hints)
            else:
                raw, proposals, _meta = extract_document(storage_path)
            att.ocr_raw_text = raw
            att.ocr_status = "done"
            for p in proposals:
                matched = match_marker(p.get("label") or "", catalog)
                label = matched.name_cs if matched else p.get("label")
                unit = normalize_unit(p.get("unit") or "")
                if matched and not unit:
                    unit = matched.default_unit
                db.add(
                    ResultValue(
                        blood_draw_id=draw.id,
                        attachment_id=att.id,
                        marker_code=matched.code if matched else None,
                        value=p["value"],
                        unit=unit,
                        lab_ref_low=p.get("lab_ref_low"),
                        lab_ref_high=p.get("lab_ref_high"),
                        confirmed=False,
                        label=label,
                        proposed_drawn_on=_proposal_dt(p),
                    )
                )
        except Exception as exc:  # noqa: BLE001
            att.ocr_status = "failed"
            att.ocr_raw_text = str(exc)
            if mode == "smart":
                request.session["flash"] = f"Smart AI selhalo ({exc}). Zkus Classic režim."
        existing += 1
    db.commit()
    if last_att_id:
        pending = (
            db.query(ResultValue)
            .filter(
                ResultValue.blood_draw_id == draw.id,
                ResultValue.attachment_id == last_att_id,
                ResultValue.confirmed.is_(False),
            )
            .count()
        )
        if pending:
            return redirect(f"/draws/{draw.id}/ocr/{last_att_id}")
    return redirect(f"/draws/{draw.id}")


@router.get("/{draw_id}/ocr/{attachment_id}", response_class=HTMLResponse)
def ocr_review(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, draw_id: int, attachment_id: int):
    draw = _get_owned_draw(db, user.id, draw_id)
    if not draw:
        return redirect("/draws")
    att = db.get(Attachment, attachment_id)
    if not att or att.blood_draw_id != draw.id:
        return redirect(f"/draws/{draw_id}")
    proposals = [
        {
            "label": r.label or "",
            "value": r.value,
            "unit": r.unit,
            "lab_ref_low": r.lab_ref_low,
            "lab_ref_high": r.lab_ref_high,
            "notes": r.notes or "",
            "id": r.id,
            "marker_code": r.marker_code,
            "proposed_drawn_on": r.proposed_drawn_on.strftime("%Y-%m-%d") if r.proposed_drawn_on else "",
        }
        for r in draw.results
        if not r.confirmed and r.attachment_id == att.id
    ]
    multi_date = any(p["proposed_drawn_on"] for p in proposals)
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
    for idx in range(count):
        if str(idx) not in selected or idx >= len(pending):
            continue
        row = pending[idx]
        row.label = form.get(f"label_{idx}") or row.label
        row.value = float(form.get(f"value_{idx}"))
        row.unit = normalize_unit(form.get(f"unit_{idx}") or "")
        low = form.get(f"low_{idx}")
        high = form.get(f"high_{idx}")
        row.lab_ref_low = float(low) if low else None
        row.lab_ref_high = float(high) if high else None
        note = (form.get(f"notes_{idx}") or "").strip()
        row.notes = note or None
        date_raw = (form.get(f"date_{idx}") or "").strip()
        if date_raw:
            d = parse_iso_date(date_raw)
            row.proposed_drawn_on = date_to_datetime(d) if d else row.proposed_drawn_on
        matched = match_marker(row.label or "", catalog)
        if matched:
            row.marker_code = matched.code
            row.custom_marker_id = None
            if not row.unit:
                row.unit = matched.default_unit
            row.label = matched.name_cs
        elif row.label:
            row.marker_code = None
            existing = (
                db.query(CustomMarker)
                .filter(CustomMarker.user_id == user.id, CustomMarker.name == row.label)
                .first()
            )
            if not existing:
                existing = CustomMarker(user_id=user.id, name=row.label, unit=row.unit or "")
                db.add(existing)
                db.flush()
            row.custom_marker_id = existing.id
        target = _resolve_target_draw(db, user, draw, row.proposed_drawn_on)
        row.blood_draw_id = target.id
        row.confirmed = True
        row.proposed_drawn_on = None
    for idx, row in enumerate(pending):
        if str(idx) not in selected:
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
    custom_id = None
    code = marker_code or None
    label = None
    if code:
        marker = db.get(Marker, code)
        if marker and not unit:
            unit = marker.default_unit
    elif custom_name.strip():
        label = custom_name.strip()
        existing = (
            db.query(CustomMarker)
            .filter(CustomMarker.user_id == user.id, CustomMarker.name == label)
            .first()
        )
        if not existing:
            existing = CustomMarker(user_id=user.id, name=label, unit=unit or "")
            db.add(existing)
            db.flush()
        custom_id = existing.id
    else:
        return redirect(f"/draws/{draw_id}")

    note = notes.strip() or None
    db.add(
        ResultValue(
            blood_draw_id=draw.id,
            marker_code=code,
            custom_marker_id=custom_id,
            value=value,
            unit=unit,
            lab_ref_low=_parse_float(lab_ref_low),
            lab_ref_high=_parse_float(lab_ref_high),
            confirmed=True,
            label=label,
            notes=note,
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
