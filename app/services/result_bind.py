"""Shared helpers for result confirmation (units + marker binding)."""

from __future__ import annotations

from app.models import CustomMarker, Marker
from app.services.label_aliases import learn_label_alias, load_user_aliases
from app.services.markers import resolve_marker
from app.services.ocr_parse import normalize_unit
from app.services.units import to_canonical


def bind_marker_and_units(
    db,
    user_id: int,
    *,
    label: str | None,
    value: float,
    unit: str,
    lab_low: float | None,
    lab_high: float | None,
    catalog: list[Marker],
    code_hint: str | None = None,
    allow_fuzzy: bool = True,
    learn_alias: bool = True,
) -> tuple[str | None, int | None, str | None, float, str, float | None, float | None]:
    """Return marker_code, custom_id, label, value, unit, lab_low, lab_high.

    When allow_fuzzy is False and code_hint is empty, force custom marker
    (user explicitly chose \"custom\" in the review select).
    """
    aliases = load_user_aliases(db, user_id)
    if code_hint:
        matched = resolve_marker(label or "", catalog, code_hint=code_hint, user_aliases=aliases)
    elif allow_fuzzy:
        matched = resolve_marker(label or "", catalog, code_hint=None, user_aliases=aliases)
    else:
        matched = None

    unit_n = normalize_unit(unit or "")
    if matched:
        nv, nu, ok = to_canonical(value, unit_n or unit, matched.code, matched.default_unit)
        if not ok:
            nv, nu = value, unit_n or matched.default_unit
        low_out, high_out = lab_low, lab_high
        src_unit = unit_n or unit
        if lab_low is not None:
            lv, _, lok = to_canonical(lab_low, src_unit, matched.code, matched.default_unit)
            if lok:
                low_out = lv
        if lab_high is not None:
            hv, _, hok = to_canonical(lab_high, src_unit, matched.code, matched.default_unit)
            if hok:
                high_out = hv
        if not nu:
            nu = matched.default_unit
        if learn_alias and label:
            learn_label_alias(db, user_id, label, matched.code, catalog)
        return matched.code, None, matched.name_cs, nv, nu, low_out, high_out

    custom_id = None
    if label:
        existing = (
            db.query(CustomMarker)
            .filter(CustomMarker.user_id == user_id, CustomMarker.name == label)
            .first()
        )
        if not existing:
            existing = CustomMarker(user_id=user_id, name=label, unit=unit_n or "")
            db.add(existing)
            db.flush()
        custom_id = existing.id
    return None, custom_id, label, value, unit_n, lab_low, lab_high
