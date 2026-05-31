"""Admin database diagnostics routes."""

import logging

from flask import Blueprint, jsonify

from modules.db.diagnostics import get_debug_db_info
from utils.auth import admin_required

logger = logging.getLogger(__name__)

db_admin_bp = Blueprint("db_admin", __name__, url_prefix="/admin")


@db_admin_bp.route("/debug-db")
@admin_required
def debug_db():
    try:
        return jsonify(get_debug_db_info())
    except Exception as exc:
        logger.exception("debug-db failed")
        return jsonify(
            {
                "database_type": "unknown",
                "database_url_detected": False,
                "total_series": 0,
                "total_seasons": 0,
                "total_episodes": 0,
                "error": str(exc),
            }
        ), 200
