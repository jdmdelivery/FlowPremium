"""Automatic multilingual subtitles: Whisper (ES) + auto-translate to other languages."""

from __future__ import annotations

import gc
import json
import logging
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from flask import current_app

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.services.memory_diagnostics import log_memory
from modules.streaming.services.languages import (
    AUTO_TRANSLATE_SUBTITLE_CODES,
    LANG_BY_CODE,
    SUPPORTED_LANGUAGE_CODES,
)
from modules.streaming.services.subtitle_diagnostics import (
    log_episode_subtitle_state,
    validate_vtt_content,
)
from modules.streaming.upload import (
    delete_episode_subtitle_lang,
    is_local_media_url,
    resolve_storage_path,
    save_subtitle_vtt,
)

logger = logging.getLogger(__name__)

SUBTITLE_STATUSES = frozenset({"none", "pending", "processing", "ready", "failed", "skipped"})
_ALL_SUBTITLE_CODES = ("es",) + AUTO_TRANSLATE_SUBTITLE_CODES


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


def subtitle_auto_translate_enabled() -> bool:
    return bool(current_app.config.get("SUBTITLE_AUTO_TRANSLATE_ENABLED", True))


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


def _ffmpeg_bin() -> str:
    from modules.streaming.services.video_processing import ffmpeg_path

    return ffmpeg_path()


def _extract_audio_wav(video_path: Path, wav_path: Path) -> None:
    cmd = [
        _ffmpeg_bin(),
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
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(timeout=3600)
        if proc.returncode != 0:
            err = (stderr or stdout or "ffmpeg failed")[-500:]
            raise RuntimeError(f"ffmpeg audio extract failed: {err}")
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def _transcribe_audio(wav_path: Path, language: str, *, episode_id: int | None = None):
    from faster_whisper import WhisperModel

    model_size = current_app.config.get("WHISPER_MODEL_SIZE", "base")
    device = current_app.config.get("WHISPER_DEVICE", "cpu")
    compute_type = current_app.config.get("WHISPER_COMPUTE_TYPE", "int8")

    log_memory("before_whisper_model_load", episode_id=episode_id, extra=f"model={model_size}")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    log_memory("after_whisper_model_load", episode_id=episode_id)
    try:
        segments, _info = model.transcribe(
            str(wav_path),
            language=language or None,
            vad_filter=True,
        )
        return list(segments)
    finally:
        del model
        gc.collect()
        log_memory("after_whisper_model_release", episode_id=episode_id)


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


def _clear_generated_subtitles(episode: Episode) -> None:
    for code in _ALL_SUBTITLE_CODES:
        delete_episode_subtitle_lang(episode, code)
    episode.subtitle_url_es = None
    episode.subtitle_url_en = None
    episode.subtitle_url = None
    episode.subtitle_tracks = None
    episode.subtitle_languages = None


def _translate_subtitles_from_es(episode: Episode, vtt_es: str) -> dict[str, str]:
    """Translate Spanish VTT to en/pt/fr/it/de and persist each file."""
    from modules.streaming.services.episode_media import set_subtitle_key
    from utils.vtt import translate_vtt

    log_memory("before_subtitle_translation", episode_id=episode.id)
    saved: dict[str, str] = {}
    for code in AUTO_TRANSLATE_SUBTITLE_CODES:
        try:
            vtt_out = translate_vtt(vtt_es, code, source_lang="es")
            ok, msg = validate_vtt_content(vtt_out)
            if not ok:
                logger.warning(
                    "Translated VTT invalid episode=%s lang=%s: %s",
                    episode.id,
                    code,
                    msg,
                )
                continue
            key = save_subtitle_vtt(vtt_out, episode.series_id, episode.id, lang=code)
            episode = db.session.get(Episode, episode.id)
            set_subtitle_key(episode, code, key)
            saved[code] = key
            logger.info(
                "subtitle_%s.vtt ready episode=%s key=%s",
                code,
                episode.id,
                key,
            )
        except Exception:
            logger.exception(
                "Subtitle translation failed episode=%s lang=%s",
                episode.id,
                code,
            )
    log_memory("after_subtitle_translation", episode_id=episode.id, extra=f"langs={sorted(saved)}")
    return saved


def _sync_episode_subtitle_fields(episode: Episode, *, ready: bool = True) -> None:
    from modules.streaming.services.episode_media import (
        get_subtitle_storage_keys,
        sync_episode_track_metadata,
    )

    keys = get_subtitle_storage_keys(episode)
    langs = sorted(keys.keys())
    episode.subtitle_langs = json.dumps(langs, ensure_ascii=False)
    episode.subtitle_url = episode.subtitle_url_es
    episode.subtitle_lang = "es"

    names = [LANG_BY_CODE[code]["name"] for code in SUPPORTED_LANGUAGE_CODES if code in keys]
    episode.subtitle_languages = json.dumps(names, ensure_ascii=False)

    if ready and episode.subtitle_url_es:
        episode.subtitle_status = "ready"
        episode.subtitle_generated_at = datetime.utcnow()

    episode.sync_legacy_subtitle_fields()
    sync_episode_track_metadata(episode)


def generate_subtitles_for_episode(
    episode_id: int,
    *,
    source_path: Path | None = None,
) -> None:
    """Whisper Spanish VTT, then auto-translate to EN/PT/FR/IT/DE."""
    ok, reason = prerequisites_ok()
    episode = db.session.get(Episode, episode_id)
    if not episode or not episode.video_url_r2:
        return

    if not ok:
        logger.warning("Subtitle generation skipped for episode %s: %s", episode_id, reason)
        episode.subtitle_status = "skipped"
        db.session.commit()
        return

    source_lang = (
        episode.subtitle_lang or current_app.config.get("WHISPER_LANGUAGE") or "es"
    ).strip()[:2]

    episode.subtitle_status = "processing"
    _clear_generated_subtitles(episode)
    db.session.commit()

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"fp_sub_{episode_id}_"))
    owns_video_tmp = False
    es_ready = False

    try:
        if source_path and source_path.is_file():
            video_path = source_path
        else:
            video_path = _materialize_video(episode, tmp_dir)
            owns_video_tmp = video_path.parent == tmp_dir

        wav_path = tmp_dir / "audio.wav"
        log_memory("before_ffmpeg_audio_extract", episode_id=episode_id)
        _extract_audio_wav(video_path, wav_path)
        log_memory("after_ffmpeg_audio_extract", episode_id=episode_id)

        segments = _transcribe_audio(wav_path, source_lang, episode_id=episode_id)
        if wav_path.exists():
            wav_path.unlink()
        if owns_video_tmp and video_path.exists():
            video_path.unlink()

        vtt_es = segments_to_vtt(segments)
        if not vtt_es.strip() or vtt_es.strip() == "WEBVTT":
            raise RuntimeError("No speech detected for subtitles")
        vtt_ok, vtt_msg = validate_vtt_content(vtt_es)
        if not vtt_ok:
            raise RuntimeError(f"Generated VTT invalid: {vtt_msg}")

        key_es = save_subtitle_vtt(vtt_es, episode.series_id, episode.id, lang="es")
        episode = db.session.get(Episode, episode_id)
        from modules.streaming.services.episode_media import set_subtitle_key

        set_subtitle_key(episode, "es", key_es)
        es_ready = True
        db.session.commit()
        logger.info("subtitle_es.vtt ready episode=%s key=%s", episode_id, key_es)

        if subtitle_auto_translate_enabled():
            translated = _translate_subtitles_from_es(episode, vtt_es)
            logger.info(
                "Auto-translated subtitles episode=%s langs=%s",
                episode_id,
                sorted(translated.keys()),
            )
        else:
            logger.info("Auto-translate disabled; Spanish only episode=%s", episode_id)

        episode = db.session.get(Episode, episode_id)
        _sync_episode_subtitle_fields(episode, ready=True)
        db.session.commit()
        log_episode_subtitle_state(episode, context="whisper_done")
    except Exception:
        logger.exception("Subtitle generation failed for episode %s", episode_id)
        episode = db.session.get(Episode, episode_id)
        if episode:
            if es_ready:
                _sync_episode_subtitle_fields(episode, ready=True)
            else:
                episode.subtitle_status = "failed"
            db.session.commit()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        gc.collect()


def enqueue_subtitle_job(episode_id: int, *, force: bool = False) -> bool:
    """Queue subtitles after any active HLS job (sequential pipeline)."""
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

    from modules.streaming.services.media_pipeline import (
        enqueue_media_pipeline,
        is_episode_pipeline_active,
    )

    if is_episode_pipeline_active(episode_id):
        logger.info("Pipeline already active for episode %s", episode_id)
        return False
    if not force and episode.subtitle_status in ("pending", "processing"):
        return False
    if not force and episode.subtitle_status == "ready" and (
        episode.subtitle_url_es or episode.subtitle_url
    ):
        logger.info("Subtitles already ready for episode %s", episode_id)
        return False

    return enqueue_media_pipeline(
        episode_id,
        run_hls=False,
        run_subtitles=True,
        force_subtitles=force,
    )
