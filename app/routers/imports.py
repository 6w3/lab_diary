"""Upload-first import: report(s) → extract → review → BloodDraw(s) → conditions."""

from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.deps import DbDep, LocaleDep, UserDep, redirect, template_context
from app.models import Attachment, BloodDraw, ImportJob, Marker, ResultValue
from app.services.draw_organize import (
    apply_draw_conditions,
    find_draw_candidates,
    link_attachment_to_draw,
    resolve_draw_cached,
    result_is_duplicate,
)
from app.services.import_process import (
    claim_attachment_for_job,
    maybe_finalize_idle_jobs,
    process_claimed_attachment,
    save_job_payload,
)
from app.services.import_worker import kick_import_worker
from app.services.multi_date import unique_drawn_dates
from app.services.ocr_tables import date_to_datetime, parse_iso_date
from app.services.result_bind import bind_marker_and_units
from app.services.smart_extract import smart_enabled
from app.i18n import t
from app.services.storage import delete_file, save_import_upload
from app.services.units import UNIT_CHOICES, marker_unit_options_map

router = APIRouter(prefix="/import", tags=["import"])
templates = Jinja2Templates(directory="app/templates")


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
            max_import_files=get_settings().max_import_files,
        ),
    )


def _progress_dict(job: ImportJob, db, *, locale: str = "cs") -> dict:
    from app.i18n import t as i18n_t

    atts = (
        db.query(Attachment)
        .filter(Attachment.import_job_id == job.id)
        .order_by(Attachment.id)
        .all()
    )
    total = len(atts)
    failed_atts = [a for a in atts if a.ocr_status == "failed"]
    done_ok = sum(1 for a in atts if a.ocr_status == "done")
    done = sum(1 for a in atts if a.ocr_status in {"done", "failed", "skipped"})
    running = sum(1 for a in atts if a.ocr_status in {"pending", "processing"})
    current = next((a for a in atts if a.ocr_status == "processing"), None)
    if current is None:
        current = next((a for a in atts if a.ocr_status == "pending"), None)
    filename = current.filename if current else ""

    payload = {}
    try:
        payload = json.loads(job.proposals_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    file_errors = list(payload.get("file_errors") or [])
    if not file_errors and failed_atts:
        file_errors = [
            {
                "attachment_id": a.id,
                "filename": a.filename,
                "error": (a.ocr_raw_text or "failed")[:500],
            }
            for a in failed_atts
        ]

    if job.status == "review":
        message = i18n_t(locale, "import_progress_done")
    elif job.status == "failed":
        message = i18n_t(locale, "import_progress_failed")
    elif failed_atts and running:
        message = i18n_t(
            locale,
            "import_progress_partial",
            done=str(done_ok),
            failed=str(len(failed_atts)),
            running=str(running),
        )
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

    error = None
    if job.status == "failed":
        error = job.ocr_raw_text or message
    elif file_errors and job.status == "review":
        error = None

    return {
        "status": job.status,
        "done": done,
        "done_ok": done_ok,
        "failed": len(failed_atts),
        "total": total,
        "percent": int(round(100 * done / total)) if total else 0,
        "current_file": filename,
        "message": message,
        "review_url": f"/import/{job.id}/review" if job.status == "review" else None,
        "error": error,
        "file_errors": file_errors,
        "server_queue": True,
    }


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
    max_files = get_settings().max_import_files
    if len(uploads) > max_files:
        request.session["flash"] = f"Max. {max_files} souborů najednou (vybráno {len(uploads)})."
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

    save_job_payload(
        job,
        {
            "lab_name_form": (lab_name or "").strip(),
            "detected_lab": "",
            "proposals": [],
            "raw_parts": [],
        },
    )
    db.commit()
    kick_import_worker()
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
    # Ensure worker is awake if user reopened progress page
    kick_import_worker()
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
    if job.status == "processing":
        kick_import_worker()
    return JSONResponse(_progress_dict(job, db, locale=locale))


@router.post("/{job_id}/process-step")
def import_process_step(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, job_id: int):
    """Legacy/manual step: claim+process one file for this job (worker is primary path)."""
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id:
        return JSONResponse({"status": "failed", "error": "not_found"}, status_code=404)
    if job.status in {"review", "failed"}:
        return JSONResponse(_progress_dict(job, db, locale=locale))
    if job.status != "processing":
        return JSONResponse({"status": "failed", "error": "bad_state"}, status_code=400)

    kick_import_worker()
    claimed = claim_attachment_for_job(db, job_id)
    if claimed is None:
        maybe_finalize_idle_jobs(db)
        job = db.get(ImportJob, job_id)
        return JSONResponse(_progress_dict(job, db, locale=locale))

    att_id, claimed_job_id, storage_path, filename, mode = claimed
    process_claimed_attachment(
        db,
        att_id=att_id,
        job_id=claimed_job_id,
        storage_path=storage_path,
        filename=filename,
        mode=mode,
    )
    job = db.get(ImportJob, job_id)
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
    file_errors = payload.get("file_errors") or []
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
            file_errors=file_errors,
            groups=groups,
            lab_name=lab_name,
            unit_choices=UNIT_CHOICES,
            unit_choices_json=json.dumps(UNIT_CHOICES, ensure_ascii=False),
            marker_units_json=json.dumps(marker_unit_options_map(), ensure_ascii=False),
            markers=catalog,
            detected_dates=detected_dates,
            multi_date=multi_date,
        ),
    )


@router.post("/{job_id}/discard")
def import_discard(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, job_id: int):
    """Drop import job + uploaded files without creating draws."""
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id or job.status not in {"review", "failed"}:
        return redirect("/draws")

    atts = db.query(Attachment).filter(Attachment.import_job_id == job.id).all()
    paths = {a.storage_path for a in atts if a.storage_path}
    if job.storage_path:
        paths.add(job.storage_path)
    for path in paths:
        delete_file(path)
    for att in atts:
        db.delete(att)
    db.delete(job)
    db.commit()
    request.session["flash"] = t(locale, "document_discarded")
    return redirect("/draws")


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
    draw_cache: dict = {}  # one draw per date+merge choice within this confirm
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

        draw, is_new = resolve_draw_cached(
            draw_cache,
            db,
            user.id,
            drawn_at=drawn_at,
            lab_name=lab_name,
            workplace=workplace,
            choice=choice,
            group_key=date_raw or drawn_at.strftime("%Y-%m-%d"),
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
