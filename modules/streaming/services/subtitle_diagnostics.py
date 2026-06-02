"""Subtitle pipeline diagnostics for Render logs and admin debugging."""

from __future__ import annotations

import logging
import re
from typing import Any

from flask import request

from modules.streaming.models import Episode
from modules.streaming.upload import resolve_storage_path

logger = logging.getLogger(__name__)

_VTT_TS = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}$",
    re.MULTILINE,
)


def validate_vtt_content(content: str) -> tuple[bool, str]:
    if not content or not content.strip():
        return False, "empty file"
    normalized = content.replace("\r\n", "\n").lstrip("\ufeff")
    if not normalized.startswith("WEBVTT"):
        return False, "missing WEBVTT header"
    if not _VTT_TS.search(normalized):
        return False, "no valid timestamp cues found"
    return True, "ok"


def subtitle_storage_exists(key: str | None) -> tuple[bool, str]:
    if not key:
        return False, "no storage key"
    if _use_r2_for_key(key):
        return _r2_object_exists(key)
    try:
        path = resolve_storage_path(key)
        size = path.stat().st_size
        return True, f"local file ({size} bytes)"
    except FileNotFoundError:
        return False, "local file not found"
    except ValueError as exc:
        return False, f"invalid local path: {exc}"


def _use_r2_for_key(key: str) -> bool:
    from modules.storage.storage_r2 import is_r2_configured, use_r2_storage

    if key.startswith("http://") or key.startswith("https://"):
        return False
    return use_r2_storage() and is_r2_configured()


def _r2_object_exists(key: str) -> tuple[bool, str]:
    from modules.storage.storage_r2 import is_r2_configured

    if not is_r2_configured():
        return False, "R2 not configured"
    try:
        from modules.storage.storage_r2 import _get_client, _bucket

        client = _get_client()
        client.head_object(Bucket=_bucket(), Key=key)
        return True, "R2 object exists"
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "") if hasattr(exc, "response") else ""
        return False, f"R2 head_object failed: {code or exc}"


def episode_subtitle_snapshot(episode: Episode) -> dict[str, Any]:
    key = episode.subtitle_storage_key("es")
    exists, exists_detail = subtitle_storage_exists(key)
    return {
        "episode_id": episode.id,
        "subtitle_status": episode.subtitle_status,
        "subtitle_url": episode.subtitle_url,
        "subtitle_url_es": episode.subtitle_url_es,
        "subtitle_lang": episode.subtitle_lang,
        "has_subtitles": episode.has_subtitles,
        "storage_key": key,
        "file_exists": exists,
        "file_detail": exists_detail,
    }


def log_episode_subtitle_state(episode: Episode, *, context: str = "watch") -> dict[str, Any]:
    snap = episode_subtitle_snapshot(episode)
    logger.info(
        "[subtitles] %s episode=%s status=%s url=%s key=%s exists=%s (%s) has_subtitles=%s",
        context,
        snap["episode_id"],
        snap["subtitle_status"],
        snap["subtitle_url"],
        snap["storage_key"],
        snap["file_exists"],
        snap["file_detail"],
        snap["has_subtitles"],
    )
    return snap


def log_subtitle_stream_request(
    episode: Episode,
    *,
    lang: str,
    status: int,
    key: str | None,
    detail: str,
    vtt_ok: bool | None = None,
) -> None:
    user_id = None
    try:
        from flask_login import current_user

        if current_user.is_authenticated:
            user_id = current_user.id
    except Exception:
        pass
    logger.info(
        "[subtitles] stream episode=%s lang=%s user=%s status=%s key=%s vtt_valid=%s detail=%s",
        episode.id,
        lang,
        user_id,
        status,
        key,
        vtt_ok,
        detail,
    )


def cors_headers_for_track() -> dict[str, str]:
    """Allow <track> loads when video uses crossOrigin (Safari / Chrome)."""
    origin = request.headers.get("Origin")
    if origin:
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }
    return {}
