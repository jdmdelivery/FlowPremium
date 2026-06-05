"""Sequential media pipeline and low-RAM HLS height tests."""

from pathlib import Path
from unittest.mock import patch

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.services.media_pipeline import enqueue_media_pipeline, run_media_pipeline
from modules.streaming.services.video_processing import _heights_for_source


def test_heights_low_ram_defaults_to_480p(app):
    with app.app_context():
        app.config["VIDEO_HLS_LOW_RAM"] = True
        app.config["VIDEO_HLS_INCLUDE_720P"] = False
        assert _heights_for_source(1080) == [480]


def test_heights_low_ram_optional_720p(app):
    with app.app_context():
        app.config["VIDEO_HLS_LOW_RAM"] = True
        app.config["VIDEO_HLS_INCLUDE_720P"] = True
        assert _heights_for_source(1080) == [480, 720]


def test_pipeline_runs_hls_then_subtitles(app, sample_content):
    calls: list[str] = []

    def fake_hls(episode_id, *, source_path=None):
        calls.append("hls")

    def fake_subs(episode_id, *, source_path=None):
        calls.append("subs")

    with app.app_context():
        ep_id = sample_content["free_episode_id"]
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = "videos/1/test.mp4"
        db.session.commit()

        with patch(
            "modules.streaming.services.media_pipeline._materialize_source",
            return_value=Path("/tmp/fake.mp4"),
        ), patch(
            "modules.streaming.services.video_processing.process_episode_hls",
            side_effect=fake_hls,
        ), patch(
            "modules.streaming.services.subtitles.generate_subtitles_for_episode",
            side_effect=fake_subs,
        ), patch(
            "modules.streaming.services.media_pipeline._should_run_subtitles",
            return_value=True,
        ):
            run_media_pipeline(ep_id, run_hls=True, run_subtitles=True)

    assert calls == ["hls", "subs"]


def test_enqueue_pipeline_sets_pending_states(app, sample_content):
    with app.app_context():
        app.config["SUBTITLES_ENABLED"] = True
        ep_id = sample_content["free_episode_id"]
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = "videos/1/test.mp4"
        db.session.commit()

        with patch(
            "modules.streaming.services.subtitles.prerequisites_ok",
            return_value=(True, "ok"),
        ), patch(
            "modules.streaming.services.media_pipeline.run_media_pipeline",
        ):
            assert enqueue_media_pipeline(ep_id, run_hls=True, run_subtitles=True) is True
            ep = db.session.get(Episode, ep_id)
            assert ep.processing_status == "pending"
            assert ep.subtitle_status == "pending"
