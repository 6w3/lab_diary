from app.services.ocr_parse import normalize_unit
from app.services.units import (
    convert_value,
    to_canonical,
    unit_group_for_marker,
    unit_options_for_marker,
)


def test_enzyme_ukat_to_ul():
    v, ok = convert_value(1.5, "ukat/l", "U/l")
    assert ok
    assert abs(v - 90.0) < 1e-6


def test_vitamin_d_nmol_to_ng():
    v, ok = convert_value(100.0, "nmol/l", "ng/ml", marker_code="vitamin_d")
    assert ok
    assert abs(v - 40.0641) < 1e-3


def test_to_canonical_glucose():
    v, unit, ok = to_canonical(90.0, "mg/dl", "glucose", "mmol/l")
    assert ok
    assert unit == "mmol/l"
    assert abs(v - 90.0 / 18.0182) < 1e-3


def test_hba1c_ifcc_to_ngsp():
    v, ok = convert_value(42.0, "mmol/mol", "%", marker_code="hba1c")
    assert ok
    assert abs(v - (0.09148 * 42 + 2.152)) < 1e-3


def test_iron_ug_dl_to_umol():
    v, unit, ok = to_canonical(100.0, "ug/dl", "iron", "umol/l")
    assert ok
    assert unit == "umol/l"
    assert abs(v - 100.0 / 5.586) < 1e-3


def test_uric_acid_mg_dl_to_umol():
    v, unit, ok = to_canonical(5.0, "mg/dl", "uric_acid", "umol/l")
    assert ok
    assert unit == "umol/l"
    assert abs(v - 5.0 * 59.48) < 1e-3


def test_calcium_mg_dl_to_mmol():
    v, unit, ok = to_canonical(10.0, "mg/dl", "calcium", "mmol/l")
    assert ok
    assert unit == "mmol/l"
    assert abs(v - 10.0 / 4.008) < 1e-3


def test_egfr_ml_s_to_ml_min():
    v, ok = convert_value(1.5, "ml/s", "ml/min/1.73m2", marker_code="egfr")
    assert ok
    assert abs(v - 90.0) < 1e-6


def test_fraction_to_percent():
    v, ok = convert_value(0.462, "1", "%")
    assert ok
    assert abs(v - 46.2) < 1e-6


def test_normalize_l_to_fraction():
    assert normalize_unit("l") == "1"
    assert normalize_unit("l/l") == "1"
    assert normalize_unit("µkat/l") == "ukat/l"


def test_hgb_unit_options_only_mass_group():
    opts = unit_options_for_marker("hgb", default_unit="g/l")
    assert "g/l" in opts
    assert "g/dl" in opts
    assert "ukat/l" not in opts
    assert unit_group_for_marker("hgb") == "mass_conc_g"


def test_alt_and_ggt_share_enzyme_group():
    assert unit_group_for_marker("alt") == unit_group_for_marker("ggt") == "enzyme_kat"
    opts = unit_options_for_marker("alt", default_unit="U/l")
    assert "U/l" in opts or "u/l" in [o.lower() for o in opts]
    assert "ukat/l" in opts


def test_custom_gets_full_list():
    opts = unit_options_for_marker(None)
    assert "ukat/l" in opts
    assert "g/l" in opts


def test_detected_outside_group_prepended():
    opts = unit_options_for_marker("cholesterol", default_unit="mmol/l", detected="ukat/l")
    assert opts[0] == "ukat/l"
    assert "mmol/l" in opts
