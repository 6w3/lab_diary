from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from PIL import Image

from app.config import get_settings

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

    # Normalize HEIC to JPEG for OCR
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


_LINE_RE = re.compile(
    r"^(?P<name>[A-Za-zÁ-ž0-9\s\.\-\(\)/%]+?)\s+"
    r"(?P<value>\d+[.,]?\d*)\s*"
    r"(?P<unit>[A-Za-zµμ%/\^\d]+)?\s*"
    r"(?:(?P<low>\d+[.,]?\d*)\s*[-–]\s*(?P<high>\d+[.,]?\d*))?",
    re.UNICODE,
)


def normalize_unit(unit: str) -> str:
    """Normalize OCR units: Greek/micro signs → u; common μkat→pkat OCR typo."""
    if not unit:
        return ""
    u = unit.strip()
    # micro signs often OCR'd as µ (U+00B5), μ (U+03BC), or misread as p/u
    u = u.replace("μ", "u").replace("µ", "u").replace("Μ", "u")
    u = u.replace("μkat", "ukat").replace("µkat", "ukat")
    # Clinical CZ labs use µkat/L; pico-katal is not used → OCR μ→p typo
    lower = u.lower()
    if lower in {"pkat", "pkat/l", "pkat/L"} or lower.startswith("pkat"):
        u = "u" + u[1:]
    return u


def parse_ocr_lines(text: str) -> list[dict]:
    results: list[dict] = []
    # Pre-normalize micro signs in whole text so regex unit class can catch them
    text = (text or "").replace("μ", "u").replace("µ", "u")
    for raw in text.splitlines():
        line = " ".join(raw.strip().split())
        if len(line) < 3:
            continue
        match = _LINE_RE.match(line)
        if not match:
            continue
        name = match.group("name").strip(" :-")
        if len(name) < 2:
            continue
        value = float(match.group("value").replace(",", "."))
        unit = normalize_unit(match.group("unit") or "")
        low = match.group("low")
        high = match.group("high")
        results.append(
            {
                "label": name,
                "value": value,
                "unit": unit,
                "lab_ref_low": float(low.replace(",", ".")) if low else None,
                "lab_ref_high": float(high.replace(",", ".")) if high else None,
            }
        )
    return results


def run_ocr(storage_path: str) -> tuple[str, list[dict]]:
    path = Path(storage_path)
    images: list[Image.Image] = []

    if path.suffix.lower() == ".pdf":
        from pdf2image import convert_from_path

        images = convert_from_path(str(path), dpi=200)
    else:
        images = [Image.open(path)]

    import pytesseract

    texts: list[str] = []
    for img in images:
        texts.append(pytesseract.image_to_string(img, lang="ces+eng"))
    raw = "\n".join(texts)
    return raw, parse_ocr_lines(raw)
