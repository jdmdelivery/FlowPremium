"""Cloudflare R2 storage via S3-compatible API (boto3)."""

from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path
from typing import BinaryIO

from flask import current_app
from werkzeug.datastructures import FileStorage

logger = logging.getLogger(__name__)

VIDEO_CONTENT_TYPES = {
    "mp4": "video/mp4",
    "webm": "video/webm",
    "ogg": "video/ogg",
}
IMAGE_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}


def storage_provider() -> str:
    return (current_app.config.get("STORAGE_PROVIDER") or "local").lower()


def use_r2_storage() -> bool:
    from utils.runtime_env import must_use_r2_storage

    if must_use_r2_storage():
        return True
    return storage_provider() == "r2"


def is_r2_configured() -> bool:
    if not use_r2_storage():
        return False
    return all(
        [
            current_app.config.get("R2_ENDPOINT"),
            current_app.config.get("R2_ACCESS_KEY_ID"),
            current_app.config.get("R2_SECRET_ACCESS_KEY"),
            current_app.config.get("R2_BUCKET_NAME"),
        ]
    )


def _get_client():
    """Reuse one boto3 client per Flask app (bounded cache, not a growing leak)."""
    from flask import g, has_app_context

    if has_app_context():
        cached = getattr(g, "_r2_client", None)
        if cached is not None:
            return cached

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=current_app.config["R2_ENDPOINT"],
        aws_access_key_id=current_app.config["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=current_app.config["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(signature_version="s3v4", max_pool_connections=4),
    )
    if has_app_context():
        g._r2_client = client
    return client


def _bucket() -> str:
    return current_app.config["R2_BUCKET_NAME"]


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower()


def test_r2_connection() -> tuple[bool, str]:
    """Verify R2 credentials and bucket access."""
    if not use_r2_storage():
        return False, "STORAGE_PROVIDER no es R2"
    if not is_r2_configured():
        return False, "Faltan variables R2 (endpoint, keys o bucket)"
    try:
        client = _get_client()
        client.head_bucket(Bucket=_bucket())
        client.list_objects_v2(Bucket=_bucket(), MaxKeys=1)
        return True, "Conectado"
    except Exception as exc:
        logger.exception("R2 connection test failed")
        return False, f"Error de conexión: {exc}"


def get_storage_status() -> dict:
    """Status payload for /admin/storage-status."""
    from modules.db.diagnostics import get_catalog_counts

    bucket = current_app.config.get("R2_BUCKET_NAME") or ""
    configured = is_r2_configured()
    connected = False
    bucket_active = False
    message = "R2 no configurado"

    if configured:
        connected, message = test_r2_connection()
        if connected:
            try:
                _get_client().head_bucket(Bucket=_bucket())
                bucket_active = True
            except Exception:
                bucket_active = False
                connected = False
                message = "Error al verificar el bucket R2"

    try:
        counts = get_catalog_counts()
        series_count = counts["total_series"]
        episodes_count = counts["total_episodes"]
    except Exception:
        logger.exception("Failed to count series/episodes for storage status")
        series_count = 0
        episodes_count = 0

    return {
        "provider": storage_provider(),
        "configured": configured,
        "connected": connected,
        "r2_connected": connected and bucket_active,
        "bucket": bucket,
        "bucket_active": bucket_active,
        "endpoint": current_app.config.get("R2_ENDPOINT"),
        "series_count": series_count,
        "episodes_count": episodes_count,
        "total_series": series_count,
        "total_episodes": episodes_count,
        "message": "R2 conectado" if connected and bucket_active else message,
    }


def _upload_fileobj(file_obj: BinaryIO, key: str, content_type: str) -> str:
    client = _get_client()
    file_obj.seek(0)
    client.upload_fileobj(
        file_obj,
        _bucket(),
        key,
        ExtraArgs={"ContentType": content_type},
    )
    logger.info("Uploaded to R2: %s", key)
    return key


def count_r2_objects(prefix: str = "") -> int:
    """Count objects in the R2 bucket (paginated)."""
    if not is_r2_configured():
        return 0
    try:
        client = _get_client()
        total = 0
        token = None
        while True:
            kwargs = {"Bucket": _bucket(), "MaxKeys": 1000}
            if prefix:
                kwargs["Prefix"] = prefix
            if token:
                kwargs["ContinuationToken"] = token
            response = client.list_objects_v2(**kwargs)
            total += len(response.get("Contents", []))
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
        return total
    except Exception:
        logger.exception("Failed to count R2 objects")
        return -1


def upload_video(
    file: FileStorage, series_id: int | None = None, lang: str | None = None
) -> str:
    """Upload video to R2; returns object key stored in video_url_r2."""
    if not is_r2_configured():
        raise ValueError(
            "Cloudflare R2 no está disponible. Revisa las variables en Render o usa Admin → Probar conexión R2."
        )
    ext = _ext(file.filename)
    if ext not in current_app.config["ALLOWED_VIDEO_EXTENSIONS"]:
        raise ValueError("Invalid video format. Allowed: mp4, webm, ogg")

    max_size = current_app.config.get("MAX_VIDEO_SIZE", 500 * 1024 * 1024)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > max_size:
        mb = max_size // (1024 * 1024)
        raise ValueError(f"Video too large. Maximum size is {mb} MB.")

    if series_id and lang and lang != "es":
        folder = f"videos/{series_id}/{lang}"
    else:
        folder = f"videos/{series_id}" if series_id else "videos"
    key = f"{folder}/{uuid.uuid4().hex}.{ext}"
    content_type = VIDEO_CONTENT_TYPES.get(ext, "application/octet-stream")
    return _upload_fileobj(file.stream, key, content_type)


def upload_hls_playlist(content: str, series_id: int, episode_id: int) -> str:
    if not is_r2_configured():
        raise ValueError("R2 not configured")
    key = f"hls/{series_id}/{episode_id}/master.m3u8"
    data = content.encode("utf-8")
    _get_client().put_object(
        Bucket=_bucket(),
        Key=key,
        Body=data,
        ContentType="application/vnd.apple.mpegurl",
    )
    logger.info("Uploaded HLS master to R2: %s", key)
    return key


_HLS_CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
}


def upload_hls_tree(local_dir: Path, prefix: str) -> tuple[str, list[dict]]:
    """Upload generated HLS folder to R2; returns (master_key, qualities list)."""
    if not is_r2_configured():
        raise ValueError("R2 not configured")
    client = _get_client()
    bucket = _bucket()
    qualities: list[dict] = []
    height_map = {"v0": 480, "v1": 720, "v2": 1080}
    master_key = f"{prefix.rstrip('/')}/master.m3u8"

    for path in sorted(local_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(local_dir).as_posix()
        key = f"{prefix.rstrip('/')}/{rel}"
        ext = path.suffix.lower()
        content_type = _HLS_CONTENT_TYPES.get(ext, "application/octet-stream")
        client.upload_file(str(path), bucket, key, ExtraArgs={"ContentType": content_type})
        if rel.endswith("playlist.m3u8") and "/" in rel:
            folder = rel.split("/")[0]
            height = height_map.get(folder)
            if height:
                qualities.append({"height": height, "url": key, "label": f"{height}P"})

    qualities.sort(key=lambda q: int(q.get("height") or 0))
    logger.info("Uploaded HLS tree to R2 prefix=%s files=%s", prefix, len(list(local_dir.rglob('*'))))
    return master_key, qualities


def upload_thumbnail(file: FileStorage, series_id: int | None = None) -> str:
    """Upload episode thumbnail to R2; returns object key stored in thumbnail_url."""
    if not is_r2_configured():
        raise ValueError(
            "Cloudflare R2 no está disponible. Revisa la configuración de almacenamiento."
        )
    from utils.image_io import image_to_bytesio

    ext = _ext(file.filename)
    if ext == "jpeg":
        ext = "jpg"
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ValueError("Invalid image format")

    buf = image_to_bytesio(file.stream, ext=ext)
    folder = f"covers/{series_id}" if series_id else "covers"
    key = f"{folder}/{uuid.uuid4().hex}.{'jpg' if ext in ('jpg', 'jpeg') else ext}"
    content_type = IMAGE_CONTENT_TYPES.get(ext, "image/jpeg")
    return _upload_fileobj(buf, key, content_type)


def upload_payment_screenshot(file: FileStorage, payment_id: int | None = None) -> str:
    """Upload Cash App payment proof screenshot to R2."""
    if not is_r2_configured():
        raise ValueError(
            "Cloudflare R2 no está disponible. Revisa la configuración de almacenamiento."
        )
    from utils.image_io import image_to_bytesio

    ext = _ext(file.filename)
    if ext == "jpeg":
        ext = "jpg"
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ValueError("Invalid image format")

    max_size = current_app.config.get("MAX_IMAGE_SIZE", 5 * 1024 * 1024)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > max_size:
        raise ValueError("Screenshot too large. Maximum size is 5 MB.")

    buf = image_to_bytesio(file.stream, ext=ext)

    folder = f"payments/{payment_id}" if payment_id else "payments"
    key = f"{folder}/{uuid.uuid4().hex}.{'jpg' if ext in ('jpg', 'jpeg') else ext}"
    content_type = IMAGE_CONTENT_TYPES.get(ext, "image/jpeg")
    return _upload_fileobj(buf, key, content_type)


def upload_series_image(
    file: FileStorage, series_id: int | None = None, kind: str = "hero"
) -> str:
    """Upload series hero/card image to R2."""
    if not is_r2_configured():
        raise ValueError(
            "Cloudflare R2 no está disponible. Revisa la configuración de almacenamiento."
        )
    from utils.image_io import image_to_bytesio

    ext = _ext(file.filename)
    if ext == "jpeg":
        ext = "jpg"
    if ext not in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        raise ValueError("Invalid image format")

    buf = image_to_bytesio(file.stream, ext=ext)

    folder = f"series/{series_id}/{kind}" if series_id else f"series/{kind}"
    key = f"{folder}/{uuid.uuid4().hex}.{'jpg' if ext in ('jpg', 'jpeg') else ext}"
    content_type = IMAGE_CONTENT_TYPES.get(ext, "image/jpeg")
    return _upload_fileobj(buf, key, content_type)


def delete_object(key: str | None) -> bool:
    if not key or not is_r2_configured():
        return False
    if key.startswith("http://") or key.startswith("https://"):
        return False
    try:
        _get_client().delete_object(Bucket=_bucket(), Key=key)
        return True
    except Exception:
        logger.exception("Failed to delete R2 object %s", key)
        return False


def download_object_to_path(key: str, dest: Path) -> Path:
    """Download R2 object to a local file (for ffmpeg / whisper processing)."""
    if not is_r2_configured():
        raise ValueError("R2 not configured")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _get_client().download_file(_bucket(), key, str(dest))
    return dest


def upload_subtitle_vtt(
    content: str, series_id: int, episode_id: int, lang: str = "es"
) -> str:
    """Upload WebVTT bytes to R2; returns object key (e.g. subtitle_es.vtt)."""
    if not is_r2_configured():
        raise ValueError("R2 not configured")
    safe_lang = (lang or "es").lower()[:8]
    key = f"subtitles/{series_id}/{episode_id}/subtitle_{safe_lang}.vtt"
    data = content.encode("utf-8")
    _get_client().put_object(
        Bucket=_bucket(),
        Key=key,
        Body=data,
        ContentType="text/vtt; charset=utf-8",
    )
    logger.info("Uploaded subtitle to R2: %s", key)
    return key


def object_head_meta(key: str) -> dict:
    """HEAD object metadata (size, type) without downloading body."""
    if not is_r2_configured():
        raise ValueError("R2 not configured")
    resp = _get_client().head_object(Bucket=_bucket(), Key=key)
    content_type = resp.get("ContentType") or "application/octet-stream"
    if not str(content_type).startswith("video/"):
        ext = _ext(key) if "." in key else "mp4"
        content_type = VIDEO_CONTENT_TYPES.get(ext, "video/mp4")
    return {
        "content_length": int(resp["ContentLength"]),
        "content_type": content_type,
        "etag": resp.get("ETag"),
    }


def stream_object_from_r2(
    key: str,
    range_header: str | None = None,
    *,
    method: str = "GET",
) -> tuple[int, dict[str, str], object | None, dict]:
    """
    Stream object from R2 with bounded HTTP Range (max 2MB per response).
    Returns (status_code, headers, body_generator, meta). body is None for HEAD.
    Never buffers the full object in memory.
    """
    from modules.streaming.services.range_http import clamp_byte_range

    if not is_r2_configured():
        raise ValueError("R2 not configured")

    head = object_head_meta(key)
    total_size = head["content_length"]
    content_type = head["content_type"]

    base_headers: dict[str, str] = {
        "Accept-Ranges": "bytes",
        "Content-Type": content_type,
        "Cache-Control": "private, max-age=3600, no-transform",
    }

    stream_meta: dict = {"file_size": total_size, "range_in": range_header or "-"}

    if method.upper() == "HEAD":
        base_headers["Content-Length"] = str(total_size)
        return 200, base_headers, None, stream_meta

    byte_start, byte_end, effective_range = clamp_byte_range(total_size, range_header)
    stream_meta["range_out"] = effective_range

    resp = _get_client().get_object(
        Bucket=_bucket(),
        Key=key,
        Range=effective_range,
    )

    part_length = byte_end - byte_start + 1
    content_range = f"bytes {byte_start}-{byte_end}/{total_size}"

    headers = {
        **base_headers,
        "Content-Length": str(part_length),
        "Content-Range": content_range,
    }

    def _iter_body():
        for chunk in resp["Body"].iter_chunks(chunk_size=256 * 1024):
            yield chunk

    return 206, headers, _iter_body(), stream_meta


def get_playback_url(key: str, expires: int = 3600) -> str | None:
    """Public URL or presigned URL for streaming."""
    if not key:
        return None
    if key.startswith("http://") or key.startswith("https://"):
        return key

    public_base = (current_app.config.get("R2_PUBLIC_BASE_URL") or "").rstrip("/")
    if public_base:
        return f"{public_base}/{key.lstrip('/')}"

    if not is_r2_configured():
        return None
    try:
        return _get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": _bucket(), "Key": key},
            ExpiresIn=expires,
        )
    except Exception:
        logger.exception("Failed to presign R2 URL for %s", key)
        return None


def get_thumbnail_url(key: str, expires: int = 3600) -> str | None:
    return get_playback_url(key, expires=expires)


def is_r2_media(value: str | None) -> bool:
    if not value:
        return False
    if value.startswith("http://") or value.startswith("https://"):
        return True
    return use_r2_storage() and not value.startswith("storage/")

