"""Tests for import queue helpers (no live DB)."""

from types import SimpleNamespace

from app.services.import_process import recover_stuck_attachments


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.committed = False

    def query(self, model):
        return _FakeQuery(self._rows)

    def commit(self):
        self.committed = True


def test_recover_stuck_attachments_resets_processing():
    a1 = SimpleNamespace(ocr_status="processing")
    a2 = SimpleNamespace(ocr_status="processing")
    db = _FakeDB([a1, a2])
    n = recover_stuck_attachments(db)
    assert n == 2
    assert a1.ocr_status == "pending"
    assert a2.ocr_status == "pending"
    assert db.committed is True


def test_recover_stuck_noop_when_empty():
    db = _FakeDB([])
    n = recover_stuck_attachments(db)
    assert n == 0
    assert db.committed is False
