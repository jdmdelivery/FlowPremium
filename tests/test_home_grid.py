"""Tests for home grid preparation."""

from modules.streaming.services.home_grid import prepare_home_grid


def test_prepare_home_grid_adds_filters(app, sample_content):
    from extensions import db
    from modules.streaming.models import Series
    from modules.streaming.services.home import get_home_sections

    with app.app_context():
        sections = get_home_sections(None)
        cards = prepare_home_grid(sections)
        assert isinstance(cards, list)
        if cards:
            card = cards[0]
            assert "filters" in card
            assert "discover" in card["filters"]
            assert "subtitle" in card
            assert "search_text" in card
            assert "views" not in card
