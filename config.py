import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

_DEV_SECRET = "dev-streaming-secret-change-in-production"


def _normalize_database_url(url: str) -> str:
    """Render/Heroku use postgres://; SQLAlchemy 2.x needs postgresql://."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def _database_uri() -> str:
    url = os.environ.get("DATABASE_URL")
    if url and url.lower() not in ("null", "none", ""):
        return _normalize_database_url(url)
    return f"sqlite:///{BASE_DIR / 'streaming.db'}"


def _storage_root() -> Path:
    """Override with STORAGE_PATH on Render (persistent disk mount)."""
    custom = os.environ.get("STORAGE_PATH", "").strip()
    if custom:
        return Path(custom)
    return BASE_DIR / "storage" / "streaming"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET)
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    UPLOAD_FOLDER = _storage_root()
    VIDEO_FOLDER = UPLOAD_FOLDER / "videos"
    THUMBNAIL_FOLDER = UPLOAD_FOLDER / "covers"
    SERIES_COVER_FOLDER = UPLOAD_FOLDER / "series"

    MAX_VIDEO_SIZE = int(os.environ.get("MAX_VIDEO_SIZE", 500 * 1024 * 1024))
    MAX_IMAGE_SIZE = int(os.environ.get("MAX_IMAGE_SIZE", 10 * 1024 * 1024))

    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "ogg"}
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}

    DEFAULT_LOCALE = "es"
    SUPPORTED_LOCALES = ("es", "en")

    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PREFERRED_URL_SCHEME = "https"


def get_config_class():
    env = os.environ.get("FLASK_ENV", "").lower()
    on_render = os.environ.get("RENDER", "").lower() in ("true", "1", "yes")
    if env == "production" or on_render:
        return ProductionConfig
    return Config


def validate_production_config(config_class) -> None:
    """Fail fast on Render if required secrets are missing."""
    if config_class is not ProductionConfig:
        return
    if config_class.SECRET_KEY == _DEV_SECRET:
        raise RuntimeError(
            "SECRET_KEY must be set in production. Add it in Render Environment."
        )
    if config_class.SQLALCHEMY_DATABASE_URI.startswith("sqlite"):
        raise RuntimeError(
            "Use PostgreSQL on Render: link a Postgres database and set DATABASE_URL."
        )
