import logging
from datetime import datetime

from flask import Response, request

from modules.streaming.models import Episode, WatchProgress
from modules.streaming.services.access import can_watch
from modules.streaming.services.range_http import clamp_byte_range
from modules.streaming.upload import is_local_media_url, resolve_storage_path

logger = logging.getLogger(__name__)

_READ_CHUNK = 256 * 1024


def save_progress(user, episode_id: int, position: int, completed: bool = False) -> WatchProgress:
    progress = WatchProgress.query.filter_by(user_id=user.id, episode_id=episode_id).first()
    if not progress:
        progress = WatchProgress(user_id=user.id, episode_id=episode_id)
    progress.position_seconds = max(0, position)
    progress.completed = completed or progress.completed
    if completed and not progress.completed_at:
        progress.completed_at = datetime.utcnow()
    progress.updated_at = datetime.utcnow()
    from extensions import db

    db.session.add(progress)
    db.session.commit()
    return progress


def get_episode_stream_url(user, episode: Episode, lang: str = "es") -> str:
    """Same-origin stream URL so mobile browsers get proper 206 Range responses."""
    from flask import url_for

    return url_for("streaming_api.stream_video", episode_id=episode.id, lang=lang)


def resolve_episode_video_key(episode: Episode, lang: str | None = None) -> str | None:
    """Pick storage key for episode video by admin language code."""
    from modules.streaming.services.episode_media import get_audio_storage_key
    from modules.streaming.services.languages import normalize_lang_code

    code = normalize_lang_code(lang or "es") or "es"
    key = get_audio_storage_key(episode, code)
    if key:
        return key
    if code == "en" and episode.video_url_r2_en:
        return episode.video_url_r2_en
    return episode.video_url_r2


def _should_stream_from_r2(key: str) -> bool:
    if not key or key.startswith("http://") or key.startswith("https://"):
        return False
    if is_local_media_url(key):
        return False
    from modules.storage.storage_r2 import is_r2_configured, use_r2_storage

    return use_r2_storage() and is_r2_configured()


def _client_label() -> str:
    ua = (request.headers.get("User-Agent") or "")[:120]
    if "iPhone" in ua or "iPad" in ua:
        return "ios"
    if "Android" in ua:
        return "android"
    return "desktop"


def _log_stream_request(
    episode_id: int,
    key: str,
    *,
    backend: str,
    status: int,
    range_in: str,
    range_out: str,
    content_length: int,
    file_size: int | None = None,
    extra: str = "",
) -> None:
    logger.info(
        "[video] episode=%s backend=%s method=%s client=%s "
        "range_in=%s range_out=%s status=%s cl=%s file_size=%s key=%s %s",
        episode_id,
        backend,
        request.method,
        _client_label(),
        range_in or "-",
        range_out or "-",
        status,
        content_length,
        file_size if file_size is not None else "-",
        key,
        extra,
    )


def _video_response_headers(
    *,
    content_length: int,
    byte_start: int,
    byte_end: int,
    file_size: int,
) -> dict[str, str]:
    return {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
        "Content-Length": str(content_length),
        "Content-Range": f"bytes {byte_start}-{byte_end}/{file_size}",
        "Cache-Control": "private, max-age=3600, no-transform",
    }


def _local_file_chunks(path, byte_start: int, length: int):
    with open(path, "rb") as f:
        f.seek(byte_start)
        remaining = length
        while remaining > 0:
            data = f.read(min(_READ_CHUNK, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


def _stream_local_file(video_ref: str, episode_id: int) -> Response:
    try:
        video_path = resolve_storage_path(video_ref)
    except (ValueError, FileNotFoundError) as exc:
        _log_stream_request(
            episode_id,
            video_ref,
            backend="local",
            status=404,
            range_in="-",
            range_out="-",
            content_length=0,
            extra=str(exc),
        )
        return Response("Video not found", status=404)

    file_size = video_path.stat().st_size
    range_in = request.headers.get("Range") or "-"

    if request.method == "HEAD":
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": "video/mp4",
            "Content-Length": str(file_size),
            "Cache-Control": "private, max-age=3600, no-transform",
        }
        _log_stream_request(
            episode_id,
            video_ref,
            backend="local",
            status=200,
            range_in=range_in,
            range_out="-",
            content_length=file_size,
            file_size=file_size,
            extra="HEAD",
        )
        return Response(status=200, headers=headers)

    try:
        byte_start, byte_end, range_out = clamp_byte_range(
            file_size, request.headers.get("Range")
        )
    except ValueError as exc:
        if str(exc) == "invalid range":
            _log_stream_request(
                episode_id,
                video_ref,
                backend="local",
                status=416,
                range_in=range_in,
                range_out="-",
                content_length=0,
                file_size=file_size,
            )
            return Response("Invalid range", status=416, headers={"Content-Range": f"bytes */{file_size}"})
        return Response("Video empty", status=404)

    length = byte_end - byte_start + 1
    headers = _video_response_headers(
        content_length=length,
        byte_start=byte_start,
        byte_end=byte_end,
        file_size=file_size,
    )
    _log_stream_request(
        episode_id,
        video_ref,
        backend="local",
        status=206,
        range_in=range_in,
        range_out=range_out,
        content_length=length,
        file_size=file_size,
    )
    return Response(
        _local_file_chunks(video_path, byte_start, length),
        status=206,
        headers=headers,
        direct_passthrough=True,
    )


def _stream_r2_file(key: str, episode_id: int) -> Response:
    from modules.storage.storage_r2 import is_r2_configured, stream_object_from_r2

    if not is_r2_configured():
        _log_stream_request(
            episode_id,
            key,
            backend="r2",
            status=503,
            range_in="-",
            range_out="-",
            content_length=0,
            extra="R2 not configured",
        )
        return Response(
            "Video no disponible. Cloudflare R2 no está accesible en este momento.",
            status=503,
        )

    range_in = request.headers.get("Range") or "-"
    try:
        status, headers, body, meta = stream_object_from_r2(
            key,
            request.headers.get("Range"),
            method=request.method,
        )
    except ValueError as exc:
        if "invalid range" in str(exc):
            file_size = 0
            try:
                from modules.storage.storage_r2 import object_head_meta

                file_size = object_head_meta(key)["content_length"]
            except Exception:
                pass
            _log_stream_request(
                episode_id,
                key,
                backend="r2",
                status=416,
                range_in=range_in,
                range_out="-",
                content_length=0,
                file_size=file_size or None,
            )
            return Response("Invalid range", status=416, headers={"Content-Range": f"bytes */{file_size}"})
        logger.exception("[video] R2 stream failed key=%s", key)
        _log_stream_request(
            episode_id,
            key,
            backend="r2",
            status=404,
            range_in=range_in,
            range_out="-",
            content_length=0,
            extra=str(exc),
        )
        return Response("Video not found", status=404)
    except Exception as exc:
        logger.exception("[video] R2 stream failed key=%s", key)
        _log_stream_request(
            episode_id,
            key,
            backend="r2",
            status=404,
            range_in=range_in,
            range_out="-",
            content_length=0,
            extra=str(exc),
        )
        return Response("Video not found", status=404)

    headers.setdefault("Accept-Ranges", "bytes")
    headers.setdefault("Content-Type", "video/mp4")

    content_length = int(headers.get("Content-Length") or 0)
    _log_stream_request(
        episode_id,
        key,
        backend="r2",
        status=status,
        range_in=range_in,
        range_out=meta.get("range_out", "-"),
        content_length=content_length,
        file_size=meta.get("file_size"),
        extra=headers.get("Content-Range", ""),
    )

    if request.method == "HEAD" or body is None:
        return Response(status=status, headers=headers)

    return Response(body, status=status, headers=headers, direct_passthrough=True)


def stream_episode_video(user, episode: Episode) -> Response:
    from modules.streaming.services.memory_diagnostics import log_memory

    log_memory("video_stream_start", episode_id=episode.id)
    if not can_watch(user, episode):
        logger.warning(
            "[video] forbidden episode=%s user=%s client=%s",
            episode.id,
            getattr(user, "id", None),
            _client_label(),
        )
        return Response("Forbidden", status=403)

    lang = request.args.get("lang", "es")
    video_key = resolve_episode_video_key(episode, lang)
    if not video_key:
        logger.warning("[video] no video key episode=%s lang=%s", episode.id, lang)
        return Response("Video not available", status=404)

    if _should_stream_from_r2(video_key):
        return _stream_r2_file(video_key, episode.id)

    return _stream_local_file(video_key, episode.id)
