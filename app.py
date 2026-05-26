import os
from pathlib import Path

from flask import Flask, redirect, request, session, url_for

from config import get_config_class, validate_production_config
from extensions import db, login_manager
from models.user import User


def ensure_database(app: Flask) -> None:
    """Create SQLite/Postgres tables if they do not exist yet."""
    import modules.streaming.models  # noqa: F401

    db.create_all()
    if app.config.get("TESTING"):
        return
    seed = os.environ.get("SEED_DEFAULT_USERS", "true").lower() in ("1", "true", "yes")
    if seed:
        from utils.seed_users import ensure_default_users

        ensure_default_users()


def create_app(config_class=None):
    if config_class is None:
        config_class = get_config_class()
    validate_production_config(config_class)

    app = Flask(__name__)
    app.config.from_object(config_class)

    # DATABASE_URL optional: PostgreSQL if set, else sqlite:///flowpremium.db
    if not app.config.get("TESTING"):
        db_url = os.environ.get("DATABASE_URL")
        if db_url and db_url.lower() not in ("null", "none", ""):
            from config import _normalize_database_url

            app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_database_url(db_url)
        else:
            app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///flowpremium.db"

    for folder in (
        app.config["VIDEO_FOLDER"],
        app.config["THUMBNAIL_FOLDER"],
        app.config["SERIES_COVER_FOLDER"],
    ):
        Path(folder).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        ensure_database(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from routes.auth import auth_bp
    from modules.streaming.routes.public import streaming_bp
    from modules.streaming.routes.api import streaming_api_bp
    from modules.streaming.routes.admin import streaming_admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(streaming_bp)
    app.register_blueprint(streaming_api_bp)
    app.register_blueprint(streaming_admin_bp)

    @app.route("/")
    def home():
        return redirect(url_for("streaming.index"))

    @app.route("/health")
    def health():
        return {"status": "ok"}

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
        from utils.i18n import get_all_translations, get_locale, t
        return {"t": t, "locale": get_locale(), "translations": get_all_translations()}

    from utils.i18n import t as translate_fn
    app.jinja_env.globals["t"] = translate_fn

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
