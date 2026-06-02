import logging
import re
from datetime import datetime

from flask import Response, request

from modules.streaming.models import Episode, WatchProgress
from modules.streaming.services.access import can_watch
from modules.streaming.upload import is_local_media_url, resolve_storage_path

logger = logging.getLogger(__name__)

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


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
    """Pick storage key for episode video (Spanish default, optional English variant)."""
    code = (lang or "es").lower().strip()
    if code in ("en", "eng", "english") and episode.video_url_r2_en:
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
    detail: str,
) -> None:
    logger.info(
        "[video] episode=%s backend=%s method=%s range=%s status=%s client=%s key=%s detail=%s",
        episode_id,
        backend,
        request.method,
        request.headers.get("Range") or "-",
        status,
        _client_label(),
        key,
        detail,
    )


def _parse_range(file_size: int, range_header: str) -> tuple[int, int] | None:
    match = _RANGE_RE.match(range_header.strip())
    if not match:
        return None
    start_s, end_s = match.group(1), match.group(2)
    byte_start = int(start_s) if start_s else 0
    byte_end = int(end_s) if end_s else file_size - 1
    byte_end = min(byte_end, file_size - 1)
    if byte_start > byte_end or byte_start >= file_size:
        return None
    return byte_start, byte_end


def _video_response_headers(
    *,
    content_length: int,
    byte_start: int | None = None,
    byte_end: int | None = None,
    file_size: int | None = None,
    status: int = 200,
) -> dict[str, str]:
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": "video/mp4",
        "Content-Length": str(content_length),
        "Cache-Control": "private, max-age=3600, no-transform",
    }
    if status == 206 and byte_start is not None and byte_end is not None and file_size is not None:
        headers["Content-Range"] = f"bytes {byte_start}-{byte_end}/{file_size}"
    return headers


def _stream_local_file(video_ref: str, episode_id: int) -> Response:
    try:
        video_path = resolve_storage_path(video_ref)
    except (ValueError, FileNotFoundError) as exc:
        _log_stream_request(episode_id, video_ref, backend="local", status=404, detail=str(exc))
        return Response("Video not found", status=404)

    file_size = video_path.stat().st_size
    range_header = request.headers.get("Range")

    if request.method == "HEAD":
        headers = _video_response_headers(content_length=file_size, status=200)
        _log_stream_request(
            episode_id, video_ref, backend="local", status=200, detail=f"HEAD size={file_size}"
        )
        return Response(status=200, headers=headers)

    if not range_header and file_size > 0:
        range_header = f"bytes=0-{file_size - 1}"

    parsed = _parse_range(file_size, range_header) if range_header else None
    if not parsed:
        if file_size == 0:
            _log_stream_request(episode_id, video_ref, backend="local", status=404, detail="empty file")
            return Response("Video empty", status=404)
        _log_stream_request(episode_id, video_ref, backend="local", status=416, detail="invalid range")
        return Response("Invalid range", status=416, headers={"Content-Range": f"bytes */{file_size}"})

    byte_start, byte_end = parsed
    length = byte_end - byte_start + 1

    with open(video_path, "rb") as f:
        f.seek(byte_start)
        data = f.read(length)

    headers = _video_response_headers(
        content_length=length,
        byte_start=byte_start,
        byte_end=byte_end,
        file_size=file_size,
        status=206,
    )
    _log_stream_request(
        episode_id,
        video_ref,
        backend="local",
        status=206,
        detail=f"bytes {byte_start}-{byte_end}/{file_size}",
    )
    return Response(data, status=206, headers=headers)


def _stream_r2_file(key: str, episode_id: int) -> Response:
    from modules.storage.storage_r2 import is_r2_configured, stream_object_from_r2

    if not is_r2_configured():
        _log_stream_request(episode_id, key, backend="r2", status=503, detail="R2 not configured")
        return Response(
            "Video no disponible. Cloudflare R2 no está accesible en este momento.",
            status=503,
        )

    range_header = request.headers.get("Range")
    try:
        status, headers, body = stream_object_from_r2(
            key, range_header, method=request.method
        )
    except Exception as exc:
        logger.exception("[video] R2 stream failed key=%s", key)
        _log_stream_request(episode_id, key, backend="r2", status=404, detail=str(exc))
        return Response("Video not found", status=404)

    headers.setdefault("Accept-Ranges", "bytes")
    headers.setdefault("Content-Type", "video/mp4")

    if request.method == "HEAD" or body is None:
        _log_stream_request(
            episode_id,
            key,
            backend="r2",
            status=status,
            detail=f"HEAD cl={headers.get('Content-Length')}",
        )
        return Response(status=status, headers=headers)

    if isinstance(body, bytes):
        _log_stream_request(
            episode_id,
            key,
            backend="r2",
            status=status,
            detail=(
                f"{headers.get('Content-Range')} "
                f"len={len(body)} cl={headers.get('Content-Length')}"
            ),
        )
        return Response(body, status=status, headers=headers)

    _log_stream_request(
        episode_id,
        key,
        backend="r2",
        status=status,
        detail=f"stream {headers.get('Content-Range')}",
    )
    return Response(body, status=status, headers=headers, direct_passthrough=True)


def stream_episode_video(user, episode: Episode) -> Response:
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
