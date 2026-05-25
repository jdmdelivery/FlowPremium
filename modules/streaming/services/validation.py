from extensions import db
from modules.streaming.models import Season, Series


class EpisodeValidationError(ValueError):
    pass


def validate_episode_series_season(series_id: int, season_id: int) -> tuple[Series, Season]:
    """Ensure series exists and season belongs to that series."""
    series = db.session.get(Series, series_id)
    if not series:
        raise EpisodeValidationError("La serie no existe / Series not found")

    season = db.session.get(Season, season_id)
    if not season:
        raise EpisodeValidationError("La temporada no existe / Season not found")

    if season.series_id != series.id:
        raise EpisodeValidationError(
            "La temporada no pertenece a la serie seleccionada / "
            "Season does not belong to the selected series"
        )

    return series, season
