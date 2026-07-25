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
from app.services.draw_match import (
    BIOCHEM_CODES,
    HEMA_CODES,
    fingerprints_nearly_identical,
    value_fingerprint,
)
from app.services.proposal_filter import filter_proposals, is_junk_label

logger = logging.getLogger(__name__)

NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

SMART_SCHEMA_HINT = """
Return ONLY valid JSON (no markdown) with this shape:
{
  "doc_kind": "lab_results"|"not_lab_results",
  "draws": [
    {
      "drawn_on": "YYYY-MM-DD",
      "lab_name": "string or null",
      "workplace": "string or null",
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
- FIRST decide doc_kind (mandatory):
  - "lab_results" ONLY if the page shows MEASURED laboratory results: numeric analyte values with units
    (table Název/Výsledek/Jednotka/Meze, EHR result list like PC DOKTOR, multi-column history with numbers).
  - "not_lab_results" for everything else: žádanka/order forms with checkboxes, referrals, prescriptions,
    invoices, ID cards, random photos, empty forms, stamps-only pages, documents without measured lab values.
- If doc_kind is "not_lab_results": return draws: [] — NEVER invent analytes, values, or dates from test names or ticks.
- Checked boxes on an order sheet mean "order this test", NOT a numeric result.
- Read ONLY what is visible. NEVER invent analytes, values, or dates. NEVER copy example JSON fields.
- The schema numbers/names above are PLACEHOLDERS only — replace them with real rows from the image.
- Set lab_name from the report/EHR header when visible (hospital / lab / clinic). Same lab_name on every draws[] entry when it is one report.
- Set workplace when a department/site is visible (e.g. Hematologie, biochemie); otherwise null.
- Prefer the sample collection date ("Datum odběru") over visit/print timestamps.
- If this is a SINGLE visit / single result list (typical EHR screen), emit ONE draws[] object with ALL visible numeric lab rows.
- If a comparison table has several DATE COLUMNS in the header, emit one draws[] entry PER date column. Put each marker's value from that column into that draw. Do NOT collapse columns into a single draw.
- CRITICAL multi_column: values MUST differ across date columns when the printed numbers differ. NEVER copy the same column's numbers onto every date. Each draws[].results must come from THAT column only.
- Czech dates are day-first: D.M.YYYY or DD.MM.YYYY (12.01.2025 = 2025-01-12). Spaces after dots are common ("14. 10. 2020").
- Prefer ISO dates YYYY-MM-DD in output.
- Numbers as JSON numbers (dot decimal). Values like ">1.50" → 1.50 and note in warnings if needed.
- Skip non-lab rows (ano/ne flags, comments, diagnoses, prescriptions, vitals like TK/P/weight unless they are lab analytes).
- NEVER extract report header/metadata as results: ČP, IČO, IČP, Plátce, Dg., věk, pohlaví, datum narození, číslo sestavení, číslo průvodky, protokol číslo, přijato, svozová trasa, pracoviště / address lines, "Sestaveno a vydáno", page numbers, accreditation marks (AM), lab site codes (HAD), column headers (Název vyšetření / Výsledek / Jednotka / Meze).
- Only rows that are real laboratory analytes (biochemistry, hematology, hormones, urine chem, etc.) with a numeric result.
- Do NOT emit duplicate rows for the same analyte on the same draw date (same marker + same value).
- Marker mapping (CRITICAL — you are the primary matcher):
  - Analyte names on Czech reports are usually Czech (Hemoglobin, Leukocyty, Kreatinin, Glukóza, Železo, Feritin, Sodík, Draslík, Celková bílkovina, Triacylglyceroly…).
  - ALWAYS set marker_code to the catalog code when the row matches an entry in the provided catalog list. Omit marker_code ONLY if nothing in the catalog fits.
  - Never invent codes outside the catalog. Never guess a wrong close code (ALT≠AST, CRP≠hs_crp, neutrophils≠neutrophils_abs).
  - Use unit + label to choose % vs absolute (e.g. Neutrofily % → neutrophils; Neutrofily abs. počet / 10^9/l → neutrophils_abs).
  - Keep label exactly as printed on the report (Czech spelling OK).
- Units (CRITICAL): copy the unit string printed next to the value (µkat/l, U/l, mmol/l, g/l, 10^9/l, %, ml/min/1.73m2, …). Do not invent units. Do not put enzyme units on lipids or counts.
- Keep original units from the report; do not invent conversions.
- Extract EVERY visible lab analyte row (biochemistry + hematology), not just one marker.
"""

DATE_DISCOVER_HINT = """
Return ONLY valid JSON (no markdown):
{"doc_kind":"lab_results"|"not_lab_results"|"unknown","layout":"single"|"multi_column"|"unknown","dates":["YYYY-MM-DD"],"notes":""}
Task: FIRST decide whether this page shows measured laboratory results; only then find draw/sample dates.

doc_kind (mandatory first):
- "lab_results" if the page shows MEASURED lab values (Název/Výsledek/Jednotka/Meze, numeric result rows, or multi-column history with numbers).
- "not_lab_results" if it is NOT lab results: žádanka/order form (checkbox grids to ORDER tests), referral, prescription, invoice, ID, empty form, photo without result values.
- "unknown" only if truly unclear.
If doc_kind is "not_lab_results": set dates to [] and layout "unknown". Do NOT invent dates.

layout (only when lab_results):
- "multi_column" if there is a historical comparison TABLE with several DATE COLUMNS as headers (each column = another draw).
  Typical: Czech hospital HTO/biochem printouts (e.g. Příbram OpenLIMS) with dates like "14. 10. 2020 12:15" and "18. 5. 2016 12:45" ABOVE value columns, one marker list, multiple value columns.
  If you can see TWO OR MORE date headers above value columns, layout MUST be "multi_column" (never "single").
- "single" if this is one visit / one result list (PC DOKTOR, single panel, one "Datum odběru") with NO historical date columns.
- "unknown" if unclear.

dates:
- Look at DATE COLUMN HEADERS above the numeric value grid (often near top of the results table), not only the page print/Tisk stamp.
- For multi_column: list EVERY result-column header date (ISO YYYY-MM-DD). Never drop older columns.
- For single: list at most ONE preferred sample date ("Datum odběru"), else the lab result date. Do NOT list every calendar day.
- Czech dates are ALWAYS day-first: D. M. YYYY — first number = day, MIDDLE number = month, last = year.
  Examples: "14. 10. 2020" → 2020-10-14; "18. 5. 2016" → 2016-05-18; "14. 9. 2010" → 2010-09-14.
  NEVER swap day/month. NEVER mix day from one column with month/year from another (wrong: 2020-10-18 from "18. 5. 2016").
- History tables usually span YEARS (different years per column). Do not invent near-duplicate same-month dates.
- Do NOT invent dates. Do NOT expand into a consecutive day range.
- IGNORE: print/Tisk timestamps, birth dates / rodné číslo, appointment notes, diagnoses, prescription dates, unrelated visit notes below the lab panel.
"""

JSON_ONLY_SYSTEM = (
    "You are a JSON extraction API for laboratory reports. "
    "Output a single JSON object only. No markdown fences, no analysis, no chain-of-thought."
)

DATE_DISCOVER_SHORT = """
Return ONLY this tiny JSON (no other text):
{"doc_kind":"lab_results","layout":"multi_column","dates":["YYYY-MM-DD","YYYY-MM-DD"]}
FIRST: if page is NOT measured lab results (žádanka/order form, referral, no value+unit columns) →
{"doc_kind":"not_lab_results","layout":"unknown","dates":[]}.
Else list EVERY date COLUMN header above the lab value grid.
Czech day-first: D. M. YYYY → YYYY-MM-DD (middle number is MONTH).
Example: "14. 10. 2020","18. 5. 2016","14. 9. 2010" → ["2020-10-14","2016-05-18","2010-09-14"].
Never invent 2020-10-18 by mixing columns. If only one draw, layout "single" and one date.
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


def _balanced_json_slice(text: str, start: int) -> str | None:
    """Return one top-level {...} starting at start, or None if unbalanced."""
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise json.JSONDecodeError("Expecting value", text, 0)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Prefer compact objects that look like our schema (avoid huge broken dumps).
    for m in re.finditer(r"\{", text):
        chunk = _balanced_json_slice(text, m.start())
        if not chunk or len(chunk) > 8000:
            continue
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and ("layout" in data or "draws" in data or "dates" in data):
            return data
    for m in re.finditer(r"\{", text):
        chunk = _balanced_json_slice(text, m.start())
        if not chunk or len(chunk) > 8000:
            continue
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise json.JSONDecodeError("Expecting value", text[:200], 0)


def _message_text(msg: dict[str, Any]) -> str:
    """Prefer final content; fall back to JSON object in reasoning dump."""
    content = str(msg.get("content") or "").strip()
    if content:
        # Huge CoT leaked into content — still try to pull a small JSON object out.
        if len(content) > 2000 and not content.lstrip().startswith("{"):
            try:
                return json.dumps(_extract_json(content), ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        elif content.lstrip().startswith("{") or len(content) <= 2000:
            return content
        try:
            return json.dumps(_extract_json(content), ensure_ascii=False)
        except json.JSONDecodeError:
            return content
    reasoning = str(msg.get("reasoning_content") or "").strip()
    if not reasoning:
        return ""
    try:
        return json.dumps(_extract_json(reasoning), ensure_ascii=False)
    except json.JSONDecodeError:
        return reasoning


def _scrape_iso_dates(text: str) -> list[str]:
    """Pull ISO dates from free text / broken model output."""
    from app.services.ocr_tables import find_dates_in_text

    out: list[str] = []
    for iso in find_dates_in_text(text or ""):
        if iso not in out:
            out.append(iso)
    for m in re.finditer(r"\b(20\d{2}-\d{2}-\d{2})\b", text or ""):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def _normalize_drawn_on(raw: str) -> str | None:
    """Accept YYYY-MM-DD or Czech D.M.YYYY / D. M. YYYY (+ optional time) → ISO."""
    from app.services.ocr_tables import _parse_date_token

    return _parse_date_token(raw or "")


def _normalize_doc_kind(raw: Any) -> str:
    """Return lab_results | not_lab_results | unknown."""
    s = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        # measured results
        "results": "lab_results",
        "lab": "lab_results",
        "lab_result": "lab_results",
        "lab_report": "lab_results",
        "report": "lab_results",
        "result": "lab_results",
        # not measured lab results (žádanka, other docs, …)
        "order": "not_lab_results",
        "orderform": "not_lab_results",
        "order_form": "not_lab_results",
        "request": "not_lab_results",
        "request_form": "not_lab_results",
        "zadanka": "not_lab_results",
        "žádanka": "not_lab_results",
        "zadanka_vysetreni": "not_lab_results",
        "not_lab": "not_lab_results",
        "non_lab": "not_lab_results",
        "other": "not_lab_results",
        "unrelated": "not_lab_results",
        "no_results": "not_lab_results",
    }
    s = aliases.get(s, s)
    if s in {"lab_results", "not_lab_results", "unknown"}:
        return s
    return "unknown"


def _empty_non_lab_payload(*, warning: str = "not_lab_results") -> dict[str, Any]:
    return {
        "doc_kind": "not_lab_results",
        "draws": [],
        "warnings": [warning],
    }


def _validate_smart_payload(data: dict[str, Any]) -> dict[str, Any]:
    warnings = list(data.get("warnings") or [])
    doc_kind = _normalize_doc_kind(
        data.get("doc_kind") or data.get("document_type") or data.get("doc_type")
    )
    # Explicit non-results → never emit biomarkers.
    if doc_kind == "not_lab_results":
        if "not_lab_results" not in warnings:
            warnings.append("not_lab_results")
        return {"doc_kind": "not_lab_results", "draws": [], "warnings": warnings}

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
            if len(label) < 2 or is_junk_label(label):
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
        results_out = filter_proposals(results_out)
        if results_out:
            lab = d.get("lab_name")
            lab_s = str(lab).strip() if lab not in (None, "") else None
            if lab_s and len(lab_s) > 120:
                lab_s = lab_s[:120]
            wp = d.get("workplace")
            wp_s = str(wp).strip() if wp not in (None, "") else None
            if wp_s and len(wp_s) > 120:
                wp_s = wp_s[:120]
            draws_out.append(
                {
                    "drawn_on": drawn_on,
                    "lab_name": lab_s,
                    "workplace": wp_s,
                    "results": results_out,
                }
            )
    # Omitted doc_kind + real rows → treat as lab_results (models often forget the field).
    if doc_kind == "unknown" and draws_out:
        doc_kind = "lab_results"
    elif doc_kind == "unknown" and not draws_out:
        doc_kind = "not_lab_results"
        if "not_lab_results" not in warnings:
            warnings.append("not_lab_results")
    return {"doc_kind": doc_kind, "draws": draws_out, "warnings": warnings}


def _draw_result_fingerprint(draw: dict[str, Any]) -> frozenset[tuple[str, float]]:
    return value_fingerprint(draw.get("results") or [])


def multi_column_draws_are_cloned(draws: list[dict[str, Any]]) -> bool:
    """True when ≥2 date draws share nearly identical marker/value fingerprints."""
    fps: list[frozenset[tuple[str, float]]] = []
    for d in draws:
        fp = _draw_result_fingerprint(d)
        if len(fp) >= 3:
            fps.append(fp)
    if len(fps) < 2:
        return False
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            if fingerprints_nearly_identical(fps[i], fps[j]):
                return True
    return False


def drop_cloned_multi_column_draws(parsed: dict[str, Any]) -> dict[str, Any]:
    """Keep one draw per unique fingerprint; prefer newest drawn_on when dropping clones."""
    draws = list(parsed.get("draws") or [])
    if len(draws) < 2 or not multi_column_draws_are_cloned(draws):
        return parsed
    kept: list[dict[str, Any]] = []
    seen_fps: list[frozenset[tuple[str, float]]] = []
    # Newest first so we keep the most recent column when fingerprints collide.
    ordered = sorted(draws, key=lambda d: str(d.get("drawn_on") or ""), reverse=True)
    warnings = list(parsed.get("warnings") or [])
    dropped = 0
    for d in ordered:
        fp = _draw_result_fingerprint(d)
        if len(fp) >= 3 and any(fingerprints_nearly_identical(fp, prev) for prev in seen_fps):
            dropped += 1
            continue
        kept.append(d)
        if fp:
            seen_fps.append(fp)
    if dropped:
        warnings.append(f"dropped_{dropped}_cloned_multi_column_draws")
    # Restore chronological order
    kept.sort(key=lambda d: str(d.get("drawn_on") or ""))
    return {"draws": kept, "warnings": warnings}


CLONE_COLUMN_HINT = (
    "CRITICAL FIX: Your previous answer copied the SAME numbers onto multiple date columns. "
    "This is a multi-column history table — each date column has DIFFERENT values. "
    "Re-read each column separately. Do NOT duplicate one column across dates."
)


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


def looks_like_non_lab_hallucination(proposals: list[dict]) -> bool:
    """Invented CBC from non-result docs: many hema rows, no refs, several zeros, almost no biochem."""
    if len(proposals) < 8:
        return False
    hema = bio = zeros = refs = 0
    for p in proposals:
        code = str(p.get("marker_code") or "").strip().lower()
        if code in HEMA_CODES:
            hema += 1
        if code in BIOCHEM_CODES:
            bio += 1
        try:
            if p.get("value") is not None and abs(float(p["value"])) < 1e-12:
                zeros += 1
        except (TypeError, ValueError):
            pass
        if p.get("lab_ref_low") is not None or p.get("lab_ref_high") is not None:
            refs += 1
    if bio >= 2:
        return False
    # Invented KO from checkbox/order sheet — real KO printouts almost always show ref ranges.
    return hema >= 8 and refs == 0 and zeros >= 2 and hema >= int(0.7 * len(proposals))


# Back-compat alias
looks_like_order_form_hallucination = looks_like_non_lab_hallucination


def _looks_like_collapsed_multi_dates(dates: list[str]) -> bool:
    """True when VLM labeled multi-column but dates are near-duplicates (day/month swap)."""
    clean: list[str] = []
    for raw in dates:
        iso = _normalize_drawn_on(str(raw))
        if iso and iso not in clean:
            clean.append(iso)
    return len(clean) >= 2 and not _looks_like_history_columns(clean)


def _looks_like_history_columns(dates: list[str]) -> bool:
    """True when dates look like multi-year comparison columns, not one draw."""
    parsed: list[date] = []
    for raw in dates:
        try:
            parsed.append(date.fromisoformat(str(raw)[:10]))
        except ValueError:
            continue
    parsed = sorted(set(parsed))
    if len(parsed) < 2:
        return False
    iso = [d.isoformat() for d in parsed]
    if _is_consecutive_day_run(iso):
        return False
    span_days = (parsed[-1] - parsed[0]).days
    return span_days >= 60 or len(parsed) >= 3


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
        # VLM often lists all column dates but mislabels layout as single.
        if _looks_like_history_columns(clean):
            return clean
        return clean[:1]
    if layout != "multi_column":
        # Unknown layout: never force a consecutive day run into extraction
        if _is_consecutive_day_run(clean) or len(clean) > 8:
            return []
        # Near-duplicates without year span → keep newest/first only (not fake columns)
        if _looks_like_collapsed_multi_dates(clean):
            return clean[:1]
        return clean[:3]
    # multi_column: still reject absurd consecutive calendars (not real lab columns)
    if _is_consecutive_day_run(clean):
        return []
    # Near-duplicate same-year pairs (e.g. 2020-10-14 + 2020-10-18) are not history columns.
    if not _looks_like_history_columns(clean):
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


def _nvidia_chat(
    content: list[dict],
    *,
    max_tokens: int = 8192,
    temperature: float = 0.1,
) -> str:
    settings = get_settings()
    model = settings.smart_model or "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
    payload = {
        "model": model,
        # System message keeps reasoning/omni models from dumping chain-of-thought into content.
        "messages": [
            {"role": "system", "content": JSON_ONLY_SYSTEM},
            {"role": "user", "content": content},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        # Nemotron omni/reasoning otherwise fills the budget with CoT and returns empty content.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {
        "Authorization": f"Bearer {settings.nvidia_api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    # Omni/reasoning VLMs are slower than nano-12b on dense tables.
    with httpx.Client(timeout=240.0) as client:
        resp = client.post(f"{NVIDIA_BASE}/chat/completions", headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"NVIDIA API {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
    msg = body["choices"][0]["message"]
    text = _message_text(msg if isinstance(msg, dict) else dict(msg))
    if not text.strip():
        finish = (body.get("choices") or [{}])[0].get("finish_reason")
        raise RuntimeError(f"NVIDIA returned empty content (finish={finish})")
    return text


def _image_content(pages: list[Path]) -> list[dict]:
    parts: list[dict] = []
    for p in pages:
        mime, b64 = _encode_image(p)
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return parts


def _finalize_discovery(layout: str, raw_dates: list[Any]) -> tuple[str, list[str]]:
    if layout not in {"single", "multi_column", "unknown"}:
        layout = "unknown"
    tentative: list[str] = []
    for raw in raw_dates:
        iso = _normalize_drawn_on(str(raw))
        if iso and iso not in tentative:
            tentative.append(iso)
    if layout in {"single", "unknown"} and _looks_like_history_columns(tentative):
        layout = "multi_column"
    # Fake multi (near-duplicate dates) → drop to unknown so caller can retry.
    if layout == "multi_column" and _looks_like_collapsed_multi_dates(tentative):
        logger.warning("Rejecting collapsed multi-column dates: %s", tentative)
        layout = "unknown"
        dates = _sanitize_discovered_dates(list(raw_dates), layout="unknown")
        return layout, dates
    dates = _sanitize_discovered_dates(list(raw_dates), layout=layout)
    if layout == "multi_column" and not dates:
        layout = "unknown"
    return layout, dates


def _discover_dates(pages: list[Path]) -> tuple[str, list[str], str]:
    last_text = ""
    attempts: list[tuple[list[dict], int]] = [
        ([{"type": "text", "text": DATE_DISCOVER_HINT}, *_image_content(pages)], 512),
        ([{"type": "text", "text": DATE_DISCOVER_SHORT}, *_image_content(pages)], 384),
    ]
    best: tuple[str, list[str], str] | None = None
    for content, max_tokens in attempts:
        try:
            last_text = _nvidia_chat(content, max_tokens=max_tokens, temperature=0.0)
            data = _extract_json(last_text)
            doc_kind = _normalize_doc_kind(
                data.get("doc_kind") or data.get("document_type") or data.get("doc_type")
            )
            if doc_kind == "not_lab_results":
                return "unknown", [], "not_lab_results"
            layout = str(data.get("layout") or "unknown").strip().lower()
            layout, dates = _finalize_discovery(layout, list(data.get("dates") or []))
            if _looks_like_history_columns(dates):
                return "multi_column", dates, "lab_results"
            if layout == "single" and dates:
                return layout, dates, doc_kind if doc_kind != "unknown" else "lab_results"
            # Keep partial result but keep trying for real history columns.
            if dates and (best is None or len(dates) > len(best[1])):
                best = (layout, dates, doc_kind)
            if layout == "multi_column" and not _looks_like_history_columns(dates):
                logger.warning("Date discovery multi without year span: %s — retrying", dates)
                continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("Date discovery attempt failed: %s", exc)

    scraped = _scrape_iso_dates(last_text)
    if scraped:
        layout, dates = _finalize_discovery("unknown", scraped)
        if _looks_like_history_columns(dates):
            logger.info("Date discovery recovered via scrape: layout=%s dates=%s", layout, dates)
            return "multi_column", dates, "lab_results"
        if dates and (best is None or len(dates) > len(best[1])):
            best = (layout, dates, "unknown")

    if best:
        return best
    return "unknown", [], "unknown"


def _flatten_draws(parsed: dict[str, Any]) -> list[dict]:
    proposals: list[dict] = []
    for d in parsed.get("draws") or []:
        lab = d.get("lab_name")
        lab_s = str(lab).strip() if lab not in (None, "") else ""
        wp = d.get("workplace")
        wp_s = str(wp).strip() if wp not in (None, "") else ""
        for r in d.get("results") or []:
            row = dict(r)
            if lab_s:
                row["proposed_lab_name"] = lab_s
            if wp_s:
                row["proposed_workplace"] = wp_s
            proposals.append(row)
    return filter_proposals(proposals)


def _build_extract_content(
    pages: list[Path],
    *,
    marker_hints: list[str] | None,
    layout: str,
    discovered: list[str],
    force_single: bool = False,
    user_hint: str | None = None,
) -> list[dict]:
    content: list[dict] = [{"type": "text", "text": SMART_SCHEMA_HINT}]
    hint = (user_hint or "").strip()[:1500]
    if hint:
        content.append(
            {
                "type": "text",
                "text": (
                    "USER CORRECTION — follow this carefully when interpreting the document:\n"
                    + hint
                ),
            }
        )
    effective_layout = layout
    if (
        not force_single
        and effective_layout != "multi_column"
        and _looks_like_history_columns(discovered)
    ):
        effective_layout = "multi_column"
    if force_single or effective_layout == "single":
        content.append({"type": "text", "text": SINGLE_DRAW_HINT})
        if discovered:
            content.append(
                {
                    "type": "text",
                    "text": f"Preferred sample date (Datum odběru) if visible: {discovered[0]}.",
                }
            )
    elif effective_layout == "multi_column" and discovered:
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
    elif not force_single:
        content.append(
            {
                "type": "text",
                "text": (
                    "IMPORTANT: Czech hospital comparison tables often have several DATE COLUMNS "
                    "(e.g. 14. 10. 2020 | 18. 5. 2016 | 14. 9. 2010). If you see multiple date "
                    "headers above value columns, emit one draws[] entry PER column date — "
                    "do not keep only the newest column."
                ),
            }
        )
    if marker_hints:
        content.append(
            {
                "type": "text",
                "text": (
                    "CATALOG — map each Czech/English analyte to exactly one marker_code from this list "
                    "(format code=Czech name). This mapping is your main job; set marker_code whenever "
                    "possible, omit only if unmatched: "
                    + ", ".join(marker_hints[:300])
                ),
            }
        )
    content.extend(_image_content(pages))
    return content


def run_smart_extract(
    storage_path: str,
    marker_hints: list[str] | None = None,
    *,
    user_hint: str | None = None,
) -> tuple[str, list[dict], dict]:
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
        doc_kind = "unknown"
        try:
            layout, discovered, doc_kind = _discover_dates(pages)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Date discovery failed: %s", exc)

        model = settings.smart_model or "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
        if doc_kind == "not_lab_results":
            empty = _empty_non_lab_payload()
            text = json.dumps(empty, ensure_ascii=False)
            logger.info("Smart extract: not lab results — skipping extract")
            return (
                text,
                [],
                {
                    "engine": "nvidia",
                    "model": model,
                    "mode": "smart",
                    "layout": "not_lab_results",
                    "doc_kind": "not_lab_results",
                    "dates": [],
                    "discovered_dates": [],
                    "lab_name": None,
                    "workplace": None,
                    "warnings": empty["warnings"],
                },
            )

        content = _build_extract_content(
            pages,
            marker_hints=marker_hints,
            layout=layout,
            discovered=discovered,
            user_hint=user_hint,
        )
        text = _nvidia_chat(content, max_tokens=8192)
        parsed = _validate_smart_payload(_extract_json(text))
        proposals = _flatten_draws(parsed)

        got_dates = sorted({p.get("proposed_drawn_on") for p in proposals if p.get("proposed_drawn_on")})

        # Fake multi (e.g. 2020-10-14 + 2020-10-18): re-probe real column headers.
        if _looks_like_collapsed_multi_dates(got_dates):
            logger.warning(
                "Extract dates look collapsed (day/month swap?): %s — re-probing",
                got_dates,
            )
            try:
                layout2, discovered2, doc_kind2 = _discover_dates(pages)
                if doc_kind2 == "not_lab_results":
                    empty = _empty_non_lab_payload()
                    text = json.dumps(empty, ensure_ascii=False)
                    proposals, parsed = [], empty
                    got_dates = []
                    layout, discovered, doc_kind = "not_lab_results", [], "not_lab_results"
                elif _looks_like_history_columns(discovered2):
                    layout, discovered = "multi_column", discovered2
                    content_fix = _build_extract_content(
                        pages,
                        marker_hints=marker_hints,
                        layout=layout,
                        discovered=discovered,
                        user_hint=user_hint,
                    )
                    text_fix = _nvidia_chat(content_fix, max_tokens=8192)
                    parsed_fix = _validate_smart_payload(_extract_json(text_fix))
                    props_fix = _flatten_draws(parsed_fix)
                    got_fix = sorted(
                        {
                            p.get("proposed_drawn_on")
                            for p in props_fix
                            if p.get("proposed_drawn_on")
                        }
                    )
                    if _looks_like_history_columns(got_fix):
                        text, proposals, parsed = text_fix, props_fix, parsed_fix
                        got_dates = got_fix
                    elif props_fix and not _looks_like_collapsed_multi_dates(got_fix):
                        text, proposals, parsed = text_fix, props_fix, parsed_fix
                        got_dates = got_fix
                    else:
                        # Keep hallucinated pair out of review — prefer single newest date
                        keep = discovered2[0]
                        filtered = [p for p in props_fix if p.get("proposed_drawn_on") == keep]
                        if filtered:
                            text, proposals, parsed = text_fix, filtered, parsed_fix
                            got_dates = [keep]
                            layout = "single"
                            discovered = [keep]
                        else:
                            keep = got_dates[0]
                            proposals = [p for p in proposals if p.get("proposed_drawn_on") == keep]
                            got_dates = [keep] if proposals else []
                            layout = "single"
                            discovered = [keep]
                else:
                    keep = got_dates[0]
                    proposals = [p for p in proposals if p.get("proposed_drawn_on") == keep]
                    got_dates = [keep] if proposals else []
                    layout = "single"
                    discovered = discovered2[:1] if discovered2 else [keep]
            except Exception as exc:  # noqa: BLE001
                logger.warning("Smart collapsed-date re-probe failed: %s", exc)
                keep = got_dates[0]
                proposals = [p for p in proposals if p.get("proposed_drawn_on") == keep]
                got_dates = [keep] if proposals else []
                layout = "single"

        # If extract collapsed to ≤1 date, re-probe column headers and retry once.
        if len(got_dates) <= 1:
            try:
                layout2, discovered2, doc_kind2 = _discover_dates(pages)
                if doc_kind2 == "not_lab_results":
                    empty = _empty_non_lab_payload()
                    text = json.dumps(empty, ensure_ascii=False)
                    proposals, parsed = [], empty
                    got_dates = []
                    layout, discovered, doc_kind = "not_lab_results", [], "not_lab_results"
                elif _looks_like_history_columns(discovered2) and (
                    len(discovered2) > len(discovered) or layout != "multi_column"
                ):
                    logger.info(
                        "Re-probed multi-column dates after single-draw extract: %s",
                        discovered2,
                    )
                    layout, discovered = "multi_column", discovered2
                    content_retry0 = _build_extract_content(
                        pages,
                        marker_hints=marker_hints,
                        layout=layout,
                        discovered=discovered,
                        user_hint=user_hint,
                    )
                    text0 = _nvidia_chat(content_retry0, max_tokens=8192)
                    parsed0 = _validate_smart_payload(_extract_json(text0))
                    props0 = _flatten_draws(parsed0)
                    got0 = sorted(
                        {p.get("proposed_drawn_on") for p in props0 if p.get("proposed_drawn_on")}
                    )
                    if len(got0) > len(got_dates):
                        text, proposals, parsed = text0, props0, parsed0
                        got_dates = got0
            except Exception as exc:  # noqa: BLE001
                logger.warning("Smart multi-column re-probe failed: %s", exc)

        # Multi-column: retry if discovery dates missing from extract
        missing = [d for d in discovered if d not in got_dates]
        if layout == "multi_column" and missing and discovered:
            content_retry = _build_extract_content(
                pages,
                marker_hints=marker_hints,
                layout=layout,
                discovered=discovered,
                user_hint=user_hint,
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

        # Cloned multi-column columns (same values on every date) → retry once, then drop clones
        if multi_column_draws_are_cloned(parsed.get("draws") or []):
            logger.warning(
                "Smart multi-column draws look cloned; retrying with column-diff hint"
            )
            try:
                content_clone = _build_extract_content(
                    pages,
                    marker_hints=marker_hints,
                    layout="multi_column" if layout != "single" else layout,
                    discovered=discovered or got_dates,
                    user_hint=user_hint,
                )
                content_clone.insert(1, {"type": "text", "text": CLONE_COLUMN_HINT})
                text_c = _nvidia_chat(content_clone, max_tokens=8192)
                parsed_c = _validate_smart_payload(_extract_json(text_c))
                if not multi_column_draws_are_cloned(parsed_c.get("draws") or []):
                    text, proposals, parsed = text_c, _flatten_draws(parsed_c), parsed_c
                    got_dates = sorted(
                        {p.get("proposed_drawn_on") for p in proposals if p.get("proposed_drawn_on")}
                    )
                else:
                    parsed = drop_cloned_multi_column_draws(parsed_c)
                    proposals = _flatten_draws(parsed)
                    got_dates = sorted(
                        {p.get("proposed_drawn_on") for p in proposals if p.get("proposed_drawn_on")}
                    )
                    text = text_c
            except Exception as exc:  # noqa: BLE001
                logger.warning("Smart clone-column retry failed: %s", exc)
                parsed = drop_cloned_multi_column_draws(parsed)
                proposals = _flatten_draws(parsed)
                got_dates = sorted(
                    {p.get("proposed_drawn_on") for p in proposals if p.get("proposed_drawn_on")}
                )

        # Not lab results (or invented CBC from non-result docs): discard, no single-draw retry
        if parsed.get("doc_kind") == "not_lab_results" or looks_like_non_lab_hallucination(
            proposals
        ):
            logger.info(
                "Smart extract discarded — not lab results (n=%s)",
                len(proposals),
            )
            proposals = []
            parsed = _empty_non_lab_payload()
            got_dates = []
            doc_kind = "not_lab_results"
            layout = "not_lab_results"

        # Hallucination guard: one marker / zero values / date spam → single-draw retry
        elif proposals and looks_like_hallucinated_extract(proposals):
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
                    user_hint=user_hint,
                )
                text3 = _nvidia_chat(content_single, max_tokens=8192)
                parsed3 = _validate_smart_payload(_extract_json(text3))
                props3 = _flatten_draws(parsed3)
                if parsed3.get("doc_kind") == "not_lab_results" or looks_like_non_lab_hallucination(
                    props3
                ):
                    text, proposals, parsed = text3, [], _empty_non_lab_payload()
                    got_dates = []
                    doc_kind = "not_lab_results"
                    layout = "not_lab_results"
                elif props3 and not looks_like_hallucinated_extract(props3):
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

        # Still garbage → empty (caller must not fall back to classic OCR)
        if proposals and (
            looks_like_hallucinated_extract(proposals)
            or looks_like_non_lab_hallucination(proposals)
        ):
            logger.error("Smart extract still hallucinated; returning empty")
            proposals = []
            parsed = {"draws": [], "warnings": ["hallucinated_extract_discarded"]}
            got_dates = []

        lab_name = None
        workplace = None
        for d in parsed.get("draws") or []:
            if not lab_name and d.get("lab_name"):
                lab_name = d["lab_name"]
            if not workplace and d.get("workplace"):
                workplace = d["workplace"]
            if lab_name and workplace:
                break
        meta = {
            "engine": "nvidia",
            "model": model,
            "mode": "smart",
            "layout": layout,
            "doc_kind": doc_kind if doc_kind != "unknown" else parsed.get("doc_kind") or "unknown",
            "dates": got_dates,
            "discovered_dates": discovered,
            "lab_name": lab_name,
            "workplace": workplace,
            "warnings": parsed.get("warnings") or [],
        }
        return text, proposals, meta
