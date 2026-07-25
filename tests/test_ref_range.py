from app.services.ref_range import format_ref_range


def test_both_bounds():
    assert format_ref_range(1.0, 12.0) == "1–12"
    assert format_ref_range(0.75, 1.65) == "0.75–1.65"


def test_missing_low_cs():
    assert format_ref_range(None, 12.0) == "do 12"
    assert format_ref_range(None, 12.0, locale="en") == "up to 12"


def test_missing_high_cs():
    assert format_ref_range(90, None) == "od 90"
    assert format_ref_range(90, None, locale="en") == "from 90"


def test_both_missing():
    assert format_ref_range(None, None) == ""
