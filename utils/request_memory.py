"""Per-request RSS logging and SQLAlchemy session cleanup."""

from __future__ import annotations

import gc
import logging

from flask import Flask, g, request

logger = logging.getLogger(__name__)


def init_request_memory_hooks(app: Flask) -> None:
    """Log RSS per request (psutil) and always remove the DB session."""

    @app.before_request
    def _memory_before_request():
        from modules.streaming.services.memory_diagnostics import rss_mb

        g._mem_rss_start = rss_mb()

    @app.after_request
    def _memory_after_request(response):
        if app.config.get("MEMORY_LOG_REQUESTS"):
            from modules.streaming.services.memory_diagnostics import rss_mb

            start = getattr(g, "_mem_rss_start", None)
            end = rss_mb()
            delta = None
            if start is not None and end is not None:
                delta = end - start
            budget = int(app.config.get("MEMORY_BUDGET_MB", 350))
            logger.info(
                "[memory] request method=%s path=%s status=%s rss_mb=%s delta_mb=%s",
                request.method,
                request.path,
                response.status_code,
                end if end is not None else "-",
                delta if delta is not None else "-",
            )
            if end is not None and end > budget:
                logger.warning(
                    "[memory] over_budget rss_mb=%s budget_mb=%s path=%s",
                    end,
                    budget,
                    request.path,
                )
        return response

    @app.teardown_appcontext
    def _teardown_db_session(_exc=None):
        from extensions import db

        db.session.remove()
        if app.config.get("MEMORY_GC_AFTER_REQUEST"):
            gc.collect()
