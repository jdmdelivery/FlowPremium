"""Database bootstrap: rename legacy tables, create missing tables, safe migrations."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from extensions import db

logger = logging.getLogger(__name__)

LEGACY_TABLE_RENAMES = (
    ("users", "stream_users"),
    ("series", "stream_series"),
    ("seasons", "stream_seasons"),
    ("episodes", "stream_episodes"),
    ("payments", "stream_payments"),
    ("episode_purchases", "stream_purchases"),
    ("subscriptions", "stream_subscriptions"),
    ("watch_progress", "stream_watch_progress"),
)


def _table_row_count(table_name: str) -> int:
    result = db.session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    return int(result.scalar() or 0)


def rename_legacy_tables() -> None:
    """Rename pre-stream_* tables without dropping data."""
    inspector = inspect(db.engine)
    existing = set(inspector.get_table_names())
    for old_name, new_name in LEGACY_TABLE_RENAMES:
        if old_name not in existing:
            continue
        if new_name not in existing:
            db.session.execute(text(f"ALTER TABLE {old_name} RENAME TO {new_name}"))
            logger.info("Renamed table %s -> %s", old_name, new_name)
            existing.remove(old_name)
            existing.add(new_name)
            continue

        old_count = _table_row_count(old_name)
        new_count = _table_row_count(new_name)
        if old_count > 0 and new_count == 0:
            db.session.execute(text(f"DROP TABLE {new_name}"))
            db.session.execute(text(f"ALTER TABLE {old_name} RENAME TO {new_name}"))
            logger.info(
                "Replaced empty %s with legacy data from %s (%s rows)",
                new_name,
                old_name,
                old_count,
            )
            existing.discard(new_name)
            existing.remove(old_name)
            existing.add(new_name)
        elif old_count > 0 and new_count > 0:
            logger.warning(
                "Both %s (%s rows) and %s (%s rows) exist; app uses %s only.",
                old_name,
                old_count,
                new_name,
                new_count,
                new_name,
            )
    db.session.commit()


def migrate_stream_payments() -> None:
    inspector = inspect(db.engine)
    if "stream_payments" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("stream_payments")}
    additions = {
        "customer_name": "VARCHAR(255)",
        "customer_email": "VARCHAR(255)",
        "method": "VARCHAR(50)",
        "provider_payment_id": "VARCHAR(255)",
        "reference_note": "VARCHAR(500)",
        "paid_at": "DATETIME",
    }
    for name, col_type in additions.items():
        if name not in columns:
            db.session.execute(text(f"ALTER TABLE stream_payments ADD COLUMN {name} {col_type}"))

    if "provider" in columns:
        db.session.execute(
            text(
                "UPDATE stream_payments SET method = provider "
                "WHERE method IS NULL OR TRIM(method) = ''"
            )
        )
    if "approved_at" in columns:
        db.session.execute(
            text("UPDATE stream_payments SET paid_at = approved_at WHERE paid_at IS NULL")
        )
    db.session.execute(
        text("UPDATE stream_payments SET status = 'paid' WHERE status = 'approved'")
    )
    db.session.commit()


def migrate_stream_episodes() -> None:
    inspector = inspect(db.engine)
    if "stream_episodes" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("stream_episodes")}
    for name, col_type in (
        ("video_url", "VARCHAR(1000)"),
        ("thumbnail_url", "VARCHAR(1000)"),
    ):
        if name not in columns:
            db.session.execute(text(f"ALTER TABLE stream_episodes ADD COLUMN {name} {col_type}"))

    if "video_path" in columns and "video_url" in columns:
        db.session.execute(
            text(
                "UPDATE stream_episodes SET video_url = video_path "
                "WHERE (video_url IS NULL OR TRIM(video_url) = '') "
                "AND video_path IS NOT NULL AND TRIM(video_path) != ''"
            )
        )
    if "thumbnail" in columns and "thumbnail_url" in columns:
        db.session.execute(
            text(
                "UPDATE stream_episodes SET thumbnail_url = thumbnail "
                "WHERE (thumbnail_url IS NULL OR TRIM(thumbnail_url) = '') "
                "AND thumbnail IS NOT NULL AND TRIM(thumbnail) != ''"
            )
        )
    db.session.commit()


def init_database(app) -> None:
    """Create stream_* tables and apply non-destructive migrations."""
    import models.user  # noqa: F401
    import modules.streaming.models  # noqa: F401

    rename_legacy_tables()
    db.create_all()
    migrate_stream_payments()
    migrate_stream_episodes()

    from modules.db.diagnostics import log_database_startup

    log_database_startup(app)

    if app.config.get("TESTING"):
        return

    seed = __import__("os").environ.get("SEED_DEFAULT_USERS", "true").lower() in (
        "1",
        "true",
        "yes",
    )
    if seed:
        from utils.seed_users import ensure_default_users

        ensure_default_users()
