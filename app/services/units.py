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
UNIT_GROUPS: dict[str, list[str]] = {
    "mass_conc_g": ["g/l", "g/dl"],
    "fraction": ["%", "1"],
    "volume_fl": ["fl"],
    "mass_pg": ["pg"],
    "count_9": ["10^9/l"],
    "count_12": ["10^12/l"],
    "enzyme_kat": ["U/l", "ukat/l"],
    "molar_mmol": ["mmol/l", "mg/dl"],
    "molar_umol": ["umol/l", "mg/dl", "ug/dl"],
    "molar_nmol": ["nmol/l", "ng/ml", "ng/dl", "ug/dl"],
    "molar_pmol": ["pmol/l", "pg/ml"],
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
    "ft4": "molar_pmol",
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
    "lpa": "molar_nmol",
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
    "sodium": "molar_mmol",
    "potassium": "molar_mmol",
    "chloride": "molar_mmol",
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
    "shbg": "molar_nmol",
    "dhea_s": "molar_umol",
    "amh": "mass_ug",
    "hcg": "immuno_iu_l",
    "cea": "mass_ug",
    "afp": "mass_ug",
    "ca125": "tumor_ku",
    "ca19_9": "tumor_ku",
    "ca15_3": "tumor_ku",
}

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
}

# Analyte-specific mass↔molar (approx clinical factors)
_MARKER_FACTORS: dict[tuple[str, str, str], float] = {
    ("vitamin_d", "nmol/l", "ng/ml"): 0.400641,
    ("vitamin_d", "ng/ml", "nmol/l"): 2.496,
    ("glucose", "mmol/l", "mg/dl"): 18.0182,
    ("glucose", "mg/dl", "mmol/l"): 1.0 / 18.0182,
    ("creatinine", "umol/l", "mg/dl"): 1.0 / 88.4,
    ("creatinine", "mg/dl", "umol/l"): 88.4,
    ("ldl", "mmol/l", "mg/dl"): 38.67,
    ("ldl", "mg/dl", "mmol/l"): 1.0 / 38.67,
    ("hdl", "mmol/l", "mg/dl"): 38.67,
    ("hdl", "mg/dl", "mmol/l"): 1.0 / 38.67,
    ("cholesterol", "mmol/l", "mg/dl"): 38.67,
    ("cholesterol", "mg/dl", "mmol/l"): 1.0 / 38.67,
    ("non_hdl", "mmol/l", "mg/dl"): 38.67,
    ("non_hdl", "mg/dl", "mmol/l"): 1.0 / 38.67,
    ("triglycerides", "mmol/l", "mg/dl"): 88.57,
    ("triglycerides", "mg/dl", "mmol/l"): 1.0 / 88.57,
    ("b12", "pmol/l", "pg/ml"): 1.355,
    ("b12", "pg/ml", "pmol/l"): 1.0 / 1.355,
    ("folate", "nmol/l", "ng/ml"): 0.441,
    ("folate", "ng/ml", "nmol/l"): 1.0 / 0.441,
    ("testosterone", "nmol/l", "ng/dl"): 28.84,
    ("testosterone", "ng/dl", "nmol/l"): 1.0 / 28.84,
    ("cortisol", "nmol/l", "ug/dl"): 1.0 / 27.59,
    ("cortisol", "ug/dl", "nmol/l"): 27.59,
    ("iron", "umol/l", "ug/dl"): 5.586,
    ("iron", "ug/dl", "umol/l"): 1.0 / 5.586,
    ("uric_acid", "umol/l", "mg/dl"): 1.0 / 59.48,
    ("uric_acid", "mg/dl", "umol/l"): 59.48,
    ("urea", "mmol/l", "mg/dl"): 6.006,
    ("urea", "mg/dl", "mmol/l"): 1.0 / 6.006,
    ("calcium", "mmol/l", "mg/dl"): 4.008,
    ("calcium", "mg/dl", "mmol/l"): 1.0 / 4.008,
    ("magnesium", "mmol/l", "mg/dl"): 2.43,
    ("magnesium", "mg/dl", "mmol/l"): 1.0 / 2.43,
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
    """Convert toward marker default unit when possible (trends / compare)."""
    converted, ok = convert_value(value, unit, canonical_unit, marker_code=marker_code)
    if ok:
        return converted, canonical_unit or _norm(unit) or unit, True
    return value, _norm(unit) or unit, False


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
