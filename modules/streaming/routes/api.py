from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from modules.streaming.models import Episode, Series
from modules.streaming.services.access import can_watch, get_episode_access_status
from modules.streaming.services.payment import purchase_episode
from modules.streaming.services.stream import save_progress, stream_episode_video
from modules.streaming.services.audio_tracks import build_audio_manifest
from modules.streaming.services.subtitle_manifest import build_subtitle_manifest
from modules.streaming.services.subtitle_stream import stream_episode_subtitles
from utils.media import media_url

streaming_api_bp = Blueprint("streaming_api", __name__, url_prefix="/api/streaming")


@streaming_api_bp.route("/series")
def list_series():
    series = Series.query.filter_by(is_active=True).order_by(Series.created_at.desc()).all()
    return jsonify([
        {
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "cover_image": s.cover_image,
            "thumbnail_url": s.thumbnail_url,
            "hero_image_url": s.hero_image_url,
            "card_image_url": media_url(s.card_image_key()),
        }
        for s in series
    ])


@streaming_api_bp.route("/episodes")
def list_episodes():
    series_id = request.args.get("series_id", type=int)
    q = Episode.query.filter_by(is_active=True)
    if series_id:
        q = q.filter_by(series_id=series_id)
    episodes = q.order_by(Episode.id).all()
    return jsonify([
        {
            "id": ep.id,
            "series_id": ep.series_id,
            "season_id": ep.season_id,
            "title": ep.title,
            "description": ep.description,
            "thumbnail": ep.thumbnail_url,
            "price": ep.price,
            "is_free": ep.is_free,
            "duration_seconds": ep.duration_seconds,
            "access": get_episode_access_status(current_user, ep),
        }
        for ep in episodes
    ])


@streaming_api_bp.route("/purchase", methods=["POST"])
@login_required
def api_purchase():
    data = request.get_json(silent=True) or {}
    episode_id = data.get("episode_id") or request.form.get("episode_id", type=int)
    episode = Episode.query.get_or_404(episode_id)
    result = purchase_episode(current_user, episode)
    return jsonify(result)


@streaming_api_bp.route("/progress", methods=["POST"])
@login_required
def api_progress():
    data = request.get_json(silent=True) or request.form
    episode_id = int(data.get("episode_id", 0))
    position = int(data.get("position_seconds", 0))
    completed = bool(data.get("completed", False))
    if not episode_id:
        return jsonify({"error": "episode_id required"}), 400
    progress = save_progress(current_user, episode_id, position, completed)
    return jsonify({
        "episode_id": episode_id,
        "position_seconds": progress.position_seconds,
        "completed": progress.completed,
    })


@streaming_api_bp.route("/stream/<int:episode_id>", methods=["GET", "HEAD"])
def stream_video(episode_id):
    episode = Episode.query.filter_by(id=episode_id, is_active=True).first_or_404()
    if not can_watch(current_user, episode):
        return jsonify({"error": "Forbidden"}), 403
    return stream_episode_video(current_user, episode)


@streaming_api_bp.route("/audio-tracks/<int:episode_id>")
def audio_tracks(episode_id):
    episode = Episode.query.filter_by(id=episode_id, is_active=True).first_or_404()
    if not can_watch(current_user, episode):
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(build_audio_manifest(episode))


@streaming_api_bp.route("/subtitles-manifest/<int:episode_id>")
def subtitles_manifest(episode_id):
    episode = Episode.query.filter_by(id=episode_id, is_active=True).first_or_404()
    if not can_watch(current_user, episode):
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(build_subtitle_manifest(episode))


@streaming_api_bp.route("/subtitles/<int:episode_id>", methods=["GET", "HEAD"])
def stream_subtitles(episode_id):
    episode = Episode.query.filter_by(id=episode_id, is_active=True).first_or_404()
    return stream_episode_subtitles(current_user, episode)
