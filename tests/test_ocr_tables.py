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


def test_pribram_noisy_ocr_header_past_line_15():
    """Photo OCR: junk header lines push date columns past the old 15-line scan window."""
    text = """
d
/ o
. e 2
e 1 o
A
0 U e
<
Laboratore HTO ON Pribram
T4 OBLASTNI NEMOCNICE
Transfuzni lab.: 318 641 406
FLIN PRIBRAM, a. s.
prim. MUDr. Magda Nohejlova
strana 1 /1 Tisk: 14. 10. 2020 12:36:42
Rodne cislo: 8606254679 Vek: 34
Jmeno: Vaclavik Jiri
Dg: 110 H169 ZP:111
OpenLIMS STAPRO s. r. o.
- 14. 10. 2020 18. 5. 2016
Nazev metody 1215 e Hodnoceni Ref. meze Rozmer
# Leukocyty WBC 5,5 4,9 j5 el o | 4,0-10,0 10^9/l
# Erytrocyty RBC 5,13 4,80 g A ] 4,00 - 5,80 10^12/l
# Hemoglobin HGB 160 151 b lX 135 - 175 g/l
# Hematokrit HCT 0,450 0,418 o ) 0,400 - 0,500 1
# Stř.obj.eryt. MCV 87,7 87,1 sl 82,0-98,0 fl
# Trombocyty PLT 209 191 L p I 150 - 400 10^9/l
"""
    parsed = parse_multi_date_table(text)
    assert parsed is not None
    assert parsed["dates"] == ["2020-10-14", "2016-05-18"]
    flat = flatten_multi_date(parsed)
    assert len(flat) >= 10
    by_date = {d: [r for r in flat if r["proposed_drawn_on"] == d] for d in parsed["dates"]}
    assert len(by_date["2020-10-14"]) >= 5
    assert len(by_date["2016-05-18"]) >= 5
    wbc = [r for r in flat if "Leukocyty" in r["label"]]
    assert {r["proposed_drawn_on"]: r["value"] for r in wbc} == {
        "2020-10-14": 5.5,
        "2016-05-18": 4.9,
    }


def test_ref_range_not_stolen_as_date_value():
    """Incomplete row (one column missing) must not treat ref bounds as values."""
    text = """
Název metody   14. 10. 2020   18. 5. 2016   Ref. meze
Leukocyty WBC   5,5   4,9   4,0 - 10,0   10^9/l
Hemoglobin HGB   151   135 - 175   g/l
Trombocyty PLT   209   191   150 - 400   10^9/l
"""
    parsed = parse_multi_date_table(text)
    assert parsed is not None
    flat = flatten_multi_date(parsed)
    hgb = [r for r in flat if "Hemoglobin" in r["label"]]
    assert hgb == []  # only one value before ref → skip
    plt = {r["proposed_drawn_on"]: r["value"] for r in flat if "Trombocyty" in r["label"]}
    assert plt == {"2020-10-14": 209.0, "2016-05-18": 191.0}


def test_parse_still_works_on_single_lines():
    rows = parse_ocr_lines("TSH 2.1 mIU/l 0.4-4.0")
    assert rows[0]["label"].upper().startswith("TSH")
