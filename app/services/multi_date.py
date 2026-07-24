"""Prefer multi-date table structure when classic OCR finds more dates than Smart."""

from __future__ import annotations

import logging

from app.services.ocr_extract import extract_document
from app.services.smart_extract import looks_like_hallucinated_extract

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
    """Prefer classic when it finds a richer/safer parse than Smart.

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
    combined = (smart_raw or "") + "\n\n--- classic ---\n" + (classic_raw or "")

    # Smart empty / discarded hallucination → use classic if it found anything
    if not smart_proposals and classic_props:
        logger.info("Preferring classic because smart returned no usable rows")
        meta["source"] = "classic_empty_smart"
        return classic_props, combined, meta

    if smart_proposals and looks_like_hallucinated_extract(smart_proposals) and classic_props:
        logger.info("Preferring classic because smart looked hallucinated")
        meta["source"] = "classic_vs_hallucination"
        return classic_props, combined, meta

    # Classic multi-date table richer than smart
    if len(classic_dates) >= 2 and len(classic_dates) > len(smart_dates):
        logger.info(
            "Preferring classic multi-date table (%s) over smart (%s)",
            classic_dates,
            smart_dates,
        )
        meta["source"] = "classic_multidate"
        return classic_props, combined, meta

    # Classic found many more analytes on a single date (EHR screenshot case)
    smart_labels = {
        str(p.get("label") or "").strip().lower() for p in smart_proposals if p.get("label")
    }
    classic_labels = {
        str(p.get("label") or "").strip().lower() for p in classic_props if p.get("label")
    }
    if len(classic_labels) >= 5 and len(classic_labels) >= len(smart_labels) * 2 + 1:
        logger.info(
            "Preferring classic richer analyte set (%s vs smart %s)",
            len(classic_labels),
            len(smart_labels),
        )
        meta["source"] = "classic_richer"
        return classic_props, combined, meta

    return smart_proposals, smart_raw, meta
