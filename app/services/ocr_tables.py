"""Detect multi-date lab tables (marker × date columns)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

_DATE_RE = re.compile(
    r"^(?:"
    r"(?P<iso>\d{4}-\d{2}-\d{2})"
    r"|(?P<dmy>(?P<d>\d{1,2})[.\-/](?P<m>\d{1,2})[.\-/](?P<y>\d{2,4}))"
    r")$"
)
_NUM_RE = re.compile(r"^-?\d+[.,]?\d*$")
_REF_RE = re.compile(r"^(?P<low>\d+[.,]?\d*)\s*[-–]\s*(?P<high>\d+[.,]?\d*)$")


def _parse_date_token(token: str) -> str | None:
    t = token.strip()
    m = _DATE_RE.match(t)
    if not m:
        return None
    if m.group("iso"):
        return m.group("iso")
    d, mo, y = int(m.group("d")), int(m.group("m")), int(m.group("y"))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _split_row(line: str) -> list[str]:
    if "\t" in line:
        parts = [p.strip() for p in line.split("\t")]
    else:
        parts = [p for p in re.split(r"\s{2,}", line.strip()) if p.strip()]
    if len(parts) < 3:
        parts = line.split()
    return [p.strip() for p in parts if p.strip()]


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
    date_cols: list[tuple[int, str]] = []
    for i, line in enumerate(lines[:8]):
        parts = _split_row(line)
        found: list[tuple[int, str]] = []
        for j, p in enumerate(parts):
            iso = _parse_date_token(p)
            if iso:
                found.append((j, iso))
        if len(found) >= 2:
            header_idx = i
            date_cols = found
            break
    if header_idx is None:
        return None

    header_parts = _split_row(lines[header_idx])
    dates = [d for _, d in date_cols]
    date_index = {j: d for j, d in date_cols}

    # optional ref column: last non-date col that looks like "ref" header or numeric range cells
    rows_out: list[dict] = []
    for line in lines[header_idx + 1 :]:
        parts = _split_row(line)
        if len(parts) < 2:
            continue
        # label = first non-date-looking token(s) before first date column index
        first_date_j = min(j for j, _ in date_cols)
        label_parts = parts[:first_date_j] if first_date_j > 0 else [parts[0]]
        # if split left label only as parts[0]
        if first_date_j == 0:
            # dates start at 0 — unlikely; treat parts[0] as label if not date
            if _parse_date_token(parts[0]):
                continue
            label_parts = [parts[0]]
            value_parts = parts[1:]
            # remap: assume consecutive date columns after label
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

        label = " ".join(label_parts).strip(" :-")
        if len(label) < 2:
            continue
        values = {}
        for j, d in date_index.items():
            if j < len(parts) and _NUM_RE.match(parts[j].replace(" ", "")):
                values[d] = float(parts[j].replace(",", "."))
        ref_low = ref_high = None
        # trailing ref range
        for p in parts[first_date_j + len(date_cols) :]:
            rm = _REF_RE.match(p)
            if rm:
                ref_low = float(rm.group("low").replace(",", "."))
                ref_high = float(rm.group("high").replace(",", "."))
                break
            # "0.10-0.70" might be one token already handled; also "low high" skip
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
        return None


def date_to_datetime(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time())
