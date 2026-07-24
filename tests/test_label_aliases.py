from types import SimpleNamespace

from app.services.label_aliases import learn_label_alias, normalize_alias_label
from app.services.markers import MARKER_SEED


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self):
        self.new = set()
        self.added = []

    def query(self, model):
        return _FakeQuery([])

    def add(self, obj):
        self.added.append(obj)
        self.new.add(obj)


def _catalog():
    return [
        SimpleNamespace(
            **{k: v for k, v in item.items() if k in {"code", "name_cs", "name_en", "default_unit"}}
        )
        for item in MARKER_SEED
        if item["code"] in {"nrbc", "nrbc_abs"}
    ]


def test_learn_alias_same_norm_twice_no_duplicate():
    db = _FakeDB()
    catalog = _catalog()
    learn_label_alias(db, 1, "Normoblasty NRBC", "nrbc", catalog)
    learn_label_alias(db, 1, "Normoblasty NRBC", "nrbc_abs", catalog)
    assert len(db.added) == 1
    assert db.added[0].marker_code == "nrbc_abs"
    assert db.added[0].label_norm == normalize_alias_label("Normoblasty NRBC")
