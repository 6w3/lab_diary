from app.services.trend_points import collapse_points_per_draw, day_average_points


def test_collapse_one_point_per_draw():
    points = [
        {"draw_id": 1, "date": "2026-04-22", "value": 0.75, "unit": "mmol/l"},
        {"draw_id": 1, "date": "2026-04-22", "value": 38.7, "unit": "mmol/l"},
        {"draw_id": 1, "date": "2026-04-22", "value": 5.1, "unit": "ng/l"},
        {"draw_id": 2, "date": "2026-01-15", "value": 1.1, "unit": "mmol/l"},
    ]
    out = collapse_points_per_draw(points, tip_low=0.75, tip_high=1.65)
    assert len(out) == 2
    by_draw = {p["draw_id"]: p["value"] for p in out}
    assert by_draw[1] == 0.75  # only value in tip range
    assert by_draw[2] == 1.1


def test_day_average_keeps_dual_points_mean():
    points = [
        {"draw_id": 1, "date": "2010-09-14", "value": 4.8, "unit": "mmol/l"},
        {"draw_id": 2, "date": "2010-09-14", "value": 5.8, "unit": "mmol/l"},
        {"draw_id": 3, "date": "2016-05-18", "value": 5.0, "unit": "mmol/l"},
    ]
    avg = day_average_points(points)
    assert len(avg) == 2
    by_day = {p["date"]: p["value"] for p in avg}
    assert by_day["2010-09-14"] == 5.3
    assert by_day["2016-05-18"] == 5.0
    assert avg[0]["source_count"] == 2
