import uuid
from pathlib import Path

from flask import current_app
from werkzeug.datastructures import FileStorage

from utils.runtime_env import must_use_r2_storage


def _allowed(filename: str, allowed: set[str]) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in allowed


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _relative_path(full: Path) -> str:
    return str(full.relative_to(current_app.root_path)).replace("\\", "/")


def use_r2_storage() -> bool:
    from modules.storage.storage_r2 import use_r2_storage as _use_r2

    return _use_r2()


def is_local_media_url(value: str | None) -> bool:
    return bool(value and value.startswith("storage/"))


def _require_r2_for_episode_media() -> None:
    if not must_use_r2_storage():
        return
    from modules.storage.storage_r2 import is_r2_configured

    if not is_r2_configured():
        raise ValueError(
            "Cloudflare R2 es obligatorio en producción. "
            "Configura STORAGE_PROVIDER=r2 y las variables R2 en Render."
        )


def _delete_media_key(url: str | None) -> None:
    from modules.storage.storage_r2 import delete_object

    if not url:
        return
    if is_local_media_url(url):
        delete_storage_file(url)
    else:
        delete_object(url)


def delete_episode_video(episode) -> None:
    _delete_media_key(episode.video_url_r2)
    _delete_media_key(episode.video_url_r2_en)


def delete_episode_primary_video(episode) -> None:
    _delete_media_key(episode.video_url_r2)


def delete_episode_hls(episode) -> None:
    from modules.storage.storage_r2 import delete_object

    if not episode.hls_url_r2:
        return
    if is_local_media_url(episode.hls_url_r2):
        delete_storage_file(episode.hls_url_r2)
    else:
        delete_object(episode.hls_url_r2)


def delete_episode_thumbnail(episode) -> None:
    from modules.storage.storage_r2 import delete_object

    if not episode.thumbnail_url:
        return
    if is_local_media_url(episode.thumbnail_url):
        delete_storage_file(episode.thumbnail_url)
    else:
        delete_object(episode.thumbnail_url)


def delete_episode_subtitle_lang(episode, lang: str) -> None:
    """Remove subtitle file(s) for one language."""
    import json

    from modules.streaming.services.episode_media import get_subtitle_storage_key
    from modules.streaming.services.languages import normalize_lang_code

    code = normalize_lang_code(lang) or "es"
    key = get_subtitle_storage_key(episode, code)
    if key:
        _delete_media_key(key)

    if code == "es":
        episode.subtitle_url = None
        episode.subtitle_url_es = None
    elif code == "en":
        episode.subtitle_url_en = None

    tracks = []
    if episode.subtitle_tracks:
        try:
            tracks = json.loads(episode.subtitle_tracks)
        except json.JSONDecodeError:
            tracks = []
    if isinstance(tracks, list):
        tracks = [
            item
            for item in tracks
            if not (
                isinstance(item, dict)
                and normalize_lang_code(item.get("lang") or item.get("language")) == code
            )
        ]
        episode.subtitle_tracks = json.dumps(tracks, ensure_ascii=False) if tracks else None


def delete_episode_subtitles(episode) -> None:
    """Remove all subtitle files for an episode."""
    from modules.streaming.services.languages import AUTO_TRANSLATE_SUBTITLE_CODES

    for lang in ("es", *AUTO_TRANSLATE_SUBTITLE_CODES):
        delete_episode_subtitle_lang(episode, lang)


def delete_episode_subtitle(episode) -> None:
    delete_episode_subtitles(episode)


def save_subtitle_vtt(
    content: str, series_id: int, episode_id: int, lang: str = "es"
) -> str:
    """Persist WebVTT; returns storage key or local relative path."""
    safe_lang = (lang or "es").lower()[:8]
    if use_r2_storage():
        from modules.storage.storage_r2 import upload_subtitle_vtt

        return upload_subtitle_vtt(content, series_id, episode_id, lang=safe_lang)

    folder = (
        Path(current_app.config["UPLOAD_FOLDER"])
        / "subtitles"
        / str(series_id)
        / str(episode_id)
    )
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"subtitle_{safe_lang}.vtt"
    dest.write_text(content, encoding="utf-8")
    return _relative_path(dest)


def delete_episode_media(episode) -> None:
    delete_episode_video(episode)
    delete_episode_hls(episode)
    delete_episode_thumbnail(episode)
    delete_episode_subtitles(episode)


def delete_series_media(series) -> None:
    from modules.storage.storage_r2 import delete_object

    for field in (series.hero_image_url, series.thumbnail_url):
        if not field:
            continue
        if is_local_media_url(field):
            delete_storage_file(field)
        else:
            delete_object(field)
    if series.cover_image and is_local_media_url(series.cover_image):
        delete_storage_file(series.cover_image)


def save_series_cover(file: FileStorage, series_id: int) -> tuple[str, str]:
    """Upload series cover to R2; returns (hero_image_url, thumbnail_url) keys."""
    _require_r2_for_episode_media()
    if use_r2_storage():
        from modules.storage.storage_r2 import upload_series_image

        key = upload_series_image(file, series_id=series_id, kind="hero")
        return key, key
    path = save_image(file, kind="series", entity_id=series_id)
    return path, path


def save_subtitle_file(
    file: FileStorage, series_id: int, episode_id: int, lang: str = "es"
) -> tuple[str, str]:
    """Save .vtt or convert .srt → .vtt. Returns (storage_key, vtt_content)."""
    if not file or not file.filename:
        raise ValueError("No subtitle file provided")
    ext = file.filename.rsplit(".", 1)[-1].lower()
    raw = file.read()
    if ext == "srt":
        from utils.srt import srt_to_vtt

        content = srt_to_vtt(raw.decode("utf-8-sig", errors="replace"))
    elif ext == "vtt":
        content = raw.decode("utf-8-sig", errors="replace")
        if not content.strip().upper().startswith("WEBVTT"):
            raise ValueError("El archivo VTT no es válido")
    else:
        raise ValueError("Formato no soportado. Usa .vtt o .srt")
    key = save_subtitle_vtt(content, series_id, episode_id, lang=lang)
    return key, content


def save_episode_audio_track(
    file: FileStorage, series_id: int, episode_id: int, lang: str
) -> str:
    """Upload additional language audio (MP4) for an episode."""
    safe_lang = (lang or "es").lower()[:8]
    return save_episode_video(file, series_id=series_id, lang=f"audio_{episode_id}_{safe_lang}")


def save_episode_video(
    file: FileStorage, series_id: int | None = None, lang: str = "es"
) -> str:
    """Upload video to R2 only in production; local path only for dev tests."""
    _require_r2_for_episode_media()
    if use_r2_storage():
        from modules.storage.storage_r2 import upload_video

        return upload_video(file, series_id=series_id, lang=lang)
    return save_video(file, series_id=series_id, lang=lang)


def save_episode_hls(file: FileStorage, series_id: int, episode_id: int) -> str:
    if not file or not file.filename:
        raise ValueError("No HLS playlist provided")
    if not file.filename.lower().endswith(".m3u8"):
        raise ValueError("HLS master must be a .m3u8 file")
    content = file.read().decode("utf-8", errors="replace")
    if use_r2_storage():
        from modules.storage.storage_r2 import upload_hls_playlist

        return upload_hls_playlist(content, series_id, episode_id)
    folder = Path(current_app.config["UPLOAD_FOLDER"]) / "hls" / str(series_id) / str(episode_id)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "master.m3u8"
    dest.write_text(content, encoding="utf-8")
    return _relative_path(dest)


def save_episode_thumbnail(file: FileStorage, series_id: int | None = None) -> str:
    _require_r2_for_episode_media()
    if use_r2_storage():
        from modules.storage.storage_r2 import upload_thumbnail

        return upload_thumbnail(file, series_id=series_id)
    return save_image(file, kind="thumbnail", entity_id=series_id)


def save_payment_screenshot(file: FileStorage, payment_id: int | None = None) -> str:
    if not file or not file.filename:
        raise ValueError("No screenshot provided")
    if use_r2_storage():
        from modules.storage.storage_r2 import upload_payment_screenshot

        return upload_payment_screenshot(file, payment_id=payment_id)
    return save_image(file, kind="payment", entity_id=payment_id)


def save_video(file: FileStorage, series_id: int | None = None, lang: str = "es") -> str:
    if must_use_r2_storage():
        raise ValueError("Los videos no se guardan en el servidor. Usa Cloudflare R2.")
    if not file or not file.filename:
        raise ValueError("No video file provided")
    if not _allowed(file.filename, current_app.config["ALLOWED_VIDEO_EXTENSIONS"]):
        raise ValueError("Invalid video format. Allowed: mp4, webm, ogg")

    max_size = current_app.config.get("MAX_VIDEO_SIZE", 500 * 1024 * 1024)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > max_size:
        mb = max_size // (1024 * 1024)
        raise ValueError(f"Video too large. Maximum size is {mb} MB on this server.")

    folder = Path(current_app.config["VIDEO_FOLDER"])
    if series_id:
        folder = folder / str(series_id)
        if lang and lang != "es":
            folder = folder / lang
    _ensure_dir(folder)
    ext = file.filename.rsplit(".", 1)[1].lower()
    name = f"{uuid.uuid4().hex}.{ext}"
    dest = folder / name
    file.save(dest)
    return _relative_path(dest)


def save_image(
    file: FileStorage,
    kind: str = "cover",
    entity_id: int | None = None,
) -> str:
    if not file or not file.filename:
        raise ValueError("No image file provided")
    if not _allowed(file.filename, current_app.config["ALLOWED_IMAGE_EXTENSIONS"]):
        raise ValueError("Invalid image format. Allowed: jpg, png, webp, gif")

    if kind == "series":
        folder = Path(current_app.config["SERIES_COVER_FOLDER"])
        if entity_id:
            folder = folder / str(entity_id)
    elif kind == "thumbnail":
        if must_use_r2_storage():
            raise ValueError("Las miniaturas de episodio deben subirse a Cloudflare R2.")
        folder = Path(current_app.config["THUMBNAIL_FOLDER"])
        if entity_id:
            folder = folder / str(entity_id)
    elif kind == "payment":
        folder = Path(current_app.config["UPLOAD_FOLDER"]) / "payments"
        if entity_id:
            folder = folder / str(entity_id)
    else:
        folder = Path(current_app.config["THUMBNAIL_FOLDER"])

    _ensure_dir(folder)
    ext = file.filename.rsplit(".", 1)[1].lower()
    if ext == "jpeg":
        ext = "jpg"
    name = f"{uuid.uuid4().hex}.{ext}"
    dest = folder / name

    from utils.image_io import save_image_to_path

    save_image_to_path(file.stream, dest)
    return _relative_path(dest)


def resolve_storage_path(relative_path: str) -> Path:
    if not relative_path:
        raise ValueError("Empty path")
    full = (Path(current_app.root_path) / relative_path).resolve()
    storage_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    if not str(full).startswith(str(storage_root)):
        raise ValueError("Invalid storage path")
    if not full.is_file():
        raise FileNotFoundError("File not found")
    return full


def delete_storage_file(relative_path: str) -> bool:
    if not relative_path:
        return False
    try:
        full = resolve_storage_path(relative_path)
    except (ValueError, FileNotFoundError):
        return False
    if full.is_file():
        full.unlink()
        return True
    return False
