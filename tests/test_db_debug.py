"""Tests for database diagnostics and /admin/debug-db."""


def test_debug_db_requires_admin(client):
    resp = client.get("/admin/debug-db")
    assert resp.status_code == 403


def test_debug_db_sqlite_local(admin_client):
    resp = admin_client.get("/admin/debug-db")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["database_type"] == "sqlite"
    assert data["database_engine"] == "SQLite"
    assert data["database_url_detected"] is False
    assert "total_series" in data
    assert "total_seasons" in data
    assert "total_episodes" in data


def test_debug_db_counts(admin_client, sample_content):
    resp = admin_client.get("/admin/debug-db")
    data = resp.get_json()
    assert data["total_series"] >= 1
    assert data["total_seasons"] >= 1
    assert data["total_episodes"] >= 2


def test_resolve_app_database_uri_uses_postgres_when_url_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host/dbname")
    from modules.db.diagnostics import resolve_app_database_uri

    uri = resolve_app_database_uri(production=False)
    assert uri.startswith("postgresql://")


def test_database_url_detected(monkeypatch):
    from utils.runtime_env import database_url_detected

    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database_url_detected() is False

    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    assert database_url_detected() is True

    monkeypatch.setenv("DATABASE_URL", "none")
    assert database_url_detected() is False
