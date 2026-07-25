"""Tests for import queue helpers (no live DB)."""

from types import SimpleNamespace
from unittest.mock import patch

from app.services.import_process import (
    attachment_display_name,
    finish_job_if_idle,
    job_payload,
    record_file_failure,
    recover_stuck_attachments,
    retry_failed_attachments,
)


def _clause_values(arg) -> set:
    out: set = set()
    right = getattr(arg, "right", None)
    val = getattr(right, "value", None) if right is not None else None
    if isinstance(val, (list, tuple, set)):
        out.update(val)
    elif val is not None:
        out.add(val)
    return out


class _AttachmentQuery:
    def __init__(self, rows):
        self._all = list(rows)
        self._mode = "all"

    def filter(self, *args, **kwargs):
        modes = set()
        for arg in args:
            vals = _clause_values(arg)
            if vals == {"done"} or vals == {"failed"}:
                modes.add(next(iter(vals)))
            elif vals >= {"pending", "processing"} or vals == {"pending", "processing"}:
                modes.add("active")
            elif vals == {"processing"}:
                modes.add("processing")
        if "active" in modes:
            self._mode = "active"
        elif "done" in modes:
            self._mode = "done"
        elif "failed" in modes:
            self._mode = "failed"
        elif "processing" in modes:
            self._mode = "processing"
        return self

    def order_by(self, *args, **kwargs):
        return self

    def _filtered(self):
        if self._mode == "processing":
            return [r for r in self._all if r.ocr_status == "processing"]
        if self._mode == "done":
            return [r for r in self._all if r.ocr_status == "done"]
        if self._mode == "failed":
            return [r for r in self._all if r.ocr_status == "failed"]
        if self._mode == "active":
            return [r for r in self._all if r.ocr_status in ("pending", "processing")]
        return list(self._all)

    def all(self):
        return self._filtered()

    def count(self):
        return len(self._filtered())


class _FakeDB:
    def __init__(self, *, attachments=None, jobs=None):
        self.attachments = list(attachments or [])
        self.jobs = {j.id: j for j in (jobs or [])}
        self.committed = False

    def query(self, model):
        from app.models import Attachment

        if model is Attachment:
            return _AttachmentQuery(self.attachments)
        return _AttachmentQuery([])

    def get(self, model, pk):
        from app.models import Attachment, ImportJob

        if model is ImportJob:
            return self.jobs.get(pk)
        if model is Attachment:
            for a in self.attachments:
                if a.id == pk:
                    return a
        return None

    def commit(self):
        self.committed = True


@patch("app.services.import_process.finalize_job")
def test_recover_stuck_with_partial_done_soft_fails(mock_finalize):
    job = SimpleNamespace(
        id=1,
        status="processing",
        proposals_json="{}",
        user_id=1,
        extract_mode="smart",
        ocr_raw_text=None,
    )
    done = SimpleNamespace(
        id=10, import_job_id=1, ocr_status="done", filename="a.jpg", ocr_raw_text="ok"
    )
    hung = SimpleNamespace(
        id=11, import_job_id=1, ocr_status="processing", filename="b.jpg", ocr_raw_text=None
    )
    db = _FakeDB(attachments=[done, hung], jobs=[job])
    n = recover_stuck_attachments(db)
    assert n == 1
    assert hung.ocr_status == "failed"
    mock_finalize.assert_called_once()
    assert job_payload(job)["file_errors"]
    assert db.committed is True


def test_recover_stuck_without_done_resets_pending():
    job = SimpleNamespace(
        id=1, status="processing", proposals_json="{}", user_id=1, extract_mode="smart", ocr_raw_text=None
    )
    hung = SimpleNamespace(
        id=11, import_job_id=1, ocr_status="processing", filename="b.jpg", ocr_raw_text=None
    )
    db = _FakeDB(attachments=[hung], jobs=[job])
    n = recover_stuck_attachments(db)
    assert n == 1
    assert hung.ocr_status == "pending"
    assert job.status == "processing"


def test_record_file_failure_keeps_job_processing():
    job = SimpleNamespace(id=1, status="processing", proposals_json="{}", user_id=1)
    att = SimpleNamespace(
        id=5,
        import_job_id=1,
        ocr_status="processing",
        filename="aabbcc.jpg",
        original_filename="pribram_2024.jpg",
        ocr_raw_text=None,
    )
    db = _FakeDB(attachments=[att], jobs=[job])
    record_file_failure(db, att=att, job=job, error="boom")
    assert att.ocr_status == "failed"
    assert job.status == "processing"
    err = job_payload(job)["file_errors"][0]
    assert "boom" in err["error"]
    assert "pribram_2024.jpg" in err["filename"]
    assert err["filename"].startswith("1/1")


def test_ensure_proposal_uids_and_prepare():
    from app.services.import_process import ensure_proposal_uids

    payload = {"proposals": [{"label": "HGB", "value": 1}, {"label": "RBC", "value": 2, "uid": "keep"}]}
    assert ensure_proposal_uids(payload) is True
    assert payload["proposals"][0]["uid"]
    assert payload["proposals"][1]["uid"] == "keep"
    assert ensure_proposal_uids(payload) is False


def test_attachment_display_name_prefers_original():
    att = SimpleNamespace(filename="deadbeef.jpg", original_filename="moje_foto.HEIC")
    assert attachment_display_name(att) == "moje_foto.HEIC"
    assert attachment_display_name(att, index=2, total=7) == "2/7 — moje_foto.HEIC"


def test_finish_all_failed_marks_job_failed():
    job = SimpleNamespace(
        id=1,
        status="processing",
        proposals_json='{"file_errors":[{"filename":"a","error":"x"}]}',
        user_id=1,
        ocr_raw_text=None,
    )
    att = SimpleNamespace(
        id=5, import_job_id=1, ocr_status="failed", filename="a.jpg", ocr_raw_text="x"
    )
    db = _FakeDB(attachments=[att], jobs=[job])
    assert finish_job_if_idle(db, job) is True
    assert job.status == "failed"


def test_retry_failed_attachments_requeues():
    job = SimpleNamespace(
        id=1,
        status="review",
        proposals_json='{"proposals":[{"label":"HGB"}],"file_errors":[{"attachment_id":11,"filename":"b.jpg","error":"interrupted_by_restart"}]}',
        user_id=1,
        ocr_raw_text=None,
    )
    done = SimpleNamespace(
        id=10, import_job_id=1, ocr_status="done", filename="a.jpg", ocr_raw_text="ok"
    )
    failed = SimpleNamespace(
        id=11, import_job_id=1, ocr_status="failed", filename="b.jpg", ocr_raw_text="interrupted_by_restart"
    )
    db = _FakeDB(attachments=[done, failed], jobs=[job])
    n = retry_failed_attachments(db, job, attachment_ids=[11])
    assert n == 1
    assert failed.ocr_status == "pending"
    assert job.status == "processing"
    payload = job_payload(job)
    assert payload["proposals"]
    assert payload.get("file_errors") == []


def test_retry_failed_attachments_while_processing():
    """User can queue another failed file without waiting for the first retry."""
    job = SimpleNamespace(
        id=1,
        status="processing",
        proposals_json='{"proposals":[{"label":"HGB"}],"file_errors":[{"attachment_id":12,"filename":"c.jpg","error":"timeout"}]}',
        user_id=1,
        ocr_raw_text=None,
    )
    done = SimpleNamespace(
        id=10, import_job_id=1, ocr_status="done", filename="a.jpg", ocr_raw_text="ok"
    )
    running = SimpleNamespace(
        id=11, import_job_id=1, ocr_status="processing", filename="b.jpg", ocr_raw_text=None
    )
    failed = SimpleNamespace(
        id=12, import_job_id=1, ocr_status="failed", filename="c.jpg", ocr_raw_text="timeout"
    )
    db = _FakeDB(attachments=[done, running, failed], jobs=[job])
    n = retry_failed_attachments(db, job, attachment_ids=[12])
    assert n == 1
    assert failed.ocr_status == "pending"
    assert running.ocr_status == "processing"
    assert job.status == "processing"
    assert job_payload(job).get("file_errors") == []


def test_queue_attachment_reextract_drops_proposals_and_stores_hint():
    from app.services.import_process import queue_attachment_reextract

    job = SimpleNamespace(
        id=1,
        status="review",
        proposals_json=(
            '{"proposals":['
            '{"label":"HGB","attachment_id":10,"uid":"a"},'
            '{"label":"RBC","attachment_id":11,"uid":"b"}'
            '],"file_errors":[]}'
        ),
        user_id=1,
        ocr_raw_text=None,
    )
    done = SimpleNamespace(
        id=10, import_job_id=1, ocr_status="done", filename="a.jpg", ocr_raw_text="{}"
    )
    other = SimpleNamespace(
        id=11, import_job_id=1, ocr_status="done", filename="b.jpg", ocr_raw_text="{}"
    )
    db = _FakeDB(attachments=[done, other], jobs=[job])
    ok = queue_attachment_reextract(
        db, job, attachment_id=10, user_hint="sloupce jsou data"
    )
    assert ok is True
    assert done.ocr_status == "pending"
    assert done.ocr_raw_text is None
    assert job.status == "processing"
    payload = job_payload(job)
    assert [p["label"] for p in payload["proposals"]] == ["RBC"]
    assert payload["extract_hints"]["10"] == "sloupce jsou data"
