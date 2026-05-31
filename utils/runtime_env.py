"""Production/runtime helpers for database and storage configuration."""

from __future__ import annotations

import os


def is_render() -> bool:
    return os.environ.get("RENDER", "").lower() in ("true", "1", "yes")


def is_production_runtime() -> bool:
    env = os.environ.get("FLASK_ENV", "").lower()
    return env == "production" or is_render()


def database_url_detected() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    return bool(url and url.lower() not in ("null", "none", ""))


def must_use_postgresql() -> bool:
    """PostgreSQL required on Render or when DATABASE_URL is set."""
    return is_render() or database_url_detected()


def must_use_r2_storage() -> bool:
    """R2 required on Render production deploys."""
    if is_render() or is_production_runtime():
        return True
    provider = os.environ.get("STORAGE_PROVIDER", "local").lower()
    return provider == "r2"
