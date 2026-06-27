"""Home grid cards (DramaWave-style layout + search metadata)."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta


def normalize_text(text: str) -> str:
    """Match client-side normalizeText (lowercase, strip accents)."""
    if not text:
        return ""
    lowered = str(text).lower().strip()
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _series_subtitle(item: dict) -> str:
    series = item["series"]
    desc = (series.description or "").strip()
    if desc:
        short = desc.replace("\n", " ").strip()
        if len(short) > 42:
            return short[:42].rstrip() + "…"
        return short
    count = item.get("episode_count") or 0
    if count == 1:
        return "1 episodio"
    return f"{count} episodios"


def _search_keywords(item: dict, filters: list[str]) -> str:
    series = item["series"]
    badge = item.get("badge") or ""
    keywords = [
        series.title,
        series.description or "",
        _series_subtitle(item),
        "drama",
        badge,
        "gratis free",
        "premium vip exclusivo exclusive",
        "nuevo new",
        "popular trending",
        "descubrir discover",
    ]
    if badge == "free":
        keywords.append("gratis free")
    elif badge == "premium":
        keywords.append("premium vip exclusivo exclusive")
    elif badge == "mixed":
        keywords.append("gratis premium mixed")

    if "new" in filters:
        keywords.append("nuevo new")
    if "exclusive" in filters:
        keywords.append("exclusivo exclusive vip premium")
    if "popular" in filters:
        keywords.append("popular trending")
    if "discover" in filters:
        keywords.append("discubrir discover todas")

    return normalize_text(" ".join(keywords))


def prepare_home_grid(sections: dict) -> list[dict]:
    trending_ids = {c["series"].id for c in sections.get("trending", [])}
    recent_ids = {c["series"].id for c in sections.get("recently_added", [])}
    premium_ids = {c["series"].id for c in sections.get("top_premium", [])}
    cutoff = datetime.utcnow() - timedelta(days=21)

    cards: list[dict] = []
    for item in sections.get("all_cards", []):
        series = item["series"]
        sid = series.id
        filters = ["discover"]
        if sid in trending_ids:
            filters.append("popular")
        if sid in recent_ids or (series.created_at and series.created_at >= cutoff):
            filters.append("new")
        if item.get("badge") == "premium" or sid in premium_ids:
            filters.append("exclusive")

        cards.append(
            {
                **item,
                "filters": filters,
                "subtitle": _series_subtitle(item),
                "show_new_badge": "new" in filters,
                "show_exclusive_badge": item.get("badge") == "premium",
                "show_free_badge": item.get("badge") == "free",
                "search_text": _search_keywords(item, filters),
            }
        )
    return cards
