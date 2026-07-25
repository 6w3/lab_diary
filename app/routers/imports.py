"""Upload-first import: report(s) → extract → review → BloodDraw(s) → conditions."""

from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.deps import DbDep, LocaleDep, UserDep, read_form, redirect, template_context
from app.models import Attachment, BloodDraw, ImportJob, Marker, ResultValue
from app.services.draw_organize import (
    apply_draw_conditions,
    find_draw_candidates,
    link_attachment_to_draw,
    resolve_draw_cached,
    result_is_duplicate,
)
from app.services.import_process import (
    attachment_display_name,
    claim_attachment_for_job,
    ensure_proposal_uids,
    job_has_active_attachments,
    job_payload,
    maybe_finalize_idle_jobs,
    prepare_review_proposals,
    process_claimed_attachment,
    queue_attachment_reextract,
    retry_failed_attachments,
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
    default_lab: str,
) -> list[dict]:
    """Group by draw date + lab so multi-file imports keep distinct labs/workplaces."""
    buckets: dict[tuple[str, str], list] = {}
    order: list[tuple[str, str]] = []
    for p in proposals:
        d = p.get("proposed_drawn_on") or ""
        lab = (p.get("proposed_lab_name") or "").strip() or (default_lab or "").strip() or "Laboratoř"
        key = (d, lab.casefold())
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(p)

    groups: list[dict] = []
    for i, key in enumerate(sorted(order, key=lambda k: (k[0] or "9999", k[1]))):
        rows = buckets[key]
        date_s, _lab_fold = key
        lab_name = next(
            ((r.get("proposed_lab_name") or "").strip() for r in rows if (r.get("proposed_lab_name") or "").strip()),
            default_lab or "Laboratoř",
        )
        workplace = next(
            ((r.get("proposed_workplace") or "").strip() for r in rows if (r.get("proposed_workplace") or "").strip()),
            "",
        )
        candidates: list[dict] = []
        default_choice = "new"
        if date_s:
            parsed = parse_iso_date(date_s)
            if parsed:
                cands = find_draw_candidates(db, user_id, parsed, lab_name)
                candidates = [_candidate_info(c) for c in cands]
                if len(candidates) == 1:
                    default_choice = f"existing:{candidates[0]['id']}"
                elif len(candidates) > 1:
                    default_choice = ""
        groups.append(
            {
                "idx": i,
                "date": date_s,
                "lab_name": lab_name,
                "workplace": workplace,
                "rows": rows,
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


def _progress_file_entry(att: Attachment, atts: list[Attachment], total: int) -> dict:
    pos = next((i + 1 for i, x in enumerate(atts) if x.id == att.id), None)
    return {
        "attachment_id": att.id,
        "filename": attachment_display_name(att, index=pos, total=total),
        "original_filename": (att.original_filename or "").strip() or None,
        "stored_filename": att.filename,
        "index": pos,
        "total": total,
        "status": att.ocr_status,
    }


def _progress_dict(job: ImportJob, db, *, locale: str = "cs") -> dict:
    from app.i18n import t as i18n_t

    atts = (
        db.query(Attachment)
        .filter(Attachment.import_job_id == job.id)
        .order_by(Attachment.id)
        .all()
    )
    total = len(atts)
    done_atts = [a for a in atts if a.ocr_status == "done"]
    failed_atts = [a for a in atts if a.ocr_status == "failed"]
    processing_atts = [a for a in atts if a.ocr_status == "processing"]
    pending_atts = [a for a in atts if a.ocr_status == "pending"]
    done_ok = len(done_atts)
    done = sum(1 for a in atts if a.ocr_status in {"done", "failed", "skipped"})
    running = len(processing_atts)
    queued = len(pending_atts)
    unfinished = running + queued

    file_done = [_progress_file_entry(a, atts, total) for a in done_atts]
    file_running = [_progress_file_entry(a, atts, total) for a in processing_atts]
    file_queued = [_progress_file_entry(a, atts, total) for a in pending_atts]

    current = processing_atts[0] if processing_atts else (pending_atts[0] if pending_atts else None)
    filename = (
        attachment_display_name(
            current,
            index=next((i + 1 for i, a in enumerate(atts) if a.id == current.id), None),
            total=total,
        )
        if current
        else ""
    )

    payload = {}
    try:
        payload = json.loads(job.proposals_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    file_errors = list(payload.get("file_errors") or [])
    # Prefer live labels from attachments (original upload names + batch position).
    # Never keep stale payload errors once nothing is failed anymore.
    if failed_atts:
        by_id = {e.get("attachment_id"): e for e in file_errors if e.get("attachment_id")}
        rebuilt = []
        for a in failed_atts:
            entry = _progress_file_entry(a, atts, total)
            prev = by_id.get(a.id) or {}
            rebuilt.append(
                {
                    **prev,
                    **entry,
                    "error": prev.get("error") or (a.ocr_raw_text or "failed")[:500],
                }
            )
        file_errors = rebuilt
    else:
        file_errors = []

    if job.status == "review":
        message = i18n_t(locale, "import_progress_done")
    elif job.status == "failed":
        message = i18n_t(locale, "import_progress_failed")
    elif failed_atts and unfinished:
        if queued:
            message = i18n_t(
                locale,
                "import_progress_partial_queued",
                done=str(done_ok),
                failed=str(len(failed_atts)),
                running=str(running),
                queued=str(queued),
            )
        else:
            message = i18n_t(
                locale,
                "import_progress_partial",
                done=str(done_ok),
                failed=str(len(failed_atts)),
                running=str(running),
            )
    elif total > 1 and unfinished:
        # Names live in the file lists below — status keeps a short count.
        message = i18n_t(
            locale,
            "import_progress_batch",
            n=str(total),
            done=str(done),
            total=str(total),
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

    proposal_count = len(payload.get("proposals") or [])
    # Mid-flight review: confirm already-extracted rows while other files still run.
    review_ready = proposal_count > 0 and job.status in {"processing", "review"}
    review_url = f"/import/{job.id}/review" if review_ready else None

    return {
        "status": job.status,
        "done": done,
        "done_ok": done_ok,
        "failed": len(failed_atts),
        "running": running,
        "queued": queued,
        "total": total,
        "percent": int(round(100 * done / total)) if total else 0,
        "current_file": filename,
        "message": message,
        "proposal_count": proposal_count,
        "review_ready": review_ready,
        "review_url": review_url,
        "error": error,
        "file_done": file_done,
        "file_running": file_running,
        "file_queued": file_queued,
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
            filename, content_type, storage_path, original_filename = save_import_upload(
                file, user.id, job.id
            )
        except ValueError:
            continue
        if not saved_any:
            job.filename = original_filename
            job.content_type = content_type
            job.storage_path = storage_path
            saved_any = True
        db.add(
            Attachment(
                blood_draw_id=None,
                import_job_id=job.id,
                filename=filename,
                original_filename=original_filename,
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
    form = dict(await read_form(request))
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
    cont = (request.session.pop("import_continue_url", None) or "").strip()
    if cont.startswith("/import/"):
        return redirect(cont)
    return redirect("/draws")


@router.get("/{job_id}/review", response_class=HTMLResponse)
def import_review(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, job_id: int):
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id or job.status not in {"review", "processing"}:
        return redirect("/draws")
    raw_payload = job_payload(job)
    if job.status == "processing" and not (raw_payload.get("proposals") or []):
        return redirect(f"/import/{job.id}/progress")

    def _safe_save(payload_to_save: dict) -> None:
        try:
            # Drop legacy bloated OCR copies if present.
            payload_to_save.pop("raw_parts", None)
            save_job_payload(job, payload_to_save)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()

    # Ensure stable uids exist before rendering (confirm drops by uid).
    # Mid-flight: do not rewrite enriched/sorted proposals — worker may still append.
    if job.status == "processing":
        if ensure_proposal_uids(raw_payload):
            _safe_save(raw_payload)
        proposals, payload = prepare_review_proposals(db, job, raw_payload)
    else:
        proposals, payload = prepare_review_proposals(db, job, raw_payload)
        _safe_save({**raw_payload, **payload, "proposals": proposals})
    # Live failed attachments only — never show a stale empty/ stale payload error box.
    job_atts = (
        db.query(Attachment)
        .filter(Attachment.import_job_id == job.id)
        .order_by(Attachment.id)
        .all()
    )
    att_by_id = {a.id: a for a in job_atts}
    failed = [a for a in job_atts if a.ocr_status == "failed"]
    by_err = {
        e.get("attachment_id"): e
        for e in (payload.get("file_errors") or [])
        if e.get("attachment_id")
    }
    file_errors: list[dict] = []
    for a in failed:
        pos = next((i + 1 for i, x in enumerate(job_atts) if x.id == a.id), None)
        prev = by_err.get(a.id) or {}
        err = (prev.get("error") or (a.ocr_raw_text or "") or "").strip()
        name = attachment_display_name(a, index=pos, total=len(job_atts))
        if not name and not err:
            continue
        file_errors.append(
            {
                **prev,
                "attachment_id": a.id,
                "filename": name,
                "original_filename": (a.original_filename or "").strip() or None,
                "error": err or "failed",
            }
        )
    if payload.get("file_errors") != file_errors:
        payload["file_errors"] = file_errors
        _safe_save({**raw_payload, **payload, "proposals": proposals})
    # Backfill lab/workplace from attachment raw when labs_by_attachment gaps remain.
    labs_by_att = payload.get("labs_by_attachment") or {}
    needs_lab = any(not (p.get("proposed_lab_name") or "").strip() for p in proposals)
    if proposals and needs_lab:
        for p in proposals:
            att_id = p.get("attachment_id")
            info = labs_by_att.get(str(att_id or "")) or {}
            if not (p.get("proposed_lab_name") or "").strip():
                lab = (info.get("lab_name") or "").strip()
                if not lab and att_id in att_by_id:
                    lab = _lab_from_attachment_raw(att_by_id[att_id])
                if lab:
                    p["proposed_lab_name"] = lab
            if not (p.get("proposed_workplace") or "").strip():
                wp = (info.get("workplace") or "").strip()
                if not wp and att_id in att_by_id:
                    wp = _workplace_from_attachment_raw(att_by_id[att_id])
                if wp:
                    p["proposed_workplace"] = wp
    detected_dates = payload.get("detected_dates") or unique_drawn_dates(proposals)
    multi_date = len(detected_dates) > 1
    lab_name = payload.get("lab_name") or "Laboratoř"
    groups = _build_groups(db, user.id, proposals, lab_name)
    catalog = db.query(Marker).order_by(Marker.name_cs).all()
    still_running = job.status == "processing" and job_has_active_attachments(db, job.id)
    status_labels = {
        "done": t(locale, "import_att_status_done"),
        "failed": t(locale, "import_att_status_failed"),
        "pending": t(locale, "import_att_status_pending"),
        "processing": t(locale, "import_att_status_processing"),
    }
    reextract_atts = []
    for i, a in enumerate(job_atts):
        if a.ocr_status not in {"done", "failed"}:
            continue
        reextract_atts.append(
            SimpleNamespace(
                id=a.id,
                display_name=attachment_display_name(a, index=i + 1, total=len(job_atts)),
                status=a.ocr_status,
                status_label=status_labels.get(a.ocr_status, a.ocr_status),
            )
        )
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
            still_running=still_running,
            progress_url=f"/import/{job.id}/progress",
            reextract_atts=reextract_atts,
            smart_available=smart_enabled(),
        ),
    )


def _lab_from_attachment_raw(att: Attachment) -> str:
    raw = (att.ocr_raw_text or "").strip()
    if not raw.startswith("{"):
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    for d in data.get("draws") or []:
        lab = (d.get("lab_name") or "").strip()
        if lab:
            return lab[:120]
    return ""


def _workplace_from_attachment_raw(att: Attachment) -> str:
    raw = (att.ocr_raw_text or "").strip()
    if not raw.startswith("{"):
        return ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    for d in data.get("draws") or []:
        wp = (d.get("workplace") or "").strip()
        if wp:
            return wp[:120]
    return ""


@router.post("/{job_id}/retry-files")
async def import_retry_files(request: Request, db: DbDep, user: UserDep, job_id: int):
    """Re-queue one or more failed attachments; keep successful proposals.

    Works while job is already processing so remaining failed files can be
    queued one-by-one from the progress page without waiting.
    """
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id or job.status not in {"review", "failed", "processing"}:
        return redirect("/draws")

    form = await read_form(request)
    raw_ids = form.getlist("attachment_id")
    ids: list[int] = []
    for raw in raw_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    # Empty list + retry_all → all failed; single button sends one id.
    retry_all = (form.get("retry_all") or "").strip() in {"1", "true", "on"}
    n = retry_failed_attachments(
        db,
        job,
        attachment_ids=None if retry_all or not ids else ids,
    )
    if n:
        kick_import_worker()
        return redirect(f"/import/{job.id}/progress")
    if job.status == "review":
        return redirect(f"/import/{job.id}/review")
    if job.status == "processing":
        return redirect(f"/import/{job.id}/progress")
    return redirect("/draws")


@router.post("/{job_id}/reextract")
async def import_reextract(request: Request, db: DbDep, user: UserDep, job_id: int):
    """Re-read one attachment with optional Smart user hint; replace its proposals."""
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id or job.status not in {"review", "failed", "processing"}:
        return redirect("/draws")

    form = await read_form(request)
    try:
        att_id = int(form.get("attachment_id") or 0)
    except (TypeError, ValueError):
        att_id = 0
    hint = (form.get("user_hint") or "").strip()
    if not att_id:
        return redirect(f"/import/{job.id}/review")
    ok = queue_attachment_reextract(db, job, attachment_id=att_id, user_hint=hint)
    if ok:
        kick_import_worker()
        return redirect(f"/import/{job.id}/progress")
    return redirect(f"/import/{job.id}/review")


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
    if not job or job.user_id != user.id or job.status not in {"review", "processing"}:
        return redirect("/draws")

    form = await read_form(request)
    selected = set(form.getlist("selected"))
    count = int(form.get("count") or 0)
    catalog = db.query(Marker).all()

    raw_payload = job_payload(job)
    _, prepared = prepare_review_proposals(db, job, raw_payload)

    # Per-group merge choice + lab/workplace (multi-file imports differ by draw)
    group_choices: dict[str, str] = {}
    group_labs: dict[str, tuple[str, str | None]] = {}
    for key in form.keys():
        if key.startswith("merge_"):
            gidx = key[len("merge_") :]
            group_choices[gidx] = (form.get(key) or "new").strip()
        elif key.startswith("lab_name_"):
            gidx = key[len("lab_name_") :]
            lab = (form.get(key) or "").strip() or "Laboratoř"
            wp = (form.get(f"workplace_{gidx}") or "").strip() or None
            group_labs[gidx] = (lab, wp)

    touched: dict[int, bool] = {}  # draw_id → is_new
    draw_cache: dict = {}  # one draw per group+merge choice within this confirm
    used_att_ids: set[int] = set()
    consumed_uids: set[str] = set()
    added = 0
    skipped = 0
    job_attachments = (
        db.query(Attachment).filter(Attachment.import_job_id == job.id).all()
    )
    att_by_id = {a.id: a for a in job_attachments}

    for idx in range(count):
        if str(idx) not in selected:
            continue
        uid = (form.get(f"uid_{idx}") or "").strip()
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
        gidx = (form.get(f"group_idx_{idx}") or "0").strip() or "0"
        lab_name, workplace = group_labs.get(gidx, ("Laboratoř", None))
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
        choice = group_choices.get(gidx, "new") or "new"
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
            group_key=f"{gidx}|{date_raw or drawn_at.strftime('%Y-%m-%d')}|{lab_name.casefold()}",
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
            if uid:
                consumed_uids.add(uid)
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
        if attachment_id is not None:
            used_att_ids.add(attachment_id)
        if uid:
            consumed_uids.add(uid)

    # Link only attachments that contributed confirmed rows (progressive confirm safe).
    for draw_id in touched:
        for att_id in used_att_ids:
            link_attachment_to_draw(db, draw_id, att_id)

    # Re-read payload: worker may have appended while user confirmed.
    db.refresh(job)
    fresh = job_payload(job)
    remaining = [
        p
        for p in (fresh.get("proposals") or [])
        if (p.get("uid") or "").strip() not in consumed_uids
    ]

    still_active = job_has_active_attachments(db, job.id)
    failed_left = any(a.ocr_status == "failed" for a in job_attachments)

    next_payload = {
        **fresh,
        "proposals": remaining,
        "detected_dates": unique_drawn_dates(remaining),
        "lab_name": prepared.get("lab_name") or fresh.get("lab_name") or "Laboratoř",
    }
    save_job_payload(job, next_payload)

    if still_active:
        job.status = "processing"
        continue_url = f"/import/{job.id}/progress"
    elif remaining or failed_left:
        job.status = "review"
        continue_url = f"/import/{job.id}/review"
    else:
        job.status = "confirmed"
        continue_url = "/draws"

    db.commit()

    if added or skipped:
        request.session["flash"] = f"Přidáno {added}, přeskočeno {skipped} duplicit."

    if touched:
        request.session["conditions_queue"] = [
            {"id": did, "is_new": bool(is_new)} for did, is_new in touched.items()
        ]
        if continue_url != "/draws":
            request.session["import_continue_url"] = continue_url
        else:
            request.session.pop("import_continue_url", None)
        return redirect("/import/conditions")

    if continue_url != "/draws":
        return redirect(continue_url)
    return redirect("/draws")
