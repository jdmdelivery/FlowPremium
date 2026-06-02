"""HTTP Range / 206 tests for mobile video playback."""

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from extensions import db
from modules.streaming.models import Episode


def _install_local_video(app, filename: str, payload: bytes) -> str:
    """Write MP4 under UPLOAD_FOLDER; return DB path for resolve_storage_path."""
    upload = Path(app.config["UPLOAD_FOLDER"]).resolve()
    dest = upload / "videos" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return str(dest.relative_to(Path(app.root_path).resolve())).replace("\\", "/")


def test_watch_page_uses_api_stream_url(user_client, sample_content):
    ep_id = sample_content["free_episode_id"]
    resp = user_client.get(f"/streaming/watch/{ep_id}")
    assert resp.status_code == 200
    assert f"/api/streaming/stream/{ep_id}" in resp.data.decode()


def test_local_stream_range_returns_206(user_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    payload = b"\x00" * 1000
    rel = _install_local_video(app, "range-test.mp4", payload)

    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = rel
        db.session.commit()

    resp = user_client.get(
        f"/api/streaming/stream/{ep_id}",
        headers={"Range": "bytes=0-99"},
    )
    assert resp.status_code == 206
    assert resp.headers.get("Accept-Ranges") == "bytes"
    assert resp.headers.get("Content-Type") == "video/mp4"
    assert resp.headers.get("Content-Length") == "100"
    assert resp.headers.get("Content-Range") == f"bytes 0-99/{len(payload)}"
    assert len(resp.data) == 100


def test_local_stream_open_range_bytes_0_dash(user_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    payload = b"\xab" * 500
    rel = _install_local_video(app, "open-range.mp4", payload)

    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = rel
        db.session.commit()

    resp = user_client.get(
        f"/api/streaming/stream/{ep_id}",
        headers={"Range": "bytes=0-"},
    )
    assert resp.status_code == 206
    assert resp.headers.get("Content-Range") == f"bytes 0-499/{len(payload)}"


def test_r2_stream_proxies_range_206(user_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = "videos/1/test.mp4"
        db.session.commit()

    mock_body = MagicMock()
    mock_body.iter_chunks.return_value = [b"chunk"]

    with patch("modules.storage.storage_r2.is_r2_configured", return_value=True), patch(
        "modules.storage.storage_r2.stream_object_from_r2",
        return_value=(
            206,
            {
                "Accept-Ranges": "bytes",
                "Content-Type": "video/mp4",
                "Content-Length": "5",
                "Content-Range": "bytes 0-4/1000",
            },
            mock_body,
        ),
    ):
        resp = user_client.get(
            f"/api/streaming/stream/{ep_id}",
            headers={"Range": "bytes=0-"},
        )

    assert resp.status_code == 206
    assert resp.headers.get("Accept-Ranges") == "bytes"
    assert resp.headers.get("Content-Type") == "video/mp4"
    assert resp.headers.get("Content-Range") == "bytes 0-4/1000"


def test_mp4_faststart_detection():
    from utils.video import mp4_likely_faststart

    good = BytesIO(b"\x00\x00\x00\x20ftypisom" + b"x" * 8 + b"moov" + b"y" * 8 + b"mdat")
    assert mp4_likely_faststart(good) is True

    bad = BytesIO(b"\x00\x00\x00\x20ftypisom" + b"x" * 8 + b"mdat" + b"y" * 8 + b"moov")
    assert mp4_likely_faststart(bad) is False
