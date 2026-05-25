from pathlib import Path

from extensions import db
from modules.streaming.models import Episode, EpisodePurchase, Payment, Season, Series, WatchProgress
from modules.streaming.upload import delete_storage_file


def _purge_episode_relations_and_files(episode: Episode) -> None:
    episode_id = episode.id
    payment_ids = {
        p.payment_id
        for p in EpisodePurchase.query.filter_by(episode_id=episode_id).all()
        if p.payment_id
    }

    WatchProgress.query.filter_by(episode_id=episode_id).delete(synchronize_session=False)
    EpisodePurchase.query.filter_by(episode_id=episode_id).delete(synchronize_session=False)

    for payment in Payment.query.filter(
        Payment.payment_type == "episode",
        Payment.reference_id == str(episode_id),
    ).all():
        payment_ids.add(payment.id)

    for payment_id in payment_ids:
        payment = db.session.get(Payment, payment_id)
        if not payment or payment.payment_type != "episode":
            continue
        if payment.reference_id != str(episode_id):
            continue
        still_linked = EpisodePurchase.query.filter_by(payment_id=payment_id).first()
        if not still_linked:
            db.session.delete(payment)

    if episode.video_path:
        delete_storage_file(episode.video_path)
    if episode.thumbnail:
        delete_storage_file(episode.thumbnail)


def delete_episode(episode_id: int) -> bool:
    """Delete episode, related records, and local media files. Returns True if deleted."""
    episode = db.session.get(Episode, episode_id)
    if not episode:
        return False

    _purge_episode_relations_and_files(episode)
    db.session.delete(episode)
    db.session.commit()
    return True
