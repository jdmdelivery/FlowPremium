from datetime import datetime

from modules.streaming.models import Episode, EpisodePurchase, Subscription, WatchProgress


def has_active_subscription(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    sub = (
        Subscription.query.filter_by(user_id=user.id, is_active=True)
        .order_by(Subscription.expires_at.desc())
        .first()
    )
    return sub is not None and sub.is_valid


def has_episode_purchase(user, episode_id: int) -> bool:
    if not user or not user.is_authenticated:
        return False
    return (
        EpisodePurchase.query.filter_by(user_id=user.id, episode_id=episode_id).first()
        is not None
    )


def can_watch(user, episode: Episode) -> bool:
    if not episode or not episode.is_active:
        return False
    if episode.is_free:
        return True
    if not user or not user.is_authenticated:
        return False
    if has_episode_purchase(user, episode.id):
        return True
    return has_active_subscription(user)


def get_episode_access_status(user, episode: Episode) -> str:
    """Returns: free | purchased | subscribed | locked"""
    if not episode.is_active:
        return "locked"
    if episode.is_free:
        return "free"
    if user and user.is_authenticated:
        if has_episode_purchase(user, episode.id):
            return "purchased"
        if has_active_subscription(user):
            return "subscribed"
    return "locked"


def get_watch_progress(user, episode_id: int) -> WatchProgress | None:
    if not user or not user.is_authenticated:
        return None
    return WatchProgress.query.filter_by(user_id=user.id, episode_id=episode_id).first()
