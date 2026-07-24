"""Filter non-analyte junk rows and dedupe extract proposals."""

from __future__ import annotations

import re
from typing import Any

from app.services.markers import _fold, clean_ocr_label

# Exact labels (folded) that are report metadata, not analytes.
_JUNK_EXACT: set[str] = {
    "cp",
    "ico",
    "icp",
    "dg",
    "diagnoza",
    "vek",
    "pohlavi",
    "platce",
    "rutina",
    "had",
    "am",
    "odber",
    "prijato",
    "pruvodce",
    "pruvodce cislo",
    "sestaveno",
    "strana",
    "hodnoceni",
    "meze",
    "jednotka",
    "vysledek",
    "nazev vysetreni",
    "jmeno",
    "adresa",
    "telefon",
    "email",
    "e-mail",
    "rodne cislo",
    "datum narozeni",
    "svozova trasa",
    "lab online",
    "lab.online",
    "unilabs online",
    "cislo sestaveni",
}

# Substrings (folded, compact) — glued OCR like "cisloosestaveni"
_JUNK_COMPACT_SUBSTR: tuple[str, ...] = (
    "cisloosestaveni",
    "cisloosestaven",
    "rodnecislo",
    "datumnarozeni",
    "svozovatrasa",
    "vydavajicilaborator",
    "pruvodcecislo",
    "kpruvodce",
)

_JUNK_PHRASE_SUBSTR: tuple[str, ...] = (
    "cislo sestaven",
    "cislo pojist",
    "rodne cislo",
    "datum narozeni",
    "svozova trasa",
    "vydavajici laborator",
    "nazev vysetreni",
    "hodnoceni stadia",
    "poznamka lekare",
    "metoda v rozsahu",
    "elektronickou peceti",
    "klasifikace dokum",
    "bez souhlasu laborator",
)


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _fold(text or ""))


_SHORT_ANALYTES: set[str] = {"p", "k", "na", "ca", "mg", "cl", "fe", "zn", "cu", "se"}


def is_junk_label(label: str) -> bool:
    """True for report header/metadata rows that are not lab analytes."""
    cleaned = clean_ocr_label(label or "")
    if not cleaned:
        return True
    folded = _fold(cleaned)
    compact = _compact(cleaned)
    if len(cleaned) < 2 and compact not in _SHORT_ANALYTES:
        return True

    if folded in _JUNK_EXACT or compact in {_compact(x) for x in _JUNK_EXACT}:
        return True
    # Glued "číslosestavení"
    if compact.startswith("cisloosestaven") or compact.startswith("ciselosestaven"):
        return True
    for sub in _JUNK_COMPACT_SUBSTR:
        if sub and sub in compact:
            return True
    for phrase in _JUNK_PHRASE_SUBSTR:
        if phrase in folded:
            return True
    # Pure administrative IDs / long digit strings as "label"
    if re.fullmatch(r"[\d\s./\-]+", cleaned):
        return True
    # "ČP: 8606254679" style leftover
    if compact.startswith("cp") and len(compact) > 2 and compact[2:].isdigit():
        return True
    if folded.startswith("cp ") or folded.startswith("cp:"):
        return True
    if folded.startswith("platce"):
        return True
    if folded.startswith("ico") or folded.startswith("icp"):
        return True
    return False


def _proposal_score(p: dict[str, Any]) -> int:
    score = 0
    if p.get("marker_code"):
        score += 10
    if p.get("unit"):
        score += 2
    if p.get("lab_ref_low") is not None or p.get("lab_ref_high") is not None:
        score += 3
    if p.get("attachment_id"):
        score += 1
    return score


def _dedupe_key(p: dict[str, Any]) -> tuple:
    date = str(p.get("proposed_drawn_on") or "").strip()[:10]
    code = str(p.get("marker_code") or "").strip().lower()
    label_c = _compact(clean_ocr_label(str(p.get("label") or "")))
    try:
        value = round(float(p.get("value")), 6)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        value = None
    # Prefer catalog code; else compact label (so "ALP" and marker_code=alp collide)
    identity = code or label_c
    return (date, identity, value)


def filter_proposals(proposals: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Drop junk metadata rows and duplicate analyte rows."""
    if not proposals:
        return []
    best: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    for raw in proposals:
        p = dict(raw)
        label = str(p.get("label") or "")
        if is_junk_label(label):
            continue
        # marker_code alone is never enough without a sane label
        if len(clean_ocr_label(label)) < 2 and not p.get("marker_code"):
            continue
        key = _dedupe_key(p)
        if key not in best:
            best[key] = p
            order.append(key)
            continue
        if _proposal_score(p) > _proposal_score(best[key]):
            best[key] = p
    return [best[k] for k in order]
