"""Subtitle (VTT / whisper) tests — no GPU or model download required."""

from types import SimpleNamespace
from unittest.mock import patch

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.services.subtitles import (
    enqueue_subtitle_job,
    format_vtt_timestamp,
    segments_to_vtt,
)


def test_format_vtt_timestamp():
    assert format_vtt_timestamp(0) == "00:00:00.000"
    assert format_vtt_timestamp(61.5) == "00:01:01.500"


def test_segments_to_vtt():
    segments = [
        SimpleNamespace(start=0.0, end=2.5, text=" Hola "),
        SimpleNamespace(start=2.5, end=5.0, text="mundo"),
    ]
    vtt = segments_to_vtt(segments)
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500" in vtt
    assert "Hola" in vtt
    assert "mundo" in vtt


def test_enqueue_skipped_when_disabled(app, sample_content):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/x.mp4"
        db.session.commit()
        assert enqueue_subtitle_job(ep.id) is False
        ep = db.session.get(Episode, ep.id)
        assert ep.subtitle_status == "skipped"


def test_enqueue_sets_pending(app, sample_content):
    with app.app_context():
        app.config["SUBTITLES_ENABLED"] = True
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/x.mp4"
        db.session.commit()
        ep_id = ep.id

    with patch(
        "modules.streaming.services.subtitles.prerequisites_ok",
        return_value=(True, "ok"),
    ), patch("modules.streaming.services.subtitles.generate_subtitles_for_episode"):
        with app.app_context():
            assert enqueue_subtitle_job(ep_id) is True
            ep = db.session.get(Episode, ep_id)
            assert ep.subtitle_status == "pending"


def test_subtitle_api_requires_access(user_client, sample_content):
    ep_id = sample_content["premium_episode_id"]
    resp = user_client.get(f"/api/streaming/subtitles/{ep_id}")
    assert resp.status_code == 403


def test_subtitle_api_serves_vtt(user_client, app, sample_content):
    from pathlib import Path

    ep_id = sample_content["free_episode_id"]
    with app.app_context():
        upload = Path(app.config["UPLOAD_FOLDER"])
        vtt_path = upload / "subtitles" / "1" / "test.vtt"
        vtt_path.parent.mkdir(parents=True, exist_ok=True)
        vtt_path.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHola\n", encoding="utf-8")
        rel = str(vtt_path.relative_to(Path(app.root_path).resolve())).replace("\\", "/")
        ep = db.session.get(Episode, ep_id)
        ep.subtitle_url = rel
        ep.subtitle_status = "ready"
        db.session.commit()

    resp = user_client.get(f"/api/streaming/subtitles/{ep_id}")
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("text/vtt")
    assert b"WEBVTT" in resp.data


def test_watch_page_shows_cc_when_subtitles_ready(user_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.subtitle_url = "subtitles/1/ep.vtt"
        ep.subtitle_status = "ready"
        db.session.commit()

    resp = user_client.get(f"/streaming/watch/{ep_id}")
    assert resp.status_code == 200
    assert b'id="btn-cc"' in resp.data
    assert f"/api/streaming/subtitles/{ep_id}".encode() in resp.data
