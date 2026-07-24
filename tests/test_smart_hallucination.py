from datetime import date, timedelta

from app.services.multi_date import unique_drawn_dates
from app.services.smart_extract import (
    _is_consecutive_day_run,
    _sanitize_discovered_dates,
    looks_like_hallucinated_extract,
)


def test_unique_drawn_dates():
    props = [
        {"proposed_drawn_on": "2020-10-14"},
        {"proposed_drawn_on": "2020-10-14"},
        {"proposed_drawn_on": "2021-06-03"},
        {"proposed_drawn_on": ""},
        {},
    ]
    assert unique_drawn_dates(props) == ["2020-10-14", "2021-06-03"]


def test_consecutive_day_run():
    start = date(2024, 6, 7)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(24)]
    assert _is_consecutive_day_run(dates)
    assert not _is_consecutive_day_run(["2024-06-07", "2025-03-24"])


def test_sanitize_drops_day_spam_for_unknown():
    start = date(2024, 6, 7)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(24)]
    assert _sanitize_discovered_dates(dates, layout="unknown") == []
    assert _sanitize_discovered_dates(dates, layout="single") == ["2024-06-07"]
    assert _sanitize_discovered_dates(dates, layout="multi_column") == []


def test_hallucinated_ferritin_spam():
    start = date(2024, 6, 7)
    props = [
        {
            "label": "Feritin",
            "marker_code": "ferritin",
            "value": 0.0,
            "proposed_drawn_on": (start + timedelta(days=i)).isoformat(),
        }
        for i in range(24)
    ]
    assert looks_like_hallucinated_extract(props)


def test_real_single_draw_not_hallucination():
    props = [
        {"label": "Glukoza", "marker_code": "glucose", "value": 5.5, "proposed_drawn_on": "2024-06-07"},
        {"label": "Urea", "marker_code": "urea", "value": 3.7, "proposed_drawn_on": "2024-06-07"},
        {"label": "Kreatinin", "marker_code": "creatinine", "value": 75.0, "proposed_drawn_on": "2024-06-07"},
        {"label": "ALT", "marker_code": "alt", "value": 0.39, "proposed_drawn_on": "2024-06-07"},
        {"label": "Hemoglobin", "marker_code": "hgb", "value": 162.0, "proposed_drawn_on": "2024-06-07"},
    ]
    assert not looks_like_hallucinated_extract(props)
