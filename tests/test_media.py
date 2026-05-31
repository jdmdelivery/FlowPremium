"""Tests for media URL resolution and series image fallbacks."""

from unittest.mock import patch


def test_series_card_image_key_fallback_to_episode(app, sample_content):
    with app.app_context():
        from extensions import db
        from modules.streaming.models import Episode, Series

        series = db.session.get(Series, sample_content["series_id"])
        series.thumbnail_url = None
        series.hero_image_url = None
        series.cover_image = None
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.thumbnail_url = "covers/1/ep-thumb.jpg"
        db.session.commit()

        assert series.card_image_key() == "covers/1/ep-thumb.jpg"
        assert series.hero_image_key() == "covers/1/ep-thumb.jpg"


@patch("modules.storage.storage_r2.get_playback_url", return_value="https://signed.example/img.jpg")
def test_media_url_presigns_r2_key(mock_presign, app):
    with app.app_context():
        from utils.media import media_url

        assert media_url("covers/1/test.jpg") == "https://signed.example/img.jpg"


def test_debug_media_requires_admin(client):
    resp = client.get("/admin/debug-media/1")
    assert resp.status_code == 403


def test_debug_media_series(admin_client, sample_content):
    resp = admin_client.get(f"/admin/debug-media/{sample_content['series_id']}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["series_id"] == sample_content["series_id"]
    assert "fields" in data
    assert "thumbnail_url" in data["fields"]
