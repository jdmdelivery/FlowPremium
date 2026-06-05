"""Serve WebVTT subtitles with access control (multilingual)."""

import logging

from flask import Response, request

from modules.streaming.models import Episode
from modules.streaming.services.access import can_watch
from modules.streaming.services.subtitle_diagnostics import (
    cors_headers_for_track,
    log_subtitle_stream_request,
    subtitle_storage_exists,
    validate_vtt_content,
)
from modules.streaming.upload import resolve_storage_path

logger = logging.getLogger(__name__)


def get_subtitle_playback_url(episode: Episode, lang: str = "es") -> str | None:
    if not episode.has_subtitles:
        return None
    if not episode.subtitle_storage_key(lang):
        return None
    from flask import url_for

    return url_for("streaming_api.stream_subtitles", episode_id=episode.id, lang=lang)


def stream_episode_subtitles(user, episode: Episode) -> Response:
    lang = (request.args.get("lang") or "es").lower()[:2]

    if not can_watch(user, episode):
        log_subtitle_stream_request(
            episode, lang=lang, status=403, key=None, detail="forbidden"
        )
        return _text_response("Forbidden", 403)

    key = episode.subtitle_storage_key(lang)
    if not key:
        log_subtitle_stream_request(
            episode, lang=lang, status=404, key=None, detail="no storage key"
        )
        return _text_response("No subtitles", 404)

    exists, exists_msg = subtitle_storage_exists(key)
    if not exists:
        log_subtitle_stream_request(
            episode, lang=lang, status=404, key=key, detail=exists_msg
        )
        return _text_response("Subtitle file not found", 404)

    if not _is_r2_key(key):
        try:
            path = resolve_storage_path(key)
        except (ValueError, FileNotFoundError) as exc:
            log_subtitle_stream_request(
                episode, lang=lang, status=404, key=key, detail=str(exc)
            )
            return _text_response("Subtitle not found", 404)
        if request.method == "HEAD":
            size = path.stat().st_size
            return Response(status=200, headers=_vtt_headers(size))
        content = path.read_text(encoding="utf-8")
        return _vtt_response(episode, lang, key, content)

    from modules.storage.storage_r2 import is_r2_configured, stream_object_from_r2

    if not is_r2_configured():
        log_subtitle_stream_request(
            episode, lang=lang, status=503, key=key, detail="R2 not configured"
        )
        return _text_response("Storage unavailable", 503)

    try:
        status, headers, body, _meta = stream_object_from_r2(key, None)
    except Exception as exc:
        logger.exception("[subtitles] R2 stream failed key=%s", key)
        log_subtitle_stream_request(
            episode, lang=lang, status=404, key=key, detail=f"R2 error: {exc}"
        )
        return _text_response("Subtitle not found", 404)

    headers = dict(headers)
    headers["Content-Type"] = "text/vtt; charset=utf-8"
    headers.update(cors_headers_for_track())

    if request.method == "HEAD":
        log_subtitle_stream_request(
            episode, lang=lang, status=status, key=key, detail="HEAD ok"
        )
        return Response(status=status, headers=headers)

    chunks = []
    for chunk in body:
        chunks.append(chunk)
    content = b"".join(chunks).decode("utf-8", errors="replace")
    ok, msg = validate_vtt_content(content)
    log_subtitle_stream_request(
        episode, lang=lang, status=status, key=key, detail=msg, vtt_ok=ok
    )
    if not ok:
        logger.warning("[subtitles] invalid VTT episode=%s key=%s: %s", episode.id, key, msg)
    headers.update(_vtt_headers(len(content.encode("utf-8"))))
    return Response(content, status=status, headers=headers)


def _is_r2_key(key: str) -> bool:
    from modules.storage.storage_r2 import is_r2_configured, use_r2_storage

    if key.startswith("http://") or key.startswith("https://"):
        return False
    return use_r2_storage() and is_r2_configured()


def _vtt_response(episode: Episode, lang: str, key: str, content: str) -> Response:
    ok, msg = validate_vtt_content(content)
    log_subtitle_stream_request(
        episode, lang=lang, status=200, key=key, detail=msg, vtt_ok=ok
    )
    if not ok:
        logger.warning("[subtitles] invalid VTT episode=%s key=%s: %s", episode.id, key, msg)
    return Response(
        content,
        status=200,
        headers=_vtt_headers(len(content.encode("utf-8"))),
    )


def _vtt_headers(content_length: int) -> dict[str, str]:
    headers = {
        "Content-Type": "text/vtt; charset=utf-8",
        "Content-Length": str(content_length),
        "Cache-Control": "private, max-age=3600",
    }
    headers.update(cors_headers_for_track())
    return headers


def _text_response(message: str, status: int) -> Response:
    headers = {"Content-Type": "text/plain; charset=utf-8"}
    headers.update(cors_headers_for_track())
    return Response(message, status=status, headers=headers)
