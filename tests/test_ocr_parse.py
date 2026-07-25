from app.services.markers import clean_ocr_label, match_marker
from app.services.storage import normalize_unit, parse_ocr_lines
from types import SimpleNamespace


def test_parse_ocr_lines_basic():
    text = """
Hemoglobin 145 g/l 135-170
Feritin 55 ug/l 30-300
Something garbage
TSH 2.1 mIU/l 0.4-4.0
"""
    rows = parse_ocr_lines(text)
    assert len(rows) >= 2
    names = " ".join(r["label"].lower() for r in rows)
    assert "hemoglobin" in names or "feritin" in names or "tsh" in names


def test_normalize_unit_micro_and_pkat_typo():
    assert normalize_unit("μkat/L") == "ukat/l"
    assert normalize_unit("µkat/l") == "ukat/l"
    assert normalize_unit("pkat/L") == "ukat/l"
    assert normalize_unit("pkat") == "ukat"
    assert normalize_unit("mmol/L") == "mmol/l"


def test_parse_ocr_lines_micro_unit():
    rows = parse_ocr_lines("ALT 0.55 μkat/L 0.10-0.80")
    assert rows
    assert rows[0]["unit"].lower().startswith("ukat")


def test_clean_lab_prefix():
    assert clean_ocr_label("HAD AM S AST") == "AST"
    assert clean_ocr_label("HAD AM S Kreatinin") == "Kreatinin"
    assert clean_ocr_label("HAD S Mg") == "Mg"
    assert clean_ocr_label("HAD AM S CI") == "CI"


def test_match_marker_with_prefix():
    markers = [
        SimpleNamespace(code="ast", name_cs="AST", name_en="AST", default_unit="U/l"),
        SimpleNamespace(code="creatinine", name_cs="Kreatinin", name_en="Creatinine", default_unit="umol/l"),
        SimpleNamespace(code="sodium", name_cs="Sodík", name_en="Sodium", default_unit="mmol/l"),
        SimpleNamespace(code="chloride", name_cs="Chloridy", name_en="Chloride", default_unit="mmol/l"),
        SimpleNamespace(code="magnesium", name_cs="Hořčík", name_en="Magnesium", default_unit="mmol/l"),
        SimpleNamespace(code="urea", name_cs="Urea", name_en="Urea", default_unit="mmol/l"),
        SimpleNamespace(code="uric_acid", name_cs="Kyselina močová", name_en="Uric acid", default_unit="umol/l"),
    ]
    assert match_marker("HAD AM S AST", markers).code == "ast"
    assert match_marker("HAD AM S Kreatinin", markers).code == "creatinine"
    assert match_marker("HAD AM S Na", markers).code == "sodium"
    assert match_marker("HAD AM S CI", markers).code == "chloride"
    assert match_marker("HAD S Mg", markers).code == "magnesium"
    assert match_marker("HAD AM S Urea", markers).code == "urea"
    assert match_marker("HAD AM S Kyselina moč", markers).code == "uric_acid"
