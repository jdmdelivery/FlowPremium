"""Database connection diagnostics and persistence startup logging."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from flask import current_app
from sqlalchemy import inspect, text

from config import get_database_uri
from extensions import db
from utils.runtime_env import database_url_detected, is_render, must_use_r2_storage

logger = logging.getLogger(__name__)

STREAM_TABLES = (
    "stream_users",
    "stream_series",
    "stream_seasons",
    "stream_episodes",
    "stream_payments",
    "stream_purchases",
    "stream_subscriptions",
    "stream_watch_progress",
)


def get_database_type(uri: str | None = None) -> str:
    if uri is None:
        uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri:
        return "unknown"
    if uri.startswith("postgresql") or uri.startswith("postgres://"):
        return "postgresql"
    if uri.startswith("sqlite"):
        return "sqlite"
    parsed = urlparse(uri)
    if parsed.scheme in ("postgres", "postgresql"):
        return "postgresql"
    return parsed.scheme or "unknown"


def get_active_engine_label() -> str:
    db_type = get_database_type()
    if db_type == "postgresql":
        return "PostgreSQL"
    if db_type == "sqlite":
        return "SQLite"
    return db_type.upper()


def _mask_database_uri(uri: str) -> str:
    if not uri:
        return ""
    parsed = urlparse(uri)
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    db_name = (parsed.path or "").lstrip("/") or "?"
    return f"{parsed.scheme}://***@{host}{port}/{db_name}"


def _table_row_count(table_name: str) -> int:
    try:
        return int(db.session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0)
    except Exception:
        return -1


def _postgres_database_name() -> str | None:
    if db.engine.dialect.name != "postgresql":
        return None
    try:
        return db.session.execute(text("SELECT current_database()")).scalar()
    except Exception:
        return None


def get_catalog_counts() -> dict[str, int]:
    """Read catalog totals from PostgreSQL/SQLAlchemy (never from memory cache)."""
    from modules.streaming.models import Episode, Season, Series

    db.session.expire_all()
    return {
        "total_series": Series.query.count(),
        "total_seasons": Season.query.count(),
        "total_episodes": Episode.query.count(),
    }


def get_debug_db_info() -> dict:
    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    db_type = get_database_type(uri)
    url_detected = database_url_detected()
    using_sqlite = db_type == "sqlite"
    misconfigured = url_detected and using_sqlite
    counts = get_catalog_counts()

    inspector = inspect(db.engine)
    existing_tables = sorted(inspector.get_table_names())

    legacy_counts = {}
    for legacy in ("series", "seasons", "episodes"):
        if legacy in existing_tables:
            legacy_counts[legacy] = _table_row_count(legacy)

    stream_counts = {name: _table_row_count(name) for name in STREAM_TABLES if name in existing_tables}

    diagnosis = []
    if misconfigured:
        diagnosis.append("DATABASE_URL definida pero la app usa SQLite.")
    if is_render() and using_sqlite:
        diagnosis.append("Render está usando SQLite. Los datos se pierden en cada deploy.")
    if legacy_counts and counts["total_series"] == 0 and any(v > 0 for v in legacy_counts.values()):
        diagnosis.append("Hay datos legacy sin migrar a stream_*.")
    if counts["total_series"] == 0 and not legacy_counts and db_type == "postgresql":
        diagnosis.append("PostgreSQL conectado pero el catálogo está vacío.")

    return {
        "database_type": db_type,
        "database_engine": get_active_engine_label(),
        "database_url_detected": url_detected,
        "postgresql_connected": db_type == "postgresql",
        "using_postgresql": db_type == "postgresql",
        "using_sqlite": using_sqlite,
        "misconfigured": misconfigured,
        "database_uri_masked": _mask_database_uri(uri),
        "postgres_database_name": _postgres_database_name(),
        **counts,
        "stream_tables_present": [t for t in STREAM_TABLES if t in existing_tables],
        "legacy_table_counts": legacy_counts,
        "stream_table_counts": stream_counts,
        "diagnosis": diagnosis,
    }


def get_debug_storage_info() -> dict:
    from modules.storage.storage_r2 import count_r2_objects, get_storage_status, is_r2_configured

    db_info = get_debug_db_info()
    storage = get_storage_status()
    r2_objects = count_r2_objects() if is_r2_configured() else 0

    postgres_ok = db_info["database_type"] == "postgresql" and db_info["database_url_detected"]

    return {
        "postgresql_conectado": "SI" if postgres_ok else "NO",
        "postgresql_connected": postgres_ok,
        "database_type": db_info["database_type"],
        "database_url_detected": db_info["database_url_detected"],
        "postgres_database_name": db_info.get("postgres_database_name"),
        "total_series": db_info["total_series"],
        "total_seasons": db_info["total_seasons"],
        "total_episodes": db_info["total_episodes"],
        "storage_provider": storage.get("provider"),
        "r2_connected": storage.get("connected", False),
        "bucket": storage.get("bucket"),
        "bucket_activo": "SI" if storage.get("bucket_active") else "NO",
        "bucket_active": storage.get("bucket_active", False),
        "total_objetos_r2": r2_objects,
        "total_r2_objects": r2_objects,
        "legacy_table_counts": db_info.get("legacy_table_counts", {}),
        "stream_table_counts": db_info.get("stream_table_counts", {}),
        "diagnosis": db_info.get("diagnosis", []),
    }


def log_persistence_startup(app) -> None:
    with app.app_context():
        db_info = get_debug_db_info()
        bucket = app.config.get("R2_BUCKET_NAME") or "not-configured"
        storage_label = "Cloudflare R2" if must_use_r2_storage() else app.config.get("STORAGE_PROVIDER", "local")

        logger.info("DATABASE: %s", db_info["database_engine"])
        logger.info("STORAGE: %s", storage_label)
        logger.info("BUCKET: %s", bucket)
        logger.info(
            "FlowPremium catalog: series=%s seasons=%s episodes=%s db=%s url_detected=%s",
            db_info["total_series"],
            db_info["total_seasons"],
            db_info["total_episodes"],
            db_info.get("postgres_database_name") or db_info["database_uri_masked"],
            db_info["database_url_detected"],
        )
        for note in db_info["diagnosis"]:
            logger.warning("FlowPremium persistence: %s", note)


def resolve_app_database_uri(*, production: bool) -> str:
    if database_url_detected():
        uri = get_database_uri(production=False)
        if uri.startswith("sqlite"):
            raise RuntimeError("DATABASE_URL must point to PostgreSQL, not SQLite.")
        return uri
    if is_render():
        raise RuntimeError(
            "DATABASE_URL must be linked to the Render web service (PostgreSQL)."
        )
    return get_database_uri(production=production)
