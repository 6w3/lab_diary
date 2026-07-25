"""In-process import queue: server processes pending attachments without browser keep-alive."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from app.config import get_settings
from app.db import SessionLocal
from app.models import Attachment, ImportJob
from app.services.import_process import (
    claim_next_attachment,
    maybe_finalize_idle_jobs,
    process_claimed_attachment,
    recover_stuck_attachments,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_started = False
_stop = threading.Event()
_wake = threading.Event()
_executor: ThreadPoolExecutor | None = None
_dispatch_thread: threading.Thread | None = None
_inflight = 0


def kick_import_worker() -> None:
    """Wake the dispatcher (call after upload / on demand)."""
    _wake.set()


def start_import_worker() -> None:
    """Start background dispatcher + recover stuck rows. Idempotent."""
    global _started, _executor, _dispatch_thread
    with _lock:
        if _started:
            kick_import_worker()
            return
        settings = get_settings()
        max_workers = max(1, int(getattr(settings, "import_worker_concurrency", 2) or 2))
        _executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="import")
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
    global _started, _executor, _dispatch_thread
    _stop.set()
    _wake.set()
    with _lock:
        ex = _executor
        _executor = None
        _started = False
        _dispatch_thread = None
    if ex is not None:
        ex.shutdown(wait=False, cancel_futures=False)


def _max_workers() -> int:
    settings = get_settings()
    return max(1, int(getattr(settings, "import_worker_concurrency", 2) or 2))


def _dispatch_loop() -> None:
    global _inflight
    while not _stop.is_set():
        max_w = _max_workers()
        claimed_any = False
        while not _stop.is_set():
            with _lock:
                slots = max_w - _inflight
                ex = _executor
            if slots <= 0 or ex is None:
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
            fut = ex.submit(
                _run_claimed,
                att_id,
                job_id,
                storage_path,
                filename,
                mode,
            )
            fut.add_done_callback(_on_done)

        if not claimed_any:
            # Also finalize jobs left idle (e.g. after recover)
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


def _on_done(fut: Future) -> None:
    global _inflight
    try:
        fut.result()
    except Exception:  # noqa: BLE001
        logger.exception("Import worker task crashed")
    with _lock:
        _inflight = max(0, _inflight - 1)
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
            if att and att.ocr_status == "processing":
                att.ocr_status = "failed"
                att.ocr_raw_text = "worker_crash"
            if job and job.status == "processing":
                job.status = "failed"
                job.ocr_raw_text = "worker_crash"
            db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to mark crashed attachment")
            db.rollback()
    finally:
        db.close()
