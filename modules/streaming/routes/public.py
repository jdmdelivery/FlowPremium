from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_required

from extensions import db
from modules.streaming.models import Episode, EpisodePurchase, Payment, Season, Series, Subscription
from modules.streaming.services.access import can_watch, get_episode_access_status, get_watch_progress
from modules.streaming.services.payment import admin_grant_episode, admin_grant_subscription, purchase_episode
from modules.streaming.services.stream import get_episode_stream_url, stream_episode_video
from modules.streaming.services.audio_tracks import build_audio_manifest
from modules.streaming.services.playback_manifest import build_playback_manifest, is_episode_playable
from modules.streaming.services.subtitle_diagnostics import log_episode_subtitle_state
from modules.streaming.services.subtitle_manifest import build_subtitle_manifest
from modules.streaming.services.home import get_home_sections, get_next_episode

streaming_bp = Blueprint("streaming", __name__, url_prefix="/streaming")


@streaming_bp.route("/")
def index():
    sections = get_home_sections(current_user)
    return render_template("streaming/index.html", **sections)


@streaming_bp.route("/serie/<int:series_id>")
def series_detail(series_id):
    series = Series.query.filter_by(id=series_id, is_active=True).first_or_404()
    seasons = (
        Season.query.filter_by(series_id=series_id, is_active=True)
        .order_by(Season.season_number)
        .all()
    )
    episodes_by_season = {}
    for season in seasons:
        eps = (
            Episode.query.filter_by(season_id=season.id, is_active=True)
            .order_by(Episode.id)
            .all()
        )
        episodes_by_season[season.id] = [
            {
                "episode": ep,
                "status": get_episode_access_status(current_user, ep),
            }
            for ep in eps
        ]
    return render_template(
        "streaming/series_detail.html",
        series=series,
        seasons=seasons,
        episodes_by_season=episodes_by_season,
    )


@streaming_bp.route("/watch/<int:episode_id>")
def watch(episode_id):
    episode = Episode.query.filter_by(id=episode_id, is_active=True).first_or_404()
    if not can_watch(current_user, episode):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=url_for("streaming.watch", episode_id=episode_id)))
        flash("No tienes acceso / No access", "error")
        return redirect(url_for("streaming.series_detail", series_id=episode.series_id))
    if not is_episode_playable(episode):
        flash(
            "Este video se está procesando. Vuelve en unos minutos.",
            "warning",
        )
        return redirect(url_for("streaming.series_detail", series_id=episode.series_id))

    progress = get_watch_progress(current_user, episode_id) if current_user.is_authenticated else None
    log_episode_subtitle_state(episode, context="watch")
    playback_manifest = build_playback_manifest(episode)
    subtitle_manifest = build_subtitle_manifest(episode)
    next_episode = get_next_episode(episode)
    next_access = get_episode_access_status(current_user, next_episode) if next_episode else None
    return render_template(
        "streaming/watch.html",
        episode=episode,
        progress=progress,
        next_episode=next_episode,
        next_access=next_access,
        stream_url=get_episode_stream_url(current_user, episode),
        subtitle_manifest=subtitle_manifest,
        audio_manifest=build_audio_manifest(episode),
        playback_manifest=playback_manifest,
        progress_url=url_for("streaming_api.api_progress"),
    )


@streaming_bp.route("/my-purchases")
@login_required
def my_purchases():
    purchases = (
        EpisodePurchase.query.filter_by(user_id=current_user.id)
        .order_by(EpisodePurchase.purchased_at.desc())
        .all()
    )
    sub = (
        Subscription.query.filter_by(user_id=current_user.id, is_active=True)
        .order_by(Subscription.expires_at.desc())
        .first()
    )
    return render_template("streaming/my_purchases.html", purchases=purchases, subscription=sub)


@streaming_bp.route("/purchase/<int:episode_id>", methods=["POST"])
@login_required
def purchase(episode_id):
    episode = Episode.query.get_or_404(episode_id)
    result = purchase_episode(current_user, episode)
    if result.get("checkout_url"):
        return redirect(result["checkout_url"])
    flash(result.get("message", ""), "success" if result.get("success") else "warning")
    if result.get("success"):
        return redirect(url_for("streaming.watch", episode_id=episode.id))
    return redirect(url_for("streaming.series_detail", series_id=episode.series_id))


@streaming_bp.route("/checkout/<int:episode_id>")
@login_required
def episode_checkout(episode_id):
    from modules.payments.services.billing import cashapp_pay_url, is_cashapp_configured
    from modules.payments.services.paypal_service import is_paypal_configured

    episode = Episode.query.filter_by(id=episode_id, is_active=True).first_or_404()
    if episode.is_free:
        flash("Este episodio es gratis / This episode is free", "success")
        return redirect(url_for("streaming.watch", episode_id=episode.id))

    existing = EpisodePurchase.query.filter_by(
        user_id=current_user.id, episode_id=episode.id
    ).first()
    if existing:
        flash("Ya comprado / Already purchased", "success")
        return redirect(url_for("streaming.watch", episode_id=episode.id))

    paypal_ok = is_paypal_configured()
    cashapp_ok = is_cashapp_configured()
    if not paypal_ok and not cashapp_ok:
        flash("No hay métodos de pago configurados / No payment methods configured", "error")
        return redirect(url_for("streaming.series_detail", series_id=episode.series_id))

    cashapp_tag = current_app.config.get("CASHAPP_TAG") or ""
    cashtag = cashapp_tag if cashapp_tag.startswith("$") else f"${cashapp_tag}" if cashapp_tag else ""

    return render_template(
        "streaming/episode_checkout.html",
        episode=episode,
        paypal_client_id=current_app.config.get("PAYPAL_CLIENT_ID") if paypal_ok else None,
        paypal_enabled=paypal_ok,
        cashapp_enabled=cashapp_ok,
        cashapp_tag=cashtag,
        cashapp_url=cashapp_pay_url(cashapp_tag),
    )


@streaming_bp.route("/checkout/<int:episode_id>/cashapp", methods=["POST"])
@login_required
def episode_cashapp_submit(episode_id):
    from modules.payments.services.billing import submit_episode_cashapp_payment

    episode = Episode.query.filter_by(id=episode_id, is_active=True).first_or_404()
    try:
        payment = submit_episode_cashapp_payment(
            current_user,
            episode,
            customer_name=request.form.get("customer_name"),
            customer_email=request.form.get("customer_email"),
            reference=request.form.get("reference"),
            screenshot_file=request.files.get("screenshot"),
        )
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("streaming.episode_checkout", episode_id=episode.id))

    flash(
        "Pago Cash App registrado como pendiente. El administrador lo verificará pronto.",
        "success",
    )
    return redirect(url_for("streaming.series_detail", series_id=episode.series_id))
