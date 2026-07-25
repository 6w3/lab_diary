"""Helpers for multi-date Smart extracts (classic OCR no longer consulted)."""

from __future__ import annotations


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
    """Keep Smart proposals as-is (no classic OCR merge/fallback)."""
    return (
        smart_proposals,
        smart_raw,
        {"source": "smart", "smart_dates": unique_drawn_dates(smart_proposals)},
    )
