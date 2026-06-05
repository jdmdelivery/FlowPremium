from flask import Blueprint, flash, redirect, render_template, request, url_for

from extensions import db
from models.user import User
from modules.streaming.models import Episode, EpisodePurchase, Payment, Season, Series, Subscription
from modules.db.diagnostics import get_catalog_counts
from modules.streaming.services.episode_delete import delete_episode
from modules.streaming.services.episode_form import _episode_form_context
from modules.streaming.services.series_delete import delete_series
from modules.streaming.services.payment import admin_grant_episode, admin_grant_subscription
from modules.streaming.services.validation import EpisodeValidationError, validate_episode_series_season
from modules.streaming.upload import delete_series_media, save_series_cover
from utils.auth import admin_required

streaming_admin_bp = Blueprint("streaming_admin", __name__, url_prefix="/admin/streaming")


@streaming_admin_bp.route("/")
@admin_required
def dashboard():
    counts = get_catalog_counts()
    stats = {
        "series": counts["total_series"],
        "episodes": counts["total_episodes"],
        "purchases": EpisodePurchase.query.count(),
        "payments": Payment.query.filter_by(status="paid").count(),
    }
    return render_template("streaming/admin/dashboard.html", stats=stats)


@streaming_admin_bp.route("/series")
@admin_required
def series_list():
    items = Series.query.order_by(Series.created_at.desc()).all()
    return render_template("streaming/admin/series_list.html", series_list=items)


@streaming_admin_bp.route("/series/new", methods=["GET", "POST"])
@streaming_admin_bp.route("/series/<int:series_id>/edit", methods=["GET", "POST"])
@admin_required
def series_form(series_id=None):
    series = Series.query.get(series_id) if series_id else None
    if request.method == "POST":
        if not series:
            series = Series()
        series.title = request.form.get("title", "").strip()
        series.description = request.form.get("description", "").strip()
        series.is_active = request.form.get("is_active") == "on"

        db.session.add(series)
        db.session.flush()

        cover = request.files.get("cover_image")
        if cover and cover.filename:
            try:
                if series.hero_image_url or series.thumbnail_url or series.cover_image:
                    delete_series_media(series)
                hero_key, thumb_key = save_series_cover(cover, series.id)
                series.hero_image_url = hero_key
                series.thumbnail_url = thumb_key
                series.cover_image = None
            except ValueError as e:
                flash(str(e), "error")
                return render_template("streaming/admin/series_form.html", series=series)

        db.session.commit()
        flash("Serie guardada / Series saved", "success")
        return redirect(url_for("streaming_admin.series_list"))
    return render_template("streaming/admin/series_form.html", series=series)


@streaming_admin_bp.route("/series/<int:series_id>/delete", methods=["POST"])
@admin_required
def series_delete(series_id):
    from utils.i18n import t

    if delete_series(series_id):
        flash(t("series_deleted"), "success")
    else:
        flash("Serie no encontrada / Series not found", "error")
    return redirect(url_for("streaming_admin.series_list"))


@streaming_admin_bp.route("/series/<int:series_id>/seasons", methods=["GET", "POST"])
@admin_required
def seasons_manage(series_id):
    series = Series.query.get_or_404(series_id)
    if request.method == "POST":
        season = Season(
            series_id=series_id,
            title=request.form.get("title", "").strip(),
            season_number=int(request.form.get("season_number", 1)),
            description=request.form.get("description", "").strip(),
            is_active=request.form.get("is_active") == "on",
        )
        db.session.add(season)
        db.session.commit()
        flash("Temporada creada / Season created", "success")
        return redirect(url_for("streaming_admin.seasons_manage", series_id=series_id))
    seasons = Season.query.filter_by(series_id=series_id).order_by(Season.season_number).all()
    return render_template("streaming/admin/seasons.html", series=series, seasons=seasons)


@streaming_admin_bp.route("/episodes")
@admin_required
def episodes_list():
    episodes = Episode.query.order_by(Episode.created_at.desc()).all()
    return render_template("streaming/admin/episodes_list.html", episodes=episodes)


@streaming_admin_bp.route("/episodes/quick-catalog", methods=["POST"])
@admin_required
def episode_quick_catalog():
    series_title = request.form.get("series_title", "").strip()
    season_title = request.form.get("season_title", "").strip() or "Temporada 1"
    if not series_title:
        flash("El nombre de la serie es obligatorio / Series title required", "error")
        return redirect(url_for("streaming_admin.episode_form"))

    series = Series(title=series_title, is_active=True)
    db.session.add(series)
    db.session.flush()
    season = Season(
        series_id=series.id,
        title=season_title,
        season_number=1,
        is_active=True,
    )
    db.session.add(season)
    db.session.commit()
    flash("Serie y temporada creadas / Series and season created", "success")
    return redirect(
        url_for(
            "streaming_admin.episode_form",
            series_id=series.id,
            season_id=season.id,
        )
    )


@streaming_admin_bp.route("/episodes/create")
@streaming_admin_bp.route("/episodes/new", methods=["GET", "POST"])
@streaming_admin_bp.route("/episodes/<int:episode_id>/edit", methods=["GET", "POST"])
@admin_required
def episode_form(episode_id=None):
    episode = Episode.query.get(episode_id) if episode_id else None
    preselect_series_id = request.args.get("series_id", type=int)
    preselect_season_id = request.args.get("season_id", type=int)

    if request.method == "POST":
        ctx = _episode_form_context(episode, preselect_series_id, preselect_season_id)
        series_id_raw = request.form.get("series_id")
        season_id_raw = request.form.get("season_id")
        if not series_id_raw or not season_id_raw:
            flash("Selecciona serie y temporada / Select series and season", "error")
            return render_template("streaming/admin/episode_form.html", **ctx)

        try:
            series, season = validate_episode_series_season(
                int(series_id_raw), int(season_id_raw)
            )
        except EpisodeValidationError as e:
            flash(str(e), "error")
            return render_template("streaming/admin/episode_form.html", **ctx)

        if not episode:
            episode = Episode()

        episode.series_id = series.id
        episode.season_id = season.id
        episode.title = request.form.get("title", "").strip()
        episode.description = request.form.get("description", "").strip()
        episode.duration_seconds = int(request.form.get("duration_seconds") or 0)
        episode.price = float(request.form.get("price") or 0)
        episode.is_free = request.form.get("is_free") == "on"
        episode.is_active = request.form.get("is_active") == "on"

        video = request.files.get("video")
        new_video_uploaded = bool(video and video.filename)

        db.session.add(episode)
        db.session.flush()

        try:
            from modules.streaming.services.episode_admin import apply_episode_form_uploads

            upload_messages = apply_episode_form_uploads(
                episode,
                request,
                series.id,
                new_video_uploaded=new_video_uploaded,
            )
            for level, msg in upload_messages:
                flash(msg, level)
        except ValueError as e:
            flash(str(e), "error")
            return render_template("streaming/admin/episode_form.html", **ctx)

        db.session.commit()

        if new_video_uploaded and episode.video_url_r2:
            from modules.streaming.services.video_processing import enqueue_hls_job

            if enqueue_hls_job(episode.id):
                flash(
                    "Conversión HLS en segundo plano (480p/720p/1080p). El MP4 ya está disponible.",
                    "info",
                )
            from modules.streaming.services.audio_probe_episode import probe_episode_audio
            from modules.streaming.services.subtitles import enqueue_subtitle_job

            count = probe_episode_audio(episode)
            db.session.commit()
            if count > 1:
                flash(
                    f"Detectadas {count} pistas de audio en el MP4 (selector en reproductor).",
                    "info",
                )
            elif count == 1:
                flash("El MP4 tiene 1 pista de audio.", "info")
            else:
                flash(
                    "No se detectaron pistas de audio en el MP4 (verifica el archivo).",
                    "warning",
                )

            if enqueue_subtitle_job(episode.id):
                flash(
                    "Subtítulos automáticos en proceso (puede tardar varios minutos).",
                    "info",
                )

        flash("Episodio guardado / Episode saved", "success")
        return redirect(url_for("streaming_admin.episodes_list"))

    return render_template(
        "streaming/admin/episode_form.html",
        **_episode_form_context(episode, preselect_series_id, preselect_season_id),
    )


@streaming_admin_bp.route("/episodes/<int:episode_id>/regenerate-subtitles", methods=["POST"])
@admin_required
def regenerate_episode_subtitles(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    if not episode.video_url_r2:
        flash("Sube un video antes de generar subtítulos.", "error")
        return redirect(url_for("streaming_admin.episode_form", episode_id=episode_id))

    from modules.streaming.services.subtitles import enqueue_subtitle_job

    if enqueue_subtitle_job(episode.id, force=True):
        flash("Regeneración de subtítulos en español iniciada.", "info")
    else:
        flash("No se pudo iniciar la regeneración (ya en proceso o deshabilitado).", "warning")
    return redirect(url_for("streaming_admin.episode_form", episode_id=episode_id))


@streaming_admin_bp.route("/episodes/<int:episode_id>/delete", methods=["POST"])
@admin_required
def episode_delete(episode_id):
    from utils.i18n import t

    if delete_episode(episode_id):
        flash(t("video_deleted"), "success")
    else:
        flash("Episodio no encontrado / Episode not found", "error")
    return redirect(url_for("streaming_admin.episodes_list"))


@streaming_admin_bp.route("/payments", methods=["GET", "POST"])
@admin_required
def payments_manage():
    if request.method == "POST":
        action = request.form.get("action")
        user_id = int(request.form.get("user_id"))
        if action == "grant_episode":
            episode_id = int(request.form.get("episode_id"))
            admin_grant_episode(user_id, episode_id)
            flash("Acceso otorgado / Access granted", "success")
        elif action == "grant_subscription":
            days = int(request.form.get("days", 30))
            admin_grant_subscription(user_id, days)
            flash("Suscripción activada / Subscription activated", "success")

    payments = Payment.query.order_by(Payment.created_at.desc()).limit(100).all()
    purchases = EpisodePurchase.query.order_by(EpisodePurchase.purchased_at.desc()).limit(100).all()
    users = User.query.order_by(User.username).all()
    episodes = Episode.query.order_by(Episode.title).all()
    return render_template(
        "streaming/admin/payments.html",
        payments=payments,
        purchases=purchases,
        users=users,
        episodes=episodes,
    )
