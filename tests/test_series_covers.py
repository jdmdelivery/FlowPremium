def test_series_keep_independent_covers(app, admin_client):
    """JUANA and MARIA must keep their own cover_image after episodes are created."""
    with app.app_context():
        from extensions import db
        from modules.streaming.models import Episode, Season, Series

        juana = Series(title="JUANA", is_active=True)
        maria = Series(title="MARIA", is_active=True)
        db.session.add_all([juana, maria])
        db.session.flush()
        juana.cover_image = f"storage/streaming/series/{juana.id}/juana.jpg"
        maria.cover_image = f"storage/streaming/series/{maria.id}/maria.jpg"

        s_j = Season(series_id=juana.id, title="T1", season_number=1, is_active=True)
        s_m = Season(series_id=maria.id, title="T1", season_number=1, is_active=True)
        db.session.add_all([s_j, s_m])
        db.session.commit()

        juana_season_id = s_j.id
        maria_season_id = s_m.id
        juana_id = juana.id
        maria_id = maria.id

    admin_client.post(
        "/admin/streaming/episodes/new",
        data={
            "series_id": juana_id,
            "season_id": juana_season_id,
            "title": "Cap JUANA 1",
            "duration_seconds": 60,
            "price": 0,
            "is_free": "on",
            "is_active": "on",
        },
        follow_redirects=True,
    )
    admin_client.post(
        "/admin/streaming/episodes/new",
        data={
            "series_id": maria_id,
            "season_id": maria_season_id,
            "title": "Cap MARIA 1",
            "duration_seconds": 60,
            "price": 0,
            "is_free": "on",
            "is_active": "on",
        },
        follow_redirects=True,
    )

    with app.app_context():
        j = Series.query.filter_by(title="JUANA").first()
        m = Series.query.filter_by(title="MARIA").first()
        assert j.cover_image == f"storage/streaming/series/{j.id}/juana.jpg"
        assert m.cover_image == f"storage/streaming/series/{m.id}/maria.jpg"

        ep_j = Episode.query.filter_by(title="Cap JUANA 1").first()
        ep_m = Episode.query.filter_by(title="Cap MARIA 1").first()
        assert ep_j.series_id == j.id
        assert ep_m.series_id == m.id
        assert ep_j.season_id == juana_season_id
        assert ep_m.season_id == maria_season_id


def test_episode_rejects_season_from_other_series(app, admin_client):
    with app.app_context():
        from extensions import db
        from modules.streaming.models import Season, Series

        a = Series(title="A", is_active=True)
        b = Series(title="B", is_active=True)
        db.session.add_all([a, b])
        db.session.flush()
        sa = Season(series_id=a.id, title="SA", season_number=1, is_active=True)
        sb = Season(series_id=b.id, title="SB", season_number=1, is_active=True)
        db.session.add_all([sa, sb])
        db.session.commit()
        a_id, b_id, sb_id = a.id, b.id, sb.id

    resp = admin_client.post(
        "/admin/streaming/episodes/new",
        data={
            "series_id": a_id,
            "season_id": sb_id,
            "title": "Bad episode",
            "duration_seconds": 1,
            "price": 0,
            "is_active": "on",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        from modules.streaming.models import Episode
        assert Episode.query.filter_by(title="Bad episode").first() is None


def test_display_thumbnail_falls_back_to_own_series(app, sample_content):
    with app.app_context():
        from modules.streaming.models import Episode, Series

        series = Series.query.get(sample_content["series_id"])
        series.cover_image = "storage/streaming/series/x/cover.jpg"
        ep = Episode.query.get(sample_content["free_episode_id"])
        ep.thumbnail_url = None
        ep.series = series
        assert ep.display_thumbnail() == series.cover_image

        ep.thumbnail_url = "storage/streaming/covers/1/ep-thumb.jpg"
        assert ep.display_thumbnail() == ep.thumbnail_url
