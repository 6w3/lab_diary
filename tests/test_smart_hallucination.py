from datetime import date, timedelta

from app.services.multi_date import unique_drawn_dates
from app.services.smart_extract import (
    _extract_json,
    _is_consecutive_day_run,
    _looks_like_collapsed_multi_dates,
    _looks_like_history_columns,
    _message_text,
    _sanitize_discovered_dates,
    _scrape_iso_dates,
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


def test_history_columns_promoted_from_mislabeled_single():
    dates = ["2020-10-14", "2016-05-18", "2010-09-14"]
    assert _looks_like_history_columns(dates)
    # Keep all three even when VLM said layout=single
    assert _sanitize_discovered_dates(dates, layout="single") == dates


def test_two_close_dates_still_single():
    # Same-week revisit is not a history table
    dates = ["2024-06-07", "2024-06-14"]
    assert not _looks_like_history_columns(dates)
    assert _looks_like_collapsed_multi_dates(dates)
    assert _sanitize_discovered_dates(dates, layout="single") == ["2024-06-07"]
    # Must NOT accept as multi_column (day/month-swap hallucination pattern)
    assert _sanitize_discovered_dates(dates, layout="multi_column") == []
    assert _sanitize_discovered_dates(["2020-10-14", "2020-10-18"], layout="multi_column") == []
    assert _sanitize_discovered_dates(["2020-10-14", "2020-10-18"], layout="unknown") == [
        "2020-10-14"
    ]


def test_pribram_three_columns_kept():
    dates = ["2020-10-14", "2016-05-18", "2010-09-14"]
    assert _looks_like_history_columns(dates)
    assert not _looks_like_collapsed_multi_dates(dates)
    assert _sanitize_discovered_dates(dates, layout="multi_column") == dates


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


def test_order_form_payload_cleared():
    from app.services.smart_extract import _validate_smart_payload

    out = _validate_smart_payload(
        {
            "doc_kind": "order_form",
            "draws": [
                {
                    "drawn_on": "2020-02-01",
                    "results": [
                        {"label": "Hemoglobin", "marker_code": "hgb", "value": 8.0, "unit": "g/dl"},
                    ],
                }
            ],
        }
    )
    assert out["draws"] == []
    assert "order_form_no_results" in out["warnings"]


def test_order_form_hallucination_cbc_without_refs():
    from app.services.smart_extract import looks_like_order_form_hallucination

    props = [
        {"marker_code": "wbc", "label": "Leukocyty", "value": 11.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "rbc", "label": "Erytrocyty", "value": 3.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "hgb", "label": "Hemoglobin", "value": 8.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "hct", "label": "Hematokrit", "value": 26.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "plt", "label": "Trombocyty", "value": 200.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "mcv", "label": "MCV", "value": 88.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "mch", "label": "MCH", "value": 28.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "mchc", "label": "MCHC", "value": 32.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "neutrophils", "label": "Neutrofily", "value": 7.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "lymphocytes", "label": "Lymfocyty", "value": 2.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "monocytes", "label": "Monocyty", "value": 0.5, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "eosinophils", "label": "Eozinofily", "value": 0.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "basophils", "label": "Bazofily", "value": 0.0, "proposed_drawn_on": "2020-02-01"},
        {"marker_code": "rdw", "label": "RDW", "value": 13.0, "proposed_drawn_on": "2020-02-01"},
    ]
    assert looks_like_order_form_hallucination(props)

    # Real KO with refs must pass
    with_refs = [{**p, "lab_ref_low": 1.0, "lab_ref_high": 2.0} for p in props]
    assert not looks_like_order_form_hallucination(with_refs)


def test_normalize_doc_kind():
    from app.services.smart_extract import _normalize_doc_kind

    assert _normalize_doc_kind("order_form") == "order_form"
    assert _normalize_doc_kind("žádanka") == "order_form"
    assert _normalize_doc_kind("lab_results") == "lab_results"
    assert _normalize_doc_kind("nope") == "unknown"


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


def test_extract_json_balanced_from_noise():
    blob = 'noise {"layout":"multi_column","dates":["2020-10-14","2016-05-18"]} trailing'
    assert _extract_json(blob)["layout"] == "multi_column"
    assert len(_extract_json(blob)["dates"]) == 2


def test_extract_json_skips_huge_unbalanced():
    # Greedy old regex would choke; balanced scanner should still find the small object.
    huge = '{"layout":"single","dates":["2020-10-14"],"notes":"' + ("x" * 100)
    wrapped = 'prefix {"layout":"multi_column","dates":["2020-10-14","2016-05-18","2010-09-14"]} ' + huge
    data = _extract_json(wrapped)
    assert data["layout"] == "multi_column"
    assert len(data["dates"]) == 3


def test_scrape_iso_dates_czech_and_iso():
    text = "headers 14. 10. 2020 10:30 and 18. 5. 2016 plus 2010-09-14"
    dates = _scrape_iso_dates(text)
    assert "2020-10-14" in dates
    assert "2016-05-18" in dates
    assert "2010-09-14" in dates


def test_multi_column_clone_detect_and_drop():
    from app.services.smart_extract import (
        drop_cloned_multi_column_draws,
        multi_column_draws_are_cloned,
    )

    same_results = [
        {"marker_code": "glucose", "label": "S_GLU", "value": 5.4, "unit": "mmol/l"},
        {"marker_code": "urea", "label": "S_UREA", "value": 4.3, "unit": "mmol/l"},
        {"marker_code": "creatinine", "label": "S_KREA", "value": 89.0, "unit": "umol/l"},
        {"marker_code": "alt", "label": "S_ALT", "value": 0.41, "unit": "ukat/l"},
    ]
    different = [
        {"marker_code": "glucose", "label": "S_GLU", "value": 4.8, "unit": "mmol/l"},
        {"marker_code": "urea", "label": "S_UREA", "value": 4.9, "unit": "mmol/l"},
        {"marker_code": "creatinine", "label": "S_KREA", "value": 86.0, "unit": "umol/l"},
        {"marker_code": "alt", "label": "S_ALT", "value": 0.48, "unit": "ukat/l"},
    ]
    cloned = {
        "draws": [
            {"drawn_on": "2008-12-30", "results": same_results},
            {"drawn_on": "2010-09-14", "results": same_results},
        ],
        "warnings": [],
    }
    assert multi_column_draws_are_cloned(cloned["draws"])
    cleaned = drop_cloned_multi_column_draws(cloned)
    assert len(cleaned["draws"]) == 1
    assert cleaned["draws"][0]["drawn_on"] == "2010-09-14"

    ok = {
        "draws": [
            {"drawn_on": "2008-12-30", "results": same_results},
            {"drawn_on": "2010-09-14", "results": different},
        ],
        "warnings": [],
    }
    assert not multi_column_draws_are_cloned(ok["draws"])
    assert len(drop_cloned_multi_column_draws(ok)["draws"]) == 2
