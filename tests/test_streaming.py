import os

import pytest

from extensions import db
from modules.streaming.models import Episode, EpisodePurchase, Season, Series, WatchProgress
from modules.streaming.services.payment import admin_grant_episode


def test_streaming_index_renders(client, sample_content):
    resp = client.get("/streaming/")
    assert resp.status_code == 200
    assert b"Test Series" in resp.data or b"StreamPremium" in resp.data


def test_free_episode_can_be_viewed(client, sample_content):
    ep_id = sample_content["free_episode_id"]
    resp = client.get(f"/streaming/watch/{ep_id}")
    assert resp.status_code == 200
    assert b"Free Episode" in resp.data


def test_premium_episode_blocked_without_payment(user_client, sample_content):
    ep_id = sample_content["premium_episode_id"]
    resp = user_client.get(f"/streaming/watch/{ep_id}")
    assert resp.status_code == 302


def test_purchased_episode_can_be_viewed(app, user_client, sample_content):
    ep_id = sample_content["premium_episode_id"]
    with app.app_context():
        admin_grant_episode(2, ep_id)
    resp = user_client.get(f"/streaming/watch/{ep_id}")
    assert resp.status_code == 200
    assert b"Premium Episode" in resp.data


def test_premium_stream_forbidden_without_access(user_client, sample_content, app):
    ep_id = sample_content["premium_episode_id"]
    with app.app_context():
        video_dir = os.path.join(app.config["VIDEO_FOLDER"])
        os.makedirs(video_dir, exist_ok=True)
        video_file = os.path.join(video_dir, "test.mp4")
        with open(video_file, "wb") as f:
            f.write(b"\x00" * 100)
    resp = user_client.get(f"/api/streaming/stream/{ep_id}")
    assert resp.status_code == 403


def test_admin_can_create_series(admin_client):
    resp = admin_client.post(
        "/admin/streaming/series/new",
        data={"title": "New Series", "description": "A series", "is_active": "on"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"New Series" in resp.data or b"Serie guardada" in resp.data


def test_admin_can_create_episode(admin_client, app):
    with app.app_context():
        series = Series(title="S", is_active=True)
        db.session.add(series)
        db.session.flush()
        season = Season(series_id=series.id, title="S1", season_number=1, is_active=True)
        db.session.add(season)
        db.session.commit()
        series_id, season_id = series.id, season.id

    resp = admin_client.post(
        "/admin/streaming/episodes/new",
        data={
            "series_id": series_id,
            "season_id": season_id,
            "title": "Ep 1",
            "description": "First",
            "duration_seconds": 120,
            "price": "4.99",
            "is_active": "on",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        ep = Episode.query.filter_by(title="Ep 1").first()
        assert ep is not None
        assert ep.price == 4.99


def test_watch_progress_saved(app, user_client, sample_content):
    ep_id = sample_content["free_episode_id"]
    resp = user_client.post(
        "/api/streaming/progress",
        json={"episode_id": ep_id, "position_seconds": 125, "completed": False},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["position_seconds"] == 125

    with app.app_context():
        progress = WatchProgress.query.filter_by(user_id=2, episode_id=ep_id).first()
        assert progress is not None
        assert progress.position_seconds == 125


def test_progress_marks_completed(app, user_client, sample_content):
    ep_id = sample_content["free_episode_id"]
    user_client.post(
        "/api/streaming/progress",
        json={"episode_id": ep_id, "position_seconds": 600, "completed": True},
    )
    with app.app_context():
        progress = WatchProgress.query.filter_by(user_id=2, episode_id=ep_id).first()
        assert progress.completed is True
        assert progress.completed_at is not None


def test_admin_login_redirects_to_admin_panel(client):
    resp = client.post(
        "/login",
        data={"email": "admin@test.com", "password": "admin123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/streaming" in resp.location


def test_admin_can_delete_episode(app, admin_client, sample_content):
    ep_id = sample_content["free_episode_id"]
    resp = admin_client.post(
        f"/admin/streaming/episodes/{ep_id}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert Episode.query.get(ep_id) is None
        assert WatchProgress.query.filter_by(episode_id=ep_id).count() == 0


def test_non_admin_cannot_delete_episode(user_client, sample_content):
    ep_id = sample_content["free_episode_id"]
    resp = user_client.post(f"/admin/streaming/episodes/{ep_id}/delete")
    assert resp.status_code == 403
    with user_client.application.app_context():
        assert Episode.query.get(ep_id) is not None


def test_admin_can_delete_series(app, admin_client, sample_content):
    series_id = sample_content["series_id"]
    resp = admin_client.post(
        f"/admin/streaming/series/{series_id}/delete",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert Series.query.get(series_id) is None
        assert Episode.query.filter_by(series_id=series_id).count() == 0
        assert Season.query.filter_by(series_id=series_id).count() == 0


def test_non_admin_cannot_delete_series(user_client, sample_content):
    series_id = sample_content["series_id"]
    resp = user_client.post(f"/admin/streaming/series/{series_id}/delete")
    assert resp.status_code == 403
    with user_client.application.app_context():
        assert Series.query.get(series_id) is not None


def test_seed_users_idempotent():
    import os
    import tempfile

    from app import create_app
    from extensions import db
    from utils.seed_users import ensure_default_users

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    class SeedConfig:
        TESTING = True
        SECRET_KEY = "seed-test"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        UPLOAD_FOLDER = tempfile.mkdtemp()
        VIDEO_FOLDER = os.path.join(UPLOAD_FOLDER, "videos")
        THUMBNAIL_FOLDER = os.path.join(UPLOAD_FOLDER, "covers")
        SERIES_COVER_FOLDER = os.path.join(UPLOAD_FOLDER, "series")
        ALLOWED_VIDEO_EXTENSIONS = {"mp4"}
        ALLOWED_IMAGE_EXTENSIONS = {"jpg"}
        DEFAULT_LOCALE = "es"
        SUPPORTED_LOCALES = ("es", "en")

    application = create_app(SeedConfig)
    with application.app_context():
        import modules.streaming.models  # noqa: F401
        db.create_all()
        first = ensure_default_users()
        second = ensure_default_users()
        assert len(first) == 2
        assert all("Created" in m for m in first)
        assert all("Skipped" in m for m in second)

    try:
        os.unlink(db_path)
    except OSError:
        pass
