"""Image preprocess for OCR (PIL only — no OpenCV)."""

from __future__ import annotations

from PIL import Image, ImageEnhance, ImageOps


def preprocess_image(img: Image.Image, *, upscale_min_width: int = 1200) -> Image.Image:
    """Grayscale, autocontrast, optional upscale for phone photos."""
    rgb = img.convert("RGB")
    gray = ImageOps.grayscale(rgb)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    enhancer = ImageEnhance.Contrast(gray)
    gray = enhancer.enhance(1.3)
    w, h = gray.size
    if w < upscale_min_width:
        scale = upscale_min_width / max(w, 1)
        gray = gray.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
    return gray.convert("RGB")
