"""Baseline / regression metrics for OCR line + multi-date parsers."""

from __future__ import annotations

from pathlib import Path

from app.services.ocr_parse import parse_ocr_lines
from app.services.ocr_tables import parse_multi_date_table

FIXTURES = Path(__file__).parent / "fixtures" / "ocr_samples.md"

# Expected marker labels (lowercase substrings) per fixture section
EXPECTED = {
    "digital": {"hemoglobin", "feritin", "tsh", "alt", "ast", "kreatinin", "glukóza", "glukoza", "hematokrit"},
    "scan": {"hemoglobin", "feritin", "tsh", "alt", "ast", "kreatinin"},
    "photo": {"hemoglobin", "feritin", "tsh", "alt", "ast"},
    "multi_date": {"ast", "alt", "kreatinin", "tsh", "feritin"},
}


def _load_sections() -> dict[str, str]:
    text = FIXTURES.read_text(encoding="utf-8")
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current is not None:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None and not line.startswith("#"):
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf).strip()
    return sections


def _hit_rate(labels: list[str], expected: set[str]) -> float:
    joined = " ".join(labels).lower()
    hits = sum(1 for e in expected if e in joined)
    return hits / len(expected) if expected else 0.0


def test_eval_fixtures_line_parse_hit_rates():
    sections = _load_sections()
    rates: dict[str, float] = {}
    for name in ("digital", "scan", "photo"):
        rows = parse_ocr_lines(sections[name])
        rates[name] = _hit_rate([r["label"] for r in rows], EXPECTED[name])
        assert rates[name] >= 0.5, f"{name} hit rate {rates[name]} rows={rows}"
    assert rates["digital"] >= 0.7
    assert rates["scan"] >= 0.7


def test_eval_multi_date_table():
    sections = _load_sections()
    parsed = parse_multi_date_table(sections["multi_date"])
    assert parsed is not None
    assert len(parsed["dates"]) == 2
    assert {d.replace("-", "") for d in parsed["dates"]}  # ISO-ish
    labels = [r["label"].lower() for r in parsed["rows"]]
    assert _hit_rate(labels, EXPECTED["multi_date"]) >= 0.8
    # each row has a value per date
    for row in parsed["rows"]:
        assert len(row["values"]) >= 1
