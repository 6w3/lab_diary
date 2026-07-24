"""Collapse duplicate result rows into one chart point per blood draw."""

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
