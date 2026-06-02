"""Serve WebVTT subtitles with access control."""

from flask import Response, request

from modules.streaming.models import Episode
from modules.streaming.services.access import can_watch
from modules.streaming.upload import is_local_media_url, resolve_storage_path


def get_subtitle_playback_url(episode: Episode) -> str | None:
    if not episode.has_subtitles:
        return None
    from flask import url_for

    return url_for("streaming_api.stream_subtitles", episode_id=episode.id)


def stream_episode_subtitles(user, episode: Episode) -> Response:
    if not can_watch(user, episode):
        return Response("Forbidden", status=403)

    if not episode.subtitle_url:
        return Response("No subtitles", status=404)

    key = episode.subtitle_url
    if is_local_media_url(key):
        try:
            path = resolve_storage_path(key)
        except (ValueError, FileNotFoundError):
            return Response("Subtitle not found", status=404)
        size = path.stat().st_size
        if request.method == "HEAD":
            return Response(status=200, headers=_vtt_headers(size))
        content = path.read_text(encoding="utf-8")
        return Response(content, status=200, headers=_vtt_headers(len(content.encode("utf-8"))))

    from modules.storage.storage_r2 import is_r2_configured, stream_object_from_r2

    if not is_r2_configured():
        return Response("Storage unavailable", status=503)

    try:
        status, headers, body = stream_object_from_r2(key, None)
    except Exception:
        return Response("Subtitle not found", status=404)

    headers["Content-Type"] = "text/vtt; charset=utf-8"
    if request.method == "HEAD":
        return Response(status=status, headers=headers)
    return Response(body, status=status, headers=headers, direct_passthrough=True)


def _vtt_headers(content_length: int) -> dict[str, str]:
    return {
        "Content-Type": "text/vtt; charset=utf-8",
        "Content-Length": str(content_length),
        "Cache-Control": "private, max-age=3600",
    }
