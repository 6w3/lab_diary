"""Format open-ended lab / tip reference ranges for display."""

from __future__ import annotations


def _fmt_num(value: float | int) -> str:
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    text = f"{value:g}" if isinstance(value, float) else str(value)
    return text


def format_ref_range(low, high, *, locale: str = "cs") -> str:
    """Render tip/lab bounds. Missing low → 'do X'; missing high → 'od X'."""
    if low is None and high is None:
        return ""
    if low is None:
        high_s = _fmt_num(high)
        return f"up to {high_s}" if locale == "en" else f"do {high_s}"
    if high is None:
        low_s = _fmt_num(low)
        return f"from {low_s}" if locale == "en" else f"od {low_s}"
    return f"{_fmt_num(low)}–{_fmt_num(high)}"
