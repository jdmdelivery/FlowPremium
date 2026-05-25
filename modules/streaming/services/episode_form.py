def _episode_form_context(episode=None, preselect_series_id=None, preselect_season_id=None):
    from modules.streaming.models import Season, Series

    all_series = Series.query.order_by(Series.title).all()
    seasons = Season.query.order_by(Season.series_id, Season.season_number).all()
    return {
        "episode": episode,
        "all_series": all_series,
        "seasons": seasons,
        "preselect_series_id": preselect_series_id,
        "preselect_season_id": preselect_season_id,
    }
