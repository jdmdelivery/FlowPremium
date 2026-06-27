"""Pillow helpers that close image handles promptly."""

from __future__ import annotations

import io
from typing import BinaryIO

from PIL import Image


def image_to_bytesio(stream: BinaryIO, *, ext: str, quality: int = 85) -> io.BytesIO:
    """Decode upload stream to optimized image bytes; releases PIL handles."""
    stream.seek(0)
    with Image.open(stream) as probe:
        probe.verify()
    stream.seek(0)
    with Image.open(stream) as img:
        work = img.convert("RGB") if img.mode in ("RGBA", "P") else img
        buf = io.BytesIO()
        save_ext = "JPEG" if ext in ("jpg", "jpeg") else ext.upper()
        work.save(buf, format=save_ext, optimize=True, quality=quality)
        buf.seek(0)
        return buf


def save_image_to_path(stream: BinaryIO, dest_path, *, quality: int = 85) -> None:
    stream.seek(0)
    with Image.open(stream) as probe:
        probe.verify()
    stream.seek(0)
    with Image.open(stream) as img:
        work = img.convert("RGB") if img.mode in ("RGBA", "P") else img
        work.save(dest_path, optimize=True, quality=quality)
