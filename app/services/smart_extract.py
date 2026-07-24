"""Smart lab-report extraction via NVIDIA NIM vision models."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)

NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

SMART_SCHEMA_HINT = """
Return ONLY valid JSON (no markdown) with this shape:
{
  "draws": [
    {
      "drawn_on": "YYYY-MM-DD",
      "lab_name": "string or null",
      "results": [
        {
          "marker_code": "catalog_code_or_omit",
          "label": "exact analyte name from the report",
          "value": 123.4,
          "unit": "unit from report",
          "ref_low": 1.0,
          "ref_high": 2.0,
          "confidence": 0.9
        }
      ]
    }
  ],
  "warnings": []
}
Rules:
- Czech/English laboratory blood report OR EHR screenshot (e.g. PC DOKTOR) showing lab results.
- Read ONLY what is visible. NEVER invent analytes, values, or dates. NEVER copy example JSON fields.
- The schema numbers/names above are PLACEHOLDERS only — replace them with real rows from the image.
- Set lab_name from the report/EHR header when visible (hospital / lab / clinic). Same lab_name on every draws[] entry when it is one report.
- Prefer the sample collection date ("Datum odběru") over visit/print timestamps.
- If this is a SINGLE visit / single result list (typical EHR screen), emit ONE draws[] object with ALL visible numeric lab rows.
- If a comparison table has several DATE COLUMNS in the header, emit one draws[] entry PER date column. Put each marker's value from that column into that draw. Do NOT collapse columns into a single draw.
- Czech dates are day-first: D.M.YYYY or DD.MM.YYYY (12.01.2025 = 2025-01-12). Spaces after dots are common ("14. 10. 2020").
- Prefer ISO dates YYYY-MM-DD in output.
- Numbers as JSON numbers (dot decimal). Values like ">1.50" → 1.50 and note in warnings if needed.
- Skip non-lab rows (ano/ne flags, comments, diagnoses, prescriptions, vitals like TK/P/weight unless they are lab analytes).
- When a known catalog code matches, set marker_code exactly (e.g. hgb, glucose, creatinine, alt, ggt, wbc, plt). Otherwise omit marker_code and keep the original label.
- Keep original units from the report; do not invent conversions.
- Extract EVERY visible lab analyte row (biochemistry + hematology), not just one marker.
"""

DATE_DISCOVER_HINT = """
Return ONLY valid JSON (no markdown):
{"layout": "single"|"multi_column"|"unknown", "dates": ["YYYY-MM-DD"], "notes": ""}
Task: find draw/sample dates on this Czech lab report or EHR screenshot.

layout:
- "multi_column" ONLY if there is a historical comparison TABLE with several DATE COLUMNS as headers (each column = another draw).
- "single" if this is one visit / one result list (PC DOKTOR, single panel, one "Datum odběru").
- "unknown" if unclear.

dates:
- For multi_column: list EVERY result-column header date (ISO YYYY-MM-DD).
- For single: list at most ONE preferred sample date ("Datum odběru"), else the lab result date. Do NOT list every calendar day.
- Czech dates are day-first; spaces after dots are OK.
- Do NOT invent dates. Do NOT expand into a consecutive day range.
- IGNORE: birth dates / rodné číslo, appointment notes, diagnoses, prescription dates, unrelated visit notes below the lab panel.
"""

SINGLE_DRAW_HINT = """
This image is a SINGLE-DRAW lab panel / EHR screenshot (not a multi-column history table).
Return ONE draws[] object only. Include ALL visible numeric lab analytes (biochem + hematology).
Do not invent ferritin or any marker that is not printed. Do not invent extra dates.
"""


def smart_enabled() -> bool:
    s = get_settings()
    return bool(s.nvidia_api_key) and (s.smart_provider or "nvidia").lower() == "nvidia"


def _encode_image(path: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    data = path.read_bytes()
    return mime, base64.b64encode(data).decode("ascii")


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def _normalize_drawn_on(raw: str) -> str | None:
    """Accept YYYY-MM-DD or Czech D.M.YYYY / D. M. YYYY (+ optional time) → ISO."""
    from app.services.ocr_tables import _parse_date_token

    return _parse_date_token(raw or "")


def _validate_smart_payload(data: dict[str, Any]) -> dict[str, Any]:
    draws_in = data.get("draws") or []
    draws_out: list[dict] = []
    for d in draws_in:
        drawn_on = _normalize_drawn_on(str(d.get("drawn_on") or ""))
        if not drawn_on:
            continue
        results_out = []
        for r in d.get("results") or []:
            try:
                value = float(r["value"])
            except (KeyError, TypeError, ValueError):
                # Try stripping comparison prefixes like ">1.50"
                raw_v = str(r.get("value") or "").strip().replace(",", ".")
                raw_v = re.sub(r"^[<>]=?\s*", "", raw_v)
                try:
                    value = float(raw_v)
                except (TypeError, ValueError):
                    continue
            label = str(r.get("label") or "").strip()
            if len(label) < 2:
                continue
            marker_code = str(r.get("marker_code") or "").strip() or None
            # Guard: placeholder/example echo
            if marker_code == "catalog_code_or_omit":
                marker_code = None
            if label.lower() in {"exact analyte name from the report", "string or null"}:
                continue
            ref_low = r.get("ref_low", r.get("lab_ref_low"))
            ref_high = r.get("ref_high", r.get("lab_ref_high"))
            try:
                ref_low_f = float(ref_low) if ref_low is not None else None
            except (TypeError, ValueError):
                ref_low_f = None
            try:
                ref_high_f = float(ref_high) if ref_high is not None else None
            except (TypeError, ValueError):
                ref_high_f = None
            results_out.append(
                {
                    "marker_code": marker_code,
                    "label": label,
                    "value": value,
                    "unit": str(r.get("unit") or ""),
                    "lab_ref_low": ref_low_f,
                    "lab_ref_high": ref_high_f,
                    "confidence": r.get("confidence"),
                    "proposed_drawn_on": drawn_on,
                }
            )
        if results_out:
            lab = d.get("lab_name")
            lab_s = str(lab).strip() if lab not in (None, "") else None
            if lab_s and len(lab_s) > 120:
                lab_s = lab_s[:120]
            draws_out.append(
                {
                    "drawn_on": drawn_on,
                    "lab_name": lab_s,
                    "results": results_out,
                }
            )
    return {"draws": draws_out, "warnings": list(data.get("warnings") or [])}


def _is_consecutive_day_run(dates: list[str], *, min_len: int = 5) -> bool:
    """True when dates contain a long consecutive calendar-day streak (hallucination smell)."""
    parsed: list[date] = []
    for raw in dates:
        try:
            parsed.append(date.fromisoformat(raw[:10]))
        except ValueError:
            continue
    if len(parsed) < min_len:
        return False
    parsed = sorted(set(parsed))
    run = 1
    best = 1
    for i in range(1, len(parsed)):
        if parsed[i] - parsed[i - 1] == timedelta(days=1):
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best >= min_len


def looks_like_hallucinated_extract(proposals: list[dict]) -> bool:
    """Detect classic VLM failure: one marker/zero values repeated across many invented dates."""
    if not proposals:
        return True
    dates = sorted(
        {
            str(p.get("proposed_drawn_on") or "").strip()[:10]
            for p in proposals
            if str(p.get("proposed_drawn_on") or "").strip()
        }
    )
    analytes: set[str] = set()
    for p in proposals:
        code = str(p.get("marker_code") or "").strip().lower()
        label = str(p.get("label") or "").strip().lower()
        key = code or label
        if key:
            analytes.add(key)
    values = [p.get("value") for p in proposals]
    all_zero = values and all(
        isinstance(v, (int, float)) and abs(float(v)) < 1e-12 for v in values
    )
    few_analytes = len(analytes) <= 1
    many_dates = len(dates) >= 5
    if many_dates and few_analytes:
        return True
    if _is_consecutive_day_run(dates) and few_analytes:
        return True
    if all_zero and few_analytes and len(proposals) >= 3:
        return True
    return False


def _sanitize_discovered_dates(
    dates: list[str],
    *,
    layout: str,
) -> list[str]:
    """Drop invented date spam; keep multi-column headers or a single sample date."""
    clean: list[str] = []
    for raw in dates:
        iso = _normalize_drawn_on(str(raw))
        if iso and iso not in clean:
            clean.append(iso)
    if layout == "single":
        return clean[:1]
    if layout != "multi_column":
        # Unknown layout: never force a consecutive day run into extraction
        if _is_consecutive_day_run(clean) or len(clean) > 8:
            return []
        return clean[:3]
    # multi_column: still reject absurd consecutive calendars (not real lab columns)
    if _is_consecutive_day_run(clean):
        return []
    return clean


def _pages_as_jpeg_paths(storage_path: str, tmp_dir: Path) -> list[Path]:
    path = Path(storage_path)
    out: list[Path] = []
    if path.suffix.lower() == ".pdf":
        from pdf2image import convert_from_path

        images = convert_from_path(str(path), dpi=220)
        for i, img in enumerate(images[:5]):
            dest = tmp_dir / f"page_{i}.jpg"
            _save_vision_jpeg(img.convert("RGB"), dest)
            out.append(dest)
        return out
    # HEIC may still be present if conversion failed at upload; register opener
    if path.suffix.lower() in {".heic", ".heif"}:
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except Exception:  # noqa: BLE001
            pass
    img = Image.open(path).convert("RGB")
    dest = tmp_dir / "page_0.jpg"
    _save_vision_jpeg(img, dest)
    out.append(dest)
    return out


def _save_vision_jpeg(img: Image.Image, dest: Path) -> None:
    """Downscale huge photos but keep table text readable for VLM."""
    max_side = 2200
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    img.save(dest, "JPEG", quality=92)


def _nvidia_chat(content: list[dict], *, max_tokens: int = 8192) -> str:
    settings = get_settings()
    model = settings.smart_model or "nvidia/nemotron-nano-12b-v2-vl"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    headers = {
        "Authorization": f"Bearer {settings.nvidia_api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=180.0) as client:
        resp = client.post(f"{NVIDIA_BASE}/chat/completions", headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"NVIDIA API {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
    return body["choices"][0]["message"]["content"]


def _image_content(pages: list[Path]) -> list[dict]:
    parts: list[dict] = []
    for p in pages:
        mime, b64 = _encode_image(p)
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return parts


def _discover_dates(pages: list[Path]) -> tuple[str, list[str]]:
    content: list[dict] = [{"type": "text", "text": DATE_DISCOVER_HINT}, *_image_content(pages)]
    text = _nvidia_chat(content, max_tokens=512)
    data = _extract_json(text)
    layout = str(data.get("layout") or "unknown").strip().lower()
    if layout not in {"single", "multi_column", "unknown"}:
        layout = "unknown"
    dates = _sanitize_discovered_dates(list(data.get("dates") or []), layout=layout)
    return layout, dates


def _flatten_draws(parsed: dict[str, Any]) -> list[dict]:
    proposals: list[dict] = []
    for d in parsed.get("draws") or []:
        proposals.extend(d.get("results") or [])
    return proposals


def _build_extract_content(
    pages: list[Path],
    *,
    marker_hints: list[str] | None,
    layout: str,
    discovered: list[str],
    force_single: bool = False,
) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": SMART_SCHEMA_HINT}]
    if force_single or layout == "single":
        content.append({"type": "text", "text": SINGLE_DRAW_HINT})
        if discovered:
            content.append(
                {
                    "type": "text",
                    "text": f"Preferred sample date (Datum odběru) if visible: {discovered[0]}.",
                }
            )
    elif layout == "multi_column" and discovered:
        content.append(
            {
                "type": "text",
                "text": (
                    "REQUIRED: emit one draws[] object for EACH of these COLUMN header dates "
                    f"(do not omit any): {', '.join(discovered)}. "
                    "Each marker row has one value per date column — put the correct column value "
                    "into the matching draw. Do not invent extra dates beyond this list."
                ),
            }
        )
    elif discovered:
        content.append(
            {
                "type": "text",
                "text": (
                    "Possible draw date(s) seen on the page: "
                    f"{', '.join(discovered)}. Use only dates that actually have lab values."
                ),
            }
        )
    if marker_hints:
        content.append(
            {
                "type": "text",
                "text": (
                    "Catalog marker codes (use marker_code when matching): "
                    + ", ".join(marker_hints[:120])
                ),
            }
        )
    content.extend(_image_content(pages))
    return content


def run_smart_extract(storage_path: str, marker_hints: list[str] | None = None) -> tuple[str, list[dict], dict]:
    """Call NVIDIA VLM; return (raw_json, flat proposals, meta)."""
    settings = get_settings()
    if not settings.nvidia_api_key:
        raise RuntimeError("NVIDIA_API_KEY not configured")

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pages = _pages_as_jpeg_paths(storage_path, tmp)
        if not pages:
            raise RuntimeError("No pages to analyze")

        layout = "unknown"
        discovered: list[str] = []
        try:
            layout, discovered = _discover_dates(pages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Date discovery failed: %s", exc)

        content = _build_extract_content(
            pages,
            marker_hints=marker_hints,
            layout=layout,
            discovered=discovered,
        )
        text = _nvidia_chat(content, max_tokens=8192)
        parsed = _validate_smart_payload(_extract_json(text))
        proposals = _flatten_draws(parsed)

        got_dates = sorted({p.get("proposed_drawn_on") for p in proposals if p.get("proposed_drawn_on")})

        # Multi-column: retry if discovery dates missing from extract
        missing = [d for d in discovered if d not in got_dates]
        if layout == "multi_column" and missing and discovered:
            content_retry = _build_extract_content(
                pages,
                marker_hints=marker_hints,
                layout=layout,
                discovered=discovered,
            )
            content_retry.insert(
                1,
                {
                    "type": "text",
                    "text": (
                        f"PREVIOUS ANSWER MISSED dates {missing}. "
                        f"You MUST return draws for ALL of: {', '.join(discovered)}. "
                        "Copy values from each date column separately."
                    ),
                },
            )
            try:
                text2 = _nvidia_chat(content_retry, max_tokens=8192)
                parsed2 = _validate_smart_payload(_extract_json(text2))
                props2 = _flatten_draws(parsed2)
                got2 = {p.get("proposed_drawn_on") for p in props2 if p.get("proposed_drawn_on")}
                if len(got2) > len(got_dates):
                    text, proposals, parsed = text2, props2, parsed2
                    got_dates = sorted(got2)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Smart multi-date retry failed: %s", exc)

        # Hallucination guard: one marker / zero values / date spam → single-draw retry
        if looks_like_hallucinated_extract(proposals):
            logger.warning(
                "Smart extract looks hallucinated (layout=%s dates=%s n=%s); retrying single-draw",
                layout,
                got_dates,
                len(proposals),
            )
            try:
                content_single = _build_extract_content(
                    pages,
                    marker_hints=marker_hints,
                    layout="single",
                    discovered=discovered[:1],
                    force_single=True,
                )
                text3 = _nvidia_chat(content_single, max_tokens=8192)
                parsed3 = _validate_smart_payload(_extract_json(text3))
                props3 = _flatten_draws(parsed3)
                if props3 and not looks_like_hallucinated_extract(props3):
                    text, proposals, parsed = text3, props3, parsed3
                    got_dates = sorted(
                        {p.get("proposed_drawn_on") for p in proposals if p.get("proposed_drawn_on")}
                    )
                    layout = "single_retry"
                elif props3 and len({str(p.get("label") or "").lower() for p in props3}) > len(
                    {str(p.get("label") or "").lower() for p in proposals}
                ):
                    # Prefer richer analyte set even if still imperfect
                    text, proposals, parsed = text3, props3, parsed3
                    got_dates = sorted(
                        {p.get("proposed_drawn_on") for p in proposals if p.get("proposed_drawn_on")}
                    )
                    layout = "single_retry"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Smart single-draw retry failed: %s", exc)

        # Still garbage → return empty rather than ferritin spam (classic fallback can take over)
        if looks_like_hallucinated_extract(proposals):
            logger.error("Smart extract still hallucinated; returning empty for classic fallback")
            proposals = []
            parsed = {"draws": [], "warnings": ["hallucinated_extract_discarded"]}
            got_dates = []

        model = settings.smart_model or "nvidia/nemotron-nano-12b-v2-vl"
        lab_name = None
        for d in parsed.get("draws") or []:
            if d.get("lab_name"):
                lab_name = d["lab_name"]
                break
        meta = {
            "engine": "nvidia",
            "model": model,
            "mode": "smart",
            "layout": layout,
            "dates": got_dates,
            "discovered_dates": discovered,
            "lab_name": lab_name,
            "warnings": parsed.get("warnings") or [],
        }
        return text, proposals, meta
