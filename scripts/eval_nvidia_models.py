#!/usr/bin/env python3
"""Offline eval note: compare NVIDIA vision model IDs for Smart extract.

Run (needs NVIDIA_API_KEY in env):
  python scripts/eval_nvidia_models.py

Writes results to /tmp/lab_diary_nvidia_eval.json — does not send real PHI
when using the synthetic PNG generated here.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

CANDIDATES = [
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "meta/llama-3.2-90b-vision-instruct",
    "nvidia/nemotron-nano-12b-v2-vl",
    "meta/llama-3.2-11b-vision-instruct",
    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
]


def _make_sample(path: Path) -> None:
    img = Image.new("RGB", (900, 500), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    lines = [
        "Lab report sample",
        "Marker    12.01.2025  03.06.2025  Ref",
        "AST       0.48        0.42        0.10-0.70",
        "ALT       0.61        0.55        0.10-0.80",
        "TSH       2.4         2.1         0.4-4.0",
    ]
    y = 40
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 40
    img.save(path, "PNG")


def main() -> int:
    key = os.environ.get("NVIDIA_API_KEY", "")
    if not key:
        # load .env manually
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("NVIDIA_API_KEY="):
                    key = line.split("=", 1)[1].strip()
    if not key:
        print("NVIDIA_API_KEY missing")
        return 1

    os.environ["NVIDIA_API_KEY"] = key
    os.environ.setdefault("SMART_PROVIDER", "nvidia")

    from app.services.smart_extract import run_smart_extract
    from app.config import get_settings

    get_settings.cache_clear()

    results = []
    with tempfile.TemporaryDirectory() as td:
        sample = Path(td) / "sample.png"
        _make_sample(sample)
        for model in CANDIDATES:
            os.environ["SMART_MODEL"] = model
            get_settings.cache_clear()
            entry = {"model": model, "ok": False, "proposals": 0, "dates": [], "error": None}
            try:
                _raw, proposals, meta = run_smart_extract(str(sample))
                entry["ok"] = True
                entry["proposals"] = len(proposals)
                entry["dates"] = meta.get("dates") or []
                entry["labels"] = [p.get("label") for p in proposals[:10]]
            except Exception as exc:  # noqa: BLE001
                entry["error"] = str(exc)[:300]
            results.append(entry)
            print(json.dumps(entry, ensure_ascii=False))

    out = Path("/tmp/lab_diary_nvidia_eval.json")
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")

    # Prefer first successful with >=3 proposals and 2 dates
    chosen = None
    for r in results:
        if r["ok"] and r["proposals"] >= 3 and len(r.get("dates") or []) >= 1:
            chosen = r["model"]
            break
    if not chosen:
        for r in results:
            if r["ok"] and r["proposals"] >= 1:
                chosen = r["model"]
                break
    if chosen:
        print(f"RECOMMENDED_SMART_MODEL={chosen}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
