"""Admin database diagnostics routes."""

import logging

from flask import Blueprint, jsonify

from modules.db.diagnostics import get_debug_db_info, get_debug_storage_info
from utils.media import get_series_media_debug
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


@db_admin_bp.route("/debug-storage")
@admin_required
def debug_storage():
    try:
        return jsonify(get_debug_storage_info())
    except Exception as exc:
        logger.exception("debug-storage failed")
        return jsonify(
            {
                "postgresql_conectado": "NO",
                "total_series": 0,
                "total_seasons": 0,
                "total_episodes": 0,
                "bucket_activo": "NO",
                "total_objetos_r2": 0,
                "error": str(exc),
            }
        ), 200


@db_admin_bp.route("/debug-media/<int:series_id>")
@admin_required
def debug_media(series_id: int):
    try:
        return jsonify(get_series_media_debug(series_id))
    except Exception as exc:
        logger.exception("debug-media failed")
        return jsonify({"series_id": series_id, "error": str(exc)}), 200
