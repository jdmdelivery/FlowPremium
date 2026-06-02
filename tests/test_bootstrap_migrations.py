"""Bootstrap migration column types (PostgreSQL vs SQLite)."""

from modules.db import bootstrap


def test_timestamp_column_sqlite():
    assert bootstrap._timestamp_column_type("sqlite") == "DATETIME"


def test_timestamp_column_postgresql():
    assert bootstrap._timestamp_column_type("postgresql") == "TIMESTAMPTZ"


def test_episode_subtitle_columns_postgresql():
    cols = bootstrap._episode_migration_columns("postgresql")
    assert cols["subtitle_url"] == "TEXT"
    assert cols["subtitle_status"] == "VARCHAR(20)"
    assert cols["subtitle_lang"] == "VARCHAR(10)"
    assert cols["subtitle_generated_at"] == "TIMESTAMPTZ"


def test_episode_subtitle_columns_sqlite():
    cols = bootstrap._episode_migration_columns("sqlite")
    assert cols["subtitle_generated_at"] == "DATETIME"
    assert cols["subtitle_url"] == "VARCHAR(1000)"
