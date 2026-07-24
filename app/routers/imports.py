"""Upload-first import: report → Smart/Classic extract → review → BloodDraw(s)."""

from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.deps import DbDep, LocaleDep, UserDep, redirect, template_context
from app.models import Attachment, BloodDraw, ImportJob, Marker, ResultValue
from app.services.markers import resolve_marker
from app.services.multi_date import prefer_multi_date_proposals, unique_drawn_dates
from app.services.ocr_extract import extract_document
from app.services.ocr_parse import normalize_unit
from app.services.ocr_tables import date_to_datetime, parse_iso_date
from app.services.result_bind import bind_marker_and_units
from app.services.smart_extract import run_smart_extract, smart_enabled
from app.services.storage import save_import_upload
from app.services.units import UNIT_CHOICES, unit_options_for_marker

router = APIRouter(prefix="/import", tags=["import"])
templates = Jinja2Templates(directory="app/templates")


def _proposal_dt(raw: str | None) -> str:
    if not raw:
        return ""
    d = parse_iso_date(str(raw))
    return d.isoformat() if d else ""


def _enrich_proposals(proposals: list[dict], catalog: list[Marker]) -> list[dict]:
    out: list[dict] = []
    for p in proposals:
        code = (p.get("marker_code") or "").strip() or None
        matched = resolve_marker(p.get("label") or "", catalog, code_hint=code)
        label = matched.name_cs if matched else (p.get("label") or "")
        unit = normalize_unit(p.get("unit") or "")
        if matched and not unit:
            unit = matched.default_unit
        drawn = _proposal_dt(p.get("proposed_drawn_on"))
        unit_opts = unit_options_for_marker(matched.default_unit if matched else unit)
        if unit and unit not in unit_opts:
            unit_opts = [unit] + unit_opts
        out.append(
            {
                "marker_code": matched.code if matched else "",
                "label": label,
                "value": p.get("value"),
                "unit": unit,
                "unit_options": unit_opts,
                "lab_ref_low": p.get("lab_ref_low"),
                "lab_ref_high": p.get("lab_ref_high"),
                "notes": p.get("notes") or "",
                "proposed_drawn_on": drawn,
            }
        )
    return out


def _find_or_create_draw(
    db,
    user_id: int,
    drawn_at: datetime,
    lab_name: str,
    workplace: str | None,
) -> BloodDraw:
    day = drawn_at.date()
    existing = (
        db.query(BloodDraw)
        .filter(BloodDraw.user_id == user_id, BloodDraw.lab_name == lab_name)
        .all()
    )
    for cand in existing:
        if cand.drawn_at and cand.drawn_at.date() == day:
            return cand
    draw = BloodDraw(
        user_id=user_id,
        drawn_at=drawn_at,
        lab_name=lab_name,
        workplace=workplace,
    )
    db.add(draw)
    db.flush()
    return draw


@router.get("", response_class=HTMLResponse)
def import_form(request: Request, locale: LocaleDep, user: UserDep):
    return templates.TemplateResponse(
        request,
        "import/upload.html",
        template_context(
            request,
            locale,
            smart_available=smart_enabled(),
            default_smart=smart_enabled(),
        ),
    )


@router.post("")
async def import_upload(
    request: Request,
    db: DbDep,
    user: UserDep,
    files: list[UploadFile] = File(...),
    extract_mode: str = Form("smart"),
    smart_consent: str = Form(""),
    lab_name: str = Form(""),
):
    if not files:
        return redirect("/import")
    file = files[0]
    mode = (extract_mode or "smart").lower()
    if mode == "smart":
        if not smart_enabled():
            mode = "classic"
        elif smart_consent not in {"1", "on", "true", "yes"}:
            request.session["flash"] = "Pro Smart AI je potřeba souhlas s odesláním reportu na NVIDIA."
            return redirect("/import")

    job = ImportJob(
        user_id=user.id,
        status="pending",
        extract_mode=mode,
        filename=file.filename or "upload.bin",
        content_type=file.content_type or "application/octet-stream",
        storage_path="",
    )
    db.add(job)
    db.flush()

    try:
        filename, content_type, storage_path = save_import_upload(file, user.id, job.id)
    except ValueError:
        db.delete(job)
        db.commit()
        request.session["flash"] = "Nepodporovaný typ souboru."
        return redirect("/import")

    job.filename = filename
    job.content_type = content_type
    job.storage_path = storage_path

    catalog = db.query(Marker).all()
    marker_hints = [f"{m.code}={m.name_cs}" for m in catalog]

    try:
        if mode == "smart":
            raw, proposals, _meta = run_smart_extract(storage_path, marker_hints=marker_hints)
            proposals, raw, merge_meta = prefer_multi_date_proposals(storage_path, proposals, raw)
            _meta = {**(_meta or {}), **merge_meta}
        else:
            raw, proposals, _meta = extract_document(storage_path)
        # Stable order: date then label
        proposals = sorted(
            proposals,
            key=lambda p: (str(p.get("proposed_drawn_on") or ""), str(p.get("label") or "")),
        )
        enriched = _enrich_proposals(proposals, catalog)
        detected_dates = unique_drawn_dates(enriched)
        detected_lab = ((_meta or {}).get("lab_name") or "").strip()
        default_lab = (lab_name or "").strip() or detected_lab or "Laboratoř"
        job.ocr_raw_text = raw
        job.proposals_json = json.dumps(
            {
                "lab_name": default_lab,
                "proposals": enriched,
                "detected_dates": detected_dates,
                "extract_meta": {
                    "source": (_meta or {}).get("source") or mode,
                    "dates": detected_dates,
                    "lab_name": detected_lab or None,
                },
            },
            ensure_ascii=False,
        )
        job.status = "review"
        db.add(
            Attachment(
                blood_draw_id=None,
                import_job_id=job.id,
                filename=filename,
                content_type=content_type,
                storage_path=storage_path,
                ocr_status="done",
                ocr_raw_text=raw,
            )
        )
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.ocr_raw_text = str(exc)
        db.commit()
        request.session["flash"] = f"Čtení reportu selhalo ({exc}). Zkus Classic režim."
        return redirect("/import")

    db.commit()
    return redirect(f"/import/{job.id}/review")


@router.get("/{job_id}/review", response_class=HTMLResponse)
def import_review(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, job_id: int):
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id or job.status != "review":
        return redirect("/draws")
    payload = json.loads(job.proposals_json or "{}")
    proposals = payload.get("proposals") or []
    detected_dates = payload.get("detected_dates") or unique_drawn_dates(proposals)
    multi_date = len(detected_dates) > 1
    # Group for template
    groups: list[dict] = []
    by_date: dict[str, list] = {}
    for p in proposals:
        d = p.get("proposed_drawn_on") or ""
        by_date.setdefault(d, []).append(p)
    for d in sorted(by_date.keys(), key=lambda x: x or "9999"):
        groups.append({"date": d, "rows": by_date[d]})
    return templates.TemplateResponse(
        request,
        "import/review.html",
        template_context(
            request,
            locale,
            job=job,
            proposals=proposals,
            groups=groups,
            lab_name=payload.get("lab_name") or "Laboratoř",
            unit_choices=UNIT_CHOICES,
            detected_dates=detected_dates,
            multi_date=multi_date,
        ),
    )


@router.post("/{job_id}/confirm")
async def import_confirm(request: Request, db: DbDep, user: UserDep, job_id: int):
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id or job.status != "review":
        return redirect("/draws")

    form = await request.form()
    selected = set(form.getlist("selected"))
    count = int(form.get("count") or 0)
    lab_name = (form.get("lab_name") or "").strip() or "Laboratoř"
    workplace = (form.get("workplace") or "").strip() or None
    catalog = db.query(Marker).all()

    created_draw_ids: list[int] = []

    for idx in range(count):
        if str(idx) not in selected:
            continue
        label = (form.get(f"label_{idx}") or "").strip()
        value_raw = form.get(f"value_{idx}")
        if value_raw in (None, ""):
            continue
        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            continue
        unit = form.get(f"unit_{idx}") or ""
        low_raw = form.get(f"low_{idx}")
        high_raw = form.get(f"high_{idx}")
        lab_low = float(low_raw) if low_raw not in (None, "") else None
        lab_high = float(high_raw) if high_raw not in (None, "") else None
        notes = (form.get(f"notes_{idx}") or "").strip() or None
        date_raw = (form.get(f"date_{idx}") or "").strip()
        code_hint = (form.get(f"marker_code_{idx}") or "").strip() or None

        drawn_at = datetime.combine(date.today(), datetime.min.time())
        if date_raw:
            d = parse_iso_date(date_raw)
            if d:
                drawn_at = date_to_datetime(d)

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
        )

        draw = _find_or_create_draw(db, user.id, drawn_at, lab_name, workplace)
        if draw.id not in created_draw_ids:
            created_draw_ids.append(draw.id)

        db.add(
            ResultValue(
                blood_draw_id=draw.id,
                marker_code=marker_code,
                custom_marker_id=custom_id,
                value=value,
                unit=unit,
                lab_ref_low=lab_low,
                lab_ref_high=lab_high,
                confirmed=True,
                label=result_label,
                notes=notes,
            )
        )

    for draw_id in created_draw_ids:
        db.add(
            Attachment(
                blood_draw_id=draw_id,
                import_job_id=job.id,
                filename=job.filename,
                content_type=job.content_type,
                storage_path=job.storage_path,
                ocr_status="done",
                ocr_raw_text=job.ocr_raw_text,
            )
        )

    job.status = "confirmed"
    db.commit()

    if len(created_draw_ids) == 1:
        return redirect(f"/draws/{created_draw_ids[0]}")
    if created_draw_ids:
        request.session["flash"] = f"Vytvořeno {len(created_draw_ids)} odběrů z reportu."
    return redirect("/draws")
