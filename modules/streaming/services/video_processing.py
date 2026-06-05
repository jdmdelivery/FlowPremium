"""Background MP4 → HLS transcoding (FFmpeg). Does not block upload requests."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from flask import current_app

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.upload import is_local_media_url, resolve_storage_path

logger = logging.getLogger(__name__)

_ACTIVE_JOBS: set[int] = set()
_JOBS_LOCK = threading.Lock()

QUALITY_PRESETS: tuple[tuple[int, int, str], ...] = (
    (480, 1_000_000, "854x480"),
    (720, 2_500_000, "1280x720"),
    (1080, 5_000_000, "1920x1080"),
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


def _run_ffmpeg_hls(input_path: Path, output_dir: Path, heights: list[int]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if len(heights) == 1:
        h = heights[0]
        preset = next((p for p in QUALITY_PRESETS if p[0] == h), (h, 1_000_000, f"scale={h}:-2"))
        scale = preset[2] if "x" in preset[2] else f"-2:{h}"
        cmd = [
            ffmpeg_path(),
            "-y",
            "-i",
            str(input_path),
            "-vf",
            f"scale={scale}:force_original_aspect_ratio=decrease",
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
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        master = (
            "#EXTM3U\n#EXT-X-VERSION:3\n"
            f"#EXT-X-STREAM-INF:BANDWIDTH={preset[1]},RESOLUTION={preset[2]}\n"
            "v0/playlist.m3u8\n"
        )
        (output_dir / "master.m3u8").write_text(master, encoding="utf-8")
        return

    filters = []
    maps = []
    var_map = []
    for idx, h in enumerate(heights):
        preset = next((p for p in QUALITY_PRESETS if p[0] == h), (h, 1_000_000, f"{1280}x{h}"))
        filters.append(
            f"[0:v]scale={preset[2]}:force_original_aspect_ratio=decrease[v{idx}]"
        )
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
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def process_episode_hls(episode_id: int) -> None:
    episode = db.session.get(Episode, episode_id)
    if not episode or not episode.video_url_r2:
        return

    episode.processing_status = "processing"
    episode.processing_error = None
    db.session.commit()

    tmp_root = Path(tempfile.mkdtemp(prefix=f"hls-job-{episode_id}-"))
    source_parent: Path | None = None
    try:
        source = _resolve_local_video(episode)
        source_parent = source.parent
        if not source.is_file():
            raise FileNotFoundError("Source video missing")

        height = ffprobe_video_height(source)
        heights = [h for h, _, _ in QUALITY_PRESETS if h <= max(height, 480)]
        if not heights:
            heights = [480]

        out_dir = tmp_root / "out"
        _run_ffmpeg_hls(source, out_dir, heights)

        master_key, qualities = _upload_hls_tree(out_dir, episode.series_id, episode.id)
        episode.hls_url_r2 = master_key
        episode.hls_master_url = master_key
        episode.qualities = json.dumps(qualities, ensure_ascii=False)
        episode.processing_status = "ready"
        episode.processing_error = None
        db.session.commit()
        logger.info("HLS ready episode=%s master=%s qualities=%s", episode_id, master_key, qualities)
    except Exception as exc:
        logger.exception("HLS processing failed episode=%s", episode_id)
        episode = db.session.get(Episode, episode_id)
        if episode:
            episode.processing_status = "ready"
            episode.processing_error = str(exc)[:2000]
            db.session.commit()
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        if source_parent and source_parent.name.startswith("hls-src-"):
            shutil.rmtree(source_parent, ignore_errors=True)


def enqueue_hls_job(episode_id: int) -> bool:
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
            episode.processing_status = "ready"
            episode.processing_error = "ffmpeg no instalado — reproducción MP4 solamente"
            db.session.commit()
        return False

    with _JOBS_LOCK:
        if episode_id in _ACTIVE_JOBS:
            return False
        _ACTIVE_JOBS.add(episode_id)

    episode = db.session.get(Episode, episode_id)
    if not episode or not episode.video_url_r2:
        with _JOBS_LOCK:
            _ACTIVE_JOBS.discard(episode_id)
        return False

    episode.processing_status = "pending"
    db.session.commit()

    app = current_app._get_current_object()

    def _run() -> None:
        with app.app_context():
            try:
                process_episode_hls(episode_id)
            finally:
                with _JOBS_LOCK:
                    _ACTIVE_JOBS.discard(episode_id)

    threading.Thread(target=_run, name=f"hls-{episode_id}", daemon=True).start()
    return True
