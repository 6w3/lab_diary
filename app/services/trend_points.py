"""Collapse duplicate result rows; build chart series with day averages."""

from __future__ import annotations

from collections import defaultdict


def point_in_tip(point: dict, tip_low, tip_high) -> bool:
    v = point.get("value")
    if v is None:
        return False
    if tip_low is not None and tip_high is not None:
        return tip_low <= v <= tip_high
    if tip_low is not None:
        return v >= tip_low
    if tip_high is not None:
        return v <= tip_high
    return False


_PREFERRED_UNITS = {
    "mmol/l",
    "umol/l",
    "nmol/l",
    "pmol/l",
    "g/l",
    "mg/l",
    "ug/l",
    "u/l",
    "ukat/l",
    "10^9/l",
    "10^12/l",
    "%",
    "fl",
    "pg",
    "miu/l",
    "iu/l",
    "mmol/mol",
}


def collapse_points_per_draw(points: list[dict], tip_low, tip_high) -> list[dict]:
    """One chart point per blood draw (same date must not repeat for duplicate rows)."""
    by_draw: dict[int, list[dict]] = defaultdict(list)
    for p in points:
        did = p.get("draw_id")
        if did is None:
            by_draw[id(p)].append(p)
        else:
            by_draw[int(did)].append(p)
    out: list[dict] = []
    for group in by_draw.values():
        if len(group) == 1:
            out.append(group[0])
            continue
        in_tip = [p for p in group if point_in_tip(p, tip_low, tip_high)]
        if in_tip:
            out.append(in_tip[-1])
            continue
        preferred = [
            p for p in group if (p.get("unit") or "").lower() in _PREFERRED_UNITS
        ]
        out.append((preferred or group)[-1])
    out.sort(key=lambda p: (p.get("date") or "", p.get("draw_id") or 0))
    return out


def day_average_points(points: list[dict]) -> list[dict]:
    """One point per calendar day = mean of values that day (for trend line)."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    for p in points:
        day = (p.get("date") or "")[:10]
        if not day:
            continue
        by_day[day].append(p)
    out: list[dict] = []
    for day in sorted(by_day):
        group = by_day[day]
        vals = [float(p["value"]) for p in group if p.get("value") is not None]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        base = dict(group[-1])
        base["value"] = avg
        base["date"] = day
        base["is_day_average"] = True
        base["source_count"] = len(vals)
        # Prefer lab refs from last point; clear draw_id so it is not a measurement
        base["draw_id"] = None
        out.append(base)
    return out
