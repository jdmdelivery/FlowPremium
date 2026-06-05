"""Episode media keys, admin language sync, and file existence checks."""

from __future__ import annotations

import json
import logging
from typing import Any

from modules.streaming.models import Episode
from modules.streaming.services.languages import (
    LANG_BY_CODE,
    LANG_BY_NAME,
    SUPPORTED_LANGUAGE_NAMES,
    normalize_lang_code,
    parse_admin_language_list,
)
from modules.streaming.upload import is_local_media_url, resolve_storage_path

logger = logging.getLogger(__name__)

LEGACY_AUDIO_KEYS = {
    "es": "video_url_r2",
    "en": "video_url_r2_en",
}


def _loads_json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def media_file_exists(key: str | None) -> bool:
    if not key:
        return False
    if key.startswith("http://") or key.startswith("https://"):
        return True
    if is_local_media_url(key):
        try:
            resolve_storage_path(key)
            return True
        except (ValueError, FileNotFoundError):
            return False
    try:
        from modules.storage.storage_r2 import is_r2_configured, object_head_meta, use_r2_storage

        if use_r2_storage() and is_r2_configured():
            object_head_meta(key)
            return True
    except Exception:
        logger.debug("R2 head failed for %s", key, exc_info=True)
        return False
    return False


def get_extra_audio_keys(episode: Episode) -> dict[str, str]:
    """Non-legacy audio storage keys from audio_tracks JSON."""
    tracks = _loads_json(episode.audio_tracks, [])
    out: dict[str, str] = {}
    if not isinstance(tracks, list):
        return out
    for item in tracks:
        if not isinstance(item, dict):
            continue
        code = normalize_lang_code(item.get("lang") or item.get("language"))
        key = item.get("key") or item.get("storage_key")
        if code and key and code not in LEGACY_AUDIO_KEYS:
            out[code] = key
    return out


def get_audio_storage_key(episode: Episode, code: str) -> str | None:
    code = normalize_lang_code(code) or ""
    if not code:
        return None
    legacy_field = LEGACY_AUDIO_KEYS.get(code)
    if legacy_field:
        value = getattr(episode, legacy_field, None)
        if value:
            return value
    return get_extra_audio_keys(episode).get(code)


def get_subtitle_storage_keys(episode: Episode) -> dict[str, str]:
    tracks = _loads_json(episode.subtitle_tracks, [])
    out: dict[str, str] = {}
    if isinstance(tracks, list):
        for item in tracks:
            if not isinstance(item, dict):
                continue
            code = normalize_lang_code(item.get("lang") or item.get("language"))
            key = item.get("key") or item.get("storage_key")
            if code and key:
                out[code] = key
    if episode.subtitle_url_es or episode.subtitle_url:
        out.setdefault("es", episode.subtitle_url_es or episode.subtitle_url or "")
    if episode.subtitle_url_en:
        out.setdefault("en", episode.subtitle_url_en)
    return {k: v for k, v in out.items() if v}


def get_subtitle_storage_key(episode: Episode, code: str) -> str | None:
    code = normalize_lang_code(code) or ""
    if not code:
        return None
    keys = get_subtitle_storage_keys(episode)
    return keys.get(code)


def get_admin_audio_languages(episode: Episode) -> list[str]:
    stored = parse_admin_language_list(_loads_json(episode.audio_languages, []))
    if stored:
        return stored
    langs: list[str] = []
    if episode.video_url_r2:
        langs.append(LANG_BY_CODE["es"]["name"])
    if episode.video_url_r2_en:
        langs.append(LANG_BY_CODE["en"]["name"])
    return langs


def get_admin_subtitle_languages(episode: Episode) -> list[str]:
    stored = parse_admin_language_list(_loads_json(episode.subtitle_languages, []))
    if stored:
        return stored
    keys = get_subtitle_storage_keys(episode)
    if keys and episode.subtitle_status == "ready":
        from modules.streaming.services.languages import SUPPORTED_LANGUAGE_CODES

        return [
            LANG_BY_CODE[code]["name"]
            for code in SUPPORTED_LANGUAGE_CODES
            if code in keys
        ]
    if episode.has_subtitles:
        return [LANG_BY_CODE["es"]["name"]]
    legacy = _loads_json(episode.subtitle_langs, [])
    if isinstance(legacy, list):
        names = []
        for code in legacy:
            item = LANG_BY_CODE.get(str(code).lower()[:2])
            if item:
                names.append(item["name"])
        return names
    return []


def sync_episode_track_metadata(episode: Episode) -> None:
    """Rebuild audio_tracks / subtitle_tracks JSON from admin selections + real files."""
    audio_langs = get_admin_audio_languages(episode)
    episode.audio_languages = json.dumps(audio_langs, ensure_ascii=False)

    audio_out: list[dict[str, Any]] = []
    for name in audio_langs:
        code = LANG_BY_NAME[name]["code"]
        key = get_audio_storage_key(episode, code)
        if not key:
            continue
        exists = media_file_exists(key)
        audio_out.append(
            {
                "language": name,
                "label": name,
                "lang": code,
                "key": key,
                "available": exists,
            }
        )
    episode.audio_tracks = json.dumps(audio_out, ensure_ascii=False)

    subtitle_langs = get_admin_subtitle_languages(episode)
    episode.subtitle_languages = json.dumps(subtitle_langs, ensure_ascii=False)

    subtitle_out: list[dict[str, Any]] = []
    for name in subtitle_langs:
        code = LANG_BY_NAME[name]["code"]
        key = get_subtitle_storage_key(episode, code)
        if not key:
            continue
        exists = media_file_exists(key)
        from modules.streaming.services.languages import player_subtitle_label

        stream_path = f"/api/streaming/subtitles/{episode.id}?lang={code}"
        subtitle_out.append(
            {
                "language": name,
                "label": player_subtitle_label(code),
                "lang": code,
                "key": key,
                "url": stream_path,
                "available": exists,
            }
        )
    episode.subtitle_tracks = json.dumps(subtitle_out, ensure_ascii=False)


def set_extra_audio_key(episode: Episode, code: str, key: str) -> None:
    code = normalize_lang_code(code) or ""
    if not code or code in LEGACY_AUDIO_KEYS:
        return
    tracks = _loads_json(episode.audio_tracks, [])
    if not isinstance(tracks, list):
        tracks = []
    replaced = False
    for item in tracks:
        if isinstance(item, dict) and normalize_lang_code(item.get("lang") or item.get("language")) == code:
            item["key"] = key
            item["lang"] = code
            item["language"] = LANG_BY_CODE[code]["name"]
            item["label"] = LANG_BY_CODE[code]["name"]
            replaced = True
            break
    if not replaced:
        tracks.append(
            {
                "lang": code,
                "language": LANG_BY_CODE[code]["name"],
                "label": LANG_BY_CODE[code]["name"],
                "key": key,
            }
        )
    episode.audio_tracks = json.dumps(tracks, ensure_ascii=False)


def set_subtitle_key(episode: Episode, code: str, key: str) -> None:
    code = normalize_lang_code(code) or ""
    if not code:
        return
    if code == "es":
        episode.subtitle_url_es = key
        episode.subtitle_url = key
    elif code == "en":
        episode.subtitle_url_en = key

    tracks = _loads_json(episode.subtitle_tracks, [])
    if not isinstance(tracks, list):
        tracks = []
    replaced = False
    for item in tracks:
        if isinstance(item, dict) and normalize_lang_code(item.get("lang") or item.get("language")) == code:
            item["key"] = key
            item["lang"] = code
            item["language"] = LANG_BY_CODE[code]["name"]
            item["label"] = LANG_BY_CODE[code]["name"]
            replaced = True
            break
    if not replaced:
        tracks.append(
            {
                "lang": code,
                "language": LANG_BY_CODE[code]["name"],
                "label": LANG_BY_CODE[code]["name"],
                "key": key,
            }
        )
    episode.subtitle_tracks = json.dumps(tracks, ensure_ascii=False)

    episode.subtitle_langs = json.dumps(
        sorted(get_subtitle_storage_keys(episode).keys()),
        ensure_ascii=False,
    )


def admin_language_checkbox_values() -> list[dict[str, str]]:
    from modules.streaming.services.languages import SUPPORTED_LANGUAGES

    return [{"code": item["code"], "name": item["name"]} for item in SUPPORTED_LANGUAGES]
