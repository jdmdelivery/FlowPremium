"""Automatic subtitles via faster-whisper + ffmpeg."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from flask import current_app

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.upload import (
    delete_episode_subtitle,
    is_local_media_url,
    resolve_storage_path,
    save_subtitle_vtt,
)

logger = logging.getLogger(__name__)

SUBTITLE_STATUSES = frozenset({"none", "pending", "processing", "ready", "failed", "skipped"})


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def is_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def subtitles_enabled() -> bool:
    return bool(current_app.config.get("SUBTITLES_ENABLED"))


def prerequisites_ok() -> tuple[bool, str]:
    if not subtitles_enabled():
        return False, "Subtitles disabled in configuration"
    if not is_ffmpeg_available():
        return False, "ffmpeg not found (install ffmpeg or add aptfile on Render)"
    if not is_whisper_available():
        return False, "faster-whisper not installed"
    return True, "ok"


def format_vtt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    whole = int(secs)
    millis = int(round((secs - whole) * 1000))
    return f"{hours:02d}:{minutes:02d}:{whole:02d}.{millis:03d}"


def segments_to_vtt(segments) -> str:
    lines = ["WEBVTT", ""]
    for seg in segments:
        text = (getattr(seg, "text", None) or "").strip()
        if not text:
            continue
        start = format_vtt_timestamp(float(getattr(seg, "start", 0)))
        end = format_vtt_timestamp(float(getattr(seg, "end", 0)))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _extract_audio_wav(video_path: Path, wav_path: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(wav_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ffmpeg failed")[-500:]
        raise RuntimeError(f"ffmpeg audio extract failed: {err}")


def _transcribe_audio(wav_path: Path, language: str):
    from faster_whisper import WhisperModel

    model_size = current_app.config.get("WHISPER_MODEL_SIZE", "base")
    device = current_app.config.get("WHISPER_DEVICE", "cpu")
    compute_type = current_app.config.get("WHISPER_COMPUTE_TYPE", "int8")

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(
        str(wav_path),
        language=language or None,
        vad_filter=True,
    )
    return list(segments)


def _materialize_video(episode: Episode, tmp_dir: Path) -> Path:
    key = episode.video_url_r2
    if not key:
        raise ValueError("Episode has no video")

    if is_local_media_url(key):
        return resolve_storage_path(key)

    from modules.storage.storage_r2 import download_object_to_path

    dest = tmp_dir / f"episode_{episode.id}.mp4"
    download_object_to_path(key, dest)
    return dest


def generate_subtitles_for_episode(episode_id: int) -> None:
    """Run inside Flask app context (background thread)."""
    ok, reason = prerequisites_ok()
    episode = db.session.get(Episode, episode_id)
    if not episode or not episode.video_url_r2:
        return

    if not ok:
        logger.warning("Subtitle generation skipped for episode %s: %s", episode_id, reason)
        episode.subtitle_status = "skipped"
        db.session.commit()
        return

    language = (episode.subtitle_lang or current_app.config.get("WHISPER_LANGUAGE") or "es").strip()
    episode.subtitle_status = "processing"
    episode.subtitle_url = None
    db.session.commit()

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"fp_sub_{episode_id}_"))
    try:
        video_path = _materialize_video(episode, tmp_dir)
        wav_path = tmp_dir / "audio.wav"
        _extract_audio_wav(video_path, wav_path)
        segments = _transcribe_audio(wav_path, language)
        vtt_content = segments_to_vtt(segments)
        if not vtt_content.strip() or vtt_content.strip() == "WEBVTT":
            raise RuntimeError("No speech detected for subtitles")

        if episode.subtitle_url:
            delete_episode_subtitle(episode)

        subtitle_key = save_subtitle_vtt(vtt_content, episode.series_id, episode.id)
        episode = db.session.get(Episode, episode_id)
        episode.subtitle_url = subtitle_key
        episode.subtitle_status = "ready"
        episode.subtitle_lang = language
        db.session.commit()
        logger.info("Subtitles ready for episode %s -> %s", episode_id, subtitle_key)
    except Exception as exc:
        logger.exception("Subtitle generation failed for episode %s", episode_id)
        episode = db.session.get(Episode, episode_id)
        if episode:
            episode.subtitle_status = "failed"
            db.session.commit()
        raise exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def enqueue_subtitle_job(episode_id: int) -> bool:
    """Queue subtitle generation without blocking the upload request."""
    ok, reason = prerequisites_ok()
    if not ok:
        logger.info("Not enqueueing subtitles for episode %s: %s", episode_id, reason)
        episode = db.session.get(Episode, episode_id)
        if episode:
            episode.subtitle_status = "skipped"
            db.session.commit()
        return False

    episode = db.session.get(Episode, episode_id)
    if not episode or not episode.video_url_r2:
        return False

    episode.subtitle_status = "pending"
    db.session.commit()

    app = current_app._get_current_object()

    def _run() -> None:
        with app.app_context():
            try:
                generate_subtitles_for_episode(episode_id)
            except Exception:
                pass

    threading.Thread(target=_run, name=f"subtitle-{episode_id}", daemon=True).start()
    return True
