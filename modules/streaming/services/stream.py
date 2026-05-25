import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from flask import Response, request, send_file

from modules.streaming.models import Episode, WatchProgress
from modules.streaming.services.access import can_watch
from modules.streaming.upload import resolve_storage_path


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


def stream_episode_video(user, episode: Episode) -> Response:
    if not can_watch(user, episode):
        return Response("Forbidden", status=403)

    if not episode.video_path:
        return Response("Video not available", status=404)

    try:
        video_path = resolve_storage_path(episode.video_path)
    except (ValueError, FileNotFoundError):
        return Response("Video not found", status=404)

    file_size = video_path.stat().st_size
    range_header = request.headers.get("Range")

    if not range_header:
        return send_file(
            video_path,
            mimetype="video/mp4",
            conditional=True,
            download_name=f"episode_{episode.id}.mp4",
        )

    byte_start, byte_end = 0, file_size - 1
    try:
        range_val = range_header.replace("bytes=", "").strip()
        parts = range_val.split("-")
        if parts[0]:
            byte_start = int(parts[0])
        if len(parts) > 1 and parts[1]:
            byte_end = int(parts[1])
    except (ValueError, IndexError):
        byte_end = file_size - 1

    byte_end = min(byte_end, file_size - 1)
    length = byte_end - byte_start + 1

    with open(video_path, "rb") as f:
        f.seek(byte_start)
        data = f.read(length)

    resp = Response(data, status=206, mimetype="video/mp4", direct_passthrough=True)
    resp.headers["Content-Range"] = f"bytes {byte_start}-{byte_end}/{file_size}"
    resp.headers["Accept-Ranges"] = "bytes"
    resp.headers["Content-Length"] = str(length)
    return resp
