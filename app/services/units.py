"""Canonical units, quantity groups, and conversions for lab markers."""

from __future__ import annotations

from app.services.ocr_parse import normalize_unit

# Display / selectable units for custom markers (normalized lowercase keys)
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
    "IU/ml",
    "kU/l",
    "U/l",
    "ukat/l",
    "mmol/mol",
    "%HbA1c",
    "ml/min/1.73m2",
    "ml/s",
    "mmol/kg",
    "mm/h",
    "s",
]

# Quantity groups: mutually interchangeable unit spellings for a physical quantity.
# Order = preference in select (canonical-ish first within group).
#
# molar_* groups are NOT a universal mmol/l pool across analytes. Each group is the
# set of report units allowed for ONE marker (via MARKER_UNIT_GROUP). Mass↔molar
# conversion always requires that marker's factor — mmol/l glucose ≠ mmol/l LDL.
UNIT_GROUPS: dict[str, list[str]] = {
    "mass_conc_g": ["g/l", "g/dl"],
    "fraction": ["%", "1"],
    "volume_fl": ["fl"],
    "mass_pg": ["pg"],
    "count_9": ["10^9/l"],
    "count_12": ["10^12/l"],
    "enzyme_kat": ["U/l", "ukat/l"],
    # Per-marker molar concentration (+ mass alternatives for that analyte only)
    "molar_mmol": ["mmol/l", "mg/dl"],
    "molar_mmol_only": ["mmol/l"],  # electrolytes: mEq/l ≡ mmol/l; no mass form
    "molar_umol": ["umol/l", "mg/dl", "ug/dl"],
    "molar_nmol": ["nmol/l", "ng/ml", "ng/dl", "ug/dl"],
    "molar_nmol_only": ["nmol/l"],  # particle / binding protein — no fixed mass factor
    "molar_pmol": ["pmol/l", "pg/ml"],
    "molar_pmol_ft4": ["pmol/l", "ng/dl", "pg/ml"],  # FT4 conventional is usually ng/dl
    "mass_ug": ["ug/l", "ng/ml", "ng/l"],
    "mass_mg": ["mg/l"],
    "hormone_miu": ["mIU/l"],
    "immuno_iu_l": ["IU/l"],
    "immuno_iu_ml": ["IU/ml"],
    "tumor_ku": ["kU/l"],
    "hba1c": ["mmol/mol", "%HbA1c", "%"],
    "egfr": ["ml/min/1.73m2", "ml/s"],
    "osmolality": ["mmol/kg"],
    "esr": ["mm/h"],
    "time_s": ["s"],
    "ratio": ["1"],
    "excretion_24h": ["mg/24h", "umol/24h", "ug/24h"],
    "urine_dipstick": ["1", "g/l", "mg/l", "mmol/l", "umol/l"],
}

# marker_code → UNIT_GROUPS key
MARKER_UNIT_GROUP: dict[str, str] = {
    "hgb": "mass_conc_g",
    "hct": "fraction",
    "rbc": "count_12",
    "mcv": "volume_fl",
    "mch": "mass_pg",
    "mchc": "mass_conc_g",
    "rdw": "fraction",
    "wbc": "count_9",
    "plt": "count_9",
    "mpv": "volume_fl",
    "pdw": "fraction",
    "nrbc": "fraction",
    "nrbc_abs": "count_9",
    "neutrophils": "fraction",
    "neutrophils_abs": "count_9",
    "lymphocytes": "fraction",
    "lymphocytes_abs": "count_9",
    "monocytes": "fraction",
    "monocytes_abs": "count_9",
    "eosinophils": "fraction",
    "eosinophils_abs": "count_9",
    "basophils": "fraction",
    "basophils_abs": "count_9",
    "ig": "fraction",
    "ig_abs": "count_9",
    "reticulocytes": "fraction",
    "reticulocytes_abs": "count_9",
    "ferritin": "mass_ug",
    "iron": "molar_umol",
    "transferrin": "mass_conc_g",
    "tibc": "molar_umol",
    "uibc": "molar_umol",
    "transferrin_sat": "fraction",
    "stfr": "mass_mg",
    "vitamin_d": "molar_nmol",
    "b12": "molar_pmol",
    "folate": "molar_nmol",
    "tsh": "hormone_miu",
    "ft4": "molar_pmol_ft4",
    "ft3": "molar_pmol",
    "tt3": "molar_nmol",
    "tt4": "molar_nmol",
    "anti_tg": "immuno_iu_l",
    "anti_tpo": "immuno_iu_l",
    "anti_tshr": "immuno_iu_l",
    "prolactin": "hormone_miu",
    "testosterone": "molar_nmol",
    "free_testosterone": "molar_pmol",
    "cortisol": "molar_nmol",
    "pth": "molar_pmol",
    "osteocalcin": "mass_ug",
    "p1np": "mass_ug",
    "ctx": "mass_ug",
    "psa": "mass_ug",
    "fpsa": "mass_ug",
    "fpsa_psa": "ratio",
    "glucose": "molar_mmol",
    "hba1c": "hba1c",
    "insulin": "hormone_miu",
    "c_peptide": "molar_nmol",
    "lactate": "molar_mmol",
    "cholesterol": "molar_mmol",
    "apob": "mass_conc_g",
    "apoa1": "mass_conc_g",
    "ldl": "molar_mmol",
    "hdl": "molar_mmol",
    "non_hdl": "molar_mmol",
    "triglycerides": "molar_mmol",
    "lpa": "molar_nmol_only",
    "crp": "mass_mg",
    "hs_crp": "mass_mg",
    "albumin": "mass_conc_g",
    "total_protein": "mass_conc_g",
    "fibrinogen": "mass_conc_g",
    "iga": "mass_conc_g",
    "igg": "mass_conc_g",
    "igm": "mass_conc_g",
    "ck": "enzyme_kat",
    "ck_mb": "mass_ug",
    "alt": "enzyme_kat",
    "ast": "enzyme_kat",
    "ggt": "enzyme_kat",
    "alp": "enzyme_kat",
    "ldh": "enzyme_kat",
    "che": "enzyme_kat",
    "amylase": "enzyme_kat",
    "lipase": "enzyme_kat",
    "gmd": "enzyme_kat",
    "bilirubin": "molar_umol",
    "bilirubin_direct": "molar_umol",
    "creatinine": "molar_umol",
    "urea": "molar_mmol",
    "uric_acid": "molar_umol",
    "egfr": "egfr",
    "cystatin_c": "mass_mg",
    "sodium": "molar_mmol_only",
    "potassium": "molar_mmol_only",
    "chloride": "molar_mmol_only",
    "calcium": "molar_mmol",
    "magnesium": "molar_mmol",
    "phosphorus": "molar_mmol",
    "osmolality": "osmolality",
    "homocysteine": "molar_umol",
    "zinc": "molar_umol",
    "copper": "molar_umol",
    "selenium": "mass_ug",
    "troponin_i": "mass_ug",
    "nt_pro_bnp": "mass_ug",
    "myoglobin": "mass_ug",
    "esr": "esr",
    "inr": "ratio",
    "aptt": "time_s",
    "d_dimer": "mass_mg",
    "rf": "immuno_iu_ml",
    "aslo": "immuno_iu_ml",
    "ige": "immuno_iu_ml",
    "fsh": "immuno_iu_l",
    "lh": "immuno_iu_l",
    "estradiol": "molar_pmol",
    "progesterone": "molar_nmol",
    "shbg": "molar_nmol_only",
    "dhea_s": "molar_umol",
    "amh": "mass_ug",
    "hcg": "immuno_iu_l",
    "cea": "mass_ug",
    "afp": "mass_ug",
    "ca125": "tumor_ku",
    "ca19_9": "tumor_ku",
    "ca15_3": "tumor_ku",
    "ca72_4": "tumor_ku",
    "scc": "mass_ug",
    "thyroglobulin": "mass_ug",
    "pct": "fraction",
    "hiiaa": "excretion_24h",
    "vma": "excretion_24h",
    "bence_jones": "excretion_24h",
    "urobilinogen": "urine_dipstick",
    "urine_ketones": "urine_dipstick",
    "urine_blood": "urine_dipstick",
    "urine_ph": "ratio",
}

# Molar concentration units (amount-of-substance per litre). Substance = marker_code.
_MOLAR_CONC_UNITS = frozenset({"mmol/l", "umol/l", "nmol/l", "pmol/l"})
# Mass concentration units that appear as molar-group alternatives (need analyte factor).
_MASS_CONC_UNITS = frozenset({"mg/dl", "ug/dl", "ng/ml", "ng/dl", "pg/ml", "mg/l", "ug/l", "ng/l"})

# Universal conversions (same for all markers in the quantity)
_FACTORS: dict[tuple[str, str], float] = {
    ("g/l", "g/dl"): 0.1,
    ("g/dl", "g/l"): 10.0,
    ("ug/l", "ng/ml"): 1.0,
    ("ng/ml", "ug/l"): 1.0,
    ("ug/l", "ng/l"): 1000.0,
    ("ng/l", "ug/l"): 0.001,
    ("ng/ml", "ng/l"): 1000.0,
    ("ng/l", "ng/ml"): 0.001,
    ("ukat/l", "u/l"): 60.0,
    ("u/l", "ukat/l"): 1.0 / 60.0,
    ("1", "%"): 100.0,
    ("%", "1"): 0.01,
    ("ml/s", "ml/min/1.73m2"): 60.0,
    ("ml/min/1.73m2", "ml/s"): 1.0 / 60.0,
    # SI prefix scale for molar concentration (substance-independent)
    ("mmol/l", "umol/l"): 1000.0,
    ("umol/l", "mmol/l"): 0.001,
    ("umol/l", "nmol/l"): 1000.0,
    ("nmol/l", "umol/l"): 0.001,
    ("nmol/l", "pmol/l"): 1000.0,
    ("pmol/l", "nmol/l"): 0.001,
    ("mmol/l", "nmol/l"): 1_000_000.0,
    ("nmol/l", "mmol/l"): 1e-6,
    ("mmol/l", "pmol/l"): 1_000_000_000.0,
    ("pmol/l", "mmol/l"): 1e-9,
    ("umol/l", "pmol/l"): 1_000_000.0,
    ("pmol/l", "umol/l"): 1e-6,
}

# Analyte-specific mass↔molar (clinical factors; sources: Labcorp / MSD / Mayo SI tables).
# Convention in tuples: (marker, from_unit, to_unit) → multiply value by factor.
def _bidir(marker: str, unit_a: str, unit_b: str, a_to_b: float) -> dict[tuple[str, str, str], float]:
    """Register both directions for one analyte conversion."""
    return {
        (marker, unit_a, unit_b): a_to_b,
        (marker, unit_b, unit_a): 1.0 / a_to_b,
    }


_MARKER_FACTORS: dict[tuple[str, str, str], float] = {}
_MARKER_FACTORS.update(
    {
        # Existing / lipids & carbs
        **_bidir("vitamin_d", "ng/ml", "nmol/l", 2.496),
        **_bidir("glucose", "mg/dl", "mmol/l", 1.0 / 18.0182),
        **_bidir("creatinine", "mg/dl", "umol/l", 88.4),
        **_bidir("ldl", "mg/dl", "mmol/l", 1.0 / 38.67),
        **_bidir("hdl", "mg/dl", "mmol/l", 1.0 / 38.67),
        **_bidir("cholesterol", "mg/dl", "mmol/l", 1.0 / 38.67),
        **_bidir("non_hdl", "mg/dl", "mmol/l", 1.0 / 38.67),
        **_bidir("triglycerides", "mg/dl", "mmol/l", 1.0 / 88.57),
        **_bidir("b12", "pg/ml", "pmol/l", 1.0 / 1.355),
        **_bidir("folate", "ng/ml", "nmol/l", 1.0 / 0.441),
        **_bidir("testosterone", "ng/dl", "nmol/l", 1.0 / 28.84),
        **_bidir("cortisol", "ug/dl", "nmol/l", 27.59),
        **_bidir("iron", "ug/dl", "umol/l", 1.0 / 5.586),
        **_bidir("uric_acid", "mg/dl", "umol/l", 59.48),
        **_bidir("urea", "mg/dl", "mmol/l", 1.0 / 6.006),
        **_bidir("calcium", "mg/dl", "mmol/l", 1.0 / 4.008),
        **_bidir("magnesium", "mg/dl", "mmol/l", 1.0 / 2.43),
        # Bilirubin (Labcorp/MSD: mg/dl × 17.1 → µmol/l)
        **_bidir("bilirubin", "mg/dl", "umol/l", 17.1),
        **_bidir("bilirubin", "ug/dl", "umol/l", 0.0171),
        **_bidir("bilirubin_direct", "mg/dl", "umol/l", 17.1),
        **_bidir("bilirubin_direct", "ug/dl", "umol/l", 0.0171),
        # Minerals (MSD/Labcorp)
        **_bidir("zinc", "ug/dl", "umol/l", 0.153),
        **_bidir("zinc", "mg/dl", "umol/l", 153.0),
        **_bidir("copper", "ug/dl", "umol/l", 0.157),
        **_bidir("copper", "mg/dl", "umol/l", 157.0),
        # Iron binding (same Fe atomic factor as iron)
        **_bidir("tibc", "ug/dl", "umol/l", 1.0 / 5.586),
        **_bidir("tibc", "mg/dl", "umol/l", 1000.0 / 5.586),
        **_bidir("uibc", "ug/dl", "umol/l", 1.0 / 5.586),
        **_bidir("uibc", "mg/dl", "umol/l", 1000.0 / 5.586),
        # Homocysteine MW≈135.2 (µmol/l ↔ µg/dl / mg/dl)
        **_bidir("homocysteine", "ug/dl", "umol/l", 1.0 / 13.52),
        **_bidir("homocysteine", "mg/dl", "umol/l", 1000.0 / 13.52),
        # Lactate / phosphorus (Labcorp)
        **_bidir("lactate", "mg/dl", "mmol/l", 0.111),
        **_bidir("phosphorus", "mg/dl", "mmol/l", 0.323),
        # Hormones
        **_bidir("c_peptide", "ng/ml", "nmol/l", 0.333),
        **_bidir("c_peptide", "ng/dl", "nmol/l", 0.00333),
        **_bidir("c_peptide", "ug/dl", "nmol/l", 3.33),
        **_bidir("progesterone", "ng/ml", "nmol/l", 3.18),
        **_bidir("progesterone", "ng/dl", "nmol/l", 0.0318),
        **_bidir("progesterone", "ug/dl", "nmol/l", 31.8),
        **_bidir("dhea_s", "ug/dl", "umol/l", 0.0271),
        **_bidir("dhea_s", "mg/dl", "umol/l", 27.1),
        **_bidir("estradiol", "pg/ml", "pmol/l", 3.671),
        # Free testosterone: Mayo ng/dl × 34.67 = pmol/l; 1 ng/dl = 10 pg/ml
        **_bidir("free_testosterone", "pg/ml", "pmol/l", 3.467),
        # Thyroid
        **_bidir("ft3", "pg/ml", "pmol/l", 1.536),
        **_bidir("ft4", "ng/dl", "pmol/l", 12.87),
        **_bidir("ft4", "pg/ml", "pmol/l", 1.287),
        **_bidir("tt3", "ng/dl", "nmol/l", 0.0154),
        **_bidir("tt3", "ng/ml", "nmol/l", 0.154),
        **_bidir("tt3", "ug/dl", "nmol/l", 15.4),
        **_bidir("tt4", "ug/dl", "nmol/l", 12.87),
        **_bidir("tt4", "ng/dl", "nmol/l", 0.01287),
        **_bidir("tt4", "ng/ml", "nmol/l", 1.287),
        # Intact PTH: pg/ml → pmol/l ≈ /9.4 (MW-based clinical factor 0.106)
        **_bidir("pth", "pg/ml", "pmol/l", 0.106),
    }
)


def _norm(u: str) -> str:
    return normalize_unit(u or "").lower().replace("μ", "u").replace("µ", "u").strip()


def is_molar_unit(unit: str) -> bool:
    """True for amount-of-substance concentration (or HbA1c / osmolality mol forms)."""
    u = _norm(unit)
    return u in _MOLAR_CONC_UNITS or u in {"mmol/mol", "mmol/kg"}


def _is_mass_molar_pair(src: str, dst: str) -> bool:
    return (src in _MOLAR_CONC_UNITS and dst in _MASS_CONC_UNITS) or (
        dst in _MOLAR_CONC_UNITS and src in _MASS_CONC_UNITS
    )


def format_unit(
    unit: str,
    *,
    marker_name: str | None = None,
    with_substance: bool = False,
) -> str:
    """Display unit. Optionally qualify molar units with analyte name.

    Storage stays bare (e.g. mmol/l). Use with_substance=True where the unit
    appears without the marker name nearby (trends axis / chart subtitle).
    """
    u = (unit or "").strip()
    if not u:
        return ""
    name = (marker_name or "").strip()
    if with_substance and name and is_molar_unit(u):
        return f"{u} ({name})"
    return u


def convert_value(
    value: float,
    from_unit: str,
    to_unit: str,
    *,
    marker_code: str | None = None,
) -> tuple[float, bool]:
    """Convert value between units. Returns (new_value, converted_ok).

    Mass↔molar always needs marker_code + known factor (analyte molar mass).
    Molar prefix scale (mmol/l ↔ umol/l) is substance-independent.
    """
    src, dst = _norm(from_unit), _norm(to_unit)
    if not src or not dst or src == dst:
        return value, True

    if marker_code:
        key = (marker_code, src, dst)
        if key in _MARKER_FACTORS:
            return value * _MARKER_FACTORS[key], True
        if marker_code == "hba1c":
            if src in {"mmol/mol"} and dst in {"%hba1c", "%"}:
                return 0.09148 * value + 2.152, True
            if src in {"%hba1c", "%"} and dst == "mmol/mol":
                return (value - 2.152) / 0.09148, True

    # Never treat mass↔molar as universal — substance-specific only.
    if _is_mass_molar_pair(src, dst):
        return value, False

    pair = (src, dst)
    if pair in _FACTORS and _FACTORS[pair] is not None:
        return value * float(_FACTORS[pair]), True

    return value, False


def same_quantity(
    unit_a: str,
    unit_b: str,
    *,
    marker_code: str | None = None,
) -> bool:
    """True if units convert in this marker context (or universally)."""
    if _norm(unit_a) == _norm(unit_b):
        return True
    _, ok = convert_value(1.0, unit_a, unit_b, marker_code=marker_code)
    return ok


def to_canonical(
    value: float,
    unit: str,
    marker_code: str | None,
    canonical_unit: str,
) -> tuple[float, str, bool]:
    """Convert toward marker default unit when possible (trends / compare)."""
    converted, ok = convert_value(value, unit, canonical_unit, marker_code=marker_code)
    if ok:
        return converted, canonical_unit or _norm(unit) or unit, True
    return value, _norm(unit) or unit, False


# Plausible magnitude bands for markers that share g/l ↔ g/dl and are often
# mislabeled by VLMs (value stays, only unit label is corrected).
_MARKER_UNIT_MAGNITUDE: dict[str, dict[str, tuple[float, float]]] = {
    "hgb": {"g/l": (70.0, 250.0), "g/dl": (7.0, 25.0)},
    "mchc": {"g/l": (250.0, 450.0), "g/dl": (25.0, 45.0)},
}


def _in_magnitude_band(x: float | None, lo: float, hi: float) -> bool:
    if x is None:
        return False
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return lo <= v <= hi


def correct_unit_by_magnitude(
    marker_code: str | None,
    value: float | None,
    unit: str,
    lab_low: float | None = None,
    lab_high: float | None = None,
) -> str:
    """Fix unit label when value/refs match a sibling unit better (no rescale).

    Example: HGB 13.5 with refs 12–16 labeled g/l → g/dl.
    """
    code = (marker_code or "").strip().lower()
    unit_n = _norm(unit)
    bands = _MARKER_UNIT_MAGNITUDE.get(code)
    if not bands or value is None:
        return unit_n or (unit or "")

    def score(u: str) -> int:
        lo, hi = bands[u]
        s = 0
        if _in_magnitude_band(value, lo, hi):
            s += 2
        if _in_magnitude_band(lab_low, lo, hi):
            s += 1
        if _in_magnitude_band(lab_high, lo, hi):
            s += 1
        return s

    if unit_n not in bands:
        # Unknown / empty label: pick best band if one clearly wins.
        ranked = sorted(((score(u), u) for u in bands), reverse=True)
        if ranked and ranked[0][0] >= 2:
            return ranked[0][1]
        return unit_n or (unit or "")

    current = score(unit_n)
    best_u, best_s = unit_n, current
    for u, _band in bands.items():
        if u == unit_n:
            continue
        s = score(u)
        # Require clear win so borderline values stay put.
        if s >= 2 and s >= current + 2:
            best_u, best_s = u, s
    return best_u


def units_for_group(group_id: str | None) -> list[str]:
    if not group_id:
        return list(UNIT_CHOICES)
    return list(UNIT_GROUPS.get(group_id) or UNIT_CHOICES)


def unit_group_for_marker(marker_code: str | None) -> str | None:
    if not marker_code:
        return None
    return MARKER_UNIT_GROUP.get(marker_code)


def marker_unit_options_map() -> dict[str, list[str]]:
    """code → unit list for review UI JSON."""
    return {code: list(UNIT_GROUPS[gid]) for code, gid in MARKER_UNIT_GROUP.items() if gid in UNIT_GROUPS}


def unit_options_for_marker(
    marker_code: str | None = None,
    default_unit: str | None = None,
    *,
    detected: str | None = None,
) -> list[str]:
    """Selectable units for a catalog marker (quantity group only) or custom (all).

    If detected unit is outside the group, prepend it so the user can correct it.
    Custom markers get the full catalog but mass↔molar still will not convert
    without a catalog marker_code (no silent wrong factor).
    """
    det = _norm(detected or "")
    group_id = unit_group_for_marker(marker_code)
    if group_id and group_id in UNIT_GROUPS:
        group = list(UNIT_GROUPS[group_id])
        by_norm = {_norm(u): u for u in group}
        preferred = _norm(default_unit or "")
        if preferred and preferred in by_norm:
            pref_u = by_norm[preferred]
            group = [pref_u] + [u for u in group if _norm(u) != preferred]
        out: list[str] = []
        if det and det not in {_norm(u) for u in group}:
            out.append(detected if detected else det)
        for u in group:
            if u and u not in out:
                out.append(u)
        return out

    # Custom / unknown: full catalog of units
    out: list[str] = []
    preferred = _norm(default_unit or "")
    if det:
        out.append(detected if detected else det)
    if preferred:
        # Prefer canonical spelling from UNIT_CHOICES when possible
        pref_disp = next((u for u in UNIT_CHOICES if _norm(u) == preferred), preferred)
        if pref_disp not in out:
            out.append(pref_disp)
    for u in UNIT_CHOICES:
        if u and u not in out:
            out.append(u)
    return out
