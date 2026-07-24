"""Canonical units and conversions for lab markers."""

from __future__ import annotations

from app.services.ocr_parse import normalize_unit

# Display / selectable units (normalized lowercase keys)
UNIT_CHOICES: list[str] = [
    "g/l",
    "g/dl",
    "%",
    "fl",
    "pg",
    "1",
    "10^9/l",
    "10^12/l",
    "ug/l",
    "ug/dl",
    "ng/l",
    "ng/ml",
    "ng/dl",
    "pg/ml",
    "umol/l",
    "nmol/l",
    "pmol/l",
    "mmol/l",
    "mg/dl",
    "mg/l",
    "mIU/l",
    "IU/l",
    "kU/l",
    "U/l",
    "ukat/l",
    "mmol/mol",
    "%HbA1c",
    "ml/min/1.73m2",
    "mmol/kg",
]

# factor: value_in_from * factor = value_in_to  (same dimension pairs)
# Enzyme: 1 μkat/L = 60 U/L
_FACTORS: dict[tuple[str, str], float] = {
    ("g/l", "g/dl"): 0.1,
    ("g/dl", "g/l"): 10.0,
    ("ug/l", "ng/ml"): 1.0,
    ("ng/ml", "ug/l"): 1.0,
    ("ukat/l", "u/l"): 60.0,
    ("u/l", "ukat/l"): 1.0 / 60.0,
}

# Analyte-specific mass↔molar (approx clinical factors)
# key: (marker_code, from_unit, to_unit) -> factor (multiply)
_MARKER_FACTORS: dict[tuple[str, str, str], float] = {
    # Vitamin D 25-OH: nmol/L ↔ ng/mL (×0.4)
    ("vitamin_d", "nmol/l", "ng/ml"): 0.400641,
    ("vitamin_d", "ng/ml", "nmol/l"): 2.496,
    # Glucose: mmol/L ↔ mg/dL (×18.018)
    ("glucose", "mmol/l", "mg/dl"): 18.0182,
    ("glucose", "mg/dl", "mmol/l"): 1.0 / 18.0182,
    # Creatinine: umol/L ↔ mg/dL (÷88.4)
    ("creatinine", "umol/l", "mg/dl"): 1.0 / 88.4,
    ("creatinine", "mg/dl", "umol/l"): 88.4,
    # Cholesterol/TG approx
    ("ldl", "mmol/l", "mg/dl"): 38.67,
    ("ldl", "mg/dl", "mmol/l"): 1.0 / 38.67,
    ("hdl", "mmol/l", "mg/dl"): 38.67,
    ("hdl", "mg/dl", "mmol/l"): 1.0 / 38.67,
    ("triglycerides", "mmol/l", "mg/dl"): 88.57,
    ("triglycerides", "mg/dl", "mmol/l"): 1.0 / 88.57,
    # B12 pmol/L ↔ pg/mL (×1.355)
    ("b12", "pmol/l", "pg/ml"): 1.355,
    ("b12", "pg/ml", "pmol/l"): 1.0 / 1.355,
    # Folate nmol/L ↔ ng/mL (×0.441)
    ("folate", "nmol/l", "ng/ml"): 0.441,
    ("folate", "ng/ml", "nmol/l"): 1.0 / 0.441,
    # Testosterone nmol/L ↔ ng/dL (×28.84)
    ("testosterone", "nmol/l", "ng/dl"): 28.84,
    ("testosterone", "ng/dl", "nmol/l"): 1.0 / 28.84,
    # Cortisol nmol/L ↔ ug/dL (÷27.59)
    ("cortisol", "nmol/l", "ug/dl"): 1.0 / 27.59,
    ("cortisol", "ug/dl", "nmol/l"): 27.59,
    # Iron: umol/L ↔ ug/dL (×5.586)
    ("iron", "umol/l", "ug/dl"): 5.586,
    ("iron", "ug/dl", "umol/l"): 1.0 / 5.586,
    # Uric acid: umol/L ↔ mg/dL (÷59.48)
    ("uric_acid", "umol/l", "mg/dl"): 1.0 / 59.48,
    ("uric_acid", "mg/dl", "umol/l"): 59.48,
    # Urea (not BUN): mmol/L ↔ mg/dL (×6.006)
    ("urea", "mmol/l", "mg/dl"): 6.006,
    ("urea", "mg/dl", "mmol/l"): 1.0 / 6.006,
    # Calcium: mmol/L ↔ mg/dL (×4.008)
    ("calcium", "mmol/l", "mg/dl"): 4.008,
    ("calcium", "mg/dl", "mmol/l"): 1.0 / 4.008,
    # Magnesium: mmol/L ↔ mg/dL (×2.43)
    ("magnesium", "mmol/l", "mg/dl"): 2.43,
    ("magnesium", "mg/dl", "mmol/l"): 1.0 / 2.43,
    # HbA1c mmol/mol ↔ % (NGSP): % = 0.09148*IFCC + 2.152
    # handled specially
}


def _norm(u: str) -> str:
    return normalize_unit(u or "").lower().replace("μ", "u").replace("µ", "u").strip()


def convert_value(
    value: float,
    from_unit: str,
    to_unit: str,
    *,
    marker_code: str | None = None,
) -> tuple[float, bool]:
    """Convert value between units. Returns (new_value, converted_ok)."""
    src, dst = _norm(from_unit), _norm(to_unit)
    if not src or not dst or src == dst:
        return value, True

    if marker_code:
        key = (marker_code, src, dst)
        if key in _MARKER_FACTORS:
            return value * _MARKER_FACTORS[key], True
        # HbA1c special
        if marker_code == "hba1c":
            if src in {"mmol/mol"} and dst in {"%hba1c", "%"}:
                return 0.09148 * value + 2.152, True
            if src in {"%hba1c", "%"} and dst == "mmol/mol":
                return (value - 2.152) / 0.09148, True

    pair = (src, dst)
    if pair in _FACTORS and _FACTORS[pair] is not None:
        return value * float(_FACTORS[pair]), True

    return value, False


def to_canonical(
    value: float,
    unit: str,
    marker_code: str | None,
    canonical_unit: str,
) -> tuple[float, str, bool]:
    """Convert toward marker default unit when possible."""
    converted, ok = convert_value(value, unit, canonical_unit, marker_code=marker_code)
    if ok:
        return converted, canonical_unit or _norm(unit) or unit, True
    return value, _norm(unit) or unit, False


def unit_options_for_marker(default_unit: str) -> list[str]:
    """Choices related to a marker's default unit + global list."""
    d = _norm(default_unit)
    related = {d} if d else set()
    for a, b in list(_FACTORS.keys()):
        if a == d:
            related.add(b)
        if b == d:
            related.add(a)
    for (code, a, b), _ in _MARKER_FACTORS.items():
        if a == d:
            related.add(b)
        if b == d:
            related.add(a)
    # keep stable order: default first, then related, then rest
    out: list[str] = []
    for u in [d] + sorted(related - {d}) + UNIT_CHOICES:
        if u and u not in out:
            out.append(u)
    return out
