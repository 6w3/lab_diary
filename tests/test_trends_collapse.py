from app.services.trend_points import collapse_points_per_draw


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
