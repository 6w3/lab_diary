"""Prefer multi-date table structure when classic OCR finds more dates than Smart."""

from __future__ import annotations

import logging

from app.services.ocr_extract import extract_document

logger = logging.getLogger(__name__)


def unique_drawn_dates(proposals: list[dict]) -> list[str]:
    dates = sorted(
        {
            str(p.get("proposed_drawn_on") or "").strip()[:10]
            for p in proposals
            if str(p.get("proposed_drawn_on") or "").strip()
        }
    )
    return [d for d in dates if d]


def prefer_multi_date_proposals(
    storage_path: str,
    smart_proposals: list[dict],
    smart_raw: str,
) -> tuple[list[dict], str, dict]:
    """If classic finds ≥2 date columns and more dates than smart, use classic rows.

    Returns (proposals, raw_for_storage, meta).
    """
    smart_dates = unique_drawn_dates(smart_proposals)
    meta: dict = {"source": "smart", "smart_dates": smart_dates}
    try:
        classic_raw, classic_props, classic_meta = extract_document(storage_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Classic fallback after smart failed: %s", exc)
        return smart_proposals, smart_raw, meta

    classic_dates = unique_drawn_dates(classic_props)
    meta["classic_dates"] = classic_dates
    meta["classic_engine"] = classic_meta.get("engine")

    if len(classic_dates) >= 2 and len(classic_dates) > len(smart_dates):
        logger.info(
            "Preferring classic multi-date table (%s) over smart (%s)",
            classic_dates,
            smart_dates,
        )
        meta["source"] = "classic_multidate"
        # Keep smart raw for debugging, append classic text
        combined = (smart_raw or "") + "\n\n--- classic ---\n" + (classic_raw or "")
        return classic_props, combined, meta

    return smart_proposals, smart_raw, meta
