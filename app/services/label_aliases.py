"""Per-user OCR/custom label → catalog marker learning."""

from __future__ import annotations

from app.services.markers import _fold, clean_ocr_label


def normalize_alias_label(label: str) -> str:
    return _fold(clean_ocr_label(label or ""))


def load_user_aliases(db, user_id: int) -> dict[str, str]:
    """Return label_norm → marker_code for user."""
    from app.models import LabelAlias

    rows = db.query(LabelAlias).filter(LabelAlias.user_id == user_id).all()
    return {r.label_norm: r.marker_code for r in rows}


def lookup_user_alias(db, user_id: int, label: str) -> str | None:
    from app.models import LabelAlias

    norm = normalize_alias_label(label)
    if not norm:
        return None
    row = (
        db.query(LabelAlias)
        .filter(LabelAlias.user_id == user_id, LabelAlias.label_norm == norm)
        .first()
    )
    return row.marker_code if row else None


def _is_trivial_alias(label: str, marker) -> bool:
    """Skip learning when label already is the catalog name/code."""
    norm = normalize_alias_label(label)
    if not norm:
        return True
    names = {_fold(marker.code), _fold(marker.name_cs), _fold(marker.name_en)}
    return norm in names


def learn_label_alias(db, user_id: int, label: str, marker_code: str, catalog: list) -> None:
    """Remember OCR/custom label → catalog code for future auto-match."""
    from app.models import LabelAlias

    raw = (label or "").strip()
    if not raw or not marker_code:
        return
    by_code = {m.code: m for m in catalog}
    marker = by_code.get(marker_code)
    if not marker:
        return
    if _is_trivial_alias(raw, marker):
        return
    norm = normalize_alias_label(raw)
    if not norm:
        return
    existing = (
        db.query(LabelAlias)
        .filter(LabelAlias.user_id == user_id, LabelAlias.label_norm == norm)
        .first()
    )
    if existing:
        existing.marker_code = marker_code
        existing.label_raw = raw
        return
    db.add(
        LabelAlias(
            user_id=user_id,
            label_raw=raw,
            label_norm=norm,
            marker_code=marker_code,
        )
    )
