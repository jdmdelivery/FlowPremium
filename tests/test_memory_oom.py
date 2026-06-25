"""Memory guard and home query optimization tests."""

from unittest.mock import patch

from extensions import db
from modules.streaming.models import Episode, Series
from modules.streaming.services.home import get_home_sections
from modules.streaming.services.media_pipeline import enqueue_media_pipeline, run_media_pipeline


def test_pipeline_aborts_when_memory_low(app, sample_content):
    with app.app_context():
        ep_id = sample_content["free_episode_id"]
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = "videos/1/test.mp4"
        ep.processing_status = "pending"
        db.session.commit()

        with patch(
            "modules.streaming.services.media_pipeline.pipeline_memory_ok",
            return_value=(False, "rss_mb=400 exceeds max=280"),
        ), patch(
            "modules.streaming.services.media_pipeline._materialize_source",
        ) as materialize:
            run_media_pipeline(ep_id, run_hls=True, run_subtitles=False)
            materialize.assert_not_called()

        ep = db.session.get(Episode, ep_id)
        assert ep.processing_status == "ready"
        assert "memoria" in (ep.processing_error or "").lower()


def test_home_sections_single_pass_stats(app, sample_content):
    with app.app_context():
        sections = get_home_sections(None)
        assert "all_cards" in sections
        assert sections["all_cards"]


def test_enqueue_uses_subprocess_when_configured(app, sample_content):
    class _SyncThread:
        def __init__(self, target=None, **kwargs):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    with app.app_context():
        app.config["MEDIA_PIPELINE_USE_SUBPROCESS"] = True
        app.config["MEDIA_PIPELINE_DEFER_SECONDS"] = 0
        ep_id = sample_content["free_episode_id"]
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = "videos/1/test.mp4"
        db.session.commit()

        mock_proc = type("P", (), {"wait": lambda self: 0})()
        with patch(
            "modules.streaming.services.subtitles.prerequisites_ok",
            return_value=(True, "ok"),
        ), patch(
            "modules.streaming.services.media_pipeline.threading.Thread",
            _SyncThread,
        ), patch(
            "modules.streaming.services.media_pipeline._spawn_pipeline_subprocess",
            return_value=mock_proc,
        ) as spawn:
            assert enqueue_media_pipeline(ep_id, run_hls=True, run_subtitles=False) is True
            spawn.assert_called_once()


def test_health_memory_endpoint(client):
    resp = client.get("/health?mem=1")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "memory" in data
