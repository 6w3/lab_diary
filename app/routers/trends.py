from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.deps import DbDep, LocaleDep, UserDep, template_context
from app.models import BloodDraw, CustomMarker, Marker, ResultValue

router = APIRouter(tags=["trends"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/trends", response_class=HTMLResponse)
def trends(request: Request, db: DbDep, locale: LocaleDep, user: UserDep, marker: str | None = None):
    markers = db.query(Marker).order_by(Marker.code).all()
    custom_markers = db.query(CustomMarker).filter(CustomMarker.user_id == user.id).all()
    chart_labels: list[str] = []
    chart_values: list[float] = []
    chart_label = ""

    if marker:
        q = (
            db.query(ResultValue, BloodDraw)
            .join(BloodDraw, ResultValue.blood_draw_id == BloodDraw.id)
            .filter(BloodDraw.user_id == user.id, ResultValue.confirmed.is_(True))
            .order_by(BloodDraw.drawn_at.asc())
        )
        if marker.startswith("custom:"):
            cm_id = int(marker.split(":", 1)[1])
            q = q.filter(ResultValue.custom_marker_id == cm_id)
            cm = db.get(CustomMarker, cm_id)
            chart_label = cm.name if cm else marker
        else:
            q = q.filter(ResultValue.marker_code == marker)
            m = db.get(Marker, marker)
            if m:
                chart_label = m.name_cs if locale == "cs" else m.name_en
            else:
                chart_label = marker

        for result, draw in q.all():
            chart_labels.append(draw.drawn_at.strftime("%Y-%m-%d"))
            chart_values.append(result.value)

    return templates.TemplateResponse(
        "trends.html",
        template_context(
            request,
            locale,
            markers=markers,
            custom_markers=custom_markers,
            selected=marker or "",
            chart_labels_json=json.dumps(chart_labels),
            chart_values_json=json.dumps(chart_values),
            chart_label_json=json.dumps(chart_label),
            has_chart=bool(chart_labels),
        ),
    )
