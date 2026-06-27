"""Tests for DramaWave-style episode list cards."""

from modules.streaming.services.episode_list import (
    _format_views,
    build_series_episode_cards,
)


def test_format_views():
    assert _format_views(500) == "500"
    assert _format_views(1500) == "1.5K"
    assert _format_views(209700) == "209.7K"
    assert _format_views(2_500_000) == "2.5M"


def test_build_series_episode_cards(app, sample_content):
    from extensions import db
    from modules.streaming.models import Episode, Season

    with app.app_context():
        ep_id = sample_content["free_episode_id"]
        ep = db.session.get(Episode, ep_id)
        ep.description = "Una historia de venganza y amor."
        db.session.commit()

        season = db.session.get(Season, ep.season_id)
        seasons = [season]
        episodes_by_season = {
            season.id: [{"episode": ep, "status": "free"}],
        }
        with app.test_request_context():
            cards = build_series_episode_cards(None, seasons, episodes_by_season)
        assert len(cards) == 1
        card = cards[0]
        assert card["rank"] == 1
        assert "free" in card["tags"]
        assert card["href"].endswith(f"/watch/{ep_id}")
