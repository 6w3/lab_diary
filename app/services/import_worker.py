"""In-process import queue: server processes pending attachments without browser keep-alive."""

from __future__ import annotations

import logging
import threading
import time

from app.config import get_settings
from app.db import SessionLocal
from app.models import Attachment, ImportJob
from app.services.import_process import (
    claim_next_attachment,
    fail_timed_out_attachment,
    finish_job_if_idle,
    maybe_finalize_idle_jobs,
    process_claimed_attachment,
    record_file_failure,
    recover_stuck_attachments,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_started = False
_stop = threading.Event()
_wake = threading.Event()
_dispatch_thread: threading.Thread | None = None
_inflight = 0
_abandoned = 0  # timed-out threads still running (do not block new claims)
_claim_started: dict[int, float] = {}
_abandoned_ids: set[int] = set()


def kick_import_worker() -> None:
    """Wake the dispatcher (call after upload / on demand)."""
    _wake.set()


def start_import_worker() -> None:
    """Start background dispatcher + recover stuck rows. Idempotent."""
    global _started, _dispatch_thread
    with _lock:
        if _started:
            kick_import_worker()
            return
        settings = get_settings()
        max_workers = max(1, int(getattr(settings, "import_worker_concurrency", 2) or 2))
        _stop.clear()
        _started = True
        _dispatch_thread = threading.Thread(
            target=_dispatch_loop,
            name="import-dispatch",
            daemon=True,
        )
        _dispatch_thread.start()

    db = SessionLocal()
    try:
        recover_stuck_attachments(db)
        maybe_finalize_idle_jobs(db)
    except Exception:  # noqa: BLE001
        logger.exception("Import worker startup recover failed")
    finally:
        db.close()
    kick_import_worker()
    logger.info("Import worker started (concurrency=%s)", max_workers)


def stop_import_worker() -> None:
    global _started, _dispatch_thread
    _stop.set()
    _wake.set()
    with _lock:
        _started = False
        _dispatch_thread = None


def _max_workers() -> int:
    settings = get_settings()
    return max(1, int(getattr(settings, "import_worker_concurrency", 2) or 2))


def _file_timeout_sec() -> int:
    settings = get_settings()
    return max(60, int(getattr(settings, "import_file_timeout_sec", 720) or 720))


def _reclaim_timed_out() -> int:
    """Soft-fail hung attachments; free effective slots so the batch continues."""
    global _abandoned
    timeout = _file_timeout_sec()
    now = time.time()
    overdue: list[int] = []
    with _lock:
        for att_id, started in list(_claim_started.items()):
            if now - started >= timeout and att_id not in _abandoned_ids:
                overdue.append(att_id)
    n = 0
    for att_id in overdue:
        err = f"timed_out after {timeout}s"
        db = SessionLocal()
        try:
            changed = fail_timed_out_attachment(db, att_id, error=err)
        except Exception:  # noqa: BLE001
            logger.exception("Timeout reclaim failed att=%s", att_id)
            changed = False
        finally:
            db.close()
        if not changed:
            continue
        with _lock:
            _claim_started.pop(att_id, None)
            if att_id not in _abandoned_ids:
                _abandoned_ids.add(att_id)
                _abandoned += 1
        n += 1
        logger.warning("Import attachment timed out att=%s", att_id)
    if n:
        kick_import_worker()
    return n


def _dispatch_loop() -> None:
    global _inflight
    while not _stop.is_set():
        _reclaim_timed_out()
        max_w = _max_workers()
        claimed_any = False
        while not _stop.is_set():
            with _lock:
                if not _started:
                    return
                effective = max(0, _inflight - _abandoned)
                slots = max_w - effective
            if slots <= 0:
                break
            db = SessionLocal()
            try:
                claimed = claim_next_attachment(db)
            except Exception:  # noqa: BLE001
                logger.exception("Claim next attachment failed")
                claimed = None
            finally:
                db.close()
            if claimed is None:
                break
            claimed_any = True
            att_id, job_id, storage_path, filename, mode = claimed
            with _lock:
                _inflight += 1
                _claim_started[att_id] = time.time()
            threading.Thread(
                target=_run_claimed,
                name=f"import-att-{att_id}",
                args=(att_id, job_id, storage_path, filename, mode),
                daemon=True,
            ).start()

        if not claimed_any:
            db = SessionLocal()
            try:
                maybe_finalize_idle_jobs(db)
            except Exception:  # noqa: BLE001
                logger.exception("Finalize idle jobs failed")
            finally:
                db.close()
            _wake.clear()
            _wake.wait(timeout=2.0)
        else:
            time.sleep(0.05)


def _task_finished(att_id: int) -> None:
    global _inflight, _abandoned
    with _lock:
        _inflight = max(0, _inflight - 1)
        _claim_started.pop(att_id, None)
        if att_id in _abandoned_ids:
            _abandoned_ids.discard(att_id)
            _abandoned = max(0, _abandoned - 1)
    kick_import_worker()


def _run_claimed(
    att_id: int,
    job_id: int,
    storage_path: str,
    filename: str,
    mode: str,
) -> None:
    db = SessionLocal()
    try:
        process_claimed_attachment(
            db,
            att_id=att_id,
            job_id=job_id,
            storage_path=storage_path,
            filename=filename,
            mode=mode,
        )
    except Exception:  # noqa: BLE001
        logger.exception("process_claimed_attachment failed att=%s", att_id)
        try:
            att = db.get(Attachment, att_id)
            job = db.get(ImportJob, job_id)
            if att and job and att.ocr_status == "processing" and job.status == "processing":
                record_file_failure(db, att=att, job=job, error="worker_crash")
                finish_job_if_idle(db, job)
                db.commit()
            elif att and att.ocr_status == "processing":
                att.ocr_status = "failed"
                att.ocr_raw_text = "worker_crash"
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to mark crashed attachment")
            db.rollback()
    finally:
        db.close()
        _task_finished(att_id)
