"""Detect audio streams in video files via ffprobe."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_LANG_LABELS = {
    "es": ("Español", "🇪🇸"),
    "spa": ("Español", "🇪🇸"),
    "en": ("English", "🇺🇸"),
    "eng": ("English", "🇺🇸"),
    "en-us": ("English", "🇺🇸"),
    "en-gb": ("English", "🇺🇸"),
}


def is_ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def _normalize_lang(tag: str | None) -> str:
    if not tag:
        return "und"
    code = tag.lower().strip().replace("_", "-")
    if code.startswith("es"):
        return "es"
    if code.startswith("en"):
        return "en"
    return code.split("-")[0] if "-" in code else code


def _label_for_lang(lang: str, index: int) -> tuple[str, str]:
    if lang in _LANG_LABELS:
        return _LANG_LABELS[lang]
    if lang == "und":
        return (f"Audio {index + 1}", "🔊")
    return (lang.upper(), "🔊")


def probe_audio_streams(video_path: Path) -> list[dict]:
    """
    Return embedded audio streams in an MP4/MKV file.
    Each item: {index, lang, label, flag, codec, channels}
    """
    if not is_ffprobe_available():
        return []
    if not video_path.is_file():
        return []

    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-select_streams",
        "a",
        str(video_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("ffprobe failed: %s", exc)
        return []

    if proc.returncode != 0:
        logger.warning("ffprobe error: %s", (proc.stderr or "")[-300:])
        return []

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return []

    streams = payload.get("streams") or []
    tracks = []
    for stream in streams:
        idx = stream.get("index", len(tracks))
        tags = stream.get("tags") or {}
        lang = _normalize_lang(tags.get("language") or tags.get("LANGUAGE"))
        label, flag = _label_for_lang(lang, len(tracks))
        tracks.append(
            {
                "index": idx,
                "lang": lang,
                "label": label,
                "flag": flag,
                "codec": stream.get("codec_name"),
                "channels": stream.get("channels"),
            }
        )
    return tracks
