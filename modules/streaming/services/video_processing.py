"""Background MP4 → HLS transcoding (FFmpeg). Does not block upload requests."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import current_app

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.services.memory_diagnostics import is_low_ram_instance, log_memory
from modules.streaming.upload import is_local_media_url, resolve_storage_path

logger = logging.getLogger(__name__)

_MAX_PROCESSING_ERROR_LEN = 50_000

# (target_height, bandwidth, max_width, max_height) — scale keeps even dimensions.
QUALITY_PRESETS: tuple[tuple[int, int, int, int], ...] = (
    (480, 1_000_000, 854, 480),
    (720, 2_500_000, 1280, 720),
    (1080, 5_000_000, 1920, 1080),
)


def ffmpeg_path() -> str:
    custom = (current_app.config.get("FFMPEG_PATH") or "").strip()
    if custom:
        return custom
    found = shutil.which("ffmpeg")
    return found or "ffmpeg"


def ffprobe_video_height(path: Path) -> int:
    cmd = [
        shutil.which("ffprobe") or "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=height",
        "-of",
        "csv=p=0",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        return int(out.split("\n")[0]) if out else 0
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return 0


def hls_processing_enabled() -> bool:
    return bool(current_app.config.get("VIDEO_HLS_PROCESSING_ENABLED", True))


def _resolve_local_video(episode: Episode) -> Path:
    key = episode.video_url_r2
    if not key:
        raise ValueError("No source video")
    if is_local_media_url(key):
        return resolve_storage_path(key)
    from modules.storage.storage_r2 import download_object_to_path

    tmp = Path(tempfile.mkdtemp(prefix=f"hls-src-{episode.id}-"))
    return download_object_to_path(key, tmp / "source.mp4")


def _upload_hls_tree(local_dir: Path, series_id: int, episode_id: int) -> tuple[str, list[dict]]:
    from modules.streaming.upload import use_r2_storage

    prefix = f"hls/{series_id}/{episode_id}"
    qualities: list[dict] = []

    if use_r2_storage():
        from modules.storage.storage_r2 import upload_hls_tree

        master_key, qualities = upload_hls_tree(local_dir, prefix)
        return master_key, qualities

    from flask import current_app as app

    dest_root = Path(app.config["UPLOAD_FOLDER"]) / "hls" / str(series_id) / str(episode_id)
    if dest_root.exists():
        shutil.rmtree(dest_root, ignore_errors=True)
    shutil.copytree(local_dir, dest_root)

    master = dest_root / "master.m3u8"
    master_key = str(master.relative_to(app.root_path)).replace("\\", "/")
    for pl in sorted(dest_root.glob("v*/playlist.m3u8")):
        height = _height_from_playlist_name(pl.parent.name)
        if height:
            rel = str(pl.relative_to(app.root_path)).replace("\\", "/")
            qualities.append({"height": height, "url": rel, "label": f"{height}P"})
    return master_key, qualities


def _height_from_playlist_name(folder: str) -> int | None:
    mapping = {"v0": 480, "v1": 720, "v2": 1080}
    return mapping.get(folder)


class FFmpegError(RuntimeError):
    """Raised when ffmpeg exits with a non-zero status."""

    def __init__(
        self,
        message: str,
        *,
        stdout: str = "",
        stderr: str = "",
        cmd: list[str] | None = None,
        returncode: int | None = None,
    ) -> None:
        super().__init__(message)
        self.stdout = stdout or ""
        self.stderr = stderr or ""
        self.cmd = list(cmd or [])
        self.returncode = returncode


def _format_ffmpeg_error(err: FFmpegError) -> str:
    parts = [str(err)]
    if err.returncode is not None:
        parts[0] = f"ffmpeg exit code {err.returncode}"
    if err.cmd:
        parts.append(f"--- CMD ---\n{' '.join(err.cmd)}")
    if err.stderr:
        parts.append(f"--- STDERR ---\n{err.stderr}")
    if err.stdout:
        parts.append(f"--- STDOUT ---\n{err.stdout}")
    text = "\n\n".join(parts)
    if len(text) > _MAX_PROCESSING_ERROR_LEN:
        return text[:_MAX_PROCESSING_ERROR_LEN] + "\n\n... (truncated)"
    return text


def _even_scale_filter(max_width: int, max_height: int, *, escape_commas: bool = False) -> str:
    """
    Scale down preserving aspect ratio; width/height always divisible by 2 (libx264).
    escape_commas=True for filter_complex (commas separate filters).
    """
    comma = "\\," if escape_commas else ","
    ratio = f"min({max_width}/iw{comma}{max_height}/ih)"
    return f"trunc(iw*{ratio}/2)*2:trunc(ih*{ratio}/2)*2"


def _preset_for_height(height: int) -> tuple[int, int, int, int]:
    for preset in QUALITY_PRESETS:
        if preset[0] == height:
            return preset
    return (height, 1_000_000, 1280, height)


def _heights_for_source(source_height: int) -> list[int]:
    """Low-RAM instances encode 480p only; 720p optional via config."""
    max_h = max(source_height, 480)
    if is_low_ram_instance():
        heights = [480]
        if current_app.config.get("VIDEO_HLS_INCLUDE_720P", False) and max_h >= 720:
            heights.append(720)
        logger.info(
            "Low-RAM HLS mode heights=%s (VIDEO_HLS_INCLUDE_720P=%s)",
            heights,
            current_app.config.get("VIDEO_HLS_INCLUDE_720P", False),
        )
        return heights
    heights = [h for h, *_ in QUALITY_PRESETS if h <= max_h]
    return heights or [480]


def _run_ffmpeg(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ffmpeg in a subprocess; always terminate the child process."""
    logger.info("FFmpeg command: %s", " ".join(cmd))
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            logger.error("FFmpeg failed exit=%s", proc.returncode)
            logger.error("FFMPEG CMD: %s", " ".join(cmd))
            logger.error("FFMPEG STDOUT:\n%s", stdout)
            logger.error("FFMPEG STDERR:\n%s", stderr)
            raise FFmpegError(
                f"ffmpeg exited with code {proc.returncode}",
                stdout=stdout or "",
                stderr=stderr or "",
                cmd=cmd,
                returncode=proc.returncode,
            )
        if stdout:
            logger.debug("FFMPEG STDOUT:\n%s", stdout)
        if stderr:
            logger.debug("FFMPEG STDERR:\n%s", stderr)
        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def _write_master_playlist(output_dir: Path, heights: list[int]) -> None:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for idx, h in enumerate(heights):
        preset = _preset_for_height(h)
        max_w, max_h = preset[2], preset[3]
        lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={preset[1]},RESOLUTION={max_w}x{max_h}")
        lines.append(f"v{idx}/playlist.m3u8")
    (output_dir / "master.m3u8").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_ffmpeg_hls_single(input_path: Path, output_dir: Path, height: int, idx: int) -> None:
    preset = _preset_for_height(height)
    max_w, max_h = preset[2], preset[3]
    variant_dir = output_dir / f"v{idx}"
    variant_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_path(),
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"scale={_even_scale_filter(max_w, max_h)}",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_filename",
        str(variant_dir / "segment_%03d.ts"),
        str(variant_dir / "playlist.m3u8"),
    ]
    _run_ffmpeg(cmd)


def _run_ffmpeg_hls(input_path: Path, output_dir: Path, heights: list[int]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if is_low_ram_instance() and len(heights) > 1:
        for idx, h in enumerate(heights):
            log_memory("before_ffmpeg_hls_variant", extra=f"height={h}")
            _run_ffmpeg_hls_single(input_path, output_dir, h, idx)
            log_memory("after_ffmpeg_hls_variant", extra=f"height={h}")
        _write_master_playlist(output_dir, heights)
        return

    if len(heights) == 1:
        h = heights[0]
        preset = _preset_for_height(h)
        max_w, max_h = preset[2], preset[3]
        cmd = [
            ffmpeg_path(),
            "-y",
            "-i",
            str(input_path),
            "-vf",
            f"scale={_even_scale_filter(max_w, max_h)}",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-hls_time",
            "6",
            "-hls_playlist_type",
            "vod",
            "-hls_segment_filename",
            str(output_dir / "v0" / "segment_%03d.ts"),
            str(output_dir / "v0" / "playlist.m3u8"),
        ]
        (output_dir / "v0").mkdir(exist_ok=True)
        _run_ffmpeg(cmd)
        master = (
            "#EXTM3U\n#EXT-X-VERSION:3\n"
            f"#EXT-X-STREAM-INF:BANDWIDTH={preset[1]},RESOLUTION={max_w}x{max_h}\n"
            "v0/playlist.m3u8\n"
        )
        (output_dir / "master.m3u8").write_text(master, encoding="utf-8")
        return

    filters = []
    maps = []
    var_map = []
    for idx, h in enumerate(heights):
        preset = _preset_for_height(h)
        max_w, max_h = preset[2], preset[3]
        scale = _even_scale_filter(max_w, max_h, escape_commas=True)
        filters.append(f"[0:v]scale={scale}[v{idx}]")
        maps.extend(["-map", f"[v{idx}]", "-map", "0:a:0"])
        var_map.append(f"v:{idx},a:{idx},name:v{idx}")
        (output_dir / f"v{idx}").mkdir(exist_ok=True)

    cmd = [
        ffmpeg_path(),
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        ";".join(filters),
        *maps,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-var_stream_map",
        " ".join(var_map),
        "-master_pl_name",
        "master.m3u8",
        "-f",
        "hls",
        "-hls_time",
        "6",
        "-hls_playlist_type",
        "vod",
        "-hls_segment_filename",
        str(output_dir / "v%v" / "segment_%03d.ts"),
        str(output_dir / "v%v" / "playlist.m3u8"),
    ]
    _run_ffmpeg(cmd)


def process_episode_hls(episode_id: int, *, source_path: Path | None = None) -> None:
    episode = db.session.get(Episode, episode_id)
    if not episode or not episode.video_url_r2:
        return

    episode.processing_status = "processing"
    episode.processing_error = None
    db.session.commit()

    tmp_root = Path(tempfile.mkdtemp(prefix=f"hls-job-{episode_id}-"))
    source_parent: Path | None = None
    owns_source_parent = False
    try:
        if source_path and source_path.is_file():
            source = source_path
        else:
            source = _resolve_local_video(episode)
            source_parent = source.parent
            owns_source_parent = source_parent.name.startswith("hls-src-")

        if not source.is_file():
            raise FileNotFoundError("Source video missing")

        height = ffprobe_video_height(source)
        heights = _heights_for_source(height)

        out_dir = tmp_root / "out"
        log_memory("before_ffmpeg_hls_encode", episode_id=episode_id, extra=f"heights={heights}")
        _run_ffmpeg_hls(source, out_dir, heights)
        log_memory("after_ffmpeg_hls_encode", episode_id=episode_id)

        master_key, qualities = _upload_hls_tree(out_dir, episode.series_id, episode.id)
        episode.hls_url_r2 = master_key
        episode.hls_master_url = master_key
        episode.qualities = json.dumps(qualities, ensure_ascii=False)
        episode.processing_status = "ready"
        episode.processing_error = None
        db.session.commit()
        logger.info("HLS ready episode=%s master=%s qualities=%s", episode_id, master_key, qualities)
        import gc

        gc.collect()
        log_memory("after_hls_commit", episode_id=episode_id)
    except FFmpegError as exc:
        error_detail = _format_ffmpeg_error(exc)
        logger.error("HLS FFmpeg error episode=%s\n%s", episode_id, error_detail)
        episode = db.session.get(Episode, episode_id)
        if episode:
            episode.processing_status = "failed"
            episode.processing_error = error_detail
            db.session.commit()
    except Exception as exc:
        logger.exception("HLS processing failed episode=%s", episode_id)
        episode = db.session.get(Episode, episode_id)
        if episode:
            episode.processing_status = "failed"
            detail = str(exc)
            if len(detail) > _MAX_PROCESSING_ERROR_LEN:
                detail = detail[:_MAX_PROCESSING_ERROR_LEN] + "\n\n... (truncated)"
            episode.processing_error = detail
            db.session.commit()
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        if owns_source_parent and source_parent:
            shutil.rmtree(source_parent, ignore_errors=True)


def enqueue_hls_job(episode_id: int) -> bool:
    """HLS only (legacy); prefer enqueue_media_pipeline for sequential processing."""
    if not hls_processing_enabled():
        episode = db.session.get(Episode, episode_id)
        if episode:
            episode.processing_status = "ready"
            db.session.commit()
        return False

    if not shutil.which(ffmpeg_path()) and ffmpeg_path() == "ffmpeg":
        logger.info("ffmpeg not found — skipping HLS for episode %s", episode_id)
        episode = db.session.get(Episode, episode_id)
        if episode:
            episode.processing_status = "failed"
            episode.processing_error = "ffmpeg no instalado — reproducción MP4 solamente"
            db.session.commit()
        return False

    from modules.streaming.services.media_pipeline import enqueue_media_pipeline

    return enqueue_media_pipeline(episode_id, run_hls=True, run_subtitles=False)
