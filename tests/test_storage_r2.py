"""Tests for Cloudflare R2 storage integration."""

from unittest.mock import MagicMock, patch

import pytest

from extensions import db
from modules.streaming.models import Episode, Series


def test_storage_status_requires_admin(client):
    resp = client.get("/admin/storage-status")
    assert resp.status_code == 403


def test_storage_status_admin_ok(admin_client):
    resp = admin_client.get("/admin/storage-status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["provider"] == "local"
    assert "series_count" in data
    assert "episodes_count" in data


def test_storage_status_counts(app, admin_client, sample_content):
    resp = admin_client.get("/admin/storage-status")
    data = resp.get_json()
    assert data["series_count"] >= 1
    assert data["episodes_count"] >= 2


def test_test_r2_local_provider(admin_client):
    resp = admin_client.post("/admin/storage/test-r2")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert "❌" in data["message"]


@patch("modules.storage.storage_r2._get_client")
def test_test_r2_success(mock_client_factory, app, admin_client):
    app.config.update(
        STORAGE_PROVIDER="r2",
        R2_ENDPOINT="https://example.r2.cloudflarestorage.com",
        R2_ACCESS_KEY_ID="key",
        R2_SECRET_ACCESS_KEY="secret",
        R2_BUCKET_NAME="flowpremium",
    )
    client = MagicMock()
    mock_client_factory.return_value = client

    resp = admin_client.post("/admin/storage/test-r2")
    data = resp.get_json()
    assert data["ok"] is True
    assert "✅" in data["message"]
    client.head_bucket.assert_called_once()


@patch("modules.storage.storage_r2._get_client")
def test_upload_video_to_r2(mock_client_factory, app):
    client = MagicMock()
    mock_client_factory.return_value = client

    from io import BytesIO
    from werkzeug.datastructures import FileStorage

    from modules.storage.storage_r2 import upload_video

    with app.app_context():
        app.config.update(
            STORAGE_PROVIDER="r2",
            R2_ENDPOINT="https://example.r2.cloudflarestorage.com",
            R2_ACCESS_KEY_ID="key",
            R2_SECRET_ACCESS_KEY="secret",
            R2_BUCKET_NAME="flowpremium",
            ALLOWED_VIDEO_EXTENSIONS={"mp4"},
            MAX_VIDEO_SIZE=50 * 1024 * 1024,
        )
        fs = FileStorage(stream=BytesIO(b"fake-video"), filename="clip.mp4")
        key = upload_video(fs, series_id=7)
    assert key.startswith("videos/7/")
    assert key.endswith(".mp4")
    client.upload_fileobj.assert_called_once()


def test_stream_proxies_r2_with_range(app, sample_content, admin_client):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url = "videos/1/test.mp4"
        db.session.commit()
        episode_id = ep.id

    mock_body = MagicMock()
    mock_body.iter_chunks.return_value = [b"data"]

    with patch("modules.storage.storage_r2.is_r2_configured", return_value=True), patch(
        "modules.storage.storage_r2.stream_object_from_r2",
        return_value=(
            206,
            {
                "Accept-Ranges": "bytes",
                "Content-Type": "video/mp4",
                "Content-Length": "4",
                "Content-Range": "bytes 0-3/100",
            },
            mock_body,
        ),
    ) as stream_mock:
        resp = admin_client.get(
            f"/api/streaming/stream/{episode_id}",
            headers={"Range": "bytes=0-"},
        )
        assert resp.status_code == 206
        stream_mock.assert_called_once()
        assert stream_mock.call_args[0][1] == "bytes=0-"


def test_media_url_local_path(app):
    with app.app_context():
        from utils.media import media_url

        assert media_url("storage/streaming/covers/x.jpg") == "/media/storage/streaming/covers/x.jpg"
        assert media_url("https://cdn.example/a.jpg") == "https://cdn.example/a.jpg"


def test_episode_has_video_with_r2_key(app, sample_content):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url = "videos/1/a.mp4"
        assert ep.has_video is True
