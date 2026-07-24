"""Classic OCR/extract facade: PDF text → RapidOCR → Tesseract."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from app.config import get_settings
from app.services.ocr_parse import parse_from_word_boxes, parse_ocr_lines
from app.services.ocr_pdf import extract_pdf_text
from app.services.ocr_tables import flatten_multi_date, parse_multi_date_table
from app.services.ocr_tesseract import tesseract_image_to_string

logger = logging.getLogger(__name__)


def _load_images(path: Path) -> list[Image.Image]:
    if path.suffix.lower() == ".pdf":
        from pdf2image import convert_from_path

        return convert_from_path(str(path), dpi=200)
    return [Image.open(path)]


def _engine_choice() -> str:
    settings = get_settings()
    choice = (settings.ocr_engine or "auto").lower()
    if choice in {"rapid", "tesseract", "auto"}:
        return choice
    return "auto"


def _ocr_images(images: list[Image.Image]) -> tuple[str, str]:
    """Return (raw_text, engine_used)."""
    choice = _engine_choice()
    use_rapid = choice == "rapid" or choice == "auto"
    if use_rapid:
        try:
            from app.services.ocr_rapid import rapid_ocr_words, rapidocr_available

            if rapidocr_available():
                all_words: list[dict] = []
                y_offset = 0.0
                for img in images:
                    words = rapid_ocr_words(img)
                    for w in words:
                        w = dict(w)
                        w["y"] = float(w["y"]) + y_offset
                        all_words.append(w)
                    y_offset += float(img.size[1]) + 50.0
                raw, _ = parse_from_word_boxes(all_words)
                if raw.strip():
                    return raw, "rapid"
        except Exception as exc:  # noqa: BLE001
            logger.warning("RapidOCR failed, falling back to Tesseract: %s", exc)
            if choice == "rapid":
                raise

    texts: list[str] = []
    for img in images:
        texts.append(tesseract_image_to_string(img))
    return "\n".join(texts), "tesseract"


def extract_document(storage_path: str) -> tuple[str, list[dict], dict]:
    """Extract text + proposals from upload.

    Returns (raw_text, proposals, meta) where proposals may include
    proposed_drawn_on for multi-date tables. meta has engine/mode keys.
    """
    path = Path(storage_path)
    meta: dict = {"engine": None, "mode": "lines"}

    raw: str | None = None
    if path.suffix.lower() == ".pdf":
        raw = extract_pdf_text(path)
        if raw:
            meta["engine"] = "pdf_text"

    if raw is None:
        images = _load_images(path)
        raw, engine = _ocr_images(images)
        meta["engine"] = engine

    multi = parse_multi_date_table(raw)
    if multi:
        proposals = flatten_multi_date(multi)
        meta["mode"] = "multi_date"
        meta["dates"] = multi["dates"]
        return raw, proposals, meta

    proposals = parse_ocr_lines(raw)
    return raw, proposals, meta


# Back-compat name used by routers
def run_ocr(storage_path: str) -> tuple[str, list[dict]]:
    raw, proposals, _meta = extract_document(storage_path)
    return raw, proposals
