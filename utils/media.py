"""Resolve local paths and R2 keys to browser-ready URLs."""

from __future__ import annotations


def media_url(stored: str | None) -> str | None:
    """Turn DB value (local path, R2 key, or full URL) into a public URL."""
    if not stored:
        return None
    if stored.startswith("http://") or stored.startswith("https://"):
        return stored
    if stored.startswith("storage/"):
        return f"/media/{stored}"
    from modules.storage.storage_r2 import get_playback_url

    return get_playback_url(stored)
