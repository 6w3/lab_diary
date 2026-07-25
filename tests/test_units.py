from app.services.ocr_parse import normalize_unit
from app.services.units import (
    convert_value,
    correct_unit_by_magnitude,
    format_unit,
    is_molar_unit,
    same_quantity,
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


def test_correct_hgb_g_dl_mislabeled_as_g_l():
    assert correct_unit_by_magnitude("hgb", 13.5, "g/l", lab_low=12.0, lab_high=16.0) == "g/dl"
    assert correct_unit_by_magnitude("hgb", 161.0, "g/l", lab_low=135.0, lab_high=174.0) == "g/l"
    assert correct_unit_by_magnitude("mchc", 33.5, "g/l", lab_low=32.0, lab_high=36.0) == "g/dl"
    assert correct_unit_by_magnitude("mchc", 335.0, "g/l", lab_low=320.0, lab_high=360.0) == "g/l"
    # albumin-like values must not flip via hgb helper when wrong code absent
    assert correct_unit_by_magnitude("albumin", 40.0, "g/l", lab_low=35.0, lab_high=53.0) == "g/l"


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


def test_mass_molar_without_marker_fails():
    v, ok = convert_value(5.0, "mmol/l", "mg/dl")
    assert not ok
    assert v == 5.0


def test_mass_molar_wrong_marker_fails():
    # sodium is mmol-only (no mass factor / no mg/dl option)
    v, ok = convert_value(140.0, "mmol/l", "mg/dl", marker_code="sodium")
    assert not ok


def test_bilirubin_mg_dl_to_umol():
    v, ok = convert_value(1.0, "mg/dl", "umol/l", marker_code="bilirubin")
    assert ok
    assert abs(v - 17.1) < 1e-6


def test_estradiol_pg_to_pmol():
    v, ok = convert_value(100.0, "pg/ml", "pmol/l", marker_code="estradiol")
    assert ok
    assert abs(v - 367.1) < 0.1


def test_phosphorus_mg_dl_to_mmol():
    v, ok = convert_value(3.1, "mg/dl", "mmol/l", marker_code="phosphorus")
    assert ok
    assert abs(v - 3.1 * 0.323) < 1e-6


def test_ft4_ng_dl_to_pmol():
    v, ok = convert_value(1.0, "ng/dl", "pmol/l", marker_code="ft4")
    assert ok
    assert abs(v - 12.87) < 1e-6


def test_lactate_mg_dl_to_mmol():
    v, ok = convert_value(9.0, "mg/dl", "mmol/l", marker_code="lactate")
    assert ok
    assert abs(v - 0.999) < 1e-9  # 9 × 0.111


def test_glucose_and_cholesterol_different_mass_factors():
    g, gok = convert_value(1.0, "mmol/l", "mg/dl", marker_code="glucose")
    c, cok = convert_value(1.0, "mmol/l", "mg/dl", marker_code="cholesterol")
    assert gok and cok
    assert abs(g - 18.0182) < 1e-3
    assert abs(c - 38.67) < 1e-3
    assert abs(g - c) > 1.0


def test_molar_prefix_scale_without_marker():
    v, ok = convert_value(1.0, "mmol/l", "umol/l")
    assert ok
    assert abs(v - 1000.0) < 1e-6
    v2, ok2 = convert_value(1000.0, "umol/l", "nmol/l")
    assert ok2
    assert abs(v2 - 1_000_000.0) < 1e-3


def test_same_quantity_molar_mass_needs_marker():
    assert not same_quantity("mmol/l", "mg/dl")
    assert same_quantity("mmol/l", "mg/dl", marker_code="glucose")
    assert same_quantity("mmol/l", "umol/l")


def test_format_unit_with_substance():
    assert format_unit("mmol/l") == "mmol/l"
    assert format_unit("mmol/l", marker_name="Glukóza", with_substance=True) == "mmol/l (Glukóza)"
    assert format_unit("g/l", marker_name="Hemoglobin", with_substance=True) == "g/l"
    assert is_molar_unit("umol/l")
    assert not is_molar_unit("g/l")
