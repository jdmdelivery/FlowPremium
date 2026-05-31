"""Tests for /admin/debug-storage and persistence diagnostics."""

from unittest.mock import patch


def test_debug_storage_requires_admin(client):
    resp = client.get("/admin/debug-storage")
    assert resp.status_code == 403


def test_debug_storage_local(admin_client):
    resp = admin_client.get("/admin/debug-storage")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "postgresql_conectado" in data
    assert "total_series" in data
    assert "total_seasons" in data
    assert "total_episodes" in data
    assert "bucket_activo" in data
    assert "total_objetos_r2" in data


def test_debug_storage_counts(admin_client, sample_content):
    resp = admin_client.get("/admin/debug-storage")
    data = resp.get_json()
    assert data["total_series"] >= 1
    assert data["total_seasons"] >= 1
    assert data["total_episodes"] >= 2


@patch("modules.storage.storage_r2.count_r2_objects", return_value=12)
@patch("modules.storage.storage_r2.test_r2_connection", return_value=(True, "Conectado"))
def test_debug_storage_r2_count(mock_test, mock_count, app, admin_client):
    app.config.update(
        STORAGE_PROVIDER="r2",
        R2_ENDPOINT="https://example.r2.cloudflarestorage.com",
        R2_ACCESS_KEY_ID="key",
        R2_SECRET_ACCESS_KEY="secret",
        R2_BUCKET_NAME="flowpremium-videos",
    )
    resp = admin_client.get("/admin/debug-storage")
    data = resp.get_json()
    assert data["total_objetos_r2"] == 12
    assert data["bucket"] == "flowpremium-videos"
