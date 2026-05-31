"""Database connection diagnostics and startup logging."""

from __future__ import annotations

import logging
import os
from urllib.parse import urlparse

from flask import current_app
from sqlalchemy import inspect, text

from config import get_database_uri
from extensions import db

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


def database_url_detected() -> bool:
    url = os.environ.get("DATABASE_URL", "")
    return bool(url and url.lower() not in ("null", "none", ""))


def get_database_type(uri: str | None = None) -> str:
    """Return 'postgresql', 'sqlite', or 'unknown'."""
    if uri is None:
        uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri:
        return "unknown"
    if uri.startswith("postgresql"):
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
        return db.session.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar() or 0
    except Exception:
        return -1


def get_debug_db_info() -> dict:
    from modules.streaming.models import Episode, Season, Series

    uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    db_type = get_database_type(uri)
    url_detected = database_url_detected()
    using_sqlite = db_type == "sqlite"
    misconfigured = url_detected and using_sqlite

    inspector = inspect(db.engine)
    existing_tables = sorted(inspector.get_table_names())

    legacy_counts = {}
    for legacy, stream in (
        ("series", "stream_series"),
        ("seasons", "stream_seasons"),
        ("episodes", "stream_episodes"),
    ):
        if legacy in existing_tables:
            legacy_counts[legacy] = _table_row_count(legacy)

    stream_counts = {name: _table_row_count(name) for name in STREAM_TABLES if name in existing_tables}

    total_series = Series.query.count()
    total_seasons = Season.query.count()
    total_episodes = Episode.query.count()

    diagnosis = []
    if misconfigured:
        diagnosis.append(
            "DATABASE_URL está definida pero la app usa SQLite. Revisa el orden de configuración."
        )
    if legacy_counts and total_series == 0 and any(v > 0 for v in legacy_counts.values()):
        diagnosis.append(
            "Hay datos en tablas legacy (series/seasons/episodes) pero stream_* está vacío. "
            "Ejecuta migrate o redeploy con el bootstrap actualizado."
        )
    if db_type == "sqlite" and os.environ.get("RENDER", "").lower() in ("true", "1", "yes"):
        diagnosis.append(
            "Render detectado con SQLite: los datos se pierden en cada deploy. Usa DATABASE_URL."
        )
    if total_series == 0 and not legacy_counts:
        diagnosis.append("PostgreSQL conectado pero sin catálogo. Crea series desde Admin.")

    return {
        "database_type": db_type,
        "database_engine": get_active_engine_label(),
        "database_url_detected": url_detected,
        "using_postgresql": db_type == "postgresql",
        "using_sqlite": using_sqlite,
        "misconfigured": misconfigured,
        "database_uri_masked": _mask_database_uri(uri),
        "total_series": total_series,
        "total_seasons": total_seasons,
        "total_episodes": total_episodes,
        "stream_tables_present": [t for t in STREAM_TABLES if t in existing_tables],
        "legacy_table_counts": legacy_counts,
        "stream_table_counts": stream_counts,
        "diagnosis": diagnosis,
    }


def log_database_startup(app) -> None:
    with app.app_context():
        info = get_debug_db_info()
        logger.info(
            "FlowPremium DB: engine=%s url_detected=%s uri=%s series=%s seasons=%s episodes=%s",
            info["database_engine"],
            info["database_url_detected"],
            info["database_uri_masked"],
            info["total_series"],
            info["total_seasons"],
            info["total_episodes"],
        )
        for note in info["diagnosis"]:
            logger.warning("FlowPremium DB diagnosis: %s", note)


def resolve_app_database_uri(*, production: bool) -> str:
    """DATABASE_URL always wins; SQLite only when URL is absent and not production."""
    if database_url_detected():
        uri = get_database_uri(production=False)
        if uri.startswith("sqlite"):
            raise RuntimeError(
                "DATABASE_URL is set but resolved to SQLite. Check DATABASE_URL format."
            )
        return uri
    return get_database_uri(production=production)
