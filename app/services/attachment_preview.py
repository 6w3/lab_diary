"""Build cached JPEG thumbnails for import attachment previews."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

PREVIEW_MAX_SIDE = 720
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def preview_cache_path(storage_path: str | Path) -> Path:
    path = Path(storage_path)
    return path.with_name(f"{path.stem}.preview.jpg")


def ensure_preview_jpeg(storage_path: str | Path, *, max_side: int = PREVIEW_MAX_SIDE) -> Path | None:
    """Return path to a JPEG preview, generating/caching next to the source file.

    Supports common images and PDF (first page). Returns None on failure.
    """
    src = Path(storage_path)
    if not src.is_file():
        return None
    dest = preview_cache_path(src)
    try:
        if dest.is_file() and dest.stat().st_mtime >= src.stat().st_mtime:
            return dest
    except OSError:
        pass

    suffix = src.suffix.lower()
    try:
        if suffix == ".pdf":
            img = _pdf_first_page(src)
        elif suffix in IMAGE_SUFFIXES or suffix in {".heic", ".heif"}:
            img = _open_image(src)
        else:
            return None
        if img is None:
            return None
        img = _fit_rgb(img, max_side=max_side)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "JPEG", quality=82, optimize=True)
        return dest
    except Exception as exc:  # noqa: BLE001
        logger.warning("Preview failed for %s: %s", src, exc)
        return None


def _open_image(path: Path) -> Image.Image | None:
    if path.suffix.lower() in {".heic", ".heif"}:
        try:
            from pillow_heif import register_heif_opener

            register_heif_opener()
        except Exception:  # noqa: BLE001
            pass
    return Image.open(path)


def _pdf_first_page(path: Path) -> Image.Image | None:
    from pdf2image import convert_from_path

    pages = convert_from_path(str(path), dpi=110, first_page=1, last_page=1)
    if not pages:
        return None
    return pages[0]


def _fit_rgb(img: Image.Image, *, max_side: int) -> Image.Image:
    rgb = img.convert("RGB")
    w, h = rgb.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        rgb = rgb.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return rgb
