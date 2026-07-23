from __future__ import annotations

import json
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

_CACHE: dict[str, dict[str, str]] = {}


def load_locale(locale: str) -> dict[str, str]:
    code = "en" if locale == "en" else "cs"
    if code not in _CACHE:
        path = LOCALES_DIR / f"{code}.json"
        _CACHE[code] = json.loads(path.read_text(encoding="utf-8"))
    return _CACHE[code]


def t(locale: str, key: str, **kwargs: str) -> str:
    messages = load_locale(locale)
    fallback = load_locale("cs")
    text = messages.get(key) or fallback.get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
