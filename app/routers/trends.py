from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.deps import DbDep, LocaleDep, UserDep, template_context
from app.i18n import t
from app.models import BloodDraw, CustomMarker, Marker, ResultValue, User
from app.services.markers import MARKER_CATEGORY_LABELS, marker_category, marker_sort_key
from app.services.smart_extract import smart_enabled
from app.services.trend_analysis import (
    analyze_trends,
    charts_to_analysis_payload,
    load_user_analysis,
    save_user_analysis,
)
from app.services.trend_points import collapse_points_per_draw, day_average_points
from app.services.units import format_unit, to_canonical

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
    conditions: dict = {}
    c = draw.conditions
    if c:
        if c.fasting is not None:
            conditions["fasting"] = c.fasting
        if c.weight_kg is not None:
            conditions["weight_kg"] = c.weight_kg
        if c.sleep_score is not None:
            conditions["sleep_score"] = c.sleep_score
        if c.last_hard_training:
            conditions["last_hard_training"] = c.last_hard_training
        if c.illness_14d is not None:
            conditions["illness_14d"] = c.illness_14d
        if c.supplements:
            conditions["supplements"] = c.supplements
        if c.notes:
            conditions["notes"] = c.notes
        if c.cycle_day:
            conditions["cycle_day"] = c.cycle_day
        if c.contraception is not None:
            conditions["contraception"] = c.contraception
    return {
        "date": draw.drawn_at.strftime("%Y-%m-%d"),
        "value": value,
        "unit": unit,
        "lab_low": lab_low,
        "lab_high": lab_high,
        "tip_low": tip_low,
        "tip_high": tip_high,
        "lab_name": draw.lab_name,
        "draw_id": draw.id,
        "conditions": conditions,
    }


def build_trend_charts(db, user: User, locale: str) -> tuple[list[dict], list[dict]]:
    """Build chart series + category groups for trends UI / analysis."""
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
        tip_low = meta.get("tip_low")
        tip_high = meta.get("tip_high")
        points = collapse_points_per_draw(points, tip_low, tip_high)
        avg_points = day_average_points(points)
        labels = [p["date"] for p in points]
        values = [p["value"] for p in points]
        avg_labels = [p["date"] for p in avg_points]
        avg_values = [p["value"] for p in avg_points]
        lab_lows = [p.get("lab_low") for p in points]
        lab_highs = [p.get("lab_high") for p in points]
        unit = points[-1]["unit"] or meta.get("unit") or ""
        charts.append(
            {
                "key": key,
                "name": meta["name"],
                "unit": unit,
                "unit_axis": format_unit(unit, marker_name=meta["name"], with_substance=True),
                "category": meta["category"],
                "category_label": meta["category_label"],
                "labels": labels,
                "values": values,
                "avg_labels": avg_labels,
                "avg_values": avg_values,
                "points": points,
                "lab_lows": lab_lows,
                "lab_highs": lab_highs,
                "tip_low": tip_low,
                "tip_high": tip_high,
            }
        )

    grouped: list[dict] = []
    current_cat = None
    for c in charts:
        if c["category"] != current_cat:
            current_cat = c["category"]
            grouped.append({"category_label": c["category_label"], "charts": []})
        grouped[-1]["charts"].append(c)
    return charts, grouped


@router.get("/trends", response_class=HTMLResponse)
def trends(
    request: Request,
    db: DbDep,
    locale: LocaleDep,
    user: UserDep,
    view: str = Query("charts"),
):
    view_norm = (view or "charts").strip().lower()
    if view_norm not in ("charts", "table", "analysis"):
        view_norm = "charts"

    charts, grouped = build_trend_charts(db, user, locale)
    analysis = load_user_analysis(user.id) if view_norm == "analysis" else None

    return templates.TemplateResponse(
        request,
        "trends.html",
        template_context(
            request,
            locale,
            chart_groups=grouped,
            charts_json=json.dumps(charts, ensure_ascii=False),
            has_charts=bool(charts),
            view=view_norm,
            smart_available=smart_enabled(),
            analysis=analysis,
        ),
    )


@router.post("/trends/analysis")
async def trends_analysis_generate(
    request: Request,
    db: DbDep,
    locale: LocaleDep,
    user: UserDep,
    analysis_consent: str | None = Form(None),
):
    redirect = RedirectResponse("/trends?view=analysis", status_code=303)
    if not smart_enabled():
        request.session["flash"] = t(locale, "trends_analysis_unavailable")
        return redirect
    if (analysis_consent or "").strip() != "1":
        request.session["flash"] = t(locale, "trends_analysis_consent_required")
        return redirect

    charts, _grouped = build_trend_charts(db, user, locale)
    if not charts:
        request.session["flash"] = t(locale, "trends_analysis_empty")
        return redirect

    payload = charts_to_analysis_payload(charts)
    try:
        text = analyze_trends(payload, locale=locale)
        save_user_analysis(user.id, text)
    except Exception as exc:  # noqa: BLE001 — surface to user, keep job usable
        request.session["flash"] = t(locale, "trends_analysis_error", detail=str(exc)[:240])
        return redirect

    return redirect
