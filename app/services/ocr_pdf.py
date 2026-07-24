"""PDF text-layer extraction (no OCR when embedded text exists)."""

from __future__ import annotations

from pathlib import Path


def extract_pdf_text(path: Path, *, min_chars: int = 40) -> str | None:
    """Return concatenated page text if PDF has a usable text layer."""
    try:
        import pdfplumber
    except ImportError:
        return None
    chunks: list[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip():
                    chunks.append(t)
    except Exception:
        return None
    raw = "\n".join(chunks).strip()
    if len(raw) < min_chars:
        return None
    return raw
