"""HTTP Range parsing and chunk clamping for video streaming."""

from __future__ import annotations

import re

# Max bytes per single 206 response (prevents Render OOM on bytes=0-).
DEFAULT_STREAM_CHUNK = 2 * 1024 * 1024

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def parse_range_header(range_header: str, file_size: int) -> tuple[int, int] | None:
    match = _RANGE_RE.match((range_header or "").strip())
    if not match:
        return None
    start_s, end_s = match.group(1), match.group(2)
    byte_start = int(start_s) if start_s else 0
    byte_end = int(end_s) if end_s else file_size - 1
    byte_end = min(byte_end, file_size - 1)
    if byte_start > byte_end or byte_start >= file_size:
        return None
    return byte_start, byte_end


def clamp_byte_range(
    file_size: int,
    range_header: str | None,
    *,
    max_chunk: int = DEFAULT_STREAM_CHUNK,
) -> tuple[int, int, str]:
    """
    Resolve client Range to a bounded range for one response.
    bytes=0- on a 31MB file → bytes=0-2097151 (2MB), not the full object.
    """
    if file_size <= 0:
        raise ValueError("empty file")

    if range_header:
        parsed = parse_range_header(range_header, file_size)
        if not parsed:
            raise ValueError("invalid range")
        byte_start, byte_end = parsed
    else:
        byte_start = 0
        byte_end = file_size - 1

    if byte_end - byte_start + 1 > max_chunk:
        byte_end = byte_start + max_chunk - 1

    upstream = f"bytes={byte_start}-{byte_end}"
    return byte_start, byte_end, upstream
