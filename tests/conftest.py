import os
import tempfile
from pathlib import Path

import pytest

from app import create_app
from extensions import db
from models.user import User
from modules.streaming.models import Episode, Season, Series


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    class TestConfig:
        TESTING = True
        SECRET_KEY = "test-secret"
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        _test_storage = Path(__file__).resolve().parent.parent / "storage" / "streaming" / "_pytest"
        _test_storage.mkdir(parents=True, exist_ok=True)
        UPLOAD_FOLDER = _test_storage
        VIDEO_FOLDER = _test_storage / "videos"
        THUMBNAIL_FOLDER = _test_storage / "covers"
        SERIES_COVER_FOLDER = _test_storage / "series"
        ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "ogg"}
        ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
        DEFAULT_LOCALE = "es"
        SUPPORTED_LOCALES = ("es", "en")
        STRIPE_SECRET_KEY = ""
        PAYPAL_CLIENT_ID = ""
        PAYPAL_CLIENT_SECRET = ""
        CASHAPP_TAG = "$TestTag"
        SUBTITLES_ENABLED = False
        MEDIA_PIPELINE_DEFER_SECONDS = 0
        STORAGE_PROVIDER = "local"
        R2_ENDPOINT = ""
        R2_ACCESS_KEY_ID = ""
        R2_SECRET_ACCESS_KEY = ""
        R2_BUCKET_NAME = ""
        R2_PUBLIC_BASE_URL = ""
        PAYMENT_PLANS = {
            "monthly": {"name": "Monthly", "description": "Test", "amount": 9.99, "currency": "USD"},
            "annual": {"name": "Annual", "description": "Test", "amount": 99.99, "currency": "USD"},
        }

    application = create_app(TestConfig)

    with application.app_context():
        import modules.streaming.models  # noqa: F401
        db.create_all()
        admin = User(email="admin@test.com", username="admin", is_admin=True)
        admin.set_password("admin123")
        user = User(email="user@test.com", username="user", is_admin=False)
        user.set_password("user123")
        db.session.add_all([admin, user])
        db.session.commit()

    yield application

    with application.app_context():
        db.session.remove()
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(app, client):
    client.post("/login", data={"email": "admin@test.com", "password": "admin123"})
    return client


@pytest.fixture
def user_client(app, client):
    client.post("/login", data={"email": "user@test.com", "password": "user123"})
    return client


@pytest.fixture
def sample_content(app):
    with app.app_context():
        series = Series(title="Test Series", description="Desc", is_active=True)
        db.session.add(series)
        db.session.flush()
        season = Season(series_id=series.id, title="Season 1", season_number=1, is_active=True)
        db.session.add(season)
        db.session.flush()

        free_ep = Episode(
            series_id=series.id,
            season_id=season.id,
            title="Free Episode",
            is_free=True,
            is_active=True,
            price=0,
            video_url_r2="storage/streaming/videos/free.mp4",
            processing_status="ready",
        )
        premium_ep = Episode(
            series_id=series.id,
            season_id=season.id,
            title="Premium Episode",
            is_free=False,
            is_active=True,
            price=9.99,
            video_url="storage/streaming/videos/test.mp4",
        )
        db.session.add_all([free_ep, premium_ep])
        db.session.commit()
        return {
            "series_id": series.id,
            "season_id": season.id,
            "free_episode_id": free_ep.id,
            "premium_episode_id": premium_ep.id,
        }
