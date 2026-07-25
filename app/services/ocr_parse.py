"""Shared OCR parsing helpers: units, line regex, word-box line grouping."""

from __future__ import annotations

import re
from typing import Any

_LINE_RE = re.compile(
    r"^(?P<name>[A-Za-zÁ-ž0-9\s\.\-\(\)/%]+?)\s+"
    r"(?P<value>\d+[.,]?\d*)\s*"
    r"(?P<unit>[A-Za-zµμ%/\^\d]+)?\s*"
    r"(?:(?P<low>\d+[.,]?\d*)\s*[-–]\s*(?P<high>\d+[.,]?\d*))?",
    re.UNICODE,
)


def normalize_unit(unit: str) -> str:
    """Normalize OCR/report units to catalog spellings (value unchanged)."""
    if not unit:
        return ""
    u = unit.strip()
    u = u.replace("μ", "u").replace("µ", "u").replace("Μ", "u")
    u = u.replace("μkat", "ukat").replace("µkat", "ukat")
    u = u.replace("¹⁰", "10").replace("⁹", "9").replace("¹²", "12")
    u = u.replace("×", "x").replace("⋅", ".")
    compact = u.lower().replace(" ", "")
    if compact in {"pkat", "pkat/l"} or compact.startswith("pkat"):
        compact = "u" + compact[1:]

    aliases = {
        "g/l": "g/l",
        "g/dl": "g/dl",
        "ukat/l": "ukat/l",
        "ukat": "ukat",
        "u/l": "U/l",
        "iu/l": "IU/l",
        "iu/ml": "IU/ml",
        "miu/l": "mIU/l",
        "mmol/l": "mmol/l",
        "umol/l": "umol/l",
        "mg/dl": "mg/dl",
        "ug/l": "ug/l",
        "ug/dl": "ug/dl",
        "ng/ml": "ng/ml",
        "ng/l": "ng/l",
        "10^9/l": "10^9/l",
        "10e9/l": "10^9/l",
        "x10^9/l": "10^9/l",
        "10*9/l": "10^9/l",
        "10^12/l": "10^12/l",
        "10e12/l": "10^12/l",
        "x10^12/l": "10^12/l",
        "l/l": "1",
        "ll": "1",
        "l": "1",
        "ratio": "1",
        "ml/min/1.73m2": "ml/min/1.73m2",
        "ml/min/1,73m2": "ml/min/1.73m2",
        "ml/s": "ml/s",
        "mm/h": "mm/h",
        "mm/hod": "mm/h",
        "%hba1c": "%HbA1c",
    }
    if compact in aliases:
        return aliases[compact]
    return compact


def _row_from_match(match: re.Match[str]) -> dict[str, Any] | None:
    name = match.group("name").strip(" :-")
    if len(name) < 2:
        return None
    value = float(match.group("value").replace(",", "."))
    unit = normalize_unit(match.group("unit") or "")
    low = match.group("low")
    high = match.group("high")
    return {
        "label": name,
        "value": value,
        "unit": unit,
        "lab_ref_low": float(low.replace(",", ".")) if low else None,
        "lab_ref_high": float(high.replace(",", ".")) if high else None,
    }


def parse_ocr_lines(text: str) -> list[dict]:
    results: list[dict] = []
    text = (text or "").replace("μ", "u").replace("µ", "u")
    for raw in text.splitlines():
        line = " ".join(raw.strip().split())
        if len(line) < 3:
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        row = _row_from_match(match)
        if row:
            results.append(row)
    return results


def group_words_to_lines(
    words: list[dict],
    y_tol_ratio: float = 0.6,
) -> list[str]:
    """Group OCR word boxes into text lines by vertical proximity.

    Each word: {"text": str, "x": float, "y": float, "h": float} (top-left).
    """
    if not words:
        return []
    items = [w for w in words if (w.get("text") or "").strip()]
    if not items:
        return []
    items.sort(key=lambda w: (w["y"], w["x"]))
    lines: list[list[dict]] = []
    for w in items:
        h = max(float(w.get("h") or 10.0), 1.0)
        placed = False
        for line in lines:
            avg_y = sum(x["y"] for x in line) / len(line)
            avg_h = sum(max(float(x.get("h") or 10.0), 1.0) for x in line) / len(line)
            if abs(w["y"] - avg_y) <= y_tol_ratio * max(h, avg_h):
                line.append(w)
                placed = True
                break
        if not placed:
            lines.append([w])
    out: list[str] = []
    for line in lines:
        line.sort(key=lambda w: w["x"])
        out.append(" ".join(w["text"].strip() for w in line if w["text"].strip()))
    return out


def parse_from_word_boxes(words: list[dict]) -> tuple[str, list[dict]]:
    lines = group_words_to_lines(words)
    raw = "\n".join(lines)
    return raw, parse_ocr_lines(raw)
