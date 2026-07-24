from app.services.units import convert_value, to_canonical


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
