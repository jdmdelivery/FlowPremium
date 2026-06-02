"""Audio track manifest for custom player language selector."""

from __future__ import annotations

import json
import logging
from typing import Any

from modules.streaming.models import Episode

logger = logging.getLogger(__name__)

DEFAULT_TRACKS = {
    "es": ("Español", "🇪🇸"),
    "en": ("English", "🇺🇸"),
}


def _track(
    track_id: str,
    lang: str,
    label: str,
    flag: str,
    *,
    track_type: str,
    url: str | None = None,
    index: int | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": track_id,
        "lang": lang,
        "label": label,
        "flag": flag,
        "type": track_type,
    }
    if url:
        item["url"] = url
    if index is not None:
        item["index"] = index
    return item


def _stream_url(episode_id: int, lang: str) -> str:
    from flask import has_request_context, url_for

    if has_request_context():
        return url_for("streaming_api.stream_video", episode_id=episode_id, lang=lang)
    return f"/api/streaming/stream/{episode_id}?lang={lang}"


def _hls_url(episode: Episode) -> str | None:
    if not episode.hls_url_r2:
        return None
    from utils.media import media_url

    return media_url(episode.hls_url_r2)


def save_probe_result(episode: Episode, embedded: list[dict]) -> None:
    payload = {"embedded": embedded, "count": len(embedded)}
    episode.audio_tracks_json = json.dumps(payload)
    if len(embedded) > 1:
        langs = {t.get("lang") for t in embedded}
        logger.info(
            "Episode %s: %s embedded audio tracks detected (%s)",
            episode.id,
            len(embedded),
            ", ".join(sorted(langs)),
        )
    elif embedded:
        logger.info("Episode %s: single embedded audio track", episode.id)
    else:
        logger.info("Episode %s: no embedded audio streams found", episode.id)


def get_stored_probe(episode: Episode) -> list[dict]:
    if not episode.audio_tracks_json:
        return []
    try:
        data = json.loads(episode.audio_tracks_json)
    except json.JSONDecodeError:
        return []
    return data.get("embedded") or []


def build_audio_manifest(episode: Episode) -> dict[str, Any]:
    """
    Build player manifest.
    mode: single | url | embedded | hls
    """
    tracks: list[dict[str, Any]] = []
    default_id = "es"

    if episode.hls_url_r2:
        master = _hls_url(episode)
        hls_tracks = [
            _track("es", "es", "Español", "🇪🇸", track_type="hls", url=master),
        ]
        if episode.video_url_r2_en:
            hls_tracks.append(
                _track(
                    "en",
                    "en",
                    "English",
                    "🇺🇸",
                    track_type="url",
                    url=_stream_url(episode.id, "en"),
                )
            )
        embedded = get_stored_probe(episode)
        for i, emb in enumerate(embedded):
            lang = emb.get("lang") or f"track{i}"
            if any(t["lang"] == lang for t in hls_tracks):
                continue
            hls_tracks.append(
                _track(
                    f"emb-{emb.get('index', i)}",
                    lang,
                    emb.get("label") or lang,
                    emb.get("flag") or "🔊",
                    track_type="embedded",
                    index=emb.get("index", i),
                )
            )
        return {
            "mode": "hls",
            "master_url": master,
            "tracks": hls_tracks,
            "default": default_id,
            "show_selector": len(hls_tracks) > 1,
        }

    tracks.append(
        _track("es", "es", "Español", "🇪🇸", track_type="url", url=_stream_url(episode.id, "es"))
    )
    if episode.video_url_r2_en:
        tracks.append(
            _track(
                "en",
                "en",
                "English",
                "🇺🇸",
                track_type="url",
                url=_stream_url(episode.id, "en"),
            )
        )

    embedded = get_stored_probe(episode)
    if len(embedded) > 1 and not episode.video_url_r2_en:
        tracks = []
        seen_langs: set[str] = set()
        for i, emb in enumerate(embedded):
            lang = emb.get("lang") or f"track{i}"
            track_id = f"emb-{emb.get('index', i)}"
            if lang in seen_langs:
                track_id = f"{track_id}-{i}"
            seen_langs.add(lang)
            tracks.append(
                _track(
                    track_id,
                    lang,
                    emb.get("label") or DEFAULT_TRACKS.get(lang, (lang, "🔊"))[0],
                    emb.get("flag") or DEFAULT_TRACKS.get(lang, (lang, "🔊"))[1],
                    track_type="embedded",
                    index=emb.get("index"),
                )
            )
            if lang == "es":
                default_id = track_id
        return {
            "mode": "embedded",
            "tracks": tracks,
            "default": default_id,
            "show_selector": len(tracks) > 1,
        }

    return {
        "mode": "url" if len(tracks) > 1 else "single",
        "tracks": tracks,
        "default": "en" if episode.video_url_r2_en and default_id == "es" else default_id,
        "show_selector": len(tracks) > 1,
    }
