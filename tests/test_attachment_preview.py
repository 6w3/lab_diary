"""Tests for attachment preview JPEG helper."""

from pathlib import Path

from PIL import Image

from app.services.attachment_preview import ensure_preview_jpeg, preview_cache_path


def test_ensure_preview_jpeg_from_png(tmp_path: Path):
    src = tmp_path / "report.png"
    Image.new("RGB", (1200, 800), color=(40, 120, 80)).save(src)
    out = ensure_preview_jpeg(src, max_side=400)
    assert out is not None
    assert out == preview_cache_path(src)
    assert out.is_file()
    with Image.open(out) as img:
        assert img.format == "JPEG"
        assert max(img.size) <= 400

    # Second call uses cache (mtime)
    mtime = out.stat().st_mtime
    out2 = ensure_preview_jpeg(src, max_side=400)
    assert out2 == out
    assert out2.stat().st_mtime == mtime


def test_ensure_preview_missing_file(tmp_path: Path):
    assert ensure_preview_jpeg(tmp_path / "nope.jpg") is None
