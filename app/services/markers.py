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
    {"code": "rbc", "name_cs": "Erytrocyty", "name_en": "RBC", "default_unit": "10^12/l", "tip_ref_low": 4.0, "tip_ref_high": 5.8},
    {"code": "mcv", "name_cs": "MCV", "name_en": "MCV", "default_unit": "fl", "tip_ref_low": 80, "tip_ref_high": 96},
    {"code": "mch", "name_cs": "MCH", "name_en": "MCH", "default_unit": "pg", "tip_ref_low": 27, "tip_ref_high": 32},
    {"code": "mchc", "name_cs": "MCHC", "name_en": "MCHC", "default_unit": "g/l", "tip_ref_low": 320, "tip_ref_high": 360},
    {"code": "rdw", "name_cs": "RDW", "name_en": "RDW", "default_unit": "%", "tip_ref_low": 11, "tip_ref_high": 15},
    {"code": "wbc", "name_cs": "Leukocyty", "name_en": "WBC", "default_unit": "10^9/l", "tip_ref_low": 4.0, "tip_ref_high": 10.0},
    {"code": "plt", "name_cs": "Trombocyty", "name_en": "Platelets", "default_unit": "10^9/l", "tip_ref_low": 150, "tip_ref_high": 400},
    {"code": "mpv", "name_cs": "MPV", "name_en": "MPV", "default_unit": "fl", "tip_ref_low": 7, "tip_ref_high": 12},
    {"code": "pdw", "name_cs": "PDW", "name_en": "PDW", "default_unit": "%", "tip_ref_low": 9, "tip_ref_high": 17},
    {"code": "nrbc", "name_cs": "Normoblasty", "name_en": "NRBC", "default_unit": "%", "tip_ref_low": None, "tip_ref_high": 0.0},
    {"code": "nrbc_abs", "name_cs": "Normoblasty abs. počet", "name_en": "NRBC absolute", "default_unit": "10^9/l", "tip_ref_low": None, "tip_ref_high": 0.015},
    {"code": "neutrophils", "name_cs": "Neutrofily", "name_en": "Neutrophils", "default_unit": "%", "tip_ref_low": 45, "tip_ref_high": 70},
    {"code": "neutrophils_abs", "name_cs": "Neutrofily abs. počet", "name_en": "Neutrophils absolute", "default_unit": "10^9/l", "tip_ref_low": 2.0, "tip_ref_high": 7.0},
    {"code": "lymphocytes", "name_cs": "Lymfocyty", "name_en": "Lymphocytes", "default_unit": "%", "tip_ref_low": 20, "tip_ref_high": 45},
    {"code": "lymphocytes_abs", "name_cs": "Lymfocyty abs. počet", "name_en": "Lymphocytes absolute", "default_unit": "10^9/l", "tip_ref_low": 0.8, "tip_ref_high": 4.0},
    {"code": "monocytes", "name_cs": "Monocyty", "name_en": "Monocytes", "default_unit": "%", "tip_ref_low": 2, "tip_ref_high": 10},
    {"code": "monocytes_abs", "name_cs": "Monocyty abs. počet", "name_en": "Monocytes absolute", "default_unit": "10^9/l", "tip_ref_low": 0.08, "tip_ref_high": 1.2},
    {"code": "eosinophils", "name_cs": "Eozinofily", "name_en": "Eosinophils", "default_unit": "%", "tip_ref_low": 0, "tip_ref_high": 5},
    {"code": "eosinophils_abs", "name_cs": "Eozinofily abs. počet", "name_en": "Eosinophils absolute", "default_unit": "10^9/l", "tip_ref_low": 0.0, "tip_ref_high": 0.5},
    {"code": "basophils", "name_cs": "Bazofily", "name_en": "Basophils", "default_unit": "%", "tip_ref_low": 0, "tip_ref_high": 2},
    {"code": "basophils_abs", "name_cs": "Bazofily abs. počet", "name_en": "Basophils absolute", "default_unit": "10^9/l", "tip_ref_low": 0.0, "tip_ref_high": 0.2},
    {"code": "ig", "name_cs": "Nezralé granulocyty", "name_en": "Immature granulocytes", "default_unit": "%", "tip_ref_low": 0, "tip_ref_high": 0.6},
    {"code": "ig_abs", "name_cs": "Nezralé granulocyty abs. počet", "name_en": "IG absolute", "default_unit": "10^9/l", "tip_ref_low": 0.0, "tip_ref_high": 0.06},
    {"code": "ferritin", "name_cs": "Feritin", "name_en": "Ferritin", "default_unit": "ug/l", "tip_ref_low": 30, "tip_ref_high": 300},
    {"code": "iron", "name_cs": "Železo", "name_en": "Iron", "default_unit": "umol/l", "tip_ref_low": 11, "tip_ref_high": 30},
    {"code": "vitamin_d", "name_cs": "Vitamin D (25-OH)", "name_en": "Vitamin D (25-OH)", "default_unit": "nmol/l", "tip_ref_low": 75, "tip_ref_high": 125},
    {"code": "b12", "name_cs": "Vitamin B12", "name_en": "Vitamin B12", "default_unit": "pmol/l", "tip_ref_low": 150, "tip_ref_high": 600},
    {"code": "folate", "name_cs": "Folát", "name_en": "Folate", "default_unit": "nmol/l", "tip_ref_low": 10, "tip_ref_high": 45},
    {"code": "tsh", "name_cs": "TSH", "name_en": "TSH", "default_unit": "mIU/l", "tip_ref_low": 0.4, "tip_ref_high": 4.0},
    {"code": "ft4", "name_cs": "fT4", "name_en": "Free T4", "default_unit": "pmol/l", "tip_ref_low": 10, "tip_ref_high": 25},
    {"code": "ft3", "name_cs": "fT3", "name_en": "Free T3", "default_unit": "pmol/l", "tip_ref_low": 3.1, "tip_ref_high": 6.8},
    {"code": "anti_tg", "name_cs": "anti-TG", "name_en": "anti-TG", "default_unit": "IU/l", "tip_ref_low": None, "tip_ref_high": 4.5},
    {"code": "anti_tpo", "name_cs": "anti-TPO", "name_en": "anti-TPO", "default_unit": "IU/l", "tip_ref_low": None, "tip_ref_high": 34},
    {"code": "prolactin", "name_cs": "Prolaktin", "name_en": "Prolactin", "default_unit": "mIU/l", "tip_ref_low": 45, "tip_ref_high": 375},
    {"code": "testosterone", "name_cs": "Testosteron", "name_en": "Testosterone", "default_unit": "nmol/l", "tip_ref_low": 8, "tip_ref_high": 30},
    {"code": "cortisol", "name_cs": "Kortizol", "name_en": "Cortisol", "default_unit": "nmol/l", "tip_ref_low": 100, "tip_ref_high": 500},
    {"code": "pth", "name_cs": "PTH", "name_en": "PTH", "default_unit": "pmol/l", "tip_ref_low": 1.6, "tip_ref_high": 6.9},
    {"code": "osteocalcin", "name_cs": "Osteokalcin", "name_en": "Osteocalcin", "default_unit": "ug/l", "tip_ref_low": 14, "tip_ref_high": 42},
    {"code": "p1np", "name_cs": "P1NP", "name_en": "P1NP", "default_unit": "ug/l", "tip_ref_low": 20, "tip_ref_high": 70},
    {"code": "ctx", "name_cs": "Beta-CrossLaps", "name_en": "Beta-CrossLaps (CTX)", "default_unit": "ng/l", "tip_ref_low": 70, "tip_ref_high": 700},
    {"code": "psa", "name_cs": "PSA", "name_en": "PSA", "default_unit": "ug/l", "tip_ref_low": None, "tip_ref_high": 2.5},
    {"code": "fpsa", "name_cs": "fPSA", "name_en": "Free PSA", "default_unit": "ug/l", "tip_ref_low": None, "tip_ref_high": None},
    {"code": "fpsa_psa", "name_cs": "index fPSA/PSA", "name_en": "fPSA/PSA index", "default_unit": "1", "tip_ref_low": 0.25, "tip_ref_high": None},
    {"code": "glucose", "name_cs": "Glukóza", "name_en": "Glucose", "default_unit": "mmol/l", "tip_ref_low": 3.9, "tip_ref_high": 5.6},
    {"code": "hba1c", "name_cs": "HbA1c", "name_en": "HbA1c", "default_unit": "mmol/mol", "tip_ref_low": 20, "tip_ref_high": 42},
    {"code": "insulin", "name_cs": "Inzulin", "name_en": "Insulin", "default_unit": "mIU/l", "tip_ref_low": 2, "tip_ref_high": 25},
    {"code": "cholesterol", "name_cs": "Cholesterol", "name_en": "Cholesterol", "default_unit": "mmol/l", "tip_ref_low": None, "tip_ref_high": 5.0},
    {"code": "apob", "name_cs": "ApoB", "name_en": "ApoB", "default_unit": "g/l", "tip_ref_low": None, "tip_ref_high": 0.9},
    {"code": "ldl", "name_cs": "LDL cholesterol", "name_en": "LDL cholesterol", "default_unit": "mmol/l", "tip_ref_low": None, "tip_ref_high": 3.0},
    {"code": "hdl", "name_cs": "HDL cholesterol", "name_en": "HDL cholesterol", "default_unit": "mmol/l", "tip_ref_low": 1.0, "tip_ref_high": None},
    {"code": "non_hdl", "name_cs": "Non-HDL cholesterol", "name_en": "Non-HDL cholesterol", "default_unit": "mmol/l", "tip_ref_low": None, "tip_ref_high": 3.8},
    {"code": "triglycerides", "name_cs": "Triglyceridy", "name_en": "Triglycerides", "default_unit": "mmol/l", "tip_ref_low": None, "tip_ref_high": 1.7},
    {"code": "lpa", "name_cs": "Lp(a)", "name_en": "Lp(a)", "default_unit": "nmol/l", "tip_ref_low": None, "tip_ref_high": 75},
    {"code": "crp", "name_cs": "CRP", "name_en": "CRP", "default_unit": "mg/l", "tip_ref_low": None, "tip_ref_high": 5.0},
    {"code": "albumin", "name_cs": "Albumin", "name_en": "Albumin", "default_unit": "g/l", "tip_ref_low": 35, "tip_ref_high": 53},
    {"code": "total_protein", "name_cs": "Celková bílkovina", "name_en": "Total protein", "default_unit": "g/l", "tip_ref_low": 65, "tip_ref_high": 85},
    {"code": "ck", "name_cs": "CK", "name_en": "CK", "default_unit": "U/l", "tip_ref_low": 30, "tip_ref_high": 200},
    {"code": "alt", "name_cs": "ALT", "name_en": "ALT", "default_unit": "U/l", "tip_ref_low": 5, "tip_ref_high": 45},
    {"code": "ast", "name_cs": "AST", "name_en": "AST", "default_unit": "U/l", "tip_ref_low": 5, "tip_ref_high": 45},
    {"code": "ggt", "name_cs": "GGT", "name_en": "GGT", "default_unit": "U/l", "tip_ref_low": 5, "tip_ref_high": 60},
    {"code": "alp", "name_cs": "ALP", "name_en": "ALP", "default_unit": "U/l", "tip_ref_low": 40, "tip_ref_high": 130},
    {"code": "bilirubin", "name_cs": "Bilirubin celkový", "name_en": "Total bilirubin", "default_unit": "umol/l", "tip_ref_low": 5, "tip_ref_high": 25},
    {"code": "bilirubin_direct", "name_cs": "Bilirubin konjugovaný", "name_en": "Direct bilirubin", "default_unit": "umol/l", "tip_ref_low": None, "tip_ref_high": 5.1},
    {"code": "creatinine", "name_cs": "Kreatinin", "name_en": "Creatinine", "default_unit": "umol/l", "tip_ref_low": 60, "tip_ref_high": 104},
    {"code": "urea", "name_cs": "Urea", "name_en": "Urea", "default_unit": "mmol/l", "tip_ref_low": 2.5, "tip_ref_high": 8.0},
    {"code": "uric_acid", "name_cs": "Kyselina močová", "name_en": "Uric acid", "default_unit": "umol/l", "tip_ref_low": 200, "tip_ref_high": 420},
    {"code": "egfr", "name_cs": "eGFR", "name_en": "eGFR", "default_unit": "ml/min/1.73m2", "tip_ref_low": 90, "tip_ref_high": None},
    {"code": "sodium", "name_cs": "Sodík", "name_en": "Sodium", "default_unit": "mmol/l", "tip_ref_low": 136, "tip_ref_high": 145},
    {"code": "potassium", "name_cs": "Draslík", "name_en": "Potassium", "default_unit": "mmol/l", "tip_ref_low": 3.5, "tip_ref_high": 5.1},
    {"code": "chloride", "name_cs": "Chloridy", "name_en": "Chloride", "default_unit": "mmol/l", "tip_ref_low": 98, "tip_ref_high": 107},
    {"code": "calcium", "name_cs": "Vápník", "name_en": "Calcium", "default_unit": "mmol/l", "tip_ref_low": 2.15, "tip_ref_high": 2.55},
    {"code": "magnesium", "name_cs": "Hořčík", "name_en": "Magnesium", "default_unit": "mmol/l", "tip_ref_low": 0.7, "tip_ref_high": 1.0},
    {"code": "phosphorus", "name_cs": "Fosfor", "name_en": "Phosphorus", "default_unit": "mmol/l", "tip_ref_low": 0.75, "tip_ref_high": 1.65},
    {"code": "osmolality", "name_cs": "Osmolalita", "name_en": "Osmolality", "default_unit": "mmol/kg", "tip_ref_low": 275, "tip_ref_high": 295},
    {"code": "homocysteine", "name_cs": "Homocystein", "name_en": "Homocysteine", "default_unit": "umol/l", "tip_ref_low": None, "tip_ref_high": 12},
]

# Display order for trends / multi-chart pages (category → marker codes).
MARKER_CATEGORY_ORDER: list[tuple[str, list[str]]] = [
    (
        "hematology",
        [
            "hgb", "hct", "rbc", "mcv", "mch", "mchc", "rdw", "wbc", "plt", "mpv", "pdw",
            "nrbc", "nrbc_abs",
            "neutrophils", "neutrophils_abs",
            "lymphocytes", "lymphocytes_abs",
            "monocytes", "monocytes_abs",
            "eosinophils", "eosinophils_abs",
            "basophils", "basophils_abs",
            "ig", "ig_abs",
        ],
    ),
    ("iron", ["ferritin", "iron"]),
    ("vitamins", ["vitamin_d", "b12", "folate"]),
    ("thyroid", ["tsh", "ft4", "ft3", "anti_tg", "anti_tpo"]),
    ("hormones", ["testosterone", "cortisol", "prolactin"]),
    ("bone", ["ctx", "osteocalcin", "p1np", "pth"]),
    ("tumor", ["psa", "fpsa", "fpsa_psa"]),
    ("glucose", ["glucose", "hba1c", "insulin"]),
    ("lipids", ["apob", "cholesterol", "ldl", "hdl", "non_hdl", "triglycerides", "lpa"]),
    ("inflammation", ["crp", "homocysteine", "albumin", "total_protein"]),
    ("liver_muscle", ["ck", "alt", "ast", "ggt", "alp", "bilirubin", "bilirubin_direct"]),
    ("kidney", ["creatinine", "urea", "uric_acid", "egfr"]),
    ("electrolytes", ["sodium", "potassium", "chloride", "calcium", "magnesium", "phosphorus", "osmolality"]),
]

MARKER_CATEGORY_LABELS = {
    "hematology": {"cs": "Hematologie", "en": "Hematology"},
    "iron": {"cs": "Železo", "en": "Iron"},
    "vitamins": {"cs": "Vitamíny", "en": "Vitamins"},
    "thyroid": {"cs": "Štítná žláza", "en": "Thyroid"},
    "hormones": {"cs": "Hormony", "en": "Hormones"},
    "bone": {"cs": "Kosti", "en": "Bone"},
    "tumor": {"cs": "Tumormarkery", "en": "Tumor markers"},
    "glucose": {"cs": "Glukóza / metabolismus", "en": "Glucose / metabolism"},
    "lipids": {"cs": "Lipidy", "en": "Lipids"},
    "inflammation": {"cs": "Zánět / proteiny", "en": "Inflammation / proteins"},
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
    "fosfor": "phosphorus",
    "fosfáty": "phosphorus",
    "phosphate": "phosphorus",
    "s_p": "phosphorus",
    "s p": "phosphorus",
    # NOTE: do not alias bare "p" — matches PSA/P1NP/PTH noise
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
    "egfr": "egfr",
    "ckd-epi": "egfr",
    "ckd epi": "egfr",
    "ast": "ast",
    "alt": "alt",
    "ggt": "ggt",
    "gmt": "ggt",
    "alp": "alp",
    "alkalicka fosfataza": "alp",
    "alkalická fosfatáza": "alp",
    "bilirubin": "bilirubin",
    "bilirubin celkovy": "bilirubin",
    "bilirubin celkový": "bilirubin",
    "bilirubin konjugovany": "bilirubin_direct",
    "bilirubin konjugovaný": "bilirubin_direct",
    "primy bilirubin": "bilirubin_direct",
    "přímý bilirubin": "bilirubin_direct",
    "ck": "ck",
    "cpk": "ck",
    "ldl": "ldl",
    "hdl": "hdl",
    "non-hdl": "non_hdl",
    "non hdl": "non_hdl",
    "non-hdl cholesterol": "non_hdl",
    "cholesterol": "cholesterol",
    "celkovy cholesterol": "cholesterol",
    "tg": "triglycerides",
    "triglyceridy": "triglycerides",
    "triacylglyceroly": "triglycerides",
    "triacylglycerides": "triglycerides",
    "feritin": "ferritin",
    "ferritin": "ferritin",
    "hemoglobin": "hgb",
    "hb": "hgb",
    "hgb": "hgb",
    "hematokrit": "hct",
    "hct": "hct",
    "erytrocyty": "rbc",
    "erythrocytes": "rbc",
    "rbc": "rbc",
    "mcv": "mcv",
    "strobjerytr": "mcv",
    "str.obj.erytr": "mcv",
    "mch": "mch",
    "barvivo erytr": "mch",
    "barvivo erytrocytu": "mch",
    "mchc": "mchc",
    "str.barev.kon": "mchc",
    "strebarevkon": "mchc",
    "rdw": "rdw",
    "distr.kriv.ery": "rdw",
    "distrkriv.ery": "rdw",
    "wbc": "wbc",
    "leukocyty": "wbc",
    "plt": "plt",
    "trombocyty": "plt",
    "mpv": "mpv",
    "str.obj.trombo": "mpv",
    "strobjtrombo": "mpv",
    "pdw": "pdw",
    "distrkriv.tr": "pdw",
    "distr.kriv.tr": "pdw",
    "nrbc": "nrbc",
    "normoblasty": "nrbc",
    "normoblasty abs pocet": "nrbc_abs",
    "normoblasty abs. pocet": "nrbc_abs",
    "neutrofily": "neutrophils",
    "neutrophils": "neutrophils",
    "neutrofily abs pocet": "neutrophils_abs",
    "neutrofily abs. pocet": "neutrophils_abs",
    "neutrofilyabs.pocet": "neutrophils_abs",
    "lymfocyty": "lymphocytes",
    "lymphocytes": "lymphocytes",
    "lymfocyty abs pocet": "lymphocytes_abs",
    "lymfocyty abs. pocet": "lymphocytes_abs",
    "lymfocytyabs.pocet": "lymphocytes_abs",
    "monocyty": "monocytes",
    "monocytes": "monocytes",
    "monocyty abs pocet": "monocytes_abs",
    "monocyty abs. pocet": "monocytes_abs",
    "monocytyabs.pocet": "monocytes_abs",
    "eozinofily": "eosinophils",
    "eosinofily": "eosinophils",
    "eosinophils": "eosinophils",
    "eozinofily abs pocet": "eosinophils_abs",
    "eozinofily abs. pocet": "eosinophils_abs",
    "eozinofilyabs.pocet": "eosinophils_abs",
    "bazofily": "basophils",
    "basofily": "basophils",
    "basophils": "basophils",
    "bazofily abs pocet": "basophils_abs",
    "bazofily abs. pocet": "basophils_abs",
    "bazofilyabs.pocet": "basophils_abs",
    "nezrale granulocyty": "ig",
    "nezralé granulocyty": "ig",
    "immature granulocytes": "ig",
    "ig": "ig",
    "nezrale granulocyty abs pocet": "ig_abs",
    "nezralé granulocyty abs. pocet": "ig_abs",
    "nezralegranulocytyabs.pocet": "ig_abs",
    "nezralégranulocytyabs.počet": "ig_abs",
    "glukoza": "glucose",
    "glukóza": "glucose",
    "glucose": "glucose",
    "crp": "crp",
    "hs-crp": "crp",
    "hs crp": "crp",
    "albumin": "albumin",
    "celkova bilkovina": "total_protein",
    "celková bílkovina": "total_protein",
    "total protein": "total_protein",
    "anti-tg": "anti_tg",
    "anti tg": "anti_tg",
    "antitg": "anti_tg",
    "anti-tpo": "anti_tpo",
    "anti tpo": "anti_tpo",
    "antitpo": "anti_tpo",
    "prolaktin": "prolactin",
    "prolactin": "prolactin",
    "pth": "pth",
    "parathormon": "pth",
    "osteokalcin": "osteocalcin",
    "osteocalcin": "osteocalcin",
    "p1np": "p1np",
    "pinp": "p1np",
    "beta-crosslaps": "ctx",
    "beta crosslaps": "ctx",
    "crosslaps": "ctx",
    "ctx": "ctx",
    "psa": "psa",
    "fpsa": "fpsa",
    "f-psa": "fpsa",
    "index fpsa/psa": "fpsa_psa",
    "fpsa/psa": "fpsa_psa",
    "25oh vitamin d": "vitamin_d",
    "25-oh vitamin d": "vitamin_d",
    "vitamin d": "vitamin_d",
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
            existing.name_cs = item["name_cs"]
            existing.name_en = item["name_en"]
            existing.default_unit = item["default_unit"]
            existing.tip_ref_low = item.get("tip_ref_low")
            existing.tip_ref_high = item.get("tip_ref_high")
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
    aliases_folded = {_fold(k): v for k, v in MARKER_ALIASES.items()}
    aliases_compact = {re.sub(r"[^a-z0-9]+", "", _fold(k)): v for k, v in MARKER_ALIASES.items()}

    tokens_raw = [t for t in re.split(r"[\s/|]+", cleaned) if t]
    tokens = [_fold(t).strip("()[].,:;#") for t in tokens_raw]
    tokens = [t for t in tokens if t]

    def _from_alias(code: str | None) -> MarkerLike | None:
        if code and code in by_code:
            return by_code[code]
        return None

    # 1) full-label alias (incl. glued OCR like "neutrofilyabs.pocet")
    hit = _from_alias(aliases_folded.get(folded)) or _from_alias(aliases_compact.get(folded_compact))
    if hit:
        return hit

    # 2) multi-word alias first (so "neutrofily abs pocet" wins over "neutrofily")
    for n in (4, 3, 2):
        if len(tokens) >= n:
            for phrase in (" ".join(tokens[-n:]), " ".join(tokens[:n])):
                hit = _from_alias(aliases_folded.get(phrase))
                if hit:
                    return hit
                compact = re.sub(r"[^a-z0-9]+", "", phrase)
                hit = _from_alias(aliases_compact.get(compact))
                if hit:
                    return hit

    # 3) Trailing lab abbreviation (e.g. "Barvivo erytr. MCH" → MCH)
    for tok in reversed(tokens):
        hit = _from_alias(aliases_folded.get(tok))
        if hit:
            return hit
        if tok in by_code:
            return by_code[tok]
        for m in markers:
            if tok == _fold(m.code) or tok == _fold(m.name_cs) or tok == _fold(m.name_en):
                return m

    # 4) code / names exact or contained (prefer longer names; prefer *_abs when label has abs)
    prefer_abs = "abs" in folded_compact
    candidates: list[tuple[int, MarkerLike]] = []
    for m in markers:
        names = {_fold(m.code), _fold(m.name_cs), _fold(m.name_en)}
        if folded in names or folded_compact == re.sub(r"[^a-z0-9]+", "", _fold(m.code)):
            score = 1000 + len(m.code)
            if prefer_abs and m.code.endswith("_abs"):
                score += 50
            elif prefer_abs and not m.code.endswith("_abs") and f"{m.code}_abs" in by_code:
                score -= 40
            candidates.append((score, m))
            continue
        for name in names:
            if not name:
                continue
            if name == folded:
                score = 900 + len(name)
                if prefer_abs and m.code.endswith("_abs"):
                    score += 50
                candidates.append((score, m))
            elif len(name) >= 3 and (name in folded or folded in name):
                score = 100 + len(name)
                if re.search(rf"(^|[^a-z0-9]){re.escape(name)}([^a-z0-9]|$)", folded):
                    score += 200
                if prefer_abs and m.code.endswith("_abs"):
                    score += 80
                if prefer_abs and not m.code.endswith("_abs") and f"{m.code}_abs" in by_code:
                    score -= 40
                candidates.append((score, m))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def resolve_marker(
    label: str,
    markers: list[MarkerLike],
    *,
    code_hint: str | None = None,
    user_aliases: dict[str, str] | None = None,
) -> MarkerLike | None:
    """Prefer explicit catalog code, then user alias, else fuzzy label match."""
    by_code = {m.code: m for m in markers}
    if code_hint and code_hint in by_code:
        return by_code[code_hint]
    if user_aliases and label:
        from app.services.label_aliases import normalize_alias_label

        norm = normalize_alias_label(label)
        code = user_aliases.get(norm) if norm else None
        if code and code in by_code:
            return by_code[code]
    return match_marker(label, markers)
