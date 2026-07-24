"""Upload-first import: report(s) → extract → review → BloodDraw(s) → conditions."""

from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.deps import DbDep, LocaleDep, UserDep, redirect, template_context
from app.models import Attachment, BloodDraw, ImportJob, Marker, ResultValue
from app.services.draw_organize import (
    apply_draw_conditions,
    find_draw_candidates,
    link_attachment_to_draw,
    resolve_draw_for_group,
    result_is_duplicate,
)
from app.services.label_aliases import load_user_aliases
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


def _enrich_proposals(
    proposals: list[dict],
    catalog: list[Marker],
    *,
    user_aliases: dict[str, str] | None = None,
) -> list[dict]:
    out: list[dict] = []
    for p in proposals:
        code = (p.get("marker_code") or "").strip() or None
        source_label = (p.get("label") or "").strip()
        matched = resolve_marker(
            source_label,
            catalog,
            code_hint=code,
            user_aliases=user_aliases,
        )
        label = source_label or (matched.name_cs if matched else "")
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
                "attachment_id": p.get("attachment_id"),
            }
        )
    return out


def _candidate_info(draw: BloodDraw) -> dict:
    n = sum(1 for r in draw.results if r.confirmed)
    return {
        "id": draw.id,
        "label": f"{draw.drawn_at.strftime('%Y-%m-%d')} — {draw.lab_name} ({n})",
        "result_count": n,
    }


def _build_groups(
    db,
    user_id: int,
    proposals: list[dict],
    lab_name: str,
) -> list[dict]:
    by_date: dict[str, list] = {}
    for p in proposals:
        d = p.get("proposed_drawn_on") or ""
        by_date.setdefault(d, []).append(p)
    groups: list[dict] = []
    for d in sorted(by_date.keys(), key=lambda x: x or "9999"):
        candidates: list[dict] = []
        default_choice = "new"
        if d:
            parsed = parse_iso_date(d)
            if parsed:
                cands = find_draw_candidates(db, user_id, parsed, lab_name)
                candidates = [_candidate_info(c) for c in cands]
                if len(candidates) == 1:
                    default_choice = f"existing:{candidates[0]['id']}"
                elif len(candidates) > 1:
                    default_choice = ""  # force explicit choice
        groups.append(
            {
                "date": d,
                "rows": by_date[d],
                "candidates": candidates,
                "default_choice": default_choice,
            }
        )
    return groups


def _extract_file(
    storage_path: str,
    mode: str,
    marker_hints: list[str],
) -> tuple[str, list[dict], dict]:
    if mode == "smart":
        raw, proposals, meta = run_smart_extract(storage_path, marker_hints=marker_hints)
        proposals, raw, merge_meta = prefer_multi_date_proposals(storage_path, proposals, raw)
        meta = {**(meta or {}), **merge_meta}
        return raw, proposals, meta
    return extract_document(storage_path)


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


def _job_payload(job: ImportJob) -> dict:
    try:
        return json.loads(job.proposals_json or "{}")
    except json.JSONDecodeError:
        return {}


def _save_job_payload(job: ImportJob, payload: dict) -> None:
    job.proposals_json = json.dumps(payload, ensure_ascii=False)


def _progress_dict(job: ImportJob, db, *, locale: str = "cs") -> dict:
    from app.i18n import t as i18n_t

    atts = (
        db.query(Attachment)
        .filter(Attachment.import_job_id == job.id)
        .order_by(Attachment.id)
        .all()
    )
    total = len(atts)
    done = sum(1 for a in atts if a.ocr_status in {"done", "failed", "skipped"})
    current = next((a for a in atts if a.ocr_status == "processing"), None)
    if current is None:
        current = next((a for a in atts if a.ocr_status == "pending"), None)
    filename = current.filename if current else ""
    if job.status == "review":
        message = i18n_t(locale, "import_progress_done")
    elif job.status == "failed":
        message = i18n_t(locale, "import_progress_failed")
    elif current:
        message = i18n_t(
            locale,
            "import_progress_file",
            current=str(min(done + 1, total) if total else 0),
            total=str(total),
            filename=filename,
        )
    else:
        message = i18n_t(locale, "import_progress_recognizing")
    return {
        "status": job.status,
        "done": done,
        "total": total,
        "percent": int(round(100 * done / total)) if total else 0,
        "current_file": filename,
        "message": message,
        "review_url": f"/import/{job.id}/review" if job.status == "review" else None,
        "error": job.ocr_raw_text if job.status == "failed" else None,
    }


def _finalize_job(db, job: ImportJob) -> None:
    from app.services.proposal_filter import filter_proposals

    payload = _job_payload(job)
    catalog = db.query(Marker).all()
    user_aliases = load_user_aliases(db, job.user_id)
    all_proposals = filter_proposals(list(payload.get("proposals") or []))
    all_proposals = sorted(
        all_proposals,
        key=lambda p: (str(p.get("proposed_drawn_on") or ""), str(p.get("label") or "")),
    )
    enriched = _enrich_proposals(all_proposals, catalog, user_aliases=user_aliases)
    enriched = filter_proposals(enriched)
    detected_dates = unique_drawn_dates(enriched)
    detected_lab = (payload.get("detected_lab") or "").strip()
    form_lab = (payload.get("lab_name_form") or "").strip()
    default_lab = form_lab or detected_lab or "Laboratoř"
    raw_parts = payload.get("raw_parts") or []
    job.ocr_raw_text = "\n\n".join(raw_parts) if raw_parts else job.ocr_raw_text
    atts = db.query(Attachment).filter(Attachment.import_job_id == job.id).all()
    _save_job_payload(
        job,
        {
            "lab_name": default_lab,
            "proposals": enriched,
            "detected_dates": detected_dates,
            "extract_meta": {
                "source": job.extract_mode,
                "dates": detected_dates,
                "lab_name": detected_lab or None,
                "file_count": len(atts),
            },
        },
    )
    job.status = "review"


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
    uploads = [f for f in (files or []) if f and f.filename]
    if not uploads:
        return redirect("/import")
    mode = (extract_mode or "smart").lower()
    if mode == "smart":
        if not smart_enabled():
            mode = "classic"
        elif smart_consent not in {"1", "on", "true", "yes"}:
            request.session["flash"] = "Pro Smart AI je potřeba souhlas s odesláním reportu na NVIDIA."
            return redirect("/import")

    first = uploads[0]
    job = ImportJob(
        user_id=user.id,
        status="processing",
        extract_mode=mode,
        filename=first.filename or "upload.bin",
        content_type=first.content_type or "application/octet-stream",
        storage_path="",
    )
    db.add(job)
    db.flush()

    saved_any = False
    for file in uploads:
        try:
            filename, content_type, storage_path = save_import_upload(file, user.id, job.id)
        except ValueError:
            continue
        if not saved_any:
            job.filename = filename
            job.content_type = content_type
            job.storage_path = storage_path
            saved_any = True
        db.add(
            Attachment(
                blood_draw_id=None,
                import_job_id=job.id,
                filename=filename,
                content_type=content_type,
                storage_path=storage_path,
                ocr_status="pending",
                ocr_raw_text=None,
            )
        )

    if not saved_any:
        db.delete(job)
        db.commit()
        request.session["flash"] = "Nepodporovaný typ souboru."
        return redirect("/import")

    _save_job_payload(
        job,
        {
            "lab_name_form": (lab_name or "").strip(),
            "detected_lab": "",
            "proposals": [],
            "raw_parts": [],
        },
    )
    db.commit()
    return redirect(f"/import/{job.id}/progress")


@router.get("/{job_id}/progress", response_class=HTMLResponse)
def import_progress(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, job_id: int):
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id:
        return redirect("/import")
    if job.status == "review":
        return redirect(f"/import/{job.id}/review")
    if job.status not in {"processing", "failed"}:
        return redirect("/import")
    return templates.TemplateResponse(
        request,
        "import/progress.html",
        template_context(
            request,
            locale,
            job=job,
            progress=_progress_dict(job, db, locale=locale),
        ),
    )


@router.get("/{job_id}/progress.json")
def import_progress_json(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, job_id: int):
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id:
        return JSONResponse({"status": "failed", "error": "not_found"}, status_code=404)
    return JSONResponse(_progress_dict(job, db, locale=locale))


@router.post("/{job_id}/process-step")
def import_process_step(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, job_id: int):
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id:
        return JSONResponse({"status": "failed", "error": "not_found"}, status_code=404)
    if job.status == "review":
        return JSONResponse(_progress_dict(job, db, locale=locale))
    if job.status == "failed":
        return JSONResponse(_progress_dict(job, db, locale=locale))
    if job.status != "processing":
        return JSONResponse({"status": "failed", "error": "bad_state"}, status_code=400)

    att = (
        db.query(Attachment)
        .filter(Attachment.import_job_id == job.id, Attachment.ocr_status == "pending")
        .order_by(Attachment.id)
        .with_for_update()
        .first()
    )
    if att is None:
        active = (
            db.query(Attachment)
            .filter(
                Attachment.import_job_id == job.id,
                Attachment.ocr_status.in_(("pending", "processing")),
            )
            .count()
        )
        if active == 0:
            _finalize_job(db, job)
            db.commit()
        return JSONResponse(_progress_dict(job, db, locale=locale))

    att.ocr_status = "processing"
    att_id = att.id
    storage_path = att.storage_path
    filename = att.filename
    mode = job.extract_mode
    db.commit()

    catalog = db.query(Marker).all()
    marker_hints = [f"{m.code}={m.name_cs}" for m in catalog]
    try:
        raw, proposals, meta = _extract_file(storage_path, mode, marker_hints)
    except Exception as exc:  # noqa: BLE001
        att = db.get(Attachment, att_id)
        job = db.get(ImportJob, job_id)
        if att:
            att.ocr_status = "failed"
            att.ocr_raw_text = str(exc)
        if job:
            job.status = "failed"
            job.ocr_raw_text = str(exc)
        db.commit()
        return JSONResponse(_progress_dict(job, db, locale=locale))

    # Merge under row lock so parallel workers do not clobber proposals_json
    job = (
        db.query(ImportJob)
        .filter(ImportJob.id == job_id)
        .with_for_update()
        .one()
    )
    att = (
        db.query(Attachment)
        .filter(Attachment.id == att_id)
        .with_for_update()
        .one()
    )
    if job.status == "failed":
        att.ocr_status = "done"
        att.ocr_raw_text = raw
        db.commit()
        return JSONResponse(_progress_dict(job, db, locale=locale))

    att.ocr_raw_text = raw
    att.ocr_status = "done"
    from app.services.proposal_filter import filter_proposals

    payload = _job_payload(job)
    for p in filter_proposals(proposals):
        row = dict(p)
        row["attachment_id"] = att.id
        payload.setdefault("proposals", []).append(row)
    # Dedupe across files already merged into this job
    payload["proposals"] = filter_proposals(payload.get("proposals") or [])
    payload.setdefault("raw_parts", []).append(f"--- {filename} ---\n{raw or ''}")
    lab = ((meta or {}).get("lab_name") or "").strip()
    if lab and not (payload.get("detected_lab") or "").strip():
        payload["detected_lab"] = lab
    _save_job_payload(job, payload)

    active = (
        db.query(Attachment)
        .filter(
            Attachment.import_job_id == job.id,
            Attachment.ocr_status.in_(("pending", "processing")),
            Attachment.id != att.id,
        )
        .count()
    )
    if active == 0:
        _finalize_job(db, job)
    db.commit()
    return JSONResponse(_progress_dict(job, db, locale=locale))


@router.get("/conditions", response_class=HTMLResponse)
def conditions_wizard_get(request: Request, db: DbDep, locale: LocaleDep, user: UserDep):
    queue = request.session.get("conditions_queue") or []
    if not queue:
        return redirect("/draws")
    item = queue[0]
    draw = db.get(BloodDraw, item.get("id"))
    if not draw or draw.user_id != user.id:
        request.session["conditions_queue"] = queue[1:]
        return redirect("/import/conditions")
    is_new = bool(item.get("is_new"))
    has_conditions = draw.conditions is not None
    return templates.TemplateResponse(
        request,
        "import/conditions.html",
        template_context(
            request,
            locale,
            draw=draw,
            c=draw.conditions,
            is_new=is_new,
            has_conditions=has_conditions,
            remaining=len(queue),
            drawn_at_value=draw.drawn_at.strftime("%Y-%m-%d") if draw.drawn_at else "",
        ),
    )


@router.post("/conditions")
async def conditions_wizard_post(request: Request, db: DbDep, user: UserDep):
    queue = list(request.session.get("conditions_queue") or [])
    if not queue:
        return redirect("/draws")
    form = dict(await request.form())
    action = (form.get("action") or "save").strip()
    item = queue[0]
    draw = db.get(BloodDraw, item.get("id"))
    if draw and draw.user_id == user.id and action == "save":
        conditions = apply_draw_conditions(draw, form)
        if draw.conditions is None:
            db.add(conditions)
        db.commit()
    # skip / keep unchanged / after save → next
    request.session["conditions_queue"] = queue[1:]
    if request.session["conditions_queue"]:
        return redirect("/import/conditions")
    request.session.pop("conditions_queue", None)
    return redirect("/draws")


@router.get("/{job_id}/review", response_class=HTMLResponse)
def import_review(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, job_id: int):
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id or job.status != "review":
        return redirect("/draws")
    payload = json.loads(job.proposals_json or "{}")
    proposals = payload.get("proposals") or []
    detected_dates = payload.get("detected_dates") or unique_drawn_dates(proposals)
    multi_date = len(detected_dates) > 1
    lab_name = payload.get("lab_name") or "Laboratoř"
    groups = _build_groups(db, user.id, proposals, lab_name)
    catalog = db.query(Marker).order_by(Marker.name_cs).all()
    return templates.TemplateResponse(
        request,
        "import/review.html",
        template_context(
            request,
            locale,
            job=job,
            proposals=proposals,
            groups=groups,
            lab_name=lab_name,
            unit_choices=UNIT_CHOICES,
            markers=catalog,
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

    # Per-date merge choice from form
    date_choices: dict[str, str] = {}
    for key in form.keys():
        if key.startswith("merge_"):
            date_key = key[len("merge_") :]
            date_choices[date_key] = (form.get(key) or "new").strip()

    touched: dict[int, bool] = {}  # draw_id → is_new
    added = 0
    skipped = 0
    job_attachments = (
        db.query(Attachment).filter(Attachment.import_job_id == job.id).all()
    )
    att_by_id = {a.id: a for a in job_attachments}

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
        code_raw = form.get(f"marker_code_{idx}")
        if code_raw is None:
            code_hint = None
            allow_fuzzy = True
        else:
            code_hint = (code_raw or "").strip() or None
            allow_fuzzy = bool(code_hint)

        drawn_at = datetime.combine(date.today(), datetime.min.time())
        if date_raw:
            d = parse_iso_date(date_raw)
            if d:
                drawn_at = date_to_datetime(d)

        # Multi-candidate with empty choice → force new (safe)
        choice = date_choices.get(date_raw or "", "new") or "new"
        if choice == "" or choice == "force_pick":
            choice = "new"

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

        draw, is_new = resolve_draw_for_group(
            db,
            user.id,
            drawn_at=drawn_at,
            lab_name=lab_name,
            workplace=workplace,
            choice=choice,
        )
        if draw.id not in touched:
            touched[draw.id] = is_new
        else:
            touched[draw.id] = touched[draw.id] and is_new

        if result_is_duplicate(
            db,
            draw_id=draw.id,
            marker_code=marker_code,
            custom_marker_id=custom_id,
            value=value,
            unit=unit,
        ):
            skipped += 1
            continue

        att_id_raw = form.get(f"attachment_id_{idx}")
        attachment_id = None
        try:
            if att_id_raw not in (None, ""):
                attachment_id = int(att_id_raw)
                if attachment_id not in att_by_id:
                    attachment_id = None
        except (TypeError, ValueError):
            attachment_id = None

        db.add(
            ResultValue(
                blood_draw_id=draw.id,
                attachment_id=attachment_id,
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
        added += 1

    # Link all job attachments to all touched draws (M2M)
    for draw_id in touched:
        for att in job_attachments:
            link_attachment_to_draw(db, draw_id, att.id)

    job.status = "confirmed"
    db.commit()

    if added or skipped:
        request.session["flash"] = f"Přidáno {added}, přeskočeno {skipped} duplicit."

    if touched:
        request.session["conditions_queue"] = [
            {"id": did, "is_new": bool(is_new)} for did, is_new in touched.items()
        ]
        return redirect("/import/conditions")

    return redirect("/draws")
