def _episode_form_context(episode=None, preselect_series_id=None, preselect_season_id=None):
    from modules.streaming.models import Season, Series
    from modules.streaming.services.episode_media import (
        admin_language_checkbox_values,
        get_admin_audio_languages,
        get_admin_subtitle_languages,
    )

    all_series = Series.query.order_by(Series.title).all()
    seasons = Season.query.order_by(Season.series_id, Season.season_number).all()
    languages = admin_language_checkbox_values()
    selected_audio = set(get_admin_audio_languages(episode)) if episode else set()
    selected_subs = set(get_admin_subtitle_languages(episode)) if episode else set()
    return {
        "episode": episode,
        "all_series": all_series,
        "seasons": seasons,
        "preselect_series_id": preselect_series_id,
        "preselect_season_id": preselect_season_id,
        "player_languages": languages,
        "selected_audio_languages": selected_audio,
        "selected_subtitle_languages": selected_subs,
    }
