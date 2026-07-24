"""RapidOCR (Paddle ONNX) engine with word-box output. Optional dependency."""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from app.services.ocr_preprocess import preprocess_image

logger = logging.getLogger(__name__)

_engine = None
_engine_failed = False


def rapidocr_available() -> bool:
    global _engine_failed
    if _engine_failed:
        return False
    try:
        import rapidocr  # noqa: F401

        return True
    except ImportError:
        try:
            import rapidocr_onnxruntime  # noqa: F401

            return True
        except ImportError:
            return False


def _get_engine():
    global _engine, _engine_failed
    if _engine_failed:
        return None
    if _engine is not None:
        return _engine
    try:
        try:
            from rapidocr import RapidOCR

            _engine = RapidOCR()
        except ImportError:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
        return _engine
    except Exception as exc:  # noqa: BLE001
        logger.warning("RapidOCR init failed: %s", exc)
        _engine_failed = True
        return None


def rapid_ocr_words(img: Image.Image) -> list[dict]:
    """Run RapidOCR; return word boxes {text,x,y,h}."""
    eng = _get_engine()
    if eng is None:
        raise RuntimeError("RapidOCR not available")
    prepared = preprocess_image(img)
    # RapidOCR accepts path or numpy; use temp via list conversion
    import numpy as np

    arr = np.array(prepared)
    result = eng(arr)
    # API variants: (boxes, ...) or Result object
    words: list[dict] = []
    lines = None
    if isinstance(result, tuple) and result:
        lines = result[0]
    elif hasattr(result, "boxes") or hasattr(result, "txts"):
        # newer RapidOCR Result
        boxes = getattr(result, "boxes", None)
        txts = getattr(result, "txts", None)
        if boxes is not None and txts is not None:
            for box, txt in zip(boxes, txts, strict=False):
                words.append(_box_to_word(box, str(txt)))
            return words
    if not lines:
        return words
    for item in lines:
        # item: [box, text, score] or similar
        if not item or len(item) < 2:
            continue
        box, text = item[0], item[1]
        words.append(_box_to_word(box, str(text)))
    return words


def _box_to_word(box, text: str) -> dict:
    # box: 4 points [[x,y],...] or [x1,y1,x2,y2]
    try:
        if hasattr(box, "tolist"):
            box = box.tolist()
        if len(box) == 4 and not isinstance(box[0], (list, tuple)):
            x1, y1, x2, y2 = map(float, box)
            return {"text": text, "x": x1, "y": y1, "h": abs(y2 - y1)}
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
        return {"text": text, "x": min(xs), "y": min(ys), "h": max(ys) - min(ys)}
    except Exception:
        return {"text": text, "x": 0.0, "y": 0.0, "h": 10.0}


def rapid_ocr_path(path: Path) -> list[dict]:
    return rapid_ocr_words(Image.open(path))
