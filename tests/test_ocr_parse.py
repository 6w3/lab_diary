from app.services.storage import parse_ocr_lines


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
