from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.deps import DbDep, LocaleDep, UserDep, template_context
from app.models import BloodDraw, CustomMarker, Marker, ResultValue
from app.services.markers import MARKER_CATEGORY_LABELS, marker_category, marker_sort_key
from app.services.units import to_canonical

router = APIRouter(tags=["trends"])
templates = Jinja2Templates(directory="app/templates")


def _series_point(result: ResultValue, draw: BloodDraw, marker: Marker | None) -> dict:
    value = result.value
    unit = result.unit
    tip_low = tip_high = None
    lab_low, lab_high = result.lab_ref_low, result.lab_ref_high
    if marker:
        tip_low, tip_high = marker.tip_ref_low, marker.tip_ref_high
        nv, nu, ok = to_canonical(value, unit, marker.code, marker.default_unit)
        if ok:
            value, unit = nv, nu
            if lab_low is not None:
                lv, _, lok = to_canonical(lab_low, result.unit, marker.code, marker.default_unit)
                if lok:
                    lab_low = lv
            if lab_high is not None:
                hv, _, hok = to_canonical(lab_high, result.unit, marker.code, marker.default_unit)
                if hok:
                    lab_high = hv
    return {
        "date": draw.drawn_at.strftime("%Y-%m-%d"),
        "value": value,
        "unit": unit,
        "lab_low": lab_low,
        "lab_high": lab_high,
        "tip_low": tip_low,
        "tip_high": tip_high,
    }


@router.get("/trends", response_class=HTMLResponse)
def trends(request: Request, db: DbDep, locale: LocaleDep, user: UserDep):
    rows = (
        db.query(ResultValue, BloodDraw)
        .join(BloodDraw, ResultValue.blood_draw_id == BloodDraw.id)
        .filter(BloodDraw.user_id == user.id, ResultValue.confirmed.is_(True))
        .order_by(BloodDraw.drawn_at.asc())
        .all()
    )

    by_marker: dict[str, list] = defaultdict(list)
    marker_meta: dict[str, dict] = {}
    custom_meta: dict[int, CustomMarker] = {}

    for result, draw in rows:
        if result.marker_code:
            key = result.marker_code
            m = result.marker or db.get(Marker, result.marker_code)
            if key not in marker_meta and m:
                name = m.name_cs if locale == "cs" else m.name_en
                cat = marker_category(m.code)
                marker_meta[key] = {
                    "key": key,
                    "name": name,
                    "unit": m.default_unit,
                    "category": cat,
                    "category_label": MARKER_CATEGORY_LABELS.get(cat, {}).get(locale, cat),
                    "sort": marker_sort_key(m.code),
                    "tip_low": m.tip_ref_low,
                    "tip_high": m.tip_ref_high,
                }
            by_marker[key].append(_series_point(result, draw, m if result.marker_code else None))
        elif result.custom_marker_id:
            key = f"custom:{result.custom_marker_id}"
            cm = result.custom_marker or db.get(CustomMarker, result.custom_marker_id)
            if cm and result.custom_marker_id not in custom_meta:
                custom_meta[result.custom_marker_id] = cm
                marker_meta[key] = {
                    "key": key,
                    "name": cm.name,
                    "unit": cm.unit or result.unit,
                    "category": "custom",
                    "category_label": MARKER_CATEGORY_LABELS["custom"].get(locale, "Custom"),
                    "sort": (999, result.custom_marker_id, key),
                    "tip_low": None,
                    "tip_high": None,
                }
            by_marker[key].append(_series_point(result, draw, None))

    charts = []
    for key, meta in sorted(marker_meta.items(), key=lambda kv: kv[1]["sort"]):
        points = by_marker.get(key) or []
        if not points:
            continue
        labels = [p["date"] for p in points]
        values = [p["value"] for p in points]
        # Use latest non-null lab refs; tip from catalog
        lab_low = next((p["lab_low"] for p in reversed(points) if p["lab_low"] is not None), None)
        lab_high = next((p["lab_high"] for p in reversed(points) if p["lab_high"] is not None), None)
        tip_low = meta.get("tip_low")
        tip_high = meta.get("tip_high")
        unit = points[-1]["unit"] or meta.get("unit") or ""
        charts.append(
            {
                "key": key,
                "name": meta["name"],
                "unit": unit,
                "category": meta["category"],
                "category_label": meta["category_label"],
                "labels": labels,
                "values": values,
                "lab_low": lab_low,
                "lab_high": lab_high,
                "tip_low": tip_low,
                "tip_high": tip_high,
            }
        )

    # Group for template headings
    grouped: list[dict] = []
    current_cat = None
    for c in charts:
        if c["category"] != current_cat:
            current_cat = c["category"]
            grouped.append({"category_label": c["category_label"], "charts": []})
        grouped[-1]["charts"].append(c)

    return templates.TemplateResponse(
        request,
        "trends.html",
        template_context(
            request,
            locale,
            chart_groups=grouped,
            charts_json=json.dumps(charts, ensure_ascii=False),
            has_charts=bool(charts),
        ),
    )
