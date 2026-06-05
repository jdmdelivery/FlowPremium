"""Subtitle manifest for the player (Spanish CC + Off only)."""

from __future__ import annotations

from typing import Any

from modules.streaming.models import Episode

SUBTITLE_LABELS = {
    "es": ("Español", "🇪🇸"),
}


def _stream_url(episode_id: int, lang: str) -> str:
    from flask import has_request_context, url_for

    if has_request_context():
        return url_for("streaming_api.stream_subtitles", episode_id=episode_id, lang=lang)
    return f"/api/streaming/subtitles/{episode_id}?lang={lang}"


def build_subtitle_manifest(episode: Episode) -> dict[str, Any]:
    """Subtitles configured by admin only (no auto-detect)."""
    from modules.streaming.services.episode_media import (
        get_admin_subtitle_languages,
        get_subtitle_storage_key,
        media_file_exists,
    )
    from modules.streaming.services.languages import LANG_BY_CODE, LANG_BY_NAME

    admin_langs = get_admin_subtitle_languages(episode)
    tracks: list[dict[str, Any]] = []
    for name in admin_langs:
        code = LANG_BY_NAME[name]["code"]
        key = get_subtitle_storage_key(episode, code)
        if not key or not media_file_exists(key):
            continue
        if code == "es" and episode.subtitle_status not in ("ready", "none"):
            if episode.subtitle_status in ("pending", "processing", "failed", "skipped"):
                continue
        meta = LANG_BY_CODE.get(code, {"flag": "💬"})
        tracks.append(
            {
                "lang": code,
                "label": name,
                "flag": meta.get("flag", "💬"),
                "url": _stream_url(episode.id, code),
            }
        )

    if not tracks and episode.has_subtitles:
        label, flag = SUBTITLE_LABELS["es"]
        tracks = [
            {
                "lang": "es",
                "label": label,
                "flag": flag,
                "url": _stream_url(episode.id, "es"),
            }
        ]

    return {
        "status": episode.subtitle_status or "none",
        "show_cc": len(tracks) > 0,
        "tracks": tracks,
        "default_lang": tracks[0]["lang"] if tracks else None,
    }
