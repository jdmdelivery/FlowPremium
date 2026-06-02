import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

_DEV_SECRET = "dev-streaming-secret-change-in-production"
_SQLITE_PATH = BASE_DIR / "flowpremium.db"


def _normalize_database_url(url: str) -> str:
    """Render/Heroku use postgres://; SQLAlchemy 2.x needs postgresql://."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def get_database_uri(*, production: bool = False) -> str:
    """
    PostgreSQL when DATABASE_URL is set; otherwise SQLite for local dev only.
    On Render, PostgreSQL is always required.
    """
    from utils.runtime_env import is_render, database_url_detected as url_detected

    if is_render() and not url_detected():
        raise RuntimeError(
            "DATABASE_URL must be set on Render. Link your PostgreSQL database to the web service."
        )

    url = os.environ.get("DATABASE_URL")
    if url and url.lower() not in ("null", "none", ""):
        uri = _normalize_database_url(url)
        if uri.startswith("sqlite"):
            raise RuntimeError("DATABASE_URL must point to PostgreSQL, not SQLite.")
        return uri
    if production or is_render():
        raise RuntimeError(
            "DATABASE_URL must be set in production. Add your PostgreSQL URL in Render."
        )
    return f"sqlite:///{_SQLITE_PATH}"


def _storage_root() -> Path:
    """Override with STORAGE_PATH on Render (persistent disk mount)."""
    custom = os.environ.get("STORAGE_PATH", "").strip()
    if custom:
        return Path(custom)
    return BASE_DIR / "storage" / "streaming"


def _engine_options(uri: str) -> dict:
    if uri.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


_db_uri = get_database_uri() if not os.environ.get("RENDER") else ""


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET)
    SQLALCHEMY_DATABASE_URI = _db_uri or "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(_db_uri)

    UPLOAD_FOLDER = _storage_root()
    VIDEO_FOLDER = UPLOAD_FOLDER / "videos"
    THUMBNAIL_FOLDER = UPLOAD_FOLDER / "covers"
    SERIES_COVER_FOLDER = UPLOAD_FOLDER / "series"

    _on_render = os.environ.get("RENDER", "").lower() in ("true", "1", "yes")
    _default_video_mb = 100 if _on_render else 500
    MAX_VIDEO_SIZE = int(os.environ.get("MAX_VIDEO_SIZE", _default_video_mb * 1024 * 1024))
    MAX_IMAGE_SIZE = int(os.environ.get("MAX_IMAGE_SIZE", 10 * 1024 * 1024))
    # Flask rejects oversized uploads before the worker hangs on multipart read.
    MAX_CONTENT_LENGTH = MAX_VIDEO_SIZE + (8 * 1024 * 1024)

    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "ogg"}
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}

    DEFAULT_LOCALE = "es"
    SUPPORTED_LOCALES = ("es", "en")

    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
    PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
    PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET", "")
    PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")

    CASHAPP_TAG = os.environ.get("CASHAPP_TAG", "")

    _subtitle_default = "false" if _on_render else "true"
    SUBTITLES_ENABLED = os.environ.get("SUBTITLES_ENABLED", _subtitle_default).lower() in (
        "1",
        "true",
        "yes",
    )
    WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "base")
    WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "es")
    WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")
    WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")

    STORAGE_PROVIDER = os.environ.get(
        "STORAGE_PROVIDER", "r2" if os.environ.get("RENDER") else "local"
    ).lower()
    R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "")
    R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
    R2_PUBLIC_BASE_URL = os.environ.get("R2_PUBLIC_BASE_URL", "")

    SQUARE_ACCESS_TOKEN = os.environ.get("SQUARE_ACCESS_TOKEN", "")
    SQUARE_APPLICATION_ID = os.environ.get("SQUARE_APPLICATION_ID", "")
    SQUARE_LOCATION_ID = os.environ.get("SQUARE_LOCATION_ID", "")
    SQUARE_ENV = os.environ.get("SQUARE_ENV", "sandbox")

    PAYMENT_PLANS = {
        "monthly": {
            "name": "Plan Mensual FlowPremium",
            "description": "Acceso premium mensual a catálogo y episodios.",
            "amount": float(os.environ.get("PLAN_MONTHLY_AMOUNT", "9.99")),
            "currency": "USD",
        },
        "annual": {
            "name": "Plan Anual FlowPremium",
            "description": "Acceso premium anual con mejor precio.",
            "amount": float(os.environ.get("PLAN_ANNUAL_AMOUNT", "99.99")),
            "currency": "USD",
        },
    }


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
    """SECRET_KEY and DATABASE_URL are required in production."""
    if config_class is not ProductionConfig:
        return
    if config_class.SECRET_KEY == _DEV_SECRET:
        raise RuntimeError(
            "SECRET_KEY must be set in production. Add it in Render Environment."
        )
    get_database_uri(production=True)
