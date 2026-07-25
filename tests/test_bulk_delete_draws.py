"""Tests for bulk delete of owned blood draws."""

from types import SimpleNamespace

from app.models import BloodDraw
from app.services.draw_organize import delete_owned_draws


def _clause_parts(arg):
    left = getattr(arg, "left", None)
    right = getattr(arg, "right", None)
    col = getattr(left, "key", None)
    val = getattr(right, "value", None) if right is not None else None
    return col, val


class _DrawQuery:
    def __init__(self, rows):
        self._rows = list(rows)
        self._user_id = None
        self._ids = None

    def filter(self, *args, **kwargs):
        for arg in args:
            col, val = _clause_parts(arg)
            if col == "user_id" and val is not None:
                self._user_id = val
            if col == "id" and isinstance(val, (list, tuple, set)):
                self._ids = set(val)
            elif col == "id" and val is not None:
                self._ids = {val}
        return self

    def all(self):
        out = list(self._rows)
        if self._user_id is not None:
            out = [d for d in out if d.user_id == self._user_id]
        if self._ids is not None:
            out = [d for d in out if d.id in self._ids]
        return out


class _FakeDB:
    def __init__(self, draws):
        self.draws = list(draws)
        self.deleted = []

    def query(self, model):
        assert model is BloodDraw or getattr(model, "__name__", "") == "BloodDraw"
        return _DrawQuery(self.draws)

    def delete(self, obj):
        self.deleted.append(obj.id)
        self.draws = [d for d in self.draws if d.id != obj.id]


def test_delete_owned_draws_only_own():
    db = _FakeDB(
        [
            SimpleNamespace(id=1, user_id=10),
            SimpleNamespace(id=2, user_id=10),
            SimpleNamespace(id=3, user_id=99),
        ]
    )
    n = delete_owned_draws(db, user_id=10, draw_ids=[1, 3, 2])
    assert n == 2
    assert sorted(db.deleted) == [1, 2]
    assert [d.id for d in db.draws] == [3]


def test_delete_owned_draws_empty():
    db = _FakeDB([SimpleNamespace(id=1, user_id=10)])
    assert delete_owned_draws(db, user_id=10, draw_ids=[]) == 0
    assert db.deleted == []
    assert len(db.draws) == 1


def test_delete_owned_draws_ignores_foreign():
    db = _FakeDB([SimpleNamespace(id=5, user_id=99)])
    assert delete_owned_draws(db, user_id=10, draw_ids=[5]) == 0
    assert db.deleted == []
