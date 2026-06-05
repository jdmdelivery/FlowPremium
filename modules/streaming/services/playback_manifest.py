"""Unified DramaWave-style playback manifest (audio, subtitles, qualities)."""

from __future__ import annotations

import json
import logging
from typing import Any

from modules.streaming.models import Episode
from modules.streaming.services.episode_media import (
    get_admin_audio_languages,
    get_admin_subtitle_languages,
    get_audio_storage_key,
    get_subtitle_storage_key,
    media_file_exists,
    sync_episode_track_metadata,
)
from modules.streaming.services.languages import LANG_BY_CODE, LANG_BY_NAME, normalize_lang_code

logger = logging.getLogger(__name__)

SPEED_OPTIONS = [0.5, 1.0, 1.25, 1.5, 2.0]
QUALITY_LABELS = {
    "auto": "Auto",
    480: "480P",
    720: "720P",
    1080: "1080P",
}


def _stream_url(episode_id: int, lang: str) -> str:
    from flask import has_request_context, url_for

    if has_request_context():
        return url_for("streaming_api.stream_video", episode_id=episode_id, lang=lang)
    return f"/api/streaming/stream/{episode_id}?lang={lang}"


def _subtitle_url(episode_id: int, lang: str) -> str:
    from flask import has_request_context, url_for

    if has_request_context():
        return url_for("streaming_api.stream_subtitles", episode_id=episode_id, lang=lang)
    return f"/api/streaming/subtitles/{episode_id}?lang={lang}"


def _hls_master_url(episode: Episode) -> str | None:
    key = episode.hls_master_url or episode.hls_url_r2
    if not key:
        return None
    from utils.media import media_url

    return media_url(key)


def _loads_qualities(episode: Episode) -> list[dict[str, Any]]:
    raw = episode.qualities
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def is_episode_playable(episode: Episode) -> bool:
    if episode.video_url_r2 or episode.hls_playlist_key:
        return True
    status = (episode.processing_status or "ready").lower()
    return status == "ready" and bool(episode.hls_playlist_key)


def build_playback_manifest(episode: Episode) -> dict[str, Any]:
    sync_episode_track_metadata(episode)

    admin_audio = get_admin_audio_languages(episode)
    admin_subs = get_admin_subtitle_languages(episode)

    audio_tracks: list[dict[str, Any]] = []
    for name in admin_audio:
        code = LANG_BY_NAME[name]["code"]
        key = get_audio_storage_key(episode, code)
        if not key:
            continue
        exists = media_file_exists(key)
        if not exists:
            continue
        meta = LANG_BY_CODE[code]
        track_type = "url"
        url = _stream_url(episode.id, code)
        audio_tracks.append(
            {
                "id": code,
                "lang": code,
                "language": name,
                "label": name,
                "flag": meta["flag"],
                "type": track_type,
                "url": url,
                "available": True,
            }
        )

    subtitle_tracks: list[dict[str, Any]] = []
    for name in admin_subs:
        code = LANG_BY_NAME[name]["code"]
        key = get_subtitle_storage_key(episode, code)
        if not key:
            continue
        if episode.subtitle_status not in ("ready", "none") and code == "es":
            if not media_file_exists(key):
                continue
        elif not media_file_exists(key):
            continue
        meta = LANG_BY_CODE[code]
        subtitle_tracks.append(
            {
                "lang": code,
                "language": name,
                "label": name,
                "flag": meta["flag"],
                "url": _subtitle_url(episode.id, code),
                "available": True,
            }
        )

    qualities = _loads_qualities(episode)
    quality_levels: list[dict[str, Any]] = [{"id": "auto", "label": "Auto", "height": None}]
    for q in qualities:
        height = q.get("height") or q.get("id")
        if not height:
            continue
        try:
            h = int(height)
        except (TypeError, ValueError):
            continue
        quality_levels.append(
            {
                "id": str(h),
                "label": QUALITY_LABELS.get(h, f"{h}P"),
                "height": h,
                "url": q.get("url"),
                "bitrate": q.get("bitrate"),
            }
        )

    hls_url = _hls_master_url(episode)
    source_type = "hls" if hls_url else "mp4"
    default_stream = _stream_url(episode.id, "es") if episode.video_url_r2 else None

    status = (episode.processing_status or "ready").lower()
    playable = is_episode_playable(episode)

    manifest: dict[str, Any] = {
        "episode_id": episode.id,
        "processing_status": status,
        "processing_error": episode.processing_error,
        "playable": playable,
        "source_type": source_type,
        "hls_master_url": hls_url,
        "default_stream_url": default_stream,
        "speed_options": SPEED_OPTIONS,
        "audio": {
            "available": len(audio_tracks) > 0,
            "show_selector": len(audio_tracks) > 1,
            "tracks": audio_tracks,
            "default": audio_tracks[0]["id"] if audio_tracks else None,
            "unavailable_label": "Audio no disponible",
        },
        "subtitles": {
            "available": len(subtitle_tracks) > 0,
            "show_selector": len(subtitle_tracks) > 0,
            "tracks": subtitle_tracks,
            "default_lang": subtitle_tracks[0]["lang"] if subtitle_tracks else None,
            "unavailable_label": "Subtítulos no disponibles",
        },
        "qualities": {
            "available": bool(hls_url and len(quality_levels) > 1),
            "show_selector": bool(hls_url and len(quality_levels) > 1),
            "levels": quality_levels if hls_url else [],
            "default": "auto",
            "unavailable_label": "Calidad no disponible",
        },
    }

    legacy_audio = _build_legacy_audio_fallback(episode, audio_tracks)
    if legacy_audio:
        manifest["legacy_audio"] = legacy_audio

    return manifest


def _build_legacy_audio_fallback(
    episode: Episode, admin_tracks: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Keep ffprobe embedded / HLS modes for backward compatibility."""
    from modules.streaming.services.audio_tracks import build_audio_manifest

    if admin_tracks:
        return None
    return build_audio_manifest(episode)
