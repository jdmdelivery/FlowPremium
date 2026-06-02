"""Probe episode video for embedded audio tracks after upload."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from modules.streaming.models import Episode
from modules.streaming.services.audio_tracks import save_probe_result
from modules.streaming.upload import is_local_media_url, resolve_storage_path
from utils.audio_probe import probe_audio_streams

logger = logging.getLogger(__name__)


def probe_episode_audio(episode: Episode) -> int:
    """Inspect episode video file; store embedded track metadata. Returns track count."""
    key = episode.video_url_r2
    if not key:
        save_probe_result(episode, [])
        return 0

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"fp_audio_probe_{episode.id}_"))
    try:
        if is_local_media_url(key):
            video_path = resolve_storage_path(key)
        else:
            from modules.storage.storage_r2 import download_object_to_path

            video_path = download_object_to_path(key, tmp_dir / "probe.mp4")

        tracks = probe_audio_streams(video_path)
        save_probe_result(episode, tracks)
        return len(tracks)
    except Exception:
        logger.exception("Audio probe failed for episode %s", episode.id)
        save_probe_result(episode, [])
        return 0
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
