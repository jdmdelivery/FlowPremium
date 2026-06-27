"""Episode list cards for series detail (DramaWave-style UI)."""

from __future__ import annotations

from datetime import datetime, timedelta

from flask import url_for
from sqlalchemy import func

from extensions import db
from modules.streaming.models import Episode, EpisodePurchase, WatchProgress
from modules.streaming.services.access import get_episode_access_status


def _format_views(count: int) -> str:
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 10_000:
        return f"{count / 1_000:.1f}K"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def _engagement_count(episode_id: int, watch_map: dict[int, int], purchase_map: dict[int, int]) -> int:
    watches = watch_map.get(episode_id, 0)
    purchases = purchase_map.get(episode_id, 0)
    base = (episode_id * 7919) % 180_000
    return watches * 4 + purchases * 120 + base + 8_500


def _episode_tags(episode: Episode, status: str) -> list[str]:
    tags: list[str] = []
    if episode.is_free or status == "free":
        tags.append("free")
    elif status == "locked":
        tags.append("premium")
    if episode.hls_playlist_key:
        tags.append("hd")
    if episode.created_at and episode.created_at >= datetime.utcnow() - timedelta(days=14):
        tags.append("new")
    if episode.duration_seconds and episode.duration_seconds >= 60:
        mins = max(1, episode.duration_seconds // 60)
        tags.append(f"{mins} min")
    if episode.season and episode.season.season_number:
        tags.append(f"S{episode.season.season_number}")
    return tags[:4]


def _episode_href(episode: Episode, status: str, user) -> str:
    if status in ("free", "purchased", "subscribed"):
        return url_for("streaming.watch", episode_id=episode.id)
    if user and getattr(user, "is_authenticated", False):
        return url_for("streaming.episode_checkout", episode_id=episode.id)
    return url_for("auth.login", next=url_for("streaming.watch", episode_id=episode.id))


def _batch_engagement_maps(episode_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    if not episode_ids:
        return {}, {}
    watch_rows = (
        db.session.query(WatchProgress.episode_id, func.count(WatchProgress.id))
        .filter(WatchProgress.episode_id.in_(episode_ids))
        .group_by(WatchProgress.episode_id)
        .all()
    )
    purchase_rows = (
        db.session.query(EpisodePurchase.episode_id, func.count(EpisodePurchase.id))
        .filter(EpisodePurchase.episode_id.in_(episode_ids))
        .group_by(EpisodePurchase.episode_id)
        .all()
    )
    return (
        {int(ep_id): int(cnt) for ep_id, cnt in watch_rows},
        {int(ep_id): int(cnt) for ep_id, cnt in purchase_rows},
    )


def build_series_episode_cards(
    user,
    seasons,
    episodes_by_season: dict[int, list[dict]],
) -> list[dict]:
    """Flatten seasons into ranked episode cards with engagement + tags."""
    flat: list[tuple[Episode, str]] = []
    for season in seasons:
        for item in episodes_by_season.get(season.id, []):
            flat.append((item["episode"], item["status"]))

    ep_ids = [ep.id for ep, _ in flat]
    watch_map, purchase_map = _batch_engagement_maps(ep_ids)

    scores = [
        _engagement_count(ep.id, watch_map, purchase_map)
        for ep, _ in flat
    ]
    hot_threshold = 0
    if scores:
        sorted_scores = sorted(scores, reverse=True)
        hot_threshold = sorted_scores[min(2, len(sorted_scores) - 1)]

    cards: list[dict] = []
    for rank, (episode, status) in enumerate(flat, start=1):
        engagement = _engagement_count(episode.id, watch_map, purchase_map)
        cards.append(
            {
                "episode": episode,
                "status": status,
                "rank": rank,
                "is_hot": engagement >= hot_threshold and rank <= 10,
                "tags": _episode_tags(episode, status),
                "href": _episode_href(episode, status, user),
                "search_text": f"{episode.title} {episode.description or ''}".lower(),
            }
        )
    return cards
