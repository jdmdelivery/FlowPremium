"""Convert SubRip (.srt) subtitles to WebVTT."""

from __future__ import annotations

import re

_SRT_TIMESTAMP = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def _to_vtt_time(h: str, m: str, s: str, ms: str) -> str:
    return f"{h}:{m}:{s}.{ms}"


def srt_to_vtt(content: str) -> str:
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.split("\n")
    out = ["WEBVTT", ""]
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        if line.isdigit():
            continue
        match = _SRT_TIMESTAMP.match(line)
        if not match:
            continue
        start = _to_vtt_time(*match.groups()[0:4])
        end = _to_vtt_time(*match.groups()[4:8])
        cue_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            cue_lines.append(lines[i].strip())
            i += 1
        if cue_lines:
            out.append(f"{start} --> {end}")
            out.extend(cue_lines)
            out.append("")
    return "\n".join(out).strip() + "\n"
