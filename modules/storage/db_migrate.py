"""Storage migrations (legacy; use modules.db.bootstrap)."""

from sqlalchemy import inspect, text

from extensions import db


def migrate_episode_storage_columns() -> None:
    inspector = inspect(db.engine)
    table = (
        "stream_episodes"
        if "stream_episodes" in inspector.get_table_names()
        else "episodes"
    )
    if table not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns(table)}
    additions = {
        "video_url": "VARCHAR(1000)",
        "thumbnail_url": "VARCHAR(1000)",
    }
    for name, col_type in additions.items():
        if name not in columns:
            db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}"))
    db.session.commit()
