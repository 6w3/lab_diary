"""Smart lab-report extraction via NVIDIA NIM vision models."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
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
      "lab_name": "Oblastní nemocnice Příbram",
      "results": [
        {
          "marker_code": "ferritin",
          "label": "Feritin",
          "value": 0.0,
          "unit": "ug/l",
          "ref_low": null,
          "ref_high": null,
          "confidence": 0.0
        }
      ]
    }
  ],
  "warnings": []
}
Rules:
- Czech/English laboratory blood report.
- Set lab_name from the report header (hospital / lab name), e.g. "Oblastní nemocnice Příbram" or "Laboratoř OKB". Prefer the clearest institution name visible at the top. Same lab_name on every draws[] entry when it is one report.
- If multiple draw dates/columns exist, emit one object per date in "draws".
- CRITICAL for comparison tables: when a header row has several dates (e.g. 14. 10. 2020 10:30 | 18. 5. 2016 12:15 | 14. 9. 2010 7:30), create ONE draws[] entry PER date column. Put each marker's value from that column into that draw. Do NOT collapse all columns into a single draw.
- Czech dates often have spaces after dots: "14. 10. 2020" means 14 October 2020.
- Typical Czech hospital "historické výsledky" layout: leftmost column = analyte name, then one numeric column per draw date, then reference range, then unit.
- Dates on Czech lab reports are day-first: D.M.YYYY or DD.MM.YYYY (example: 12.01.2025 = 12 January 2025 = 2025-01-12). Never treat them as US month-first.
- Prefer ISO dates YYYY-MM-DD in output.
- Numbers as JSON numbers (dot decimal). Do not invent values you cannot read.
- When a known catalog code matches, set marker_code exactly (e.g. hgb, ferritin, vitamin_d, tsh, glucose). Otherwise omit marker_code and keep the original label.
- Keep original units from the report; do not invent conversions.
- If you see more than one draw date, warnings may list them, but every date with values MUST still appear as its own draws[] object with results.
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
                continue
            label = str(r.get("label") or "").strip()
            if len(label) < 2:
                continue
            marker_code = str(r.get("marker_code") or "").strip() or None
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


DATE_DISCOVER_HINT = """
Return ONLY valid JSON (no markdown):
{"dates": ["YYYY-MM-DD"], "notes": ""}
Task: list EVERY draw/result COLUMN HEADER date on this Czech lab report.
Historical comparison tables have multiple date columns, e.g. "14. 10. 2020 10:30", "18. 5. 2016 12:15", "14. 9. 2010 7:30".
Czech dates are day-first and often have spaces after dots.
Convert each to ISO YYYY-MM-DD.
Include all result-column dates. Do not invent dates. Ignore rodné číslo / birth embedded in ID.
"""


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


def _discover_dates(pages: list[Path]) -> list[str]:
    content: list[dict] = [{"type": "text", "text": DATE_DISCOVER_HINT}, *_image_content(pages)]
    text = _nvidia_chat(content, max_tokens=512)
    data = _extract_json(text)
    dates: list[str] = []
    for raw in data.get("dates") or []:
        iso = _normalize_drawn_on(str(raw))
        if iso and iso not in dates:
            dates.append(iso)
    return dates


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

        discovered: list[str] = []
        try:
            discovered = _discover_dates(pages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Date discovery failed: %s", exc)

        content: list[dict] = [{"type": "text", "text": SMART_SCHEMA_HINT}]
        if discovered:
            content.append(
                {
                    "type": "text",
                    "text": (
                        "REQUIRED: emit one draws[] object for EACH of these column dates "
                        f"(do not omit any): {', '.join(discovered)}. "
                        "Each marker row has one value per date column — put the correct column value "
                        "into the matching draw."
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

        text = _nvidia_chat(content, max_tokens=8192)
        parsed = _validate_smart_payload(_extract_json(text))
        proposals: list[dict] = []
        for d in parsed["draws"]:
            proposals.extend(d["results"])

        got_dates = sorted({p.get("proposed_drawn_on") for p in proposals if p.get("proposed_drawn_on")})
        # If discovery found more dates than extract returned, retry once with a louder reminder
        missing = [d for d in discovered if d not in got_dates]
        if missing and discovered:
            content_retry: list[dict] = [
                {"type": "text", "text": SMART_SCHEMA_HINT},
                {
                    "type": "text",
                    "text": (
                        f"PREVIOUS ANSWER MISSED dates {missing}. "
                        f"You MUST return draws for ALL of: {', '.join(discovered)}. "
                        "Copy values from each date column separately."
                    ),
                },
                *_image_content(pages),
            ]
            try:
                text2 = _nvidia_chat(content_retry, max_tokens=8192)
                parsed2 = _validate_smart_payload(_extract_json(text2))
                props2: list[dict] = []
                for d in parsed2["draws"]:
                    props2.extend(d["results"])
                got2 = {p.get("proposed_drawn_on") for p in props2 if p.get("proposed_drawn_on")}
                if len(got2) > len(got_dates):
                    text, proposals, parsed = text2, props2, parsed2
                    got_dates = sorted(got2)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Smart multi-date retry failed: %s", exc)

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
            "dates": got_dates,
            "discovered_dates": discovered,
            "lab_name": lab_name,
            "warnings": parsed.get("warnings") or [],
        }
        return text, proposals, meta
