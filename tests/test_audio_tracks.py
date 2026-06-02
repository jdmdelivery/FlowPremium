"""Audio track manifest and probe tests."""

import json

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.services.audio_tracks import build_audio_manifest, save_probe_result


def test_build_manifest_single_track(app, sample_content):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/a.mp4"
        ep.video_url_r2_en = None
        manifest = build_audio_manifest(ep)
        assert manifest["mode"] == "single"
        assert manifest["show_selector"] is False
        assert len(manifest["tracks"]) == 1
        assert manifest["tracks"][0]["lang"] == "es"


def test_build_manifest_es_en_urls(app, sample_content):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/es.mp4"
        ep.video_url_r2_en = "videos/1/en.mp4"
        manifest = build_audio_manifest(ep)
        assert manifest["show_selector"] is True
        assert len(manifest["tracks"]) == 2
        langs = {t["lang"] for t in manifest["tracks"]}
        assert langs == {"es", "en"}
        assert "lang=en" in manifest["tracks"][1]["url"]


def test_build_manifest_embedded_tracks(app, sample_content):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/dual.mp4"
        save_probe_result(
            ep,
            [
                {"index": 1, "lang": "es", "label": "Español", "flag": "🇪🇸"},
                {"index": 2, "lang": "en", "label": "English", "flag": "🇺🇸"},
            ],
        )
        manifest = build_audio_manifest(ep)
        assert manifest["mode"] == "embedded"
        assert manifest["show_selector"] is True
        assert len(manifest["tracks"]) == 2


def test_segments_probe_storage(app, sample_content):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        save_probe_result(ep, [{"index": 0, "lang": "es"}])
        data = json.loads(ep.audio_tracks_json)
        assert data["count"] == 1


def test_audio_tracks_api(user_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2_en = "videos/1/en.mp4"
        db.session.commit()

    resp = user_client.get(f"/api/streaming/audio-tracks/{ep_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["show_selector"] is True
    assert len(data["tracks"]) >= 2
