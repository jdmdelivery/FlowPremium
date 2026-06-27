"""Tests for home grid preparation and search metadata."""

from modules.streaming.services.home_grid import normalize_text, prepare_home_grid


def test_normalize_text_strips_accents():
    assert normalize_text("Puños") == "punos"
    assert normalize_text("COLOMBIANAS") == "colombianas"
    assert normalize_text("  Gol  ") == "gol"


def test_prepare_home_grid_adds_filters(app, sample_content):
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


def test_search_text_includes_status_keywords(app, sample_content):
    from modules.streaming.services.home import get_home_sections

    with app.app_context():
        sections = get_home_sections(None)
        cards = prepare_home_grid(sections)
        if not cards:
            return
        for card in cards:
            blob = card["search_text"]
            assert "drama" in blob
            if card.get("badge") == "free":
                assert "gratis" in blob or "free" in blob
            if card.get("badge") == "premium":
                assert "premium" in blob or "exclusivo" in blob or "exclusive" in blob
            if "exclusive" in card["filters"]:
                assert "exclusivo" in blob or "exclusive" in blob
