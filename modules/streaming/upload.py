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


def save_video(file: FileStorage, series_id: int | None = None) -> str:
    if not file or not file.filename:
        raise ValueError("No video file provided")
    if not _allowed(file.filename, current_app.config["ALLOWED_VIDEO_EXTENSIONS"]):
        raise ValueError("Invalid video format. Allowed: mp4, webm, ogg")

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
    """Delete a file under storage if it exists. Returns True if file was removed."""
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
