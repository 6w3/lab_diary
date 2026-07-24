"""Tesseract OCR engine with preprocess + PSM."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.services.ocr_preprocess import preprocess_image


def tesseract_image_to_string(img: Image.Image, *, lang: str = "ces+eng") -> str:
    import pytesseract

    prepared = preprocess_image(img)
    # PSM 6: assume uniform block of text (lab reports)
    config = "--psm 6"
    return pytesseract.image_to_string(prepared, lang=lang, config=config)


def tesseract_path_to_string(path: Path) -> str:
    return tesseract_image_to_string(Image.open(path))
