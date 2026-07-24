"""Tests for multi-date table parsing and word-box grouping."""

from app.services.ocr_parse import group_words_to_lines, parse_ocr_lines
from app.services.ocr_tables import flatten_multi_date, parse_multi_date_table


def test_group_words_to_lines():
    words = [
        {"text": "AST", "x": 10, "y": 100, "h": 12},
        {"text": "0.42", "x": 80, "y": 102, "h": 12},
        {"text": "ukat/l", "x": 140, "y": 101, "h": 12},
        {"text": "ALT", "x": 10, "y": 130, "h": 12},
        {"text": "0.55", "x": 80, "y": 131, "h": 12},
    ]
    lines = group_words_to_lines(words)
    assert len(lines) == 2
    assert "AST" in lines[0] and "0.42" in lines[0]
    assert "ALT" in lines[1]


def test_multi_date_flatten():
    text = """
Marker          12.01.2025   03.06.2025   Ref
AST             0.48         0.42         0.10-0.70
ALT             0.61         0.55         0.10-0.80
"""
    parsed = parse_multi_date_table(text)
    assert parsed is not None
    flat = flatten_multi_date(parsed)
    assert len(flat) == 4
    dates = {r["proposed_drawn_on"] for r in flat}
    assert "2025-01-12" in dates
    assert "2025-06-03" in dates


def test_pribram_spaced_dates():
    from app.services.ocr_tables import _parse_date_token, find_dates_in_text

    assert _parse_date_token("14. 10. 2020") == "2020-10-14"
    assert _parse_date_token("14. 10. 2020 10:30") == "2020-10-14"
    assert _parse_date_token("18. 5. 2016 12:15") == "2016-05-18"
    assert find_dates_in_text("14. 10. 2020 10:30  18. 5. 2016 12:15  14. 9. 2010 7:30") == [
        "2020-10-14",
        "2016-05-18",
        "2010-09-14",
    ]

    text = """
Výkon Název metody   14. 10. 2020 10:30   18. 5. 2016 12:15   14. 9. 2010 7:30   Ref. meze   Rozměr
Glukoza   5.8   5.0   4.8   4.2 - 6.1   mmol/l
Urea   5.6   5.5   4.8   2.5 - 8.3   mmol/l
Kreatinin   78   70   86   64 - 104   umol/l
AST   0.35   0.32   0.28   0.1 - 0.85   ukat/l
"""
    parsed = parse_multi_date_table(text)
    assert parsed is not None
    assert parsed["dates"] == ["2020-10-14", "2016-05-18", "2010-09-14"]
    flat = flatten_multi_date(parsed)
    assert len(flat) == 12
    glucose = [r for r in flat if r["label"].startswith("Glukoza")]
    assert {r["proposed_drawn_on"]: r["value"] for r in glucose} == {
        "2020-10-14": 5.8,
        "2016-05-18": 5.0,
        "2010-09-14": 4.8,
    }


def test_parse_still_works_on_single_lines():
    rows = parse_ocr_lines("TSH 2.1 mIU/l 0.4-4.0")
    assert rows[0]["label"].upper().startswith("TSH")
