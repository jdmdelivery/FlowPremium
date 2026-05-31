"""Admin storage diagnostics."""

import logging

from flask import Blueprint, jsonify

from modules.storage.storage_r2 import get_storage_status, test_r2_connection
from utils.auth import admin_required

logger = logging.getLogger(__name__)

storage_admin_bp = Blueprint("storage_admin", __name__, url_prefix="/admin")


@storage_admin_bp.route("/storage-status")
@admin_required
def storage_status():
    try:
        return jsonify(get_storage_status())
    except Exception as exc:
        logger.exception("storage-status failed")
        return jsonify(
            {
                "provider": "r2",
                "configured": False,
                "connected": False,
                "r2_connected": False,
                "bucket": "",
                "bucket_active": False,
                "series_count": 0,
                "episodes_count": 0,
                "total_series": 0,
                "total_episodes": 0,
                "message": f"No se pudo obtener el estado de R2: {exc}",
            }
        ), 200


@storage_admin_bp.route("/storage/test-r2", methods=["POST"])
@admin_required
def test_r2():
    try:
        ok, message = test_r2_connection()
    except Exception as exc:
        logger.exception("test-r2 failed")
        ok = False
        message = str(exc)
    return jsonify(
        {
            "ok": ok,
            "connected": ok,
            "message": "✅ Conectado" if ok else f"❌ Error de conexión: {message}",
        }
    )
