"""AI educational summary of confirmed lab trends (NVIDIA text-only)."""

from __future__ import annotations

import json

from app.services.smart_extract import _nvidia_chat, smart_enabled

ANALYSIS_SYSTEM = (
    "You are a careful health educator summarizing personal laboratory trends. "
    "Write clear, structured prose for a non-clinician. "
    "You are NOT a doctor: never diagnose, prescribe, or claim certainty. "
    "Prefer cautious language (may suggest, worth discussing with a clinician). "
    "Use light markdown: ## headings, bullet lists, short paragraphs. "
    "No JSON. No chain-of-thought. No inventing values not present in the data."
)


def charts_to_analysis_payload(charts: list[dict]) -> list[dict]:
    """Compact series for the model (drop Chart.js helper fields)."""
    out: list[dict] = []
    for c in charts:
        points = []
        for p in c.get("points") or []:
            entry = {
                "date": p.get("date"),
                "value": p.get("value"),
                "unit": p.get("unit") or c.get("unit"),
            }
            if p.get("lab_low") is not None or p.get("lab_high") is not None:
                entry["lab_ref"] = [p.get("lab_low"), p.get("lab_high")]
            if p.get("tip_low") is not None or p.get("tip_high") is not None:
                entry["tip_ref"] = [p.get("tip_low"), p.get("tip_high")]
            elif c.get("tip_low") is not None or c.get("tip_high") is not None:
                entry["tip_ref"] = [c.get("tip_low"), c.get("tip_high")]
            if p.get("lab_name"):
                entry["lab_name"] = p["lab_name"]
            cond = p.get("conditions") or {}
            if cond:
                entry["conditions"] = cond
            points.append(entry)
        out.append(
            {
                "marker": c.get("name"),
                "code": c.get("key"),
                "unit": c.get("unit"),
                "category": c.get("category_label") or c.get("category"),
                "tip_ref": [c.get("tip_low"), c.get("tip_high")],
                "points": points,
            }
        )
    return out


def _user_prompt(payload: list[dict], *, locale: str) -> str:
    lang = "Czech" if locale == "cs" else "English"
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"""Analyze these confirmed personal lab results and write a detailed educational summary in {lang}.

Cover:
1. Overall picture (what looks stable vs changing).
2. Markers outside lab reference and/or tip range — what that often means in general terms.
3. Trends over time (rising/falling/flat) where enough points exist.
4. Context from draw conditions when present (fasting, illness, training, supplements, notes).
5. Sensible next steps (what to discuss with a clinician; not a treatment plan).
6. End with a short reminder that this is not a medical diagnosis.

Data (JSON):
{data_json}
"""


def analyze_trends(payload: list[dict], *, locale: str = "cs") -> str:
    if not smart_enabled():
        raise RuntimeError("Smart AI is not available")
    if not payload:
        raise RuntimeError("No trend data")
    content = [{"type": "text", "text": _user_prompt(payload, locale=locale)}]
    text = _nvidia_chat(
        content,
        system=ANALYSIS_SYSTEM,
        max_tokens=4096,
        temperature=0.3,
    )
    return (text or "").strip()
