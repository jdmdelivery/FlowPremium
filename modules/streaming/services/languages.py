"""Supported player languages — admin selects from this list only."""

from __future__ import annotations

SUPPORTED_LANGUAGES: tuple[dict[str, str], ...] = (
    {"code": "es", "name": "Español", "flag": "🇪🇸"},
    {"code": "en", "name": "Inglés", "flag": "🇺🇸"},
    {"code": "pt", "name": "Portugués", "flag": "🇵🇹"},
    {"code": "fr", "name": "Francés", "flag": "🇫🇷"},
    {"code": "it", "name": "Italiano", "flag": "🇮🇹"},
    {"code": "de", "name": "Alemán", "flag": "🇩🇪"},
)

LANG_BY_CODE: dict[str, dict[str, str]] = {item["code"]: item for item in SUPPORTED_LANGUAGES}
LANG_BY_NAME: dict[str, dict[str, str]] = {item["name"]: item for item in SUPPORTED_LANGUAGES}
SUPPORTED_LANGUAGE_NAMES: tuple[str, ...] = tuple(item["name"] for item in SUPPORTED_LANGUAGES)
SUPPORTED_LANGUAGE_CODES: tuple[str, ...] = tuple(item["code"] for item in SUPPORTED_LANGUAGES)


def normalize_lang_code(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if raw in LANG_BY_CODE:
        return raw
    if raw in LANG_BY_NAME:
        return LANG_BY_NAME[raw]["code"]
    lower = raw.lower()[:2]
    if lower in LANG_BY_CODE:
        return lower
    return None


def lang_display_name(code: str) -> str:
    item = LANG_BY_CODE.get((code or "").lower()[:2])
    return item["name"] if item else code


def parse_admin_language_list(values: list[str] | None) -> list[str]:
    """Return canonical display names checked by admin."""
    if not values:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        code = normalize_lang_code(value)
        if not code:
            continue
        name = LANG_BY_CODE[code]["name"]
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out
