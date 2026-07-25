"""Unit tests for draw_match helpers."""

from datetime import datetime, timedelta

from app.services.draw_match import (
    DRAW_TIME_WINDOW,
    drawn_at_close,
    looks_like_same_report,
    panel_family,
    panels_compatible,
    value_fingerprint,
)


def test_panel_family_hema_vs_biochem():
    hema = [
        {"marker_code": "wbc", "value": 7.0},
        {"marker_code": "rbc", "value": 5.0},
        {"marker_code": "hgb", "value": 150.0},
    ]
    bio = [
        {"marker_code": "glucose", "value": 5.0},
        {"marker_code": "urea", "value": 4.0},
        {"marker_code": "creatinine", "value": 80.0},
    ]
    assert panel_family(hema) == "hema"
    assert panel_family(bio) == "biochem"
    assert not panels_compatible("hema", "biochem")
    assert not looks_like_same_report(hema, bio)


def test_same_report_fingerprint():
    a = [
        {"marker_code": "glucose", "value": 4.8},
        {"marker_code": "urea", "value": 4.9},
        {"marker_code": "creatinine", "value": 86.0},
        {"marker_code": "alt", "value": 0.48},
    ]
    b = [
        {"marker_code": "glucose", "value": 4.8},
        {"marker_code": "urea", "value": 4.9},
        {"marker_code": "creatinine", "value": 86.0},
        {"marker_code": "alt", "value": 0.48},
    ]
    assert looks_like_same_report(a, b)
    assert value_fingerprint(a) == value_fingerprint(b)


def test_drawn_at_close_two_hours():
    a = datetime(2010, 9, 14, 7, 30)
    assert drawn_at_close(a, a + timedelta(hours=2))
    assert drawn_at_close(a, a - timedelta(hours=2))
    assert not drawn_at_close(a, a + timedelta(hours=2, minutes=1))
    assert DRAW_TIME_WINDOW == timedelta(hours=2)


def test_split_day_keeps_many_markers_one_group():
    from app.services.draw_match import split_day_proposals

    rows = [
        {"marker_code": "glucose", "value": 5.0, "proposed_drawn_on": "2024-01-01"},
        {"marker_code": "urea", "value": 4.0, "proposed_drawn_on": "2024-01-01"},
        {"marker_code": "alt", "value": 0.4, "proposed_drawn_on": "2024-01-01"},
        {"marker_code": "tsh", "value": 2.0, "proposed_drawn_on": "2024-01-01"},
    ]
    groups = split_day_proposals(rows)
    assert len(groups) == 1
    assert len(groups[0]) == 4


def test_split_day_separates_hema_and_biochem():
    from app.services.draw_match import split_day_proposals

    rows = [
        {"marker_code": "wbc", "value": 7.0},
        {"marker_code": "rbc", "value": 5.0},
        {"marker_code": "hgb", "value": 150.0},
        {"marker_code": "glucose", "value": 5.0},
        {"marker_code": "urea", "value": 4.0},
        {"marker_code": "creatinine", "value": 80.0},
        {"label": "Poznámka", "value": None},
    ]
    groups = split_day_proposals(rows)
    assert len(groups) == 2
    codes = [{r.get("marker_code") for r in g if r.get("marker_code")} for g in groups]
    assert {"wbc", "rbc", "hgb"} in codes
    assert {"glucose", "urea", "creatinine"} in codes
