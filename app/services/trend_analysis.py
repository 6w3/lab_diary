"""AI educational summary of confirmed lab trends (NVIDIA text-only)."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from app.services.smart_extract import _nvidia_chat, smart_enabled
from app.services.storage import ensure_upload_dir

ANALYSIS_SYSTEM = (
    "You are a careful health educator summarizing personal laboratory trends. "
    "Write clear, structured prose for a non-clinician. "
    "You are NOT a doctor: never diagnose, prescribe, or claim certainty. "
    "Prefer cautious language (may suggest, worth discussing with a clinician). "
    "Use light markdown: ## headings, bullet lists, short paragraphs. "
    "No JSON. No chain-of-thought. No inventing values not present in the data."
)

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^[-*•]\s+(.+)\s*$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _inline_md(text: str) -> str:
    """Escape HTML then apply **bold**."""
    escaped = html.escape(text, quote=True)
    return _BOLD_RE.sub(r"<strong>\1</strong>", escaped)


def render_analysis_html(text: str) -> str:
    """Convert light markdown (headings, lists, bold, paragraphs) to safe HTML."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        return ""

    parts: list[str] = []
    in_ul = False
    para_lines: list[str] = []

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            parts.append("</ul>")
            in_ul = False

    def flush_para() -> None:
        nonlocal para_lines
        if not para_lines:
            return
        body = "<br>\n".join(_inline_md(line) for line in para_lines)
        parts.append(f"<p>{body}</p>")
        para_lines = []

    for line in raw.split("\n"):
        stripped = line.strip()
        if not stripped:
            close_ul()
            flush_para()
            continue

        hm = _HEADING_RE.match(stripped)
        if hm:
            close_ul()
            flush_para()
            hashes = len(hm.group(1))
            tag = "h3" if hashes >= 3 else "h2"
            parts.append(f"<{tag}>{_inline_md(hm.group(2))}</{tag}>")
            continue

        bm = _BULLET_RE.match(stripped)
        if bm:
            flush_para()
            if not in_ul:
                parts.append("<ul>")
                in_ul = True
            parts.append(f"<li>{_inline_md(bm.group(1))}</li>")
            continue

        close_ul()
        # Drop trailing markdown hard-break spaces
        para_lines.append(stripped.rstrip())

    close_ul()
    flush_para()
    return "\n".join(parts)


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


def _user_prompt(payload: list[dict], *, locale: str, user_focus: str | None = None) -> str:
    lang = "Czech" if locale == "cs" else "English"
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    focus = (user_focus or "").strip()
    focus_block = ""
    if focus:
        focus_block = (
            "\nUser focus (prioritize this; still cover the rest briefly):\n"
            f"{focus}\n"
        )
    return f"""Analyze these confirmed personal lab results and write a detailed educational summary in {lang}.
{focus_block}
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


def analyze_trends(
    payload: list[dict],
    *,
    locale: str = "cs",
    user_focus: str | None = None,
) -> str:
    if not smart_enabled():
        raise RuntimeError("Smart AI is not available")
    if not payload:
        raise RuntimeError("No trend data")
    content = [
        {
            "type": "text",
            "text": _user_prompt(payload, locale=locale, user_focus=user_focus),
        }
    ]
    text = _nvidia_chat(
        content,
        system=ANALYSIS_SYSTEM,
        max_tokens=4096,
        temperature=0.3,
    )
    cleaned = (text or "").strip()
    if not cleaned:
        raise RuntimeError("NVIDIA returned empty analysis")
    return cleaned


def _analysis_path(user_id: int) -> Path:
    base = ensure_upload_dir() / "trend_analysis"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"user_{int(user_id)}.json"


def save_user_analysis(user_id: int, text: str) -> dict:
    """Persist analysis on disk (cookie session cannot hold long text)."""
    payload = {
        "text": text,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    path = _analysis_path(user_id)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def load_user_analysis(user_id: int) -> dict | None:
    path = _analysis_path(user_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not (data.get("text") or "").strip():
        return None
    text = str(data["text"])
    return {
        "text": text,
        "generated_at": data.get("generated_at"),
        "html": render_analysis_html(text),
    }
