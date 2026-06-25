import os
from pathlib import Path

from flask import Flask, redirect, request, session, url_for

from config import get_config_class, validate_production_config
from extensions import db, login_manager
from models import get_user_by_id

import logging

logging.basicConfig(level=logging.INFO)


def ensure_database(app: Flask) -> None:
    """Create stream_* tables if missing; never drop existing data."""
    from modules.db.bootstrap import init_database

    init_database(app)


def create_app(config_class=None):
    if config_class is None:
        config_class = get_config_class()
    validate_production_config(config_class)

    app = Flask(__name__)
    app.config.from_object(config_class)

    from config import ProductionConfig, _engine_options
    from modules.db.diagnostics import resolve_app_database_uri, get_database_type

    if not app.config.get("TESTING"):
        production = config_class is ProductionConfig
        db_uri = resolve_app_database_uri(production=production)
        app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = _engine_options(db_uri)

    from utils.runtime_env import is_render, must_use_r2_storage

    media_folders = [app.config["SERIES_COVER_FOLDER"]]
    if not must_use_r2_storage():
        media_folders = [
            app.config["VIDEO_FOLDER"],
            app.config["THUMBNAIL_FOLDER"],
            app.config["SERIES_COVER_FOLDER"],
        ]
    for folder in media_folders:
        Path(folder).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        ensure_database(app)
        if is_render() and get_database_type(app.config.get("SQLALCHEMY_DATABASE_URI", "")) != "postgresql":
            raise RuntimeError("Render deploy must use PostgreSQL via DATABASE_URL.")

        if not app.config.get("TESTING"):
            from modules.streaming.services.memory_diagnostics import log_memory

            log_memory("app_startup")

    @login_manager.user_loader
    def load_user(user_id):
        return get_user_by_id(user_id)

    from routes.auth import auth_bp
    from routes.legal import legal_bp
    from modules.streaming.routes.public import streaming_bp
    from modules.streaming.routes.api import streaming_api_bp
    from modules.streaming.routes.admin import streaming_admin_bp
    from modules.payments.routes import payments_bp
    from modules.storage.routes import storage_admin_bp
    from modules.db.routes import db_admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(legal_bp)
    app.register_blueprint(streaming_bp)
    app.register_blueprint(streaming_api_bp)
    app.register_blueprint(streaming_admin_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(storage_admin_bp)
    app.register_blueprint(db_admin_bp)

    @app.route("/")
    def home():
        return redirect(url_for("streaming.index"))

    @app.route("/health")
    def health():
        from modules.streaming.services.memory_diagnostics import memory_snapshot

        payload = {"status": "ok"}
        if request.args.get("mem") == "1":
            snap = memory_snapshot()
            payload["memory"] = {
                "rss_mb": snap.get("rss_mb"),
                "mem_available_mb": (
                    int(snap["mem_available_kb"] / 1024)
                    if snap.get("mem_available_kb")
                    else None
                ),
                "mem_total_mb": (
                    int(snap["mem_total_kb"] / 1024) if snap.get("mem_total_kb") else None
                ),
            }
        return payload

    @app.route("/set-locale/<locale>")
    def set_locale(locale):
        if locale in app.config["SUPPORTED_LOCALES"]:
            session["locale"] = locale
        return redirect(request.referrer or url_for("streaming.index"))

    @app.route("/media/<path:filepath>")
    def serve_media(filepath):
        """Public route for images only (covers/thumbnails). Videos use protected stream API."""
        from flask import abort, send_file
        from modules.streaming.upload import resolve_storage_path
        if "videos" in filepath.replace("\\", "/"):
            abort(403)
        try:
            full_path = resolve_storage_path(filepath)
        except (ValueError, FileNotFoundError):
            abort(404)
        return send_file(full_path)

    @app.context_processor
    def inject_i18n():
        from flask import current_app
        from utils.i18n import get_all_translations, get_locale, t
        from utils.media import (
            episode_thumbnail_url,
            media_url,
            series_card_url,
            series_hero_url,
        )
        return {
            "t": t,
            "locale": get_locale(),
            "translations": get_all_translations(),
            "media_url": media_url,
            "series_card_url": series_card_url,
            "series_hero_url": series_hero_url,
            "episode_thumbnail_url": episode_thumbnail_url,
            "adsense_slots_enabled": current_app.config.get("ADSENSE_SLOTS_ENABLED", False),
        }

    from utils.i18n import t as translate_fn
    app.jinja_env.globals["t"] = translate_fn

    @app.errorhandler(413)
    def request_entity_too_large(_error):
        from flask import flash, redirect, url_for

        max_mb = app.config.get("MAX_VIDEO_SIZE", 0) // (1024 * 1024)
        flash(
            f"Archivo demasiado grande / File too large (max {max_mb} MB on this server).",
            "error",
        )
        return redirect(request.referrer or url_for("streaming_admin.episodes_list"))

    @app.context_processor
    def inject_upload_limits():
        max_bytes = app.config.get("MAX_VIDEO_SIZE", 500 * 1024 * 1024)
        return {"max_video_mb": max(1, max_bytes // (1024 * 1024))}

    @app.cli.command("init-db")
    def init_db():
        with app.app_context():
            ensure_database(app)
        print("Database initialized.")

    return app


app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "1").lower() in ("1", "true", "yes")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug, host="0.0.0.0", port=port)
