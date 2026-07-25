"""Process one import attachment (extract + merge into job). Shared by HTTP + worker."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Attachment, ImportJob, Marker
from app.services.label_aliases import load_user_aliases
from app.services.markers import resolve_marker
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
    out: list[dict] = []
    for p in proposals:
        code = (p.get("marker_code") or "").strip() or None
        source_label = (p.get("label") or "").strip()
        matched = resolve_marker(
            source_label,
            catalog,
            code_hint=code,
            user_aliases=user_aliases,
            allow_fuzzy=allow_fuzzy,
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


def finalize_job(db: Session, job: ImportJob) -> None:
    from app.services.proposal_filter import filter_proposals

    payload = job_payload(job)
    catalog = db.query(Marker).all()
    user_aliases = load_user_aliases(db, job.user_id)
    all_proposals = filter_proposals(list(payload.get("proposals") or []))
    all_proposals = sorted(
        all_proposals,
        key=lambda p: (str(p.get("proposed_drawn_on") or ""), str(p.get("label") or "")),
    )
    # Smart AI owns marker mapping; do not let OCR heuristics override missing codes.
    allow_fuzzy = (job.extract_mode or "").lower() != "smart"
    enriched = enrich_proposals(
        all_proposals,
        catalog,
        user_aliases=user_aliases,
        allow_fuzzy=allow_fuzzy,
    )
    enriched = filter_proposals(enriched)
    detected_dates = unique_drawn_dates(enriched)
    detected_lab = (payload.get("detected_lab") or "").strip()
    form_lab = (payload.get("lab_name_form") or "").strip()
    default_lab = form_lab or detected_lab or "Laboratoř"
    raw_parts = payload.get("raw_parts") or []
    job.ocr_raw_text = "\n\n".join(raw_parts) if raw_parts else job.ocr_raw_text
    atts = db.query(Attachment).filter(Attachment.import_job_id == job.id).all()
    save_job_payload(
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


def recover_stuck_attachments(db: Session) -> int:
    """Reset attachments left in 'processing' after crash/restart → pending."""
    stuck = (
        db.query(Attachment)
        .filter(Attachment.ocr_status == "processing")
        .all()
    )
    n = 0
    for att in stuck:
        att.ocr_status = "pending"
        n += 1
    if n:
        db.commit()
        logger.info("Recovered %s stuck import attachment(s)", n)
    return n


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
        active = (
            db.query(Attachment)
            .filter(
                Attachment.import_job_id == job.id,
                Attachment.ocr_status.in_(("pending", "processing")),
            )
            .count()
        )
        if active == 0:
            # Only finalize if at least one file finished (avoid empty upload race)
            done = (
                db.query(Attachment)
                .filter(
                    Attachment.import_job_id == job.id,
                    Attachment.ocr_status == "done",
                )
                .count()
            )
            if done:
                finalize_job(db, job)
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
        if att:
            att.ocr_status = "failed"
            att.ocr_raw_text = str(exc)
        if job and job.status == "processing":
            job.status = "failed"
            job.ocr_raw_text = str(exc)
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
    if job.status == "failed":
        att.ocr_status = "done"
        att.ocr_raw_text = raw
        db.commit()
        return {"ok": True, "skipped_merge": True}

    att.ocr_raw_text = raw
    att.ocr_status = "done"
    from app.services.proposal_filter import filter_proposals

    payload = job_payload(job)
    for p in filter_proposals(proposals):
        row = dict(p)
        row["attachment_id"] = att.id
        payload.setdefault("proposals", []).append(row)
    payload["proposals"] = filter_proposals(payload.get("proposals") or [])
    payload.setdefault("raw_parts", []).append(f"--- {filename} ---\n{raw or ''}")
    lab = ((meta or {}).get("lab_name") or "").strip()
    if lab and not (payload.get("detected_lab") or "").strip():
        payload["detected_lab"] = lab
    save_job_payload(job, payload)

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
        finalize_job(db, job)
    db.commit()
    return {"ok": True}
