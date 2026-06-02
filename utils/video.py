"""MP4 helpers for mobile-friendly streaming."""

from __future__ import annotations

from werkzeug.datastructures import FileStorage


def mp4_likely_faststart(file_obj, sample_size: int = 1024 * 1024) -> bool:
    """
    Return True if moov appears before mdat in the first chunk (faststart / web optimized).
  Unknown layout returns True to avoid false positives.
    """
    pos = file_obj.tell()
    try:
        file_obj.seek(0)
        head = file_obj.read(sample_size)
    finally:
        file_obj.seek(pos)

    if not head or b"ftyp" not in head[:32]:
        return True

    moov = head.find(b"moov")
    mdat = head.find(b"mdat")
    if moov == -1 or mdat == -1:
        return True
    return moov < mdat


def warn_if_mp4_not_faststart(file: FileStorage) -> str | None:
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext != "mp4":
        return None
    if mp4_likely_faststart(file.stream):
        return None
    return (
        "Este MP4 no tiene faststart (moov al inicio). "
        "En iPhone/Android puede quedarse cargando. "
        "Re-exporta con: ffmpeg -i entrada.mp4 -movflags +faststart salida.mp4"
    )
