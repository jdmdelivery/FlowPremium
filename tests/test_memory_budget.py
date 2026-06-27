"""Verify process RSS stays under the Render Starter memory budget."""

from __future__ import annotations

import gc

import pytest

from modules.streaming.services.memory_diagnostics import memory_snapshot, rss_mb

MEMORY_BUDGET_MB = 350


def _require_rss():
    snap = memory_snapshot()
    rss = snap.get("rss_mb")
    if rss is None:
        pytest.skip("psutil / RSS not available on this platform")
    return rss


def test_baseline_rss_under_budget():
    rss = _require_rss()
    assert rss < MEMORY_BUDGET_MB, f"baseline rss_mb={rss} exceeds {MEMORY_BUDGET_MB}"


def test_health_requests_stay_under_budget(client):
    baseline = _require_rss()
    for _ in range(10):
        resp = client.get("/health?mem=1")
        assert resp.status_code == 200
    gc.collect()
    after = rss_mb()
    assert after is not None
    assert after < MEMORY_BUDGET_MB, f"rss_mb={after} after health loop"
    assert after - baseline < 80, f"rss grew by {after - baseline} MB during health checks"


def test_home_page_stays_under_budget(client, sample_content):
    _require_rss()
    resp = client.get("/streaming/")
    assert resp.status_code == 200
    gc.collect()
    after = rss_mb()
    assert after is not None
    assert after < MEMORY_BUDGET_MB, f"rss_mb={after} after home page"


def test_payment_totals_sql_not_loading_all_rows(app):
    """Regression: payment_totals must aggregate in SQL."""
    from unittest.mock import MagicMock, patch

    from modules.payments.services.billing import payment_totals

    with app.app_context():
        with patch("modules.payments.services.billing.db.session") as mock_session:
            mock_session.query.return_value.filter.return_value.scalar.side_effect = [
                10.0,
                50.0,
            ]
            totals = payment_totals()
            assert totals == {"day": 10.0, "month": 50.0}
            assert not mock_session.query.return_value.filter.return_value.all.called
