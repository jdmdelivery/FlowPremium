from sqlalchemy import case, func

from extensions import db
from modules.streaming.models import Episode, EpisodePurchase, Series, Season, WatchProgress
from modules.streaming.services.access import can_watch


def _series_badge(free_count: int, total: int) -> str:
    if total <= 0:
        return "free"
    if free_count == total:
        return "free"
    if free_count == 0:
        return "premium"
    return "mixed"


def _episode_stats_by_series() -> dict[int, dict]:
    """One query: episode counts per series (avoids N+1 on home)."""
    rows = (
        db.session.query(
            Episode.series_id,
            func.count(Episode.id).label("total"),
            func.sum(case((Episode.is_free.is_(True), 1), else_=0)).label("free_count"),
            func.min(Episode.id).label("first_ep_id"),
        )
        .filter(Episode.is_active.is_(True))
        .group_by(Episode.series_id)
        .all()
    )
    out: dict[int, dict] = {}
    for row in rows:
        out[row.series_id] = {
            "total": int(row.total or 0),
            "free_count": int(row.free_count or 0),
            "first_ep_id": row.first_ep_id,
        }
    return out


def _first_thumbnails_by_series() -> dict[int, str]:
    """First non-null thumbnail per series in one query."""
    subq = (
        db.session.query(
            Episode.series_id,
            func.min(Episode.id).label("min_id"),
        )
        .filter(Episode.is_active.is_(True), Episode.thumbnail_url.isnot(None))
        .group_by(Episode.series_id)
        .subquery()
    )
    rows = (
        db.session.query(Episode.series_id, Episode.thumbnail_url)
        .join(
            subq,
            (Episode.series_id == subq.c.series_id) & (Episode.id == subq.c.min_id),
        )
        .all()
    )
    return {sid: thumb for sid, thumb in rows if thumb}


def enrich_series(series: Series, stats: dict, first_thumbs: dict) -> dict:
    st = stats.get(series.id, {})
    total = st.get("total", 0)
    free_count = st.get("free_count", 0)
    first_thumb = first_thumbs.get(series.id)
    card_key = series.thumbnail_url or series.hero_image_url or series.cover_image or first_thumb
    hero_key = series.hero_image_url or series.thumbnail_url or series.cover_image or first_thumb
    return {
        "series": series,
        "episode_count": total,
        "badge": _series_badge(free_count, total),
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
    stats = _episode_stats_by_series()
    first_thumbs = _first_thumbnails_by_series()
    cards = [enrich_series(s, stats, first_thumbs) for s in all_series]

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

    premium_scores = {
        sid: int(st.get("total", 0)) - int(st.get("free_count", 0))
        for sid, st in stats.items()
    }
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
        ep_ids = [p.episode_id for p in progresses]
        episodes = {}
        if ep_ids:
            for ep in Episode.query.filter(
                Episode.id.in_(ep_ids), Episode.is_active.is_(True)
            ).all():
                episodes[ep.id] = ep
        for prog in progresses:
            ep = episodes.get(prog.episode_id)
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
