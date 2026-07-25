"""Tests for trend AI analysis helpers (mocked NVIDIA)."""

from unittest.mock import patch

import pytest

from app.services.trend_analysis import (
    ANALYSIS_SYSTEM,
    analyze_trends,
    charts_to_analysis_payload,
)


def test_charts_to_analysis_payload_compacts_fields():
    charts = [
        {
            "key": "glucose",
            "name": "Glukóza",
            "unit": "mmol/l",
            "category": "biochem",
            "category_label": "Biochemie",
            "labels": ["2020-01-01"],
            "values": [5.4],
            "avg_labels": ["2020-01-01"],
            "avg_values": [5.4],
            "lab_lows": [3.5],
            "lab_highs": [5.5],
            "tip_low": 4.0,
            "tip_high": 5.5,
            "points": [
                {
                    "date": "2020-01-01",
                    "value": 5.4,
                    "unit": "mmol/l",
                    "lab_low": 3.5,
                    "lab_high": 5.5,
                    "tip_low": 4.0,
                    "tip_high": 5.5,
                    "lab_name": "Synlab",
                    "draw_id": 1,
                    "conditions": {"fasting": True},
                }
            ],
        }
    ]
    payload = charts_to_analysis_payload(charts)
    assert len(payload) == 1
    row = payload[0]
    assert row["marker"] == "Glukóza"
    assert row["code"] == "glucose"
    assert "labels" not in row
    assert "avg_values" not in row
    assert row["points"][0]["conditions"] == {"fasting": True}
    assert row["points"][0]["lab_ref"] == [3.5, 5.5]


def test_analyze_trends_calls_nvidia_with_analysis_system():
    payload = [
        {
            "marker": "Ferritin",
            "code": "ferritin",
            "unit": "ug/l",
            "category": "Iron",
            "tip_ref": [30, 200],
            "points": [{"date": "2024-06-01", "value": 22, "unit": "ug/l"}],
        }
    ]
    with patch("app.services.trend_analysis.smart_enabled", return_value=True), patch(
        "app.services.trend_analysis._nvidia_chat", return_value="## Summary\nLow ferritin trend."
    ) as chat:
        text = analyze_trends(payload, locale="cs")
    assert "Low ferritin" in text
    assert chat.call_count == 1
    kwargs = chat.call_args.kwargs
    assert kwargs["system"] == ANALYSIS_SYSTEM
    assert kwargs["temperature"] == 0.3
    content = chat.call_args.args[0]
    assert content[0]["type"] == "text"
    assert "Czech" in content[0]["text"]
    assert "ferritin" in content[0]["text"]


def test_analyze_trends_requires_smart():
    with patch("app.services.trend_analysis.smart_enabled", return_value=False):
        with pytest.raises(RuntimeError, match="not available"):
            analyze_trends([{"marker": "x", "points": []}], locale="en")


def test_analyze_trends_requires_payload():
    with patch("app.services.trend_analysis.smart_enabled", return_value=True):
        with pytest.raises(RuntimeError, match="No trend data"):
            analyze_trends([], locale="en")
