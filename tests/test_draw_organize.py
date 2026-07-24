from datetime import date, datetime
from types import SimpleNamespace

from app.services.draw_organize import (
    find_draw_candidates,
    resolve_draw_cached,
    resolve_draw_for_group,
    result_is_duplicate,
    values_close,
)


def test_values_close():
    assert values_close(1.0, 1.0)
    assert values_close(100.0, 100.0000001)
    assert not values_close(1.0, 1.1)


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, draws=None, results=None, markers=None):
        self.draws = draws or []
        self.results = results or []
        self.markers = markers or {}
        self.added = []

    def query(self, model):
        name = getattr(model, "__name__", str(model))
        if "BloodDraw" in name or model.__name__ == "BloodDraw":
            return _FakeQuery(self.draws)
        if "ResultValue" in name or model.__name__ == "ResultValue":
            return _FakeQuery(self.results)
        return _FakeQuery([])

    def get(self, model, key):
        if getattr(model, "__name__", "") == "Marker":
            return self.markers.get(key)
        return None

    def add(self, obj):
        self.added.append(obj)
        if not getattr(obj, "id", None):
            obj.id = 900 + len(self.added)

    def flush(self):
        for obj in self.added:
            if not getattr(obj, "id", None):
                obj.id = 900 + len(self.added)


def test_find_candidates_same_day_lab():
    draws = [
        SimpleNamespace(
            id=1,
            user_id=1,
            lab_name="ON Příbram",
            drawn_at=datetime(2024, 6, 7),
            results=[],
        ),
        SimpleNamespace(
            id=2,
            user_id=1,
            lab_name="Other Lab",
            drawn_at=datetime(2024, 6, 7),
            results=[],
        ),
        SimpleNamespace(
            id=3,
            user_id=1,
            lab_name="ON Příbram",
            drawn_at=datetime(2024, 6, 8),
            results=[],
        ),
    ]
    db = _FakeDB(draws=draws)
    found = find_draw_candidates(db, 1, date(2024, 6, 7), "on příbram")
    assert [d.id for d in found] == [1]


def test_resolve_creates_new_by_default():
    db = _FakeDB()
    draw, is_new = resolve_draw_for_group(
        db,
        1,
        drawn_at=datetime(2024, 6, 7),
        lab_name="Lab",
        workplace=None,
        choice="new",
    )
    assert is_new
    assert draw.lab_name == "Lab"


def test_resolve_existing_choice():
    existing = SimpleNamespace(
        id=5,
        user_id=1,
        lab_name="Lab",
        workplace=None,
        drawn_at=datetime(2024, 6, 7),
    )
    db = _FakeDB(draws=[existing])
    draw, is_new = resolve_draw_for_group(
        db,
        1,
        drawn_at=datetime(2024, 6, 7),
        lab_name="Lab",
        workplace="A",
        choice="existing:5",
    )
    assert not is_new
    assert draw.id == 5
    assert draw.workplace == "A"


def test_resolve_cached_reuses_new_draw_same_date():
    db = _FakeDB()
    cache: dict = {}
    d1, n1 = resolve_draw_cached(
        cache,
        db,
        1,
        drawn_at=datetime(2024, 6, 7),
        lab_name="Lab",
        workplace=None,
        choice="new",
        group_key="2024-06-07",
    )
    d2, n2 = resolve_draw_cached(
        cache,
        db,
        1,
        drawn_at=datetime(2024, 6, 7),
        lab_name="Lab",
        workplace=None,
        choice="new",
        group_key="2024-06-07",
    )
    assert n1 and n2
    assert d1.id == d2.id
    assert len(db.added) == 1


def test_resolve_cached_separate_dates():
    db = _FakeDB()
    cache: dict = {}
    d1, _ = resolve_draw_cached(
        cache,
        db,
        1,
        drawn_at=datetime(2024, 6, 7),
        lab_name="Lab",
        workplace=None,
        choice="new",
        group_key="2024-06-07",
    )
    d2, _ = resolve_draw_cached(
        cache,
        db,
        1,
        drawn_at=datetime(2024, 6, 8),
        lab_name="Lab",
        workplace=None,
        choice="new",
        group_key="2024-06-08",
    )
    assert d1.id != d2.id
    assert len(db.added) == 2


def test_result_is_duplicate_same_marker_value():
    row = SimpleNamespace(
        blood_draw_id=1,
        confirmed=True,
        marker_code="glucose",
        custom_marker_id=None,
        value=5.5,
        unit="mmol/l",
    )
    marker = SimpleNamespace(code="glucose", default_unit="mmol/l")
    db = _FakeDB(results=[row], markers={"glucose": marker})
    assert result_is_duplicate(
        db,
        draw_id=1,
        marker_code="glucose",
        custom_marker_id=None,
        value=5.5,
        unit="mmol/l",
    )
    assert not result_is_duplicate(
        db,
        draw_id=1,
        marker_code="glucose",
        custom_marker_id=None,
        value=6.0,
        unit="mmol/l",
    )
