"""Detect multi-date lab tables (marker × date columns)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# Match ISO or Czech D. M. YYYY / D.M.YYYY, optional trailing time.
_DATE_FIND_RE = re.compile(
    r"(?:"
    r"(?P<iso>\d{4}-\d{2}-\d{2})"
    r"|"
    r"(?P<d>\d{1,2})\s*[.\-/]\s*(?P<m>\d{1,2})\s*[.\-/]\s*(?P<y>\d{2,4})"
    r")"
    r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?"
)

_NUM_RE = re.compile(r"^-?\d+[.,]?\d*$")
_NUM_FIND_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_REF_RE = re.compile(r"^(?P<low>\d+[.,]?\d*)\s*[-–]\s*(?P<high>\d+[.,]?\d*)$")
_REF_FIND_RE = re.compile(r"(\d+[.,]?\d*)\s*[-–]\s*(\d+[.,]?\d*)")


def _match_to_iso(m: re.Match) -> str | None:
    if m.groupdict().get("iso"):
        return m.group("iso")
    try:
        d = int(m.group("d"))
        mo = int(m.group("m"))
        y = int(m.group("y"))
    except (IndexError, TypeError, ValueError):
        return None
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _parse_date_token(token: str) -> str | None:
    """Parse a single date token (allows spaces and optional time)."""
    t = (token or "").strip()
    if not t:
        return None
    m = _DATE_FIND_RE.match(t)
    if not m:
        # compact form without spaces already handled by regex; try stripping spaces
        compact = re.sub(r"\s+", "", re.sub(r"\s+\d{1,2}:\d{2}(?::\d{2})?\s*$", "", t))
        m = re.match(
            r"^(?:(?P<iso>\d{4}-\d{2}-\d{2})"
            r"|(?P<d>\d{1,2})[.\-/](?P<m>\d{1,2})[.\-/](?P<y>\d{2,4}))$",
            compact,
        )
        if not m:
            return None
    return _match_to_iso(m)


def find_dates_in_text(text: str) -> list[str]:
    """Find all dates in a string (ISO order of appearance)."""
    out: list[str] = []
    for m in _DATE_FIND_RE.finditer(text or ""):
        iso = _match_to_iso(m)
        if iso:
            out.append(iso)
    return out


def _split_row(line: str) -> list[str]:
    if "\t" in line:
        parts = [p.strip() for p in line.split("\t")]
    else:
        parts = [p for p in re.split(r"\s{2,}", line.strip()) if p.strip()]
    if len(parts) < 3:
        parts = line.split()
    return [p.strip() for p in parts if p.strip()]


def _parse_data_row_for_dates(line: str, n_dates: int) -> dict[str, Any] | None:
    """Parse 'Label  v1 v2 v3  low-high  unit' style rows."""
    raw = line.strip()
    if len(raw) < 3 or n_dates < 1:
        return None
    # Skip pure section headers / dates
    if find_dates_in_text(raw) and not _NUM_FIND_RE.search(re.sub(_DATE_FIND_RE, " ", raw)):
        return None

    # Label = leading non-numeric words until we hit a run of numbers for values
    # Strategy: find all numbers; if enough for dates (+ optional ref), use them.
    nums = list(_NUM_FIND_RE.finditer(raw))
    if len(nums) < n_dates:
        return None

    first_num = nums[0].start()
    label = raw[:first_num].strip(" :-|\t#")
    label = re.sub(r"\s+", " ", label).strip()
    if len(label) < 2:
        return None
    # Skip very generic headers
    low_label = label.lower()
    if low_label in {"ref", "ref. meze", "rozměr", "rozmer", "hodnocení", "hodnoceni", "název metody", "nazev metody"}:
        return None

    values_list = [float(n.group(0).replace(",", ".")) for n in nums[:n_dates]]
    rest = raw[nums[n_dates - 1].end() :]
    ref_low = ref_high = None
    rm = _REF_FIND_RE.search(rest)
    if rm:
        ref_low = float(rm.group(1).replace(",", "."))
        ref_high = float(rm.group(2).replace(",", "."))

    # unit: trailing token with letter or /
    unit = ""
    unit_m = re.search(r"([a-zA-Zμµ%°][a-zA-Z0-9μµ/%^.\-]*)\s*$", rest)
    if unit_m and not _NUM_RE.match(unit_m.group(1).replace(",", ".")):
        unit = unit_m.group(1)

    return {
        "label": label,
        "unit": unit,
        "lab_ref_low": ref_low,
        "lab_ref_high": ref_high,
        "values_list": values_list,
    }


def parse_multi_date_table(text: str) -> dict[str, Any] | None:
    """Parse a whitespace/tab table with date headers.

    Returns None if fewer than 2 date columns found.
    Shape:
      {
        "dates": ["2025-01-12", "2025-06-03"],
        "rows": [
          {"label": "AST", "unit": "", "lab_ref_low": ..., "lab_ref_high": ...,
           "values": {"2025-01-12": 0.48, "2025-06-03": 0.42}}
        ]
      }
    """
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) < 2:
        return None

    header_idx = None
    dates: list[str] = []
    # Prefer a line with ≥2 dates (comparison table headers).
    for i, line in enumerate(lines[:15]):
        found = find_dates_in_text(line)
        if len(found) >= 2:
            header_idx = i
            dates = found
            break
    if header_idx is None:
        # Fallback: token-based header (legacy compact dates)
        date_cols: list[tuple[int, str]] = []
        for i, line in enumerate(lines[:8]):
            parts = _split_row(line)
            found_cols: list[tuple[int, str]] = []
            for j, p in enumerate(parts):
                iso = _parse_date_token(p)
                if iso:
                    found_cols.append((j, iso))
            if len(found_cols) >= 2:
                header_idx = i
                dates = [d for _, d in found_cols]
                date_cols = found_cols
                break
        if header_idx is None:
            return None
        return _parse_legacy_column_indexed(lines, header_idx, dates, date_cols)

    rows_out: list[dict] = []
    for line in lines[header_idx + 1 :]:
        parsed_row = _parse_data_row_for_dates(line, len(dates))
        if not parsed_row:
            continue
        values = {dates[k]: parsed_row["values_list"][k] for k in range(len(dates))}
        rows_out.append(
            {
                "label": parsed_row["label"],
                "unit": parsed_row["unit"],
                "lab_ref_low": parsed_row["lab_ref_low"],
                "lab_ref_high": parsed_row["lab_ref_high"],
                "values": values,
            }
        )

    if len(rows_out) < 2:
        return None
    return {"dates": dates, "rows": rows_out}


def _parse_legacy_column_indexed(
    lines: list[str],
    header_idx: int,
    dates: list[str],
    date_cols: list[tuple[int, str]],
) -> dict[str, Any] | None:
    date_index = {j: d for j, d in date_cols}
    rows_out: list[dict] = []
    for line in lines[header_idx + 1 :]:
        parts = _split_row(line)
        if len(parts) < 2:
            continue
        first_date_j = min(j for j, _ in date_cols)
        if first_date_j == 0:
            if _parse_date_token(parts[0]):
                continue
            label_parts = [parts[0]]
            value_parts = parts[1:]
            values: dict[str, float] = {}
            for k, d in enumerate(dates):
                if k < len(value_parts) and _NUM_RE.match(value_parts[k].replace(" ", "")):
                    values[d] = float(value_parts[k].replace(",", "."))
            ref_low = ref_high = None
            if len(value_parts) > len(dates):
                ref_token = value_parts[len(dates)]
                rm = _REF_RE.match(ref_token)
                if rm:
                    ref_low = float(rm.group("low").replace(",", "."))
                    ref_high = float(rm.group("high").replace(",", "."))
            label = " ".join(label_parts).strip()
            if label and values:
                rows_out.append(
                    {
                        "label": label,
                        "unit": "",
                        "lab_ref_low": ref_low,
                        "lab_ref_high": ref_high,
                        "values": values,
                    }
                )
            continue

        label = " ".join(parts[:first_date_j]).strip(" :-")
        if len(label) < 2:
            continue
        values = {}
        for j, d in date_index.items():
            if j < len(parts) and _NUM_RE.match(parts[j].replace(" ", "")):
                values[d] = float(parts[j].replace(",", "."))
        ref_low = ref_high = None
        for p in parts[first_date_j + len(date_cols) :]:
            rm = _REF_RE.match(p)
            if rm:
                ref_low = float(rm.group("low").replace(",", "."))
                ref_high = float(rm.group("high").replace(",", "."))
                break
        if not values:
            continue
        rows_out.append(
            {
                "label": label,
                "unit": "",
                "lab_ref_low": ref_low,
                "lab_ref_high": ref_high,
                "values": values,
            }
        )

    if len(rows_out) < 2:
        return None
    return {"dates": dates, "rows": rows_out}


def flatten_multi_date(parsed: dict[str, Any]) -> list[dict]:
    """Flatten to proposal rows with proposed_drawn_on + value."""
    out: list[dict] = []
    for row in parsed["rows"]:
        for drawn_on, value in row["values"].items():
            out.append(
                {
                    "label": row["label"],
                    "value": value,
                    "unit": row.get("unit") or "",
                    "lab_ref_low": row.get("lab_ref_low"),
                    "lab_ref_high": row.get("lab_ref_high"),
                    "proposed_drawn_on": drawn_on,
                }
            )
    return out


def parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        # Czech with spaces
        iso = _parse_date_token(raw)
        if iso:
            return date.fromisoformat(iso)
        return None


def date_to_datetime(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time())
