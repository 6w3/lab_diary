from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from app.config import get_settings

# Re-exports for existing imports
from app.services.ocr_extract import extract_document, run_ocr  # noqa: F401
from app.services.ocr_parse import normalize_unit, parse_ocr_lines  # noqa: F401

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "application/octet-stream",
}


def ensure_upload_dir() -> Path:
    path = Path(get_settings().upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(file: UploadFile, user_id: int, draw_id: int) -> tuple[str, str, str]:
    ensure_upload_dir()
    original = file.filename or "upload.bin"
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")

    content_type = file.content_type or "application/octet-stream"
    dest_dir = ensure_upload_dir() / str(user_id) / str(draw_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    dest = dest_dir / stored_name

    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    if suffix in {".heic", ".heif"}:
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
            img = Image.open(dest)
            jpeg_path = dest.with_suffix(".jpg")
            img.convert("RGB").save(jpeg_path, "JPEG", quality=90)
            dest.unlink(missing_ok=True)
            dest = jpeg_path
            content_type = "image/jpeg"
            stored_name = jpeg_path.name
        except Exception:
            pass

    return stored_name, content_type, str(dest)


def delete_file(storage_path: str) -> None:
    path = Path(storage_path)
    if path.exists():
        path.unlink()
