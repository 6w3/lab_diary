from __future__ import annotations

from app.models import Marker

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
    {"code": "egfr", "name_cs": "eGFR", "name_en": "eGFR", "default_unit": "ml/min/1.73m2", "tip_ref_low": 90, "tip_ref_high": None},
    {"code": "sodium", "name_cs": "Sodík", "name_en": "Sodium", "default_unit": "mmol/l", "tip_ref_low": 136, "tip_ref_high": 145},
    {"code": "potassium", "name_cs": "Draslík", "name_en": "Potassium", "default_unit": "mmol/l", "tip_ref_low": 3.5, "tip_ref_high": 5.1},
    {"code": "magnesium", "name_cs": "Hořčík", "name_en": "Magnesium", "default_unit": "mmol/l", "tip_ref_low": 0.7, "tip_ref_high": 1.0},
    {"code": "homocysteine", "name_cs": "Homocystein", "name_en": "Homocysteine", "default_unit": "umol/l", "tip_ref_low": None, "tip_ref_high": 12},
]


def seed_markers(db) -> None:
    for item in MARKER_SEED:
        existing = db.get(Marker, item["code"])
        if existing:
            continue
        db.add(Marker(**item))
    db.commit()
