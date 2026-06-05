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


def test_local_stream_head_returns_accept_ranges(user_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    payload = b"\x00" * 800
    rel = _install_local_video(app, "head-test.mp4", payload)

    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = rel
        db.session.commit()

    resp = user_client.head(f"/api/streaming/stream/{ep_id}")
    assert resp.status_code == 200
    assert resp.headers.get("Accept-Ranges") == "bytes"
    assert resp.headers.get("Content-Length") == str(len(payload))


def test_local_stream_no_range_returns_206(user_client, app, sample_content):
    """Safari/Android often send Range; server must still answer 206 when coerced."""
    ep_id = sample_content["free_episode_id"]
    payload = b"\xcd" * 300
    rel = _install_local_video(app, "no-range-mobile.mp4", payload)

    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = rel
        db.session.commit()

    resp = user_client.get(f"/api/streaming/stream/{ep_id}")
    assert resp.status_code == 206
    assert resp.headers.get("Accept-Ranges") == "bytes"
    assert resp.headers.get("Content-Range") == f"bytes 0-299/{len(payload)}"
    assert len(resp.data) == len(payload)


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


def test_local_stream_open_range_clamped_to_2mb(user_client, app, sample_content):
    """bytes=0- on a large file must not return the entire object (Render OOM)."""
    from modules.streaming.services.range_http import DEFAULT_STREAM_CHUNK

    ep_id = sample_content["free_episode_id"]
    payload = b"\xcd" * (DEFAULT_STREAM_CHUNK + 500_000)
    rel = _install_local_video(app, "large-open-range.mp4", payload)

    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = rel
        db.session.commit()

    resp = user_client.get(
        f"/api/streaming/stream/{ep_id}",
        headers={"Range": "bytes=0-"},
    )
    assert resp.status_code == 206
    assert resp.headers.get("Content-Length") == str(DEFAULT_STREAM_CHUNK)
    assert resp.headers.get("Content-Range") == (
        f"bytes 0-{DEFAULT_STREAM_CHUNK - 1}/{len(payload)}"
    )
    assert len(resp.data) == DEFAULT_STREAM_CHUNK


def test_local_stream_invalid_range_416(user_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    rel = _install_local_video(app, "bad-range.mp4", b"x" * 100)

    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = rel
        db.session.commit()

    resp = user_client.get(
        f"/api/streaming/stream/{ep_id}",
        headers={"Range": "bytes=500-10"},
    )
    assert resp.status_code == 416


def test_r2_stream_proxies_range_206(user_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = "videos/1/test.mp4"
        db.session.commit()

    with patch("modules.storage.storage_r2.is_r2_configured", return_value=True), patch(
        "modules.streaming.services.stream._should_stream_from_r2",
        return_value=True,
    ), patch(
        "modules.storage.storage_r2.stream_object_from_r2",
        return_value=(
            206,
            {
                "Accept-Ranges": "bytes",
                "Content-Type": "video/mp4",
                "Content-Length": "5",
                "Content-Range": "bytes 0-4/1000",
            },
            iter([b"chunk"]),
            {"file_size": 1000, "range_in": "bytes=0-", "range_out": "bytes=0-4"},
        ),
    ) as stream_mock:
        resp = user_client.get(
            f"/api/streaming/stream/{ep_id}",
            headers={"Range": "bytes=0-"},
        )

    assert resp.status_code == 206
    assert resp.headers.get("Accept-Ranges") == "bytes"
    assert resp.headers.get("Content-Type") == "video/mp4"
    assert resp.headers.get("Content-Range") == "bytes 0-4/1000"
    assert resp.data == b"chunk"
    stream_mock.assert_called_once()
    assert stream_mock.call_args[0][1] == "bytes=0-"


def test_r2_stream_no_range_defaults_to_full_206(app):
    from modules.storage.storage_r2 import stream_object_from_r2

    meta = {"content_length": 1000, "content_type": "video/mp4", "etag": '"x"'}

    mock_body = MagicMock()
    mock_body.iter_chunks.return_value = [b"ab"]

    mock_client = MagicMock()
    mock_client.get_object.return_value = {
        "ContentLength": 1000,
        "ContentType": "video/mp4",
        "Body": mock_body,
    }

    with app.app_context(), patch(
        "modules.storage.storage_r2.is_r2_configured", return_value=True
    ), patch("modules.storage.storage_r2.object_head_meta", return_value=meta), patch(
        "modules.storage.storage_r2._get_client", return_value=mock_client
    ):
        status, headers, body, stream_meta = stream_object_from_r2("videos/1/x.mp4", None)

    assert status == 206
    assert headers["Content-Range"] == "bytes 0-999/1000"
    assert headers["Content-Length"] == "1000"
    assert b"".join(body) == b"ab"
    assert stream_meta["range_out"] == "bytes=0-999"
    mock_client.get_object.assert_called_once()
    assert mock_client.get_object.call_args[1]["Range"] == "bytes=0-999"


def test_r2_stream_open_range_clamped_to_2mb(app):
    from modules.streaming.services.range_http import DEFAULT_STREAM_CHUNK
    from modules.storage.storage_r2 import stream_object_from_r2

    file_size = 31_182_164
    meta = {"content_length": file_size, "content_type": "video/mp4", "etag": '"x"'}

    mock_body = MagicMock()
    mock_body.iter_chunks.return_value = [b"x" * 1024]

    mock_client = MagicMock()
    mock_client.get_object.return_value = {"Body": mock_body}

    with app.app_context(), patch(
        "modules.storage.storage_r2.is_r2_configured", return_value=True
    ), patch("modules.storage.storage_r2.object_head_meta", return_value=meta), patch(
        "modules.storage.storage_r2._get_client", return_value=mock_client
    ):
        status, headers, _body, stream_meta = stream_object_from_r2(
            "videos/8/x.mp4", "bytes=0-"
        )

    assert status == 206
    assert headers["Content-Length"] == str(DEFAULT_STREAM_CHUNK)
    assert headers["Content-Range"] == f"bytes 0-{DEFAULT_STREAM_CHUNK - 1}/{file_size}"
    assert stream_meta["range_out"] == f"bytes=0-{DEFAULT_STREAM_CHUNK - 1}"
    assert mock_client.get_object.call_args[1]["Range"] == f"bytes=0-{DEFAULT_STREAM_CHUNK - 1}"


def test_mp4_faststart_detection():
    from utils.video import mp4_likely_faststart

    good = BytesIO(b"\x00\x00\x00\x20ftypisom" + b"x" * 8 + b"moov" + b"y" * 8 + b"mdat")
    assert mp4_likely_faststart(good) is True

    bad = BytesIO(b"\x00\x00\x00\x20ftypisom" + b"x" * 8 + b"mdat" + b"y" * 8 + b"moov")
    assert mp4_likely_faststart(bad) is False
