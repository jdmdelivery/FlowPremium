import uuid
from pathlib import Path

from flask import current_app
from PIL import Image
from werkzeug.datastructures import FileStorage


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


def delete_episode_video(episode) -> None:
    from modules.storage.storage_r2 import delete_object

    if not episode.video_url:
        return
    if is_local_media_url(episode.video_url):
        delete_storage_file(episode.video_url)
    else:
        delete_object(episode.video_url)


def delete_episode_thumbnail(episode) -> None:
    from modules.storage.storage_r2 import delete_object

    if not episode.thumbnail_url:
        return
    if is_local_media_url(episode.thumbnail_url):
        delete_storage_file(episode.thumbnail_url)
    else:
        delete_object(episode.thumbnail_url)


def delete_episode_media(episode) -> None:
    delete_episode_video(episode)
    delete_episode_thumbnail(episode)


def save_episode_video(file: FileStorage, series_id: int | None = None) -> str:
    """Upload video and return URL/key stored in video_url."""
    if use_r2_storage():
        from modules.storage.storage_r2 import upload_video

        return upload_video(file, series_id=series_id)
    return save_video(file, series_id=series_id)


def save_episode_thumbnail(file: FileStorage, series_id: int | None = None) -> str:
    """Upload thumbnail and return URL/key stored in thumbnail_url."""
    if use_r2_storage():
        from modules.storage.storage_r2 import upload_thumbnail

        return upload_thumbnail(file, series_id=series_id)
    return save_image(file, kind="thumbnail", entity_id=series_id)


def save_video(file: FileStorage, series_id: int | None = None) -> str:
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
        folder = Path(current_app.config["THUMBNAIL_FOLDER"])
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

    img = Image.open(file.stream)
    img.verify()
    file.stream.seek(0)
    img = Image.open(file.stream)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(dest, optimize=True, quality=85)
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
