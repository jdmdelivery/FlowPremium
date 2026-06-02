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
    """Expose only Spanish auto-subtitles in the CC menu (Español / Off)."""
    if not episode.has_subtitles:
        return {
            "status": episode.subtitle_status or "none",
            "show_cc": False,
            "tracks": [],
            "default_lang": None,
        }

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
        "show_cc": True,
        "tracks": tracks,
        "default_lang": "es",
    }
