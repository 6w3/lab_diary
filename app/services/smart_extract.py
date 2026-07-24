"""Smart lab-report extraction via NVIDIA NIM vision models."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)

NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"

SMART_SCHEMA_HINT = """
Return ONLY valid JSON (no markdown) with this shape:
{
  "draws": [
    {
      "drawn_on": "YYYY-MM-DD",
      "lab_name": null,
      "results": [
        {
          "label": "marker name",
          "value": 0.0,
          "unit": "ukat/l",
          "ref_low": null,
          "ref_high": null,
          "confidence": 0.0
        }
      ]
    }
  ],
  "warnings": []
}
Rules:
- Czech/English laboratory blood report.
- If multiple draw dates/columns exist, emit one object per date in "draws".
- Dates on Czech lab reports are day-first: D.M.YYYY or DD.MM.YYYY (example: 12.01.2025 = 12 January 2025 = 2025-01-12). Never treat them as US month-first.
- Prefer ISO dates YYYY-MM-DD in output.
- Numbers as JSON numbers (dot decimal). Do not invent values you cannot read.
- Keep original marker names; do not translate units incorrectly.
"""


def smart_enabled() -> bool:
    s = get_settings()
    return bool(s.nvidia_api_key) and (s.smart_provider or "nvidia").lower() == "nvidia"


def _encode_image(path: Path) -> tuple[str, str]:
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    data = path.read_bytes()
    return mime, base64.b64encode(data).decode("ascii")


def _pages_as_jpeg_paths(storage_path: str, tmp_dir: Path) -> list[Path]:
    path = Path(storage_path)
    out: list[Path] = []
    if path.suffix.lower() == ".pdf":
        from pdf2image import convert_from_path

        images = convert_from_path(str(path), dpi=200)
        for i, img in enumerate(images[:5]):
            dest = tmp_dir / f"page_{i}.jpg"
            img.convert("RGB").save(dest, "JPEG", quality=85)
            out.append(dest)
        return out
    img = Image.open(path).convert("RGB")
    dest = tmp_dir / "page_0.jpg"
    img.save(dest, "JPEG", quality=85)
    out.append(dest)
    return out


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def _validate_smart_payload(data: dict[str, Any]) -> dict[str, Any]:
    draws_in = data.get("draws") or []
    draws_out: list[dict] = []
    for d in draws_in:
        drawn_on = (d.get("drawn_on") or "").strip()[:10]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", drawn_on):
            continue
        results_out = []
        for r in d.get("results") or []:
            try:
                value = float(r["value"])
            except (KeyError, TypeError, ValueError):
                continue
            label = str(r.get("label") or "").strip()
            if len(label) < 2:
                continue
            ref_low = r.get("ref_low", r.get("lab_ref_low"))
            ref_high = r.get("ref_high", r.get("lab_ref_high"))
            try:
                ref_low_f = float(ref_low) if ref_low is not None else None
            except (TypeError, ValueError):
                ref_low_f = None
            try:
                ref_high_f = float(ref_high) if ref_high is not None else None
            except (TypeError, ValueError):
                ref_high_f = None
            results_out.append(
                {
                    "label": label,
                    "value": value,
                    "unit": str(r.get("unit") or ""),
                    "lab_ref_low": ref_low_f,
                    "lab_ref_high": ref_high_f,
                    "confidence": r.get("confidence"),
                    "proposed_drawn_on": drawn_on,
                }
            )
        if results_out:
            draws_out.append(
                {
                    "drawn_on": drawn_on,
                    "lab_name": d.get("lab_name"),
                    "results": results_out,
                }
            )
    return {"draws": draws_out, "warnings": list(data.get("warnings") or [])}


def run_smart_extract(storage_path: str, marker_hints: list[str] | None = None) -> tuple[str, list[dict], dict]:
    """Call NVIDIA VLM; return (raw_json, flat proposals, meta)."""
    settings = get_settings()
    if not settings.nvidia_api_key:
        raise RuntimeError("NVIDIA_API_KEY not configured")

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        pages = _pages_as_jpeg_paths(storage_path, tmp)
        if not pages:
            raise RuntimeError("No pages to analyze")

        content: list[dict] = [{"type": "text", "text": SMART_SCHEMA_HINT}]
        if marker_hints:
            content.append(
                {
                    "type": "text",
                    "text": "Known markers (prefer these labels when matching): "
                    + ", ".join(marker_hints[:80]),
                }
            )
        for p in pages:
            mime, b64 = _encode_image(p)
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            )

        model = settings.smart_model or "nvidia/nemotron-nano-12b-v2-vl"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 4096,
            "temperature": 0.1,
        }
        headers = {
            "Authorization": f"Bearer {settings.nvidia_api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{NVIDIA_BASE}/chat/completions", headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(f"NVIDIA API {resp.status_code}: {resp.text[:500]}")
            body = resp.json()

        text = body["choices"][0]["message"]["content"]
        parsed = _validate_smart_payload(_extract_json(text))
        proposals: list[dict] = []
        for d in parsed["draws"]:
            proposals.extend(d["results"])
        meta = {
            "engine": "nvidia",
            "model": model,
            "mode": "smart",
            "dates": [d["drawn_on"] for d in parsed["draws"]],
            "warnings": parsed["warnings"],
        }
        return text, proposals, meta
