"""Process one import attachment (extract + merge into job). Shared by HTTP + worker."""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from sqlalchemy.orm import Session

from app.models import Attachment, ImportJob, Marker
from app.services.label_aliases import load_user_aliases
from app.services.multi_date import prefer_multi_date_proposals, unique_drawn_dates
from app.services.ocr_extract import extract_document
from app.services.ocr_parse import normalize_unit
from app.services.ocr_tables import parse_iso_date
from app.services.smart_extract import run_smart_extract
from app.services.units import unit_options_for_marker

logger = logging.getLogger(__name__)


def job_payload(job: ImportJob) -> dict:
    try:
        return json.loads(job.proposals_json or "{}")
    except json.JSONDecodeError:
        return {}


def save_job_payload(job: ImportJob, payload: dict) -> None:
    job.proposals_json = json.dumps(payload, ensure_ascii=False)


def extract_file(
    storage_path: str,
    mode: str,
    marker_hints: list[str],
) -> tuple[str, list[dict], dict]:
    if mode == "smart":
        try:
            raw, proposals, meta = run_smart_extract(storage_path, marker_hints=marker_hints)
            proposals, raw, merge_meta = prefer_multi_date_proposals(storage_path, proposals, raw)
            meta = {**(meta or {}), **merge_meta}
            return raw, proposals, meta
        except Exception as exc:  # noqa: BLE001
            logger.exception("Smart extract failed; falling back to classic: %s", exc)
            raw, proposals, meta = extract_document(storage_path)
            meta = {**(meta or {}), "engine": meta.get("engine") or "classic", "smart_error": str(exc)[:300]}
            return raw, proposals, meta
    return extract_document(storage_path)


def _proposal_dt(raw: str | None) -> str:
    if not raw:
        return ""
    d = parse_iso_date(str(raw))
    return d.isoformat() if d else ""


def enrich_proposals(
    proposals: list[dict],
    catalog: list[Marker],
    *,
    user_aliases: dict[str, str] | None = None,
    allow_fuzzy: bool = True,
) -> list[dict]:
    from app.services.markers import (
        extract_lis_code_hint,
        match_marker,
        match_marker_alias,
        resolve_marker,
    )

    out: list[dict] = []
    for p in proposals:
        code = (p.get("marker_code") or "").strip() or None
        source_label = (p.get("label") or "").strip()
        # Strong OCR alias beats a stale/wrong persisted code_hint (e.g. pH→eosinophils).
        strong = match_marker_alias(source_label, catalog) if source_label else None
        if strong:
            matched = strong
        else:
            fuzzy = match_marker(source_label, catalog) if (allow_fuzzy and source_label) else None
            lis = extract_lis_code_hint(source_label) if source_label else None
            # Junk/unknown labels: do not keep stale marker_code (e.g. note→potassium).
            # Trust code_hint only when label itself maps somewhere or has LIS tag.
            hint = code if (fuzzy or lis or not source_label) else None
            matched = resolve_marker(
                source_label,
                catalog,
                code_hint=hint,
                user_aliases=user_aliases,
                allow_fuzzy=allow_fuzzy,
            )
        label = source_label or (matched.name_cs if matched else "")
        unit = normalize_unit(p.get("unit") or "")
        if matched and not unit:
            unit = matched.default_unit
        drawn = _proposal_dt(p.get("proposed_drawn_on"))
        unit_opts = unit_options_for_marker(
            matched.code if matched else None,
            default_unit=matched.default_unit if matched else None,
            detected=unit or None,
        )
        out.append(
            {
                "uid": (str(p.get("uid") or "").strip() or None),
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
                "proposed_lab_name": (str(p.get("proposed_lab_name") or "").strip() or None),
                "proposed_workplace": (str(p.get("proposed_workplace") or "").strip() or None),
            }
        )
    return out


def ensure_proposal_uids(payload: dict) -> bool:
    """Backfill missing proposal uids in-place. Returns True if anything changed."""
    changed = False
    for p in payload.get("proposals") or []:
        if not (p.get("uid") or "").strip():
            p["uid"] = secrets.token_hex(8)
            changed = True
    return changed


def prepare_review_proposals(db: Session, job: ImportJob, payload: dict | None = None) -> tuple[list[dict], dict]:
    """Enrich proposals for review UI — works mid-flight (status=processing) too.

    Returns (enriched_proposals, payload_with_defaults). Does not change job.status.
    """
    from app.services.proposal_filter import filter_proposals

    payload = dict(payload if payload is not None else job_payload(job))
    catalog = db.query(Marker).all()
    user_aliases = load_user_aliases(db, job.user_id)
    all_proposals = filter_proposals(list(payload.get("proposals") or []))
    detected_lab = (payload.get("detected_lab") or "").strip()
    form_lab = (payload.get("lab_name_form") or "").strip()
    default_lab = (payload.get("lab_name") or "").strip() or form_lab or detected_lab or "Laboratoř"
    labs_by_att = payload.get("labs_by_attachment") or {}
    for p in all_proposals:
        if not (p.get("proposed_lab_name") or "").strip():
            info = labs_by_att.get(str(p.get("attachment_id") or "")) or {}
            p["proposed_lab_name"] = (info.get("lab_name") or default_lab or "").strip() or None
        if not (p.get("proposed_workplace") or "").strip():
            info = labs_by_att.get(str(p.get("attachment_id") or "")) or {}
            wp = (info.get("workplace") or "").strip()
            if wp:
                p["proposed_workplace"] = wp
    all_proposals = sorted(
        all_proposals,
        key=lambda p: (
            str(p.get("proposed_drawn_on") or ""),
            str(p.get("proposed_lab_name") or ""),
            str(p.get("label") or ""),
        ),
    )
    # Smart code wins when present; LIS brackets + fuzzy fill gaps (avoids custom flood).
    enriched = enrich_proposals(
        all_proposals,
        catalog,
        user_aliases=user_aliases,
        allow_fuzzy=True,
    )
    enriched = filter_proposals(enriched)
    # Stable ids so progressive confirm can drop rows while worker still appends.
    for p in enriched:
        if not (p.get("uid") or "").strip():
            p["uid"] = secrets.token_hex(8)
    detected_dates = unique_drawn_dates(enriched)
    payload["lab_name"] = default_lab
    payload["proposals"] = enriched
    payload["detected_dates"] = detected_dates
    return enriched, payload


def finalize_job(db: Session, job: ImportJob) -> None:
    enriched, payload = prepare_review_proposals(db, job)
    raw_parts = payload.get("raw_parts") or []
    job.ocr_raw_text = "\n\n".join(raw_parts) if raw_parts else job.ocr_raw_text
    atts = db.query(Attachment).filter(Attachment.import_job_id == job.id).all()
    file_errors = list(payload.get("file_errors") or [])
    labs_by_att = payload.get("labs_by_attachment") or {}
    detected_lab = (payload.get("detected_lab") or "").strip()
    detected_dates = payload.get("detected_dates") or unique_drawn_dates(enriched)
    save_job_payload(
        job,
        {
            "lab_name": payload.get("lab_name") or "Laboratoř",
            "proposals": enriched,
            "detected_dates": detected_dates,
            "file_errors": file_errors,
            "labs_by_attachment": labs_by_att,
            "lab_name_form": payload.get("lab_name_form") or "",
            "detected_lab": detected_lab,
            "raw_parts": raw_parts,
            "extract_meta": {
                "source": job.extract_mode,
                "dates": detected_dates,
                "lab_name": detected_lab or None,
                "file_count": len(atts),
                "failed_count": len(file_errors),
            },
        },
    )
    job.status = "review"


def attachment_display_name(att: Attachment, *, index: int | None = None, total: int | None = None) -> str:
    """Human label for UI: original upload name, falling back to stored name."""
    original = getattr(att, "original_filename", None)
    stored = getattr(att, "filename", None)
    name = (original or "").strip() or (stored or "").strip() or "file"
    if index is not None and total is not None and total > 0:
        return f"{index}/{total} — {name}"
    if index is not None:
        return f"#{index} — {name}"
    return name


def record_file_failure(
    db: Session,
    *,
    att: Attachment,
    job: ImportJob,
    error: str,
) -> None:
    """Mark one attachment failed; keep job processing so the batch can continue."""
    msg = (error or "extract_failed").strip() or "extract_failed"
    att.ocr_status = "failed"
    att.ocr_raw_text = msg[:2000]
    siblings = (
        db.query(Attachment)
        .filter(Attachment.import_job_id == job.id)
        .order_by(Attachment.id)
        .all()
    )
    pos = next((i + 1 for i, a in enumerate(siblings) if a.id == att.id), None)
    display = attachment_display_name(att, index=pos, total=len(siblings) or None)
    payload = job_payload(job)
    errs = [e for e in (payload.get("file_errors") or []) if e.get("attachment_id") != att.id]
    errs.append(
        {
            "attachment_id": att.id,
            "filename": display,
            "original_filename": (getattr(att, "original_filename", None) or "").strip() or None,
            "stored_filename": getattr(att, "filename", None),
            "index": pos,
            "total": len(siblings) or None,
            "error": msg[:500],
        }
    )
    payload["file_errors"] = errs
    save_job_payload(job, payload)


def _active_attachment_count(db: Session, job_id: int, *, exclude_id: int | None = None) -> int:
    q = db.query(Attachment).filter(
        Attachment.import_job_id == job_id,
        Attachment.ocr_status.in_(("pending", "processing")),
    )
    if exclude_id is not None:
        q = q.filter(Attachment.id != exclude_id)
    return q.count()


def _done_attachment_count(db: Session, job_id: int) -> int:
    return (
        db.query(Attachment)
        .filter(Attachment.import_job_id == job_id, Attachment.ocr_status == "done")
        .count()
    )


def job_has_active_attachments(db: Session, job_id: int) -> bool:
    return _active_attachment_count(db, job_id) > 0


def finish_job_if_idle(db: Session, job: ImportJob) -> bool:
    """If no pending/processing left: review (partial OK) or failed (all files failed)."""
    if job.status != "processing":
        return False
    if _active_attachment_count(db, job.id):
        return False
    done = _done_attachment_count(db, job.id)
    if done:
        finalize_job(db, job)
        return True
    payload = job_payload(job)
    errs = payload.get("file_errors") or []
    if errs:
        job.ocr_raw_text = "\n".join(
            f"{e.get('filename') or 'file'}: {e.get('error') or 'failed'}" for e in errs
        )[:2000]
    else:
        job.ocr_raw_text = job.ocr_raw_text or "All files failed"
    job.status = "failed"
    return True


def recover_stuck_attachments(db: Session) -> int:
    """Recover attachments left in 'processing' after crash/restart.

    If the job already has successful files, soft-fail hung ones so partial review unlocks.
    Otherwise reset to pending for a clean retry.
    """
    stuck = (
        db.query(Attachment)
        .filter(Attachment.ocr_status == "processing")
        .all()
    )
    n = 0
    jobs_to_finish: set[int] = set()
    for att in stuck:
        job = db.get(ImportJob, att.import_job_id) if att.import_job_id else None
        if job and job.status == "processing" and _done_attachment_count(db, job.id) > 0:
            record_file_failure(db, att=att, job=job, error="interrupted_by_restart")
            jobs_to_finish.add(job.id)
        else:
            att.ocr_status = "pending"
        n += 1
    for job_id in jobs_to_finish:
        job = db.get(ImportJob, job_id)
        if job:
            finish_job_if_idle(db, job)
    if n:
        db.commit()
        logger.info("Recovered %s stuck import attachment(s)", n)
    return n


def fail_timed_out_attachment(db: Session, att_id: int, *, error: str) -> bool:
    """Soft-fail a hung processing attachment so the batch can continue. Returns True if changed."""
    att = db.get(Attachment, att_id)
    if not att or att.ocr_status != "processing" or not att.import_job_id:
        return False
    job = db.get(ImportJob, att.import_job_id)
    if not job or job.status != "processing":
        return False
    record_file_failure(db, att=att, job=job, error=error)
    finish_job_if_idle(db, job)
    db.commit()
    return True


def retry_failed_attachments(
    db: Session,
    job: ImportJob,
    attachment_ids: list[int] | None = None,
) -> int:
    """Re-queue failed attachments for another extract attempt. Returns count queued.

    Keeps existing proposals. Allowed while review/failed, or already processing
    (so user can queue more failed files without waiting for the current one).
    """
    if job.status not in {"review", "failed", "processing"}:
        return 0
    atts = (
        db.query(Attachment)
        .filter(Attachment.import_job_id == job.id, Attachment.ocr_status == "failed")
        .all()
    )
    if attachment_ids is not None:
        wanted = set(attachment_ids)
        atts = [a for a in atts if a.id in wanted]
    if not atts:
        return 0

    payload = job_payload(job)
    drop_ids = {a.id for a in atts}
    payload["file_errors"] = [
        e for e in (payload.get("file_errors") or []) if e.get("attachment_id") not in drop_ids
    ]
    # Preserve proposals / lab / dates; finalize will refresh after retries.
    save_job_payload(job, payload)

    for att in atts:
        att.ocr_status = "pending"
        att.ocr_raw_text = None

    job.status = "processing"
    job.ocr_raw_text = None
    db.commit()
    return len(atts)


def claim_next_attachment(db: Session) -> tuple[int, int, str, str, str] | None:
    """Claim one pending attachment for any processing job.

    Returns (att_id, job_id, storage_path, filename, mode) or None.
    """
    att = (
        db.query(Attachment)
        .join(ImportJob, ImportJob.id == Attachment.import_job_id)
        .filter(
            Attachment.ocr_status == "pending",
            ImportJob.status == "processing",
        )
        .order_by(Attachment.id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if att is None:
        return None
    return _claim_attachment_row(db, att)


def claim_attachment_for_job(db: Session, job_id: int) -> tuple[int, int, str, str, str] | None:
    """Claim next pending attachment for a specific job."""
    job = db.get(ImportJob, job_id)
    if job is None or job.status != "processing":
        return None
    att = (
        db.query(Attachment)
        .filter(
            Attachment.import_job_id == job_id,
            Attachment.ocr_status == "pending",
        )
        .order_by(Attachment.id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if att is None:
        return None
    return _claim_attachment_row(db, att)


def _claim_attachment_row(db: Session, att: Attachment) -> tuple[int, int, str, str, str] | None:
    job = db.get(ImportJob, att.import_job_id)
    if job is None or job.status != "processing":
        return None
    att.ocr_status = "processing"
    att_id = att.id
    job_id = job.id
    storage_path = att.storage_path
    filename = att.filename
    mode = job.extract_mode or "classic"
    db.commit()
    return att_id, job_id, storage_path, filename, mode


def maybe_finalize_idle_jobs(db: Session) -> int:
    """Finalize processing jobs that have no pending/processing attachments left."""
    jobs = db.query(ImportJob).filter(ImportJob.status == "processing").all()
    n = 0
    for job in jobs:
        if finish_job_if_idle(db, job):
            n += 1
    if n:
        db.commit()
    return n


def process_claimed_attachment(
    db: Session,
    *,
    att_id: int,
    job_id: int,
    storage_path: str,
    filename: str,
    mode: str,
) -> dict[str, Any]:
    """Run extract for a claimed attachment and merge into the job. Returns status info."""
    catalog = db.query(Marker).all()
    marker_hints = [
        f"{m.code}={m.name_cs}"
        + (f"/{m.name_en}" if (m.name_en or "") and m.name_en != m.name_cs else "")
        for m in catalog
    ]
    try:
        raw, proposals, meta = extract_file(storage_path, mode, marker_hints)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Import extract failed att=%s job=%s", att_id, job_id)
        att = db.get(Attachment, att_id)
        job = db.get(ImportJob, job_id)
        if att and job and att.ocr_status == "processing" and job.status == "processing":
            record_file_failure(db, att=att, job=job, error=str(exc))
            finish_job_if_idle(db, job)
            db.commit()
        elif att and att.ocr_status == "processing":
            att.ocr_status = "failed"
            att.ocr_raw_text = str(exc)[:2000]
            db.commit()
        return {"ok": False, "error": str(exc)}

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
    # Timed out / soft-failed / job already finished while extract ran.
    if att.ocr_status != "processing" or job.status != "processing":
        return {"ok": True, "skipped_merge": True}

    att.ocr_raw_text = raw
    att.ocr_status = "done"
    from app.services.proposal_filter import filter_proposals

    payload = job_payload(job)
    file_lab = ((meta or {}).get("lab_name") or "").strip() or None
    file_wp = ((meta or {}).get("workplace") or "").strip() or None
    for p in filter_proposals(proposals):
        row = dict(p)
        row["attachment_id"] = att.id
        row["uid"] = secrets.token_hex(8)
        if file_lab and not (row.get("proposed_lab_name") or "").strip():
            row["proposed_lab_name"] = file_lab
        if file_wp and not (row.get("proposed_workplace") or "").strip():
            row["proposed_workplace"] = file_wp
        payload.setdefault("proposals", []).append(row)
    payload["proposals"] = filter_proposals(payload.get("proposals") or [])
    payload.setdefault("raw_parts", []).append(f"--- {filename} ---\n{raw or ''}")
    lab = file_lab
    if lab and not (payload.get("detected_lab") or "").strip():
        payload["detected_lab"] = lab
    # Keep per-file labs for review fallbacks
    labs_by_att = dict(payload.get("labs_by_attachment") or {})
    if file_lab or file_wp:
        labs_by_att[str(att.id)] = {"lab_name": file_lab, "workplace": file_wp}
        payload["labs_by_attachment"] = labs_by_att
    save_job_payload(job, payload)

    if _active_attachment_count(db, job.id, exclude_id=att.id) == 0:
        finish_job_if_idle(db, job)
    db.commit()
    return {"ok": True}
