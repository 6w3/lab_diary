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
    # Iron status (beyond ferritin / Fe)
    {"code": "transferrin", "name_cs": "Transferin", "name_en": "Transferrin", "default_unit": "g/l", "tip_ref_low": 2.0, "tip_ref_high": 3.6},
    {"code": "tibc", "name_cs": "Vazebná kapacita železa (TIBC)", "name_en": "TIBC", "default_unit": "umol/l", "tip_ref_low": 45, "tip_ref_high": 70},
    {"code": "uibc", "name_cs": "Nenasycená vazebná kapacita (UIBC)", "name_en": "UIBC", "default_unit": "umol/l", "tip_ref_low": 20, "tip_ref_high": 50},
    {"code": "transferrin_sat", "name_cs": "Saturace transferinu", "name_en": "Transferrin saturation", "default_unit": "%", "tip_ref_low": 15, "tip_ref_high": 50},
    {"code": "stfr", "name_cs": "Solubilní receptor transferinu", "name_en": "sTfR", "default_unit": "mg/l", "tip_ref_low": 0.8, "tip_ref_high": 1.8},
    # Lipids / liver / pancreas extras
    {"code": "apoa1", "name_cs": "ApoA-I", "name_en": "ApoA-I", "default_unit": "g/l", "tip_ref_low": 1.0, "tip_ref_high": None},
    {"code": "ldh", "name_cs": "LDH", "name_en": "LDH", "default_unit": "U/l", "tip_ref_low": 135, "tip_ref_high": 250},
    {"code": "che", "name_cs": "Cholinesteráza", "name_en": "Cholinesterase", "default_unit": "U/l", "tip_ref_low": 5000, "tip_ref_high": 12000},
    {"code": "amylase", "name_cs": "Amyláza", "name_en": "Amylase", "default_unit": "U/l", "tip_ref_low": 28, "tip_ref_high": 100},
    {"code": "lipase", "name_cs": "Lipáza", "name_en": "Lipase", "default_unit": "U/l", "tip_ref_low": 13, "tip_ref_high": 60},
    {"code": "gmd", "name_cs": "GMD", "name_en": "GLDH", "default_unit": "U/l", "tip_ref_low": None, "tip_ref_high": 7},
    # Cardiac
    {"code": "troponin_i", "name_cs": "Troponin I (hs)", "name_en": "Troponin I (hs)", "default_unit": "ng/l", "tip_ref_low": None, "tip_ref_high": 34},
    {"code": "nt_pro_bnp", "name_cs": "NT-proBNP", "name_en": "NT-proBNP", "default_unit": "ng/l", "tip_ref_low": None, "tip_ref_high": 125},
    {"code": "ck_mb", "name_cs": "CK-MB", "name_en": "CK-MB", "default_unit": "ug/l", "tip_ref_low": None, "tip_ref_high": 5},
    {"code": "myoglobin", "name_cs": "Myoglobin", "name_en": "Myoglobin", "default_unit": "ug/l", "tip_ref_low": None, "tip_ref_high": 70},
    # Inflammation / coagulation / hematology extras
    {"code": "hs_crp", "name_cs": "hs-CRP", "name_en": "hs-CRP", "default_unit": "mg/l", "tip_ref_low": None, "tip_ref_high": 1.0},
    {"code": "esr", "name_cs": "FW (sedimentace)", "name_en": "ESR", "default_unit": "mm/h", "tip_ref_low": None, "tip_ref_high": 15},
    {"code": "fibrinogen", "name_cs": "Fibrinogen", "name_en": "Fibrinogen", "default_unit": "g/l", "tip_ref_low": 2.0, "tip_ref_high": 4.0},
    {"code": "inr", "name_cs": "INR (Quick)", "name_en": "INR", "default_unit": "1", "tip_ref_low": 0.8, "tip_ref_high": 1.2},
    {"code": "aptt", "name_cs": "aPTT", "name_en": "aPTT", "default_unit": "s", "tip_ref_low": 25, "tip_ref_high": 37},
    {"code": "d_dimer", "name_cs": "D-dimery", "name_en": "D-dimer", "default_unit": "mg/l", "tip_ref_low": None, "tip_ref_high": 0.5},
    {"code": "rf", "name_cs": "Revmatoidní faktor", "name_en": "Rheumatoid factor", "default_unit": "IU/ml", "tip_ref_low": None, "tip_ref_high": 14},
    {"code": "aslo", "name_cs": "ASLO", "name_en": "ASO", "default_unit": "IU/ml", "tip_ref_low": None, "tip_ref_high": 200},
    {"code": "reticulocytes", "name_cs": "Retikulocyty", "name_en": "Reticulocytes", "default_unit": "%", "tip_ref_low": 0.5, "tip_ref_high": 1.5},
    {"code": "reticulocytes_abs", "name_cs": "Retikulocyty abs. počet", "name_en": "Reticulocytes absolute", "default_unit": "10^9/l", "tip_ref_low": 25, "tip_ref_high": 90},
    # Hormones / thyroid extras
    {"code": "fsh", "name_cs": "FSH", "name_en": "FSH", "default_unit": "IU/l", "tip_ref_low": None, "tip_ref_high": None},
    {"code": "lh", "name_cs": "LH", "name_en": "LH", "default_unit": "IU/l", "tip_ref_low": None, "tip_ref_high": None},
    {"code": "estradiol", "name_cs": "Estradiol", "name_en": "Estradiol", "default_unit": "pmol/l", "tip_ref_low": None, "tip_ref_high": None},
    {"code": "progesterone", "name_cs": "Progesteron", "name_en": "Progesterone", "default_unit": "nmol/l", "tip_ref_low": None, "tip_ref_high": None},
    {"code": "shbg", "name_cs": "SHBG", "name_en": "SHBG", "default_unit": "nmol/l", "tip_ref_low": 10, "tip_ref_high": 70},
    {"code": "free_testosterone", "name_cs": "Volný testosteron", "name_en": "Free testosterone", "default_unit": "pmol/l", "tip_ref_low": None, "tip_ref_high": None},
    {"code": "dhea_s", "name_cs": "DHEA-S", "name_en": "DHEA-S", "default_unit": "umol/l", "tip_ref_low": 2, "tip_ref_high": 10},
    {"code": "amh", "name_cs": "AMH", "name_en": "AMH", "default_unit": "ug/l", "tip_ref_low": None, "tip_ref_high": None},
    {"code": "hcg", "name_cs": "hCG", "name_en": "hCG", "default_unit": "IU/l", "tip_ref_low": None, "tip_ref_high": 5},
    {"code": "tt3", "name_cs": "T3 celkový", "name_en": "Total T3", "default_unit": "nmol/l", "tip_ref_low": 1.0, "tip_ref_high": 3.0},
    {"code": "tt4", "name_cs": "T4 celkový", "name_en": "Total T4", "default_unit": "nmol/l", "tip_ref_low": 60, "tip_ref_high": 150},
    {"code": "anti_tshr", "name_cs": "anti-TSHR (TRAK)", "name_en": "anti-TSHR (TRAb)", "default_unit": "IU/l", "tip_ref_low": None, "tip_ref_high": 1.5},
    # Vitamins / minerals / kidney / metabolism
    {"code": "zinc", "name_cs": "Zinek", "name_en": "Zinc", "default_unit": "umol/l", "tip_ref_low": 10, "tip_ref_high": 18},
    {"code": "copper", "name_cs": "Měď", "name_en": "Copper", "default_unit": "umol/l", "tip_ref_low": 11, "tip_ref_high": 22},
    {"code": "selenium", "name_cs": "Selen", "name_en": "Selenium", "default_unit": "ug/l", "tip_ref_low": 70, "tip_ref_high": 150},
    {"code": "cystatin_c", "name_cs": "Cystatin C", "name_en": "Cystatin C", "default_unit": "mg/l", "tip_ref_low": 0.6, "tip_ref_high": 1.0},
    {"code": "lactate", "name_cs": "Laktát", "name_en": "Lactate", "default_unit": "mmol/l", "tip_ref_low": 0.5, "tip_ref_high": 2.2},
    {"code": "c_peptide", "name_cs": "C-peptid", "name_en": "C-peptide", "default_unit": "nmol/l", "tip_ref_low": 0.3, "tip_ref_high": 1.5},
    # Immunoglobulins
    {"code": "iga", "name_cs": "IgA", "name_en": "IgA", "default_unit": "g/l", "tip_ref_low": 0.7, "tip_ref_high": 4.0},
    {"code": "igg", "name_cs": "IgG", "name_en": "IgG", "default_unit": "g/l", "tip_ref_low": 7, "tip_ref_high": 16},
    {"code": "igm", "name_cs": "IgM", "name_en": "IgM", "default_unit": "g/l", "tip_ref_low": 0.4, "tip_ref_high": 2.3},
    {"code": "ige", "name_cs": "IgE celkový", "name_en": "Total IgE", "default_unit": "IU/ml", "tip_ref_low": None, "tip_ref_high": 100},
    # Tumor markers (beyond PSA)
    {"code": "cea", "name_cs": "CEA", "name_en": "CEA", "default_unit": "ug/l", "tip_ref_low": None, "tip_ref_high": 5},
    {"code": "afp", "name_cs": "AFP", "name_en": "AFP", "default_unit": "ug/l", "tip_ref_low": None, "tip_ref_high": 7},
    {"code": "ca125", "name_cs": "CA 125", "name_en": "CA 125", "default_unit": "kU/l", "tip_ref_low": None, "tip_ref_high": 35},
    {"code": "ca19_9", "name_cs": "CA 19-9", "name_en": "CA 19-9", "default_unit": "kU/l", "tip_ref_low": None, "tip_ref_high": 37},
    {"code": "ca15_3", "name_cs": "CA 15-3", "name_en": "CA 15-3", "default_unit": "kU/l", "tip_ref_low": None, "tip_ref_high": 30},
    {"code": "ca72_4", "name_cs": "CA 72-4", "name_en": "CA 72-4", "default_unit": "kU/l", "tip_ref_low": None, "tip_ref_high": 6.9},
    {"code": "scc", "name_cs": "SCC", "name_en": "SCC antigen", "default_unit": "ug/l", "tip_ref_low": None, "tip_ref_high": 1.5},
    {"code": "thyroglobulin", "name_cs": "Tyreoglobulin (Tg)", "name_en": "Thyroglobulin", "default_unit": "ug/l", "tip_ref_low": None, "tip_ref_high": 55},
    {"code": "pct", "name_cs": "PCT (trombocytární hematokrit)", "name_en": "Plateletcrit (PCT)", "default_unit": "%", "tip_ref_low": 0.1, "tip_ref_high": 0.5},
    {"code": "hiiaa", "name_cs": "5-HIAA", "name_en": "5-HIAA", "default_unit": "mg/24h", "tip_ref_low": None, "tip_ref_high": 8},
    {"code": "vma", "name_cs": "Kyselina vanilmandlová (VMA)", "name_en": "VMA", "default_unit": "mg/24h", "tip_ref_low": None, "tip_ref_high": 6.5},
    {"code": "bence_jones", "name_cs": "Bence-Jonesova bílkovina", "name_en": "Bence-Jones protein", "default_unit": "mg/24h", "tip_ref_low": None, "tip_ref_high": None},
    {"code": "urobilinogen", "name_cs": "Urobilinogen", "name_en": "Urobilinogen", "default_unit": "umol/l", "tip_ref_low": None, "tip_ref_high": 17},
    {"code": "urine_ketones", "name_cs": "Ketony (aceton) v moči", "name_en": "Urine ketones", "default_unit": "mmol/l", "tip_ref_low": None, "tip_ref_high": 0},
    {"code": "urine_blood", "name_cs": "Krev v moči", "name_en": "Urine blood", "default_unit": "1", "tip_ref_low": None, "tip_ref_high": 0},
    {"code": "urine_ph", "name_cs": "pH moči", "name_en": "Urine pH", "default_unit": "1", "tip_ref_low": 5.0, "tip_ref_high": 8.0},
]

# Display order for trends / multi-chart pages (category → marker codes).
MARKER_CATEGORY_ORDER: list[tuple[str, list[str]]] = [
    (
        "hematology",
        [
            "hgb", "hct", "rbc", "mcv", "mch", "mchc", "rdw", "wbc", "plt", "mpv", "pdw", "pct",
            "nrbc", "nrbc_abs",
            "neutrophils", "neutrophils_abs",
            "lymphocytes", "lymphocytes_abs",
            "monocytes", "monocytes_abs",
            "eosinophils", "eosinophils_abs",
            "basophils", "basophils_abs",
            "ig", "ig_abs",
            "reticulocytes", "reticulocytes_abs",
            "esr",
        ],
    ),
    ("iron", ["ferritin", "iron", "transferrin", "tibc", "uibc", "transferrin_sat", "stfr"]),
    ("vitamins", ["vitamin_d", "b12", "folate", "zinc", "copper", "selenium"]),
    ("thyroid", ["tsh", "ft4", "ft3", "tt4", "tt3", "thyroglobulin", "anti_tg", "anti_tpo", "anti_tshr"]),
    (
        "hormones",
        [
            "testosterone", "free_testosterone", "shbg", "cortisol", "prolactin",
            "fsh", "lh", "estradiol", "progesterone", "dhea_s", "amh", "hcg",
        ],
    ),
    ("bone", ["ctx", "osteocalcin", "p1np", "pth"]),
    ("tumor", ["psa", "fpsa", "fpsa_psa", "cea", "afp", "ca125", "ca19_9", "ca15_3", "ca72_4", "scc"]),
    ("glucose", ["glucose", "hba1c", "insulin", "c_peptide", "lactate"]),
    ("lipids", ["apob", "apoa1", "cholesterol", "ldl", "hdl", "non_hdl", "triglycerides", "lpa"]),
    ("inflammation", ["crp", "hs_crp", "homocysteine", "albumin", "total_protein", "rf", "aslo"]),
    ("immunity", ["iga", "igg", "igm", "ige"]),
    ("liver_muscle", ["ck", "ck_mb", "alt", "ast", "ggt", "alp", "ldh", "che", "gmd", "bilirubin", "bilirubin_direct", "amylase", "lipase"]),
    ("cardiac", ["troponin_i", "nt_pro_bnp", "myoglobin"]),
    ("coagulation", ["inr", "aptt", "fibrinogen", "d_dimer"]),
    ("kidney", ["creatinine", "urea", "uric_acid", "egfr", "cystatin_c"]),
    (
        "urine",
        [
            "urine_ph", "urobilinogen", "urine_ketones", "urine_blood",
            "hiiaa", "vma", "bence_jones",
        ],
    ),
    ("electrolytes", ["sodium", "potassium", "chloride", "calcium", "magnesium", "phosphorus", "osmolality"]),
]

MARKER_CATEGORY_LABELS = {
    "hematology": {"cs": "Hematologie", "en": "Hematology"},
    "iron": {"cs": "Železo", "en": "Iron"},
    "vitamins": {"cs": "Vitamíny / stopové prvky", "en": "Vitamins / trace elements"},
    "thyroid": {"cs": "Štítná žláza", "en": "Thyroid"},
    "hormones": {"cs": "Hormony", "en": "Hormones"},
    "bone": {"cs": "Kosti", "en": "Bone"},
    "tumor": {"cs": "Tumormarkery", "en": "Tumor markers"},
    "glucose": {"cs": "Glukóza / metabolismus", "en": "Glucose / metabolism"},
    "lipids": {"cs": "Lipidy", "en": "Lipids"},
    "inflammation": {"cs": "Zánět / proteiny", "en": "Inflammation / proteins"},
    "immunity": {"cs": "Imunoglobuliny", "en": "Immunoglobulins"},
    "liver_muscle": {"cs": "Játra / svaly / pankreas", "en": "Liver / muscle / pancreas"},
    "cardiac": {"cs": "Kardiální markery", "en": "Cardiac markers"},
    "coagulation": {"cs": "Koagulace", "en": "Coagulation"},
    "kidney": {"cs": "Ledviny", "en": "Kidney"},
    "urine": {"cs": "Moč / metabolity", "en": "Urine / metabolites"},
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
    "odhad dle ckd-epi": "egfr",
    "odhad dle ckd epi": "egfr",
    "vypocet gf mdrd": "egfr",
    "vypocet gf mdrd kre": "egfr",
    "vypocet gf mdrd kre.": "egfr",
    "gf mdrd": "egfr",
    "mdrd": "egfr",
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
    # Thyroglobulin must beat bare "tg" via longer phrase / name token
    "tyreoglobulin": "thyroglobulin",
    "thyroglobulin": "thyroglobulin",
    "tg tyreoglobulin": "thyroglobulin",
    "tg (tyreoglobulin)": "thyroglobulin",
    "tg thyroglobulin": "thyroglobulin",
    "feritin": "ferritin",
    "ferritin": "ferritin",
    "hemoglobin": "hgb",
    "hb": "hgb",
    "hgb": "hgb",
    "hematokrit": "hct",
    "hct": "hct",
    "pct": "pct",
    "plateletcrit": "pct",
    "tromb hematokrit": "pct",
    "tromb. hematokrit": "pct",
    "trombocytarni hematokrit": "pct",
    "trombocytární hematokrit": "pct",
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
    "hs-crp": "hs_crp",
    "hs crp": "hs_crp",
    "hscrp": "hs_crp",
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
    # New catalog aliases (CZ lab labels)
    "transferin": "transferrin",
    "transferrin": "transferrin",
    "tibc": "tibc",
    "celkova vazebna kapacita": "tibc",
    "celková vazebná kapacita": "tibc",
    "vazebna kapacita zeleza": "tibc",
    "vazebná kapacita železa": "tibc",
    "uibc": "uibc",
    "nenasycena vazebna kapacita": "uibc",
    "nenasycená vazebná kapacita": "uibc",
    "saturace transferinu": "transferrin_sat",
    "saturace transferinu %": "transferrin_sat",
    "transferrin saturation": "transferrin_sat",
    "stfr": "stfr",
    "stfrr": "stfr",
    "solubilni receptor transferinu": "stfr",
    "solubilní receptor transferinu": "stfr",
    "apoa1": "apoa1",
    "apo a-i": "apoa1",
    "apo a1": "apoa1",
    "apo-a1": "apoa1",
    "ldh": "ldh",
    "ld": "ldh",
    "laktatdehydrogenaza": "ldh",
    "laktátdehydrogenáza": "ldh",
    "che": "che",
    "cholinesterase": "che",
    "cholinesteraza": "che",
    "cholinesteráza": "che",
    "amylaza": "amylase",
    "amyláza": "amylase",
    "amylase": "amylase",
    "ams": "amylase",
    "lipaza": "lipase",
    "lipáza": "lipase",
    "lipase": "lipase",
    "gmd": "gmd",
    "gldh": "gmd",
    "troponin": "troponin_i",
    "troponin i": "troponin_i",
    "hs troponin i": "troponin_i",
    "hstni": "troponin_i",
    "nt-probnp": "nt_pro_bnp",
    "nt probnp": "nt_pro_bnp",
    "ntprobnp": "nt_pro_bnp",
    "ck-mb": "ck_mb",
    "ck mb": "ck_mb",
    "ckmb": "ck_mb",
    "myoglobin": "myoglobin",
    "fw": "esr",
    "sedimentace": "esr",
    "esr": "esr",
    "fibrinogen": "fibrinogen",
    "inr": "inr",
    "quick": "inr",
    "pt-inr": "inr",
    "aptt": "aptt",
    "d-dimery": "d_dimer",
    "d dimery": "d_dimer",
    "d-dimer": "d_dimer",
    "ddimer": "d_dimer",
    "rf": "rf",
    "revmatoidni faktor": "rf",
    "revmatoidní faktor": "rf",
    "aslo": "aslo",
    "aso": "aslo",
    "antistreptolysin": "aslo",
    "retikulocyty": "reticulocytes",
    "reticulocytes": "reticulocytes",
    "retikulocyty abs pocet": "reticulocytes_abs",
    "retikulocyty abs. pocet": "reticulocytes_abs",
    "fsh": "fsh",
    "lh": "lh",
    "estradiol": "estradiol",
    "e2": "estradiol",
    "progesteron": "progesterone",
    "progesterone": "progesterone",
    "shbg": "shbg",
    "volny testosteron": "free_testosterone",
    "volný testosteron": "free_testosterone",
    "free testosterone": "free_testosterone",
    "dhea-s": "dhea_s",
    "dheas": "dhea_s",
    "dhea s": "dhea_s",
    "amh": "amh",
    "hcg": "hcg",
    "beta hcg": "hcg",
    "t3": "tt3",
    "t3 celkovy": "tt3",
    "t3 celkový": "tt3",
    "total t3": "tt3",
    "t4": "tt4",
    "t4 celkovy": "tt4",
    "t4 celkový": "tt4",
    "total t4": "tt4",
    "anti-tshr": "anti_tshr",
    "anti tshr": "anti_tshr",
    "trak": "anti_tshr",
    "trab": "anti_tshr",
    "zinek": "zinc",
    "zinc": "zinc",
    "med": "copper",
    "měď": "copper",
    "copper": "copper",
    "selen": "selenium",
    "selenium": "selenium",
    "cystatin c": "cystatin_c",
    "cystatin": "cystatin_c",
    "laktat": "lactate",
    "laktát": "lactate",
    "lactate": "lactate",
    "c-peptid": "c_peptide",
    "c peptid": "c_peptide",
    "c-peptide": "c_peptide",
    "iga": "iga",
    "igg": "igg",
    "igm": "igm",
    "ige": "ige",
    "cea": "cea",
    "afp": "afp",
    "alfa1-fetoprotein": "afp",
    "alfa-fetoprotein": "afp",
    "ca 125": "ca125",
    "ca125": "ca125",
    "ca 19-9": "ca19_9",
    "ca19-9": "ca19_9",
    "ca19_9": "ca19_9",
    "ca 15-3": "ca15_3",
    "ca15-3": "ca15_3",
    "ca15_3": "ca15_3",
    "ca 72-4": "ca72_4",
    "ca 72.4": "ca72_4",
    "ca72-4": "ca72_4",
    "ca72.4": "ca72_4",
    "ca72_4": "ca72_4",
    "scc": "scc",
    "scc ag": "scc",
    "5-hio": "hiiaa",
    "5-hiaa": "hiiaa",
    "5 hiaa": "hiiaa",
    "5hiaa": "hiiaa",
    "hiaa": "hiiaa",
    "kys vanilmadlova": "vma",
    "kys.vanilmadlova": "vma",
    "kyselina vanilmandlova": "vma",
    "kyselina vanilmandlová": "vma",
    "vanilmandlova": "vma",
    "vma": "vma",
    "bence-jones": "bence_jones",
    "bence jones": "bence_jones",
    "bencejones": "bence_jones",
    "urobilinogen": "urobilinogen",
    "aceton": "urine_ketones",
    "ketony": "urine_ketones",
    "ketony v moci": "urine_ketones",
    "ketony v moči": "urine_ketones",
    "krev v moci": "urine_blood",
    "krev v moči": "urine_blood",
    "occult blood": "urine_blood",
    "ph": "urine_ph",
    "ph moci": "urine_ph",
    "ph moči": "urine_ph",
    "urine ph": "urine_ph",
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


def match_marker_alias(label: str, markers: list[MarkerLike]) -> MarkerLike | None:
    """Strong OCR alias / trailing abbreviation hit only (no fuzzy name containment)."""
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

    hit = _from_alias(aliases_folded.get(folded)) or _from_alias(aliases_compact.get(folded_compact))
    if hit:
        return hit

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

    for tok in reversed(tokens):
        if len(tok) <= 2 and len(tokens) > 1:
            continue
        hit = _from_alias(aliases_folded.get(tok))
        if hit:
            return hit
        if tok in by_code:
            return by_code[tok]
        for m in markers:
            if tok == _fold(m.code) or tok == _fold(m.name_cs) or tok == _fold(m.name_en):
                return m
    return None


def match_marker(label: str, markers: list[MarkerLike]) -> MarkerLike | None:
    """Map noisy OCR label to catalog marker (exact / alias / contained name)."""
    if not label or not markers:
        return None
    strong = match_marker_alias(label, markers)
    if strong:
        return strong
    cleaned = clean_ocr_label(label)
    folded = _fold(cleaned)
    folded_compact = re.sub(r"[^a-z0-9]+", "", folded)
    by_code = {m.code: m for m in markers}

    # Fuzzy: code / names exact or contained (prefer longer names; prefer *_abs when label has abs)
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
            elif len(name) >= 3 and len(folded) >= 3 and (name in folded or folded in name):
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


def extract_lis_code_hint(label: str) -> str | None:
    """Pull catalog code from LIS bracket tags like 'Hemoglobin [HGB]' or GMT."""
    text = label or ""
    m = re.search(r"\[([A-Za-z0-9_\-]+)\]", text)
    token = m.group(1) if m else None
    if not token:
        # Standalone GMT (common CZ synonym for GGT)
        folded = _fold(text)
        if re.fullmatch(r"gmt", folded) or re.search(r"\bgmt\b", folded):
            return "ggt"
        return None
    raw = token.strip().lower().replace("-", "_")
    aliases = {
        "hgb": "hgb",
        "hb": "hgb",
        "hct": "hct",
        "rbc": "rbc",
        "wbc": "wbc",
        "plt": "plt",
        "mcv": "mcv",
        "mch": "mch",
        "mchc": "mchc",
        "rdw": "rdw",
        "mpv": "mpv",
        "pdw": "pdw",
        "nrbc": "nrbc",
        "gmt": "ggt",
        "ggt": "ggt",
        "alt": "alt",
        "ast": "ast",
        "alp": "alp",
        "ck": "ck",
        "ldh": "ldh",
        "ld": "ldh",
        "tsh": "tsh",
        "ft4": "ft4",
        "ft3": "ft3",
        "psa": "psa",
        "fpsa": "fpsa",
        "crp": "crp",
        "hscrp": "hs_crp",
        "hs_crp": "hs_crp",
    }
    return aliases.get(raw)


def resolve_marker(
    label: str,
    markers: list[MarkerLike],
    *,
    code_hint: str | None = None,
    user_aliases: dict[str, str] | None = None,
    allow_fuzzy: bool = True,
) -> MarkerLike | None:
    """Prefer explicit catalog code, LIS bracket, user alias, else fuzzy label match."""
    by_code = {m.code: m for m in markers}
    hint = (code_hint or "").strip().lower() or None
    if hint and hint in by_code:
        return by_code[hint]
    lis = extract_lis_code_hint(label)
    if lis and lis in by_code:
        return by_code[lis]
    if user_aliases and label:
        from app.services.label_aliases import normalize_alias_label

        norm = normalize_alias_label(label)
        code = user_aliases.get(norm) if norm else None
        if code and code in by_code:
            return by_code[code]
    if not allow_fuzzy:
        return None
    return match_marker(label, markers)
