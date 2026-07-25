"""Match blood draws / extracts: same report fingerprint, panel family, time window."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

DRAW_TIME_WINDOW = timedelta(hours=2)

HEMA_CODES = frozenset(
    {
        "wbc",
        "rbc",
        "hgb",
        "hct",
        "plt",
        "mcv",
        "mch",
        "mchc",
        "rdw",
        "mpv",
        "neutrophils",
        "neutrophils_abs",
        "lymphocytes",
        "lymphocytes_abs",
        "monocytes",
        "monocytes_abs",
        "eosinophils",
        "eosinophils_abs",
        "basophils",
        "basophils_abs",
        "reticulocytes",
    }
)

BIOCHEM_CODES = frozenset(
    {
        "glucose",
        "urea",
        "creatinine",
        "egfr",
        "alt",
        "ast",
        "ggt",
        "bilirubin",
        "cholesterol",
        "hdl",
        "ldl",
        "triglycerides",
        "sodium",
        "potassium",
        "chloride",
        "calcium",
        "magnesium",
        "phosphate",
        "albumin",
        "total_protein",
        "ferritin",
        "iron",
        "transferrin",
        "crp",
        "hs_crp",
        "tsh",
        "ft4",
        "ft3",
        "psa",
        "hba1c",
        "uric_acid",
        "ck",
        "ldh",
        "alp",
        "amylase",
        "lipase",
    }
)


def _marker_key(row: dict[str, Any] | Any) -> str:
    if isinstance(row, dict):
        code = (row.get("marker_code") or "").strip().lower()
        label = (row.get("label") or "").strip().casefold()
    else:
        code = (getattr(row, "marker_code", None) or "").strip().lower()
        label = (getattr(row, "label", None) or "").strip().casefold()
    return code or label


def _row_value(row: dict[str, Any] | Any) -> float | None:
    try:
        if isinstance(row, dict):
            return float(row["value"])
        return float(getattr(row, "value"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def value_fingerprint(rows: Iterable[dict[str, Any] | Any]) -> frozenset[tuple[str, float]]:
    """Stable (marker, rounded value) pairs for clone / same-report detection."""
    out: set[tuple[str, float]] = set()
    for row in rows:
        key = _marker_key(row)
        val = _row_value(row)
        if not key or val is None:
            continue
        out.add((key, round(val, 4)))
    return frozenset(out)


def marker_key_set(rows: Iterable[dict[str, Any] | Any]) -> frozenset[str]:
    return frozenset(k for k in (_marker_key(r) for r in rows) if k)


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def panel_family(rows: Iterable[dict[str, Any] | Any]) -> str:
    """Return hema | biochem | mixed | unknown from marker mix."""
    codes = {k for k in marker_key_set(rows) if k}
    hema_n = len(codes & HEMA_CODES)
    bio_n = len(codes & BIOCHEM_CODES)
    if hema_n >= 2 and bio_n == 0:
        return "hema"
    if bio_n >= 2 and hema_n == 0:
        return "biochem"
    if hema_n >= 2 and bio_n >= 2:
        return "mixed"
    if hema_n >= 2:
        return "hema"
    if bio_n >= 2:
        return "biochem"
    return "unknown"


def panels_compatible(a: str, b: str) -> bool:
    if a == "unknown" or b == "unknown" or a == "mixed" or b == "mixed":
        return True
    return a == b


def _row_panel_bucket(row: dict[str, Any] | Any) -> str:
    code = _marker_key(row)
    if code in HEMA_CODES:
        return "hema"
    if code in BIOCHEM_CODES:
        return "biochem"
    return "unknown"


def split_day_proposals(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Keep one day's proposals together; split only clear hema vs biochem.

    Single-marker panel_family is always 'unknown', so do not cluster row-by-row.
    """
    if not rows:
        return []
    hema: list[dict[str, Any]] = []
    bio: list[dict[str, Any]] = []
    other: list[dict[str, Any]] = []
    for p in rows:
        bucket = _row_panel_bucket(p)
        if bucket == "hema":
            hema.append(p)
        elif bucket == "biochem":
            bio.append(p)
        else:
            other.append(p)

    hema_n = len({_marker_key(p) for p in hema})
    bio_n = len({_marker_key(p) for p in bio})
    if hema_n >= 2 and bio_n >= 2:
        if len(bio) >= len(hema):
            return [hema, bio + other]
        return [hema + other, bio]
    return [list(rows)]


def looks_like_same_report(
    rows_a: Iterable[dict[str, Any] | Any],
    rows_b: Iterable[dict[str, Any] | Any],
    *,
    min_value_jaccard: float = 0.45,
    min_marker_jaccard: float = 0.55,
) -> bool:
    """True when extracts look like the same panel print (overlap of markers/values)."""
    fa, fb = value_fingerprint(rows_a), value_fingerprint(rows_b)
    if not fa or not fb:
        return False
    if not panels_compatible(panel_family(rows_a), panel_family(rows_b)):
        return False
    if jaccard(fa, fb) >= min_value_jaccard:
        return True
    ka, kb = marker_key_set(rows_a), marker_key_set(rows_b)
    if jaccard(ka, kb) < min_marker_jaccard:
        return False
    # Shared markers agree on values (within fingerprint rounding)
    shared = {k for k, _ in fa} & {k for k, _ in fb}
    if len(shared) < 2:
        return False
    map_a = {k: v for k, v in fa}
    map_b = {k: v for k, v in fb}
    agree = sum(1 for k in shared if map_a.get(k) == map_b.get(k))
    return agree / len(shared) >= 0.7


def drawn_at_close(
    a: datetime | None,
    b: datetime | None,
    *,
    window: timedelta = DRAW_TIME_WINDOW,
) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= window


def fingerprints_nearly_identical(a: frozenset, b: frozenset, *, min_jaccard: float = 0.92) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    return jaccard(a, b) >= min_jaccard
