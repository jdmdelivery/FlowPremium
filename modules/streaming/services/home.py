from sqlalchemy import func

from extensions import db
from modules.streaming.models import Episode, EpisodePurchase, Series, Season, WatchProgress
from modules.streaming.services.access import can_watch


def _series_badge(episodes: list) -> str:
    if not episodes:
        return "free"
    free_count = sum(1 for e in episodes if e.is_free)
    if free_count == len(episodes):
        return "free"
    if free_count == 0:
        return "premium"
    return "mixed"


def enrich_series(series: Series) -> dict:
    episodes = (
        Episode.query.filter_by(series_id=series.id, is_active=True)
        .order_by(Episode.id)
        .all()
    )
    first_thumb = next((e.thumbnail_url for e in episodes if e.thumbnail_url), None)
    card_key = series.thumbnail_url or series.hero_image_url or series.cover_image or first_thumb
    hero_key = series.hero_image_url or series.thumbnail_url or series.cover_image or first_thumb
    return {
        "series": series,
        "episode_count": len(episodes),
        "badge": _series_badge(episodes),
        "card_image_key": card_key,
        "hero_image_key": hero_key,
    }


def get_next_episode(episode: Episode) -> Episode | None:
    nxt = (
        Episode.query.filter(
            Episode.season_id == episode.season_id,
            Episode.is_active.is_(True),
            Episode.id > episode.id,
        )
        .order_by(Episode.id)
        .first()
    )
    if nxt:
        return nxt

    season = Season.query.get(episode.season_id)
    if not season:
        return None

    next_season = (
        Season.query.filter(
            Season.series_id == episode.series_id,
            Season.is_active.is_(True),
            Season.season_number > season.season_number,
        )
        .order_by(Season.season_number)
        .first()
    )
    if not next_season:
        return None

    return (
        Episode.query.filter_by(season_id=next_season.id, is_active=True)
        .order_by(Episode.id)
        .first()
    )


def get_home_sections(user) -> dict:
    all_series = Series.query.filter_by(is_active=True).order_by(Series.created_at.desc()).all()
    cards = [enrich_series(s) for s in all_series]

    featured = cards[0] if cards else None
    recently_added = cards[:12]

    purchase_counts = dict(
        db.session.query(Episode.series_id, func.count(EpisodePurchase.id))
        .join(Episode, Episode.id == EpisodePurchase.episode_id)
        .group_by(Episode.series_id)
        .all()
    )
    trending = sorted(
        cards,
        key=lambda c: purchase_counts.get(c["series"].id, 0),
        reverse=True,
    )[:12]

    premium_scores = {}
    for card in cards:
        sid = card["series"].id
        premium_scores[sid] = Episode.query.filter_by(
            series_id=sid, is_active=True, is_free=False
        ).count()
    top_premium = sorted(
        cards,
        key=lambda c: premium_scores.get(c["series"].id, 0),
        reverse=True,
    )[:12]

    continue_watching = []
    if user and getattr(user, "is_authenticated", False):
        progresses = (
            WatchProgress.query.filter_by(user_id=user.id, completed=False)
            .order_by(WatchProgress.updated_at.desc())
            .limit(12)
            .all()
        )
        for prog in progresses:
            ep = Episode.query.filter_by(id=prog.episode_id, is_active=True).first()
            if ep and can_watch(user, ep):
                pct = 0
                if ep.duration_seconds and ep.duration_seconds > 0:
                    pct = min(100, int(prog.position_seconds / ep.duration_seconds * 100))
                continue_watching.append(
                    {
                        "episode": ep,
                        "series": ep.series,
                        "progress": prog,
                        "progress_pct": pct,
                    }
                )

    return {
        "featured": featured,
        "recently_added": recently_added,
        "trending": trending,
        "top_premium": top_premium,
        "continue_watching": continue_watching,
        "all_cards": cards,
    }
