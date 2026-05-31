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

LEGACY_CATALOG_COPY = (
    (
        "series",
        "stream_series",
        "INSERT INTO stream_series (id, title, description, cover_image, is_active, created_at) "
        "SELECT id, title, description, cover_image, is_active, created_at FROM series",
    ),
    (
        "seasons",
        "stream_seasons",
        "INSERT INTO stream_seasons (id, series_id, title, season_number, description, is_active, created_at) "
        "SELECT id, series_id, title, season_number, description, is_active, created_at FROM seasons",
    ),
)


def _table_row_count(table_name: str) -> int:
    result = db.session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
    return int(result.scalar() or 0)


def _table_exists(table_name: str) -> bool:
    return table_name in inspect(db.engine).get_table_names()


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


def copy_legacy_catalog_if_empty() -> None:
    """Copy rows from legacy catalog tables when stream_* tables exist but are empty."""
    for legacy, stream, insert_sql in LEGACY_CATALOG_COPY:
        if not _table_exists(legacy) or not _table_exists(stream):
            continue
        if _table_row_count(stream) > 0:
            continue
        if _table_row_count(legacy) == 0:
            continue
        db.session.execute(text(insert_sql))
        logger.info("Copied catalog data from %s into empty %s", legacy, stream)

    if _table_exists("episodes") and _table_exists("stream_episodes"):
        if _table_row_count("stream_episodes") == 0 and _table_row_count("episodes") > 0:
            legacy_cols = {c["name"] for c in inspect(db.engine).get_columns("episodes")}
            stream_cols = {c["name"] for c in inspect(db.engine).get_columns("stream_episodes")}
            video_expr = "video_url_r2"
            if "video_url_r2" not in stream_cols:
                video_expr = "video_url"
            if "video_url_r2" in stream_cols:
                if "video_url" in legacy_cols:
                    src_video = "video_url"
                elif "video_path" in legacy_cols:
                    src_video = "video_path"
                else:
                    src_video = "NULL"
                thumb_src = (
                    "thumbnail_url"
                    if "thumbnail_url" in legacy_cols
                    else ("thumbnail" if "thumbnail" in legacy_cols else "NULL")
                )
                db.session.execute(
                    text(
                        f"INSERT INTO stream_episodes "
                        f"(id, series_id, season_id, title, description, video_url_r2, thumbnail_url, "
                        f"duration_seconds, price, is_free, is_active, created_at) "
                        f"SELECT id, series_id, season_id, title, description, "
                        f"{src_video}, {thumb_src}, duration_seconds, price, is_free, is_active, created_at "
                        f"FROM episodes"
                    )
                )
            elif "video_url" in stream_cols:
                src_video = (
                    "video_url"
                    if "video_url" in legacy_cols
                    else ("video_path" if "video_path" in legacy_cols else "NULL")
                )
                thumb_src = (
                    "thumbnail_url"
                    if "thumbnail_url" in legacy_cols
                    else ("thumbnail" if "thumbnail" in legacy_cols else "NULL")
                )
                db.session.execute(
                    text(
                        "INSERT INTO stream_episodes "
                        "(id, series_id, season_id, title, description, video_url, thumbnail_url, "
                        "duration_seconds, price, is_free, is_active, created_at) "
                        f"SELECT id, series_id, season_id, title, description, "
                        f"{src_video}, {thumb_src}, duration_seconds, price, is_free, is_active, created_at "
                        "FROM episodes"
                    )
                )
            logger.info("Copied episode rows from legacy episodes table")
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
        "screenshot_url": "VARCHAR(1000)",
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
    additions = {
        "video_url_r2": "VARCHAR(1000)",
        "video_url": "VARCHAR(1000)",
        "thumbnail_url": "VARCHAR(1000)",
    }
    for name, col_type in additions.items():
        if name not in columns:
            db.session.execute(text(f"ALTER TABLE stream_episodes ADD COLUMN {name} {col_type}"))

    columns = {col["name"] for col in inspector.get_columns("stream_episodes")}

    if "video_url_r2" in columns and "video_url" in columns:
        db.session.execute(
            text(
                "UPDATE stream_episodes SET video_url_r2 = video_url "
                "WHERE (video_url_r2 IS NULL OR TRIM(video_url_r2) = '') "
                "AND video_url IS NOT NULL AND TRIM(video_url) != ''"
            )
        )
    if "video_url_r2" in columns and "video_path" in columns:
        db.session.execute(
            text(
                "UPDATE stream_episodes SET video_url_r2 = video_path "
                "WHERE (video_url_r2 IS NULL OR TRIM(video_url_r2) = '') "
                "AND video_path IS NOT NULL AND TRIM(video_path) != ''"
            )
        )
    if "thumbnail_url" in columns and "thumbnail" in columns:
        db.session.execute(
            text(
                "UPDATE stream_episodes SET thumbnail_url = thumbnail "
                "WHERE (thumbnail_url IS NULL OR TRIM(thumbnail_url) = '') "
                "AND thumbnail IS NOT NULL AND TRIM(thumbnail) != ''"
            )
        )
    db.session.commit()


def sync_postgres_sequences() -> None:
    """Keep SERIAL sequences aligned after manual id inserts (PostgreSQL only)."""
    if db.engine.dialect.name != "postgresql":
        return
    for table in ("stream_series", "stream_seasons", "stream_episodes", "stream_users"):
        if not _table_exists(table):
            continue
        db.session.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
            )
        )
    db.session.commit()


def migrate_stream_series() -> None:
    inspector = inspect(db.engine)
    if "stream_series" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("stream_series")}
    for name, col_type in (
        ("thumbnail_url", "VARCHAR(1000)"),
        ("hero_image_url", "VARCHAR(1000)"),
    ):
        if name not in columns:
            db.session.execute(text(f"ALTER TABLE stream_series ADD COLUMN {name} {col_type}"))

    columns = {col["name"] for col in inspector.get_columns("stream_series")}
    if "hero_image_url" in columns and "cover_image" in columns:
        db.session.execute(
            text(
                "UPDATE stream_series SET hero_image_url = cover_image "
                "WHERE (hero_image_url IS NULL OR TRIM(hero_image_url) = '') "
                "AND cover_image IS NOT NULL AND TRIM(cover_image) != ''"
            )
        )
    if "thumbnail_url" in columns and "hero_image_url" in columns:
        db.session.execute(
            text(
                "UPDATE stream_series SET thumbnail_url = hero_image_url "
                "WHERE (thumbnail_url IS NULL OR TRIM(thumbnail_url) = '') "
                "AND hero_image_url IS NOT NULL AND TRIM(hero_image_url) != ''"
            )
        )
    db.session.commit()


def init_database(app) -> None:
    """Create stream_* tables and apply non-destructive migrations."""
    import models.user  # noqa: F401
    import modules.streaming.models  # noqa: F401

    rename_legacy_tables()
    db.create_all()
    copy_legacy_catalog_if_empty()
    migrate_stream_payments()
    migrate_stream_episodes()
    migrate_stream_series()
    sync_postgres_sequences()

    from modules.db.diagnostics import log_persistence_startup

    log_persistence_startup(app)

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
