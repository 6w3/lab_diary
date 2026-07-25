from datetime import date, timedelta

from app.services.multi_date import unique_drawn_dates
from app.services.smart_extract import (
    _extract_json,
    _is_consecutive_day_run,
    _message_text,
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


def test_message_text_prefers_content():
    assert _message_text({"content": '{"a":1}', "reasoning_content": "noise {\"a\":2}"}) == '{"a":1}'


def test_message_text_falls_back_to_reasoning_json():
    msg = {
        "content": "",
        "reasoning_content": "thinking...\nfinal answer:\n{\"layout\":\"multi_column\",\"dates\":[\"2020-10-14\"]}\n",
    }
    text = _message_text(msg)
    assert _extract_json(text)["layout"] == "multi_column"


def test_extract_json_rejects_empty():
    import json

    try:
        _extract_json("")
        assert False, "expected JSONDecodeError"
    except json.JSONDecodeError:
        pass
