"""Sequential background media processing: HLS first, then subtitles (never parallel)."""

from __future__ import annotations

import gc
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from flask import current_app

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.services.memory_diagnostics import log_memory, pipeline_memory_ok
from modules.streaming.upload import is_local_media_url, resolve_storage_path

logger = logging.getLogger(__name__)

_ACTIVE: set[int] = set()
_ACTIVE_SINCE: dict[int, float] = {}
_LOCK = threading.Lock()
_ACTIVE_MAX_AGE_S = 7200


def _purge_stale_active() -> None:
    """Prevent _ACTIVE from blocking re-queues if a worker thread died."""
    now = time.monotonic()
    with _LOCK:
        stale = [
            episode_id
            for episode_id, started in _ACTIVE_SINCE.items()
            if now - started > _ACTIVE_MAX_AGE_S
        ]
        for episode_id in stale:
            _ACTIVE.discard(episode_id)
            _ACTIVE_SINCE.pop(episode_id, None)


def _use_subprocess_worker() -> bool:
    from flask import current_app

    cfg = current_app.config.get("MEDIA_PIPELINE_USE_SUBPROCESS")
    if cfg is not None:
        return bool(cfg)
    from utils.runtime_env import is_render

    return is_render()


def _spawn_pipeline_subprocess(
    episode_id: int,
    *,
    run_hls: bool,
    run_subtitles: bool,
    force_subtitles: bool,
) -> subprocess.Popen[bytes]:
    cmd = [sys.executable, "-m", "modules.streaming.media_worker", str(episode_id)]
    if run_hls:
        cmd.append("--hls")
    if run_subtitles:
        cmd.append("--subtitles")
    if force_subtitles:
        cmd.append("--force-subtitles")
    logger.info(
        "Spawning media worker subprocess episode=%s cmd=%s",
        episode_id,
        " ".join(cmd),
    )
    return subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=None,
        start_new_session=True,
        env=os.environ.copy(),
    )


def is_episode_pipeline_active(episode_id: int) -> bool:
    with _LOCK:
        return episode_id in _ACTIVE


def _materialize_source(episode: Episode, tmp_dir: Path) -> Path:
    key = episode.video_url_r2
    if not key:
        raise ValueError("No source video")
    if is_local_media_url(key):
        return resolve_storage_path(key)
    from modules.storage.storage_r2 import download_object_to_path

    dest = tmp_dir / f"episode_{episode.id}.mp4"
    log_memory("before_r2_download", episode_id=episode.id, extra=f"key={key}")
    path = download_object_to_path(key, dest)
    log_memory("after_r2_download", episode_id=episode.id)
    return path


def _should_run_subtitles(episode: Episode, *, force: bool) -> bool:
    from modules.streaming.services.subtitles import prerequisites_ok

    ok, reason = prerequisites_ok()
    if not ok:
        logger.info("Skipping subtitles episode=%s: %s", episode.id, reason)
        episode.subtitle_status = "skipped"
        db.session.commit()
        return False
    if force:
        return True
    if episode.subtitle_status in ("pending", "processing"):
        return True
    if episode.subtitle_status == "ready" and (episode.subtitle_url_es or episode.subtitle_url):
        logger.info("Subtitles already ready episode=%s", episode.id)
        return False
    return True


def run_media_pipeline(
    episode_id: int,
    *,
    run_hls: bool = True,
    run_subtitles: bool = True,
    force_subtitles: bool = False,
) -> None:
    """Run probe → HLS → subtitles sequentially; one R2 download per run."""
    from modules.streaming.services.audio_probe_episode import probe_episode_audio_from_path
    from modules.streaming.services.subtitles import generate_subtitles_for_episode
    from modules.streaming.services.video_processing import process_episode_hls

    ok, reason = pipeline_memory_ok()
    if not ok:
        logger.warning("Media pipeline aborted episode=%s: %s", episode_id, reason)
        episode = db.session.get(Episode, episode_id)
        if episode:
            if run_hls and episode.processing_status in ("pending", "processing"):
                episode.processing_status = "ready"
                episode.processing_error = (
                    "Procesamiento pospuesto: memoria insuficiente en el servidor. "
                    "Reintenta más tarde o desactiva HLS en instancias de 512MB."
                )
            if run_subtitles and episode.subtitle_status in ("pending", "processing"):
                episode.subtitle_status = "skipped"
            db.session.commit()
        return

    episode = db.session.get(Episode, episode_id)
    if not episode or not episode.video_url_r2:
        return

    shared_tmp = Path(tempfile.mkdtemp(prefix=f"fp-pipe-{episode_id}-"))
    source_parent: Path | None = None
    source_path: Path | None = None

    try:
        source_path = _materialize_source(episode, shared_tmp)
        if source_path.parent == shared_tmp:
            source_parent = shared_tmp
        elif source_path.parent.name.startswith("hls-src-"):
            source_parent = source_path.parent

        log_memory("before_audio_probe", episode_id=episode_id)
        probe_episode_audio_from_path(episode, source_path)
        db.session.commit()
        log_memory("after_audio_probe", episode_id=episode_id)

        if run_hls:
            log_memory("before_ffmpeg_hls", episode_id=episode_id)
            process_episode_hls(episode_id, source_path=source_path)
            log_memory("after_ffmpeg_hls", episode_id=episode_id)
            gc.collect()

        if run_subtitles:
            episode = db.session.get(Episode, episode_id)
            if episode and _should_run_subtitles(episode, force=force_subtitles):
                log_memory("before_whisper", episode_id=episode_id)
                generate_subtitles_for_episode(episode_id, source_path=source_path)
                log_memory("after_whisper", episode_id=episode_id)
                gc.collect()
    finally:
        shutil.rmtree(shared_tmp, ignore_errors=True)
        if source_parent and source_parent != shared_tmp:
            shutil.rmtree(source_parent, ignore_errors=True)
        gc.collect()
        log_memory("pipeline_done", episode_id=episode_id)


def enqueue_media_pipeline(
    episode_id: int,
    *,
    run_hls: bool = True,
    run_subtitles: bool = True,
    force_subtitles: bool = False,
) -> bool:
    """Queue sequential HLS → subtitles without blocking the request worker."""
    episode = db.session.get(Episode, episode_id)
    if not episode or not episode.video_url_r2:
        return False

    with _LOCK:
        if episode_id in _ACTIVE:
            logger.info("Media pipeline already active episode=%s", episode_id)
            return False
        _ACTIVE.add(episode_id)
        _ACTIVE_SINCE[episode_id] = time.monotonic()

    _purge_stale_active()

    if run_hls:
        from modules.streaming.services.video_processing import hls_processing_enabled

        if not hls_processing_enabled():
            episode.processing_status = "ready"
            db.session.commit()
            run_hls = False

    if run_subtitles and not force_subtitles:
        from modules.streaming.services.subtitles import prerequisites_ok

        ok, _reason = prerequisites_ok()
        if not ok:
            run_subtitles = False

    if not run_hls and not run_subtitles:
        with _LOCK:
            _ACTIVE.discard(episode_id)
            _ACTIVE_SINCE.pop(episode_id, None)
        return False

    if run_hls:
        episode.processing_status = "pending"
    if run_subtitles:
        episode.subtitle_status = "pending"
    db.session.commit()

    app = current_app._get_current_object()
    defer_s = int(current_app.config.get("MEDIA_PIPELINE_DEFER_SECONDS", 15))
    use_subprocess = _use_subprocess_worker()

    def _finish() -> None:
        with _LOCK:
            _ACTIVE.discard(episode_id)
            _ACTIVE_SINCE.pop(episode_id, None)

    def _run_in_process() -> None:
        if defer_s > 0:
            time.sleep(defer_s)
        with app.app_context():
            try:
                run_media_pipeline(
                    episode_id,
                    run_hls=run_hls,
                    run_subtitles=run_subtitles,
                    force_subtitles=force_subtitles,
                )
            except Exception:
                logger.exception("Media pipeline failed episode=%s", episode_id)
            finally:
                _finish()

    def _run_subprocess_supervisor() -> None:
        if defer_s > 0:
            time.sleep(defer_s)
        with app.app_context():
            ok, reason = pipeline_memory_ok()
            if not ok:
                logger.warning(
                    "Media worker not started episode=%s: %s",
                    episode_id,
                    reason,
                )
                run_media_pipeline(
                    episode_id,
                    run_hls=run_hls,
                    run_subtitles=run_subtitles,
                    force_subtitles=force_subtitles,
                )
                _finish()
                return
            log_memory("before_media_subprocess", episode_id=episode_id)
        proc: subprocess.Popen[bytes] | None = None
        try:
            proc = _spawn_pipeline_subprocess(
                episode_id,
                run_hls=run_hls,
                run_subtitles=run_subtitles,
                force_subtitles=force_subtitles,
            )
            exit_code = proc.wait()
            if exit_code != 0:
                logger.error(
                    "Media worker exited episode=%s code=%s",
                    episode_id,
                    exit_code,
                )
        except Exception:
            logger.exception("Media worker subprocess failed episode=%s", episode_id)
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=10)
        finally:
            with app.app_context():
                log_memory("after_media_subprocess", episode_id=episode_id)
            _finish()

    target = _run_subprocess_supervisor if use_subprocess else _run_in_process
    threading.Thread(
        target=target,
        name=f"media-pipe-{episode_id}",
        daemon=True,
    ).start()
    return True
