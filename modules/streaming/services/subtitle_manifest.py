"""Subtitle language manifest for the video player."""

from __future__ import annotations

import json
from typing import Any

from modules.streaming.models import Episode

SUBTITLE_LABELS = {
    "es": ("Español", "🇪🇸"),
    "en": ("English", "🇺🇸"),
    "pt": ("Português", "🇧🇷"),
    "fr": ("Français", "🇫🇷"),
}


def _stream_url(episode_id: int, lang: str) -> str:
    from flask import has_request_context, url_for

    if has_request_context():
        return url_for("streaming_api.stream_subtitles", episode_id=episode_id, lang=lang)
    return f"/api/streaming/subtitles/{episode_id}?lang={lang}"


def episode_subtitle_langs(episode: Episode) -> list[str]:
    if episode.subtitle_langs:
        try:
            data = json.loads(episode.subtitle_langs)
            if isinstance(data, list) and data:
                return [str(x) for x in data]
        except json.JSONDecodeError:
            pass

    langs: list[str] = []
    if episode.subtitle_url_es or episode.subtitle_url:
        langs.append("es")
    if episode.subtitle_url_en:
        langs.append("en")
    return langs


def build_subtitle_manifest(episode: Episode) -> dict[str, Any]:
    langs = episode_subtitle_langs(episode)
    tracks = []
    for lang in langs:
        label, flag = SUBTITLE_LABELS.get(lang, (lang.upper(), "💬"))
        tracks.append(
            {
                "lang": lang,
                "label": label,
                "flag": flag,
                "url": _stream_url(episode.id, lang),
            }
        )

    return {
        "status": episode.subtitle_status or "none",
        "show_cc": episode.has_subtitles and len(tracks) > 0,
        "tracks": tracks,
        "default_lang": "es" if "es" in langs else (langs[0] if langs else None),
    }
