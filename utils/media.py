"""Resolve local paths and R2 keys to browser-ready URLs."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)


def media_url(stored: str | None, *, expires: int = 3600) -> str | None:
    """Turn DB value (local path, R2 key, or full URL) into a public/presigned URL."""
    if not stored:
        return None
    if stored.startswith("http://") or stored.startswith("https://"):
        return stored
    if stored.startswith("storage/"):
        return f"/media/{stored}"
    from modules.storage.storage_r2 import get_playback_url

    return get_playback_url(stored, expires=expires)


def series_card_url(series) -> str | None:
    if not series:
        return None
    return media_url(series.card_image_key())


def series_hero_url(series) -> str | None:
    if not series:
        return None
    return media_url(series.hero_image_key())


def episode_thumbnail_url(episode) -> str | None:
    if not episode:
        return None
    return media_url(episode.display_thumbnail())


def check_url_responds(url: str | None, *, timeout: int = 10) -> dict:
    """HEAD request to verify a media URL is reachable."""
    if not url:
        return {"ok": False, "status": None, "error": "no_url"}
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        ok = resp.status_code == 200
        return {"ok": ok, "status": resp.status_code, "error": None if ok else "bad_status"}
    except requests.RequestException as exc:
        logger.debug("Media URL check failed for %s: %s", url[:80], exc)
        return {"ok": False, "status": None, "error": str(exc)}


def probe_media_field(stored: str | None) -> dict:
    resolved = media_url(stored)
    check = check_url_responds(resolved)
    return {
        "stored": stored,
        "resolved_url": resolved,
        "http_status": check["status"],
        "responds_200": check["ok"],
        "error": check["error"],
    }


def get_series_media_debug(series_id: int) -> dict:
    from modules.streaming.models import Episode, Series

    series = Series.query.get(series_id)
    if not series:
        return {"error": "series_not_found", "series_id": series_id}

    first_ep = (
        Episode.query.filter_by(series_id=series_id, is_active=True)
        .order_by(Episode.id)
        .first()
    )

    return {
        "series_id": series_id,
        "series_title": series.title,
        "fields": {
            "thumbnail_url": probe_media_field(series.thumbnail_url),
            "hero_image_url": probe_media_field(series.hero_image_url),
            "cover_image_legacy": probe_media_field(series.cover_image),
        },
        "resolved_fallbacks": {
            "card_image": probe_media_field(series.card_image_key()),
            "hero_image": probe_media_field(series.hero_image_key()),
        },
        "first_episode": {
            "id": first_ep.id if first_ep else None,
            "title": first_ep.title if first_ep else None,
            "thumbnail_url": probe_media_field(first_ep.thumbnail_url if first_ep else None),
        },
    }
