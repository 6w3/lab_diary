from __future__ import annotations

import re
import unicodedata
from typing import Protocol


class MarkerLike(Protocol):
    code: str
    name_cs: str
    name_en: str
    default_unit: str

MARKER_SEED: list[dict] = [
    {"code": "hgb", "name_cs": "Hemoglobin", "name_en": "Hemoglobin", "default_unit": "g/l", "tip_ref_low": 135, "tip_ref_high": 170},
    {"code": "hct", "name_cs": "Hematokrit", "name_en": "Hematocrit", "default_unit": "%", "tip_ref_low": 40, "tip_ref_high": 50},
    {"code": "mcv", "name_cs": "MCV", "name_en": "MCV", "default_unit": "fl", "tip_ref_low": 80, "tip_ref_high": 96},
    {"code": "wbc", "name_cs": "Leukocyty", "name_en": "WBC", "default_unit": "10^9/l", "tip_ref_low": 4.0, "tip_ref_high": 10.0},
    {"code": "plt", "name_cs": "Trombocyty", "name_en": "Platelets", "default_unit": "10^9/l", "tip_ref_low": 150, "tip_ref_high": 400},
    {"code": "ferritin", "name_cs": "Feritin", "name_en": "Ferritin", "default_unit": "ug/l", "tip_ref_low": 30, "tip_ref_high": 300},
    {"code": "iron", "name_cs": "Železo", "name_en": "Iron", "default_unit": "umol/l", "tip_ref_low": 11, "tip_ref_high": 30},
    {"code": "vitamin_d", "name_cs": "Vitamin D (25-OH)", "name_en": "Vitamin D (25-OH)", "default_unit": "nmol/l", "tip_ref_low": 75, "tip_ref_high": 125},
    {"code": "b12", "name_cs": "Vitamin B12", "name_en": "Vitamin B12", "default_unit": "pmol/l", "tip_ref_low": 150, "tip_ref_high": 600},
    {"code": "folate", "name_cs": "Folát", "name_en": "Folate", "default_unit": "nmol/l", "tip_ref_low": 10, "tip_ref_high": 45},
    {"code": "tsh", "name_cs": "TSH", "name_en": "TSH", "default_unit": "mIU/l", "tip_ref_low": 0.4, "tip_ref_high": 4.0},
    {"code": "ft4", "name_cs": "fT4", "name_en": "Free T4", "default_unit": "pmol/l", "tip_ref_low": 10, "tip_ref_high": 25},
    {"code": "ft3", "name_cs": "fT3", "name_en": "Free T3", "default_unit": "pmol/l", "tip_ref_low": 3.1, "tip_ref_high": 6.8},
    {"code": "testosterone", "name_cs": "Testosteron", "name_en": "Testosterone", "default_unit": "nmol/l", "tip_ref_low": 8, "tip_ref_high": 30},
    {"code": "cortisol", "name_cs": "Kortizol", "name_en": "Cortisol", "default_unit": "nmol/l", "tip_ref_low": 100, "tip_ref_high": 500},
    {"code": "glucose", "name_cs": "Glukóza", "name_en": "Glucose", "default_unit": "mmol/l", "tip_ref_low": 3.9, "tip_ref_high": 5.6},
    {"code": "hba1c", "name_cs": "HbA1c", "name_en": "HbA1c", "default_unit": "mmol/mol", "tip_ref_low": 20, "tip_ref_high": 42},
    {"code": "insulin", "name_cs": "Inzulin", "name_en": "Insulin", "default_unit": "mIU/l", "tip_ref_low": 2, "tip_ref_high": 25},
    {"code": "apob", "name_cs": "ApoB", "name_en": "ApoB", "default_unit": "g/l", "tip_ref_low": None, "tip_ref_high": 0.9},
    {"code": "ldl", "name_cs": "LDL cholesterol", "name_en": "LDL cholesterol", "default_unit": "mmol/l", "tip_ref_low": None, "tip_ref_high": 3.0},
    {"code": "hdl", "name_cs": "HDL cholesterol", "name_en": "HDL cholesterol", "default_unit": "mmol/l", "tip_ref_low": 1.0, "tip_ref_high": None},
    {"code": "triglycerides", "name_cs": "Triglyceridy", "name_en": "Triglycerides", "default_unit": "mmol/l", "tip_ref_low": None, "tip_ref_high": 1.7},
    {"code": "lpa", "name_cs": "Lp(a)", "name_en": "Lp(a)", "default_unit": "nmol/l", "tip_ref_low": None, "tip_ref_high": 75},
    {"code": "crp", "name_cs": "hs-CRP", "name_en": "hs-CRP", "default_unit": "mg/l", "tip_ref_low": None, "tip_ref_high": 1.0},
    {"code": "ck", "name_cs": "CK", "name_en": "CK", "default_unit": "U/l", "tip_ref_low": 30, "tip_ref_high": 200},
    {"code": "alt", "name_cs": "ALT", "name_en": "ALT", "default_unit": "U/l", "tip_ref_low": 5, "tip_ref_high": 45},
    {"code": "ast", "name_cs": "AST", "name_en": "AST", "default_unit": "U/l", "tip_ref_low": 5, "tip_ref_high": 45},
    {"code": "ggt", "name_cs": "GGT", "name_en": "GGT", "default_unit": "U/l", "tip_ref_low": 5, "tip_ref_high": 60},
    {"code": "creatinine", "name_cs": "Kreatinin", "name_en": "Creatinine", "default_unit": "umol/l", "tip_ref_low": 60, "tip_ref_high": 104},
    {"code": "urea", "name_cs": "Urea", "name_en": "Urea", "default_unit": "mmol/l", "tip_ref_low": 2.5, "tip_ref_high": 8.0},
    {"code": "uric_acid", "name_cs": "Kyselina močová", "name_en": "Uric acid", "default_unit": "umol/l", "tip_ref_low": 200, "tip_ref_high": 420},
    {"code": "egfr", "name_cs": "eGFR", "name_en": "eGFR", "default_unit": "ml/min/1.73m2", "tip_ref_low": 90, "tip_ref_high": None},
    {"code": "sodium", "name_cs": "Sodík", "name_en": "Sodium", "default_unit": "mmol/l", "tip_ref_low": 136, "tip_ref_high": 145},
    {"code": "potassium", "name_cs": "Draslík", "name_en": "Potassium", "default_unit": "mmol/l", "tip_ref_low": 3.5, "tip_ref_high": 5.1},
    {"code": "chloride", "name_cs": "Chloridy", "name_en": "Chloride", "default_unit": "mmol/l", "tip_ref_low": 98, "tip_ref_high": 107},
    {"code": "calcium", "name_cs": "Vápník", "name_en": "Calcium", "default_unit": "mmol/l", "tip_ref_low": 2.15, "tip_ref_high": 2.55},
    {"code": "magnesium", "name_cs": "Hořčík", "name_en": "Magnesium", "default_unit": "mmol/l", "tip_ref_low": 0.7, "tip_ref_high": 1.0},
    {"code": "osmolality", "name_cs": "Osmolalita", "name_en": "Osmolality", "default_unit": "mmol/kg", "tip_ref_low": 275, "tip_ref_high": 295},
    {"code": "homocysteine", "name_cs": "Homocystein", "name_en": "Homocysteine", "default_unit": "umol/l", "tip_ref_low": None, "tip_ref_high": 12},
]

# Display order for trends / multi-chart pages (category → marker codes).
MARKER_CATEGORY_ORDER: list[tuple[str, list[str]]] = [
    ("hematology", ["hgb", "hct", "mcv", "wbc", "plt"]),
    ("iron", ["ferritin", "iron"]),
    ("vitamins", ["vitamin_d", "b12", "folate"]),
    ("thyroid", ["tsh", "ft4", "ft3"]),
    ("hormones", ["testosterone", "cortisol"]),
    ("glucose", ["glucose", "hba1c", "insulin"]),
    ("lipids", ["apob", "ldl", "hdl", "triglycerides", "lpa"]),
    ("inflammation", ["crp", "homocysteine"]),
    ("liver_muscle", ["ck", "alt", "ast", "ggt"]),
    ("kidney", ["creatinine", "urea", "uric_acid", "egfr"]),
    ("electrolytes", ["sodium", "potassium", "chloride", "calcium", "magnesium", "osmolality"]),
]

MARKER_CATEGORY_LABELS = {
    "hematology": {"cs": "Hematologie", "en": "Hematology"},
    "iron": {"cs": "Železo", "en": "Iron"},
    "vitamins": {"cs": "Vitamíny", "en": "Vitamins"},
    "thyroid": {"cs": "Štítná žláza", "en": "Thyroid"},
    "hormones": {"cs": "Hormony", "en": "Hormones"},
    "glucose": {"cs": "Glukóza / metabolismus", "en": "Glucose / metabolism"},
    "lipids": {"cs": "Lipidy", "en": "Lipids"},
    "inflammation": {"cs": "Zánět", "en": "Inflammation"},
    "liver_muscle": {"cs": "Játra / svaly", "en": "Liver / muscle"},
    "kidney": {"cs": "Ledviny", "en": "Kidney"},
    "electrolytes": {"cs": "Elektrolyty", "en": "Electrolytes"},
    "other": {"cs": "Ostatní", "en": "Other"},
    "custom": {"cs": "Vlastní", "en": "Custom"},
}


def marker_sort_key(code: str) -> tuple[int, int, str]:
    for cat_i, (_cat, codes) in enumerate(MARKER_CATEGORY_ORDER):
        if code in codes:
            return (cat_i, codes.index(code), code)
    return (len(MARKER_CATEGORY_ORDER), 0, code)


def marker_category(code: str) -> str:
    for cat, codes in MARKER_CATEGORY_ORDER:
        if code in codes:
            return cat
    return "other"


# Extra OCR aliases → marker code (lowercased, stripped tokens).
MARKER_ALIASES: dict[str, str] = {
    "na": "sodium",
    "natrium": "sodium",
    "sodík": "sodium",
    "k": "potassium",
    "kalium": "potassium",
    "draslík": "potassium",
    "cl": "chloride",
    "ci": "chloride",  # OCR often reads Cl as CI
    "chloridy": "chloride",
    "ca": "calcium",
    "vápník": "calcium",
    "vapnik": "calcium",
    "mg": "magnesium",
    "hořčík": "magnesium",
    "horcik": "magnesium",
    "kreatinin": "creatinine",
    "crea": "creatinine",
    "kyselina mocova": "uric_acid",
    "kyselina moč": "uric_acid",
    "kyselina močová": "uric_acid",
    "ua": "uric_acid",
    "urea": "urea",
    "bun": "urea",
    "osmolalita": "osmolality",
    "osmolalita vypoc": "osmolality",
    "osmolalita (vypoc": "osmolality",
    "ast": "ast",
    "alt": "alt",
    "ggt": "ggt",
    "gmt": "ggt",
    "ck": "ck",
    "cpk": "ck",
    "ldl": "ldl",
    "hdl": "hdl",
    "tg": "triglycerides",
    "triglyceridy": "triglycerides",
    "feritin": "ferritin",
    "ferritin": "ferritin",
    "hemoglobin": "hgb",
    "hb": "hgb",
    "hgb": "hgb",
    "glukoza": "glucose",
    "glukóza": "glucose",
    "glucose": "glucose",
}

# Lab LIS prefixes / method tokens commonly prepended to analyte names.
_LAB_PREFIX_TOKENS = {
    "had",
    "am",
    "s",
    "p",
    "u",
    "b",
    "c",
    "se",
    "pl",
    "wb",
    "edta",
    "lihep",
    "serum",
    "plasma",
    "urine",
}


def seed_markers(db) -> None:
    from app.models import Marker

    for item in MARKER_SEED:
        existing = db.get(Marker, item["code"])
        if existing:
            continue
        db.add(Marker(**item))
    db.commit()


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().strip()


def clean_ocr_label(label: str) -> str:
    """Strip lab method prefixes like 'HAD AM S AST' → 'AST'."""
    raw = " ".join((label or "").replace("_", " ").split())
    if not raw:
        return ""
    tokens = re.split(r"[\s/|]+", raw)
    kept: list[str] = []
    for tok in tokens:
        folded = _fold(tok).strip("()[].,:;+-")
        if not folded:
            continue
        if not kept and folded in _LAB_PREFIX_TOKENS:
            continue
        if not kept and len(folded) <= 2 and folded.isalpha() and folded in _LAB_PREFIX_TOKENS:
            continue
        kept.append(tok.strip("()[].,:;"))
    cleaned = " ".join(kept).strip(" -:")
    return cleaned or raw


def match_marker(label: str, markers: list[MarkerLike]) -> MarkerLike | None:
    """Map noisy OCR label to catalog marker (exact / alias / contained name)."""
    if not label or not markers:
        return None
    cleaned = clean_ocr_label(label)
    folded = _fold(cleaned)
    folded_compact = re.sub(r"[^a-z0-9]+", "", folded)
    by_code = {m.code: m for m in markers}

    # 1) alias exact
    if folded in MARKER_ALIASES and MARKER_ALIASES[folded] in by_code:
        return by_code[MARKER_ALIASES[folded]]

    # 2) code / names exact (folded)
    candidates: list[tuple[int, Marker]] = []
    for m in markers:
        names = {_fold(m.code), _fold(m.name_cs), _fold(m.name_en)}
        if folded in names or folded_compact == re.sub(r"[^a-z0-9]+", "", _fold(m.code)):
            candidates.append((1000 + len(m.code), m))
            continue
        for name in names:
            if not name:
                continue
            if name == folded:
                candidates.append((900 + len(name), m))
            elif len(name) >= 3 and (name in folded or folded in name):
                # Prefer longer analyte names to avoid 'k' / 'ca' false positives via substring path
                score = 100 + len(name)
                if re.search(rf"(^|[^a-z0-9]){re.escape(name)}([^a-z0-9]|$)", folded):
                    score += 200
                candidates.append((score, m))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # 3) alias token-wise (last token often is the analyte: AST)
    tokens = [_fold(t) for t in cleaned.split() if t]
    for tok in reversed(tokens):
        if tok in MARKER_ALIASES and MARKER_ALIASES[tok] in by_code:
            return by_code[MARKER_ALIASES[tok]]
        for m in markers:
            if tok == _fold(m.code) or tok == _fold(m.name_cs) or tok == _fold(m.name_en):
                return m
    return None
