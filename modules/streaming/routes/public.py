from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, current_app
from flask_login import current_user, login_required

from extensions import db
from modules.streaming.models import Episode, EpisodePurchase, Payment, Season, Series, Subscription
from modules.streaming.services.access import can_watch, get_episode_access_status, get_watch_progress
from modules.streaming.services.payment import admin_grant_episode, admin_grant_subscription, purchase_episode
from modules.streaming.services.stream import stream_episode_video
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
    progress = get_watch_progress(current_user, episode_id) if current_user.is_authenticated else None
    next_episode = get_next_episode(episode)
    next_access = get_episode_access_status(current_user, next_episode) if next_episode else None
    return render_template(
        "streaming/watch.html",
        episode=episode,
        progress=progress,
        next_episode=next_episode,
        next_access=next_access,
        stream_url=url_for("streaming_api.stream_video", episode_id=episode_id),
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

    if not is_paypal_configured():
        flash("PayPal no está configurado / PayPal not configured", "error")
        return redirect(url_for("streaming.series_detail", series_id=episode.series_id))

    return render_template(
        "streaming/episode_checkout.html",
        episode=episode,
        paypal_client_id=current_app.config.get("PAYPAL_CLIENT_ID"),
    )
