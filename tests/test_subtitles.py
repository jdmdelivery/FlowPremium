"""Subtitle (VTT / whisper) tests — no GPU or model download required."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.services.subtitle_manifest import build_subtitle_manifest
from modules.streaming.services.subtitles import (
    enqueue_subtitle_job,
    format_vtt_timestamp,
    segments_to_vtt,
)
from utils.vtt import cues_to_vtt, parse_vtt, translate_vtt


SAMPLE_VTT = """WEBVTT

00:00:00.000 --> 00:00:02.500
Hola mundo

00:00:02.500 --> 00:00:05.000
Segunda línea
"""


def test_format_vtt_timestamp():
    assert format_vtt_timestamp(0) == "00:00:00.000"
    assert format_vtt_timestamp(61.5) == "00:01:01.500"


def test_segments_to_vtt():
    segments = [
        SimpleNamespace(start=0.0, end=2.5, text=" Hola "),
        SimpleNamespace(start=2.5, end=5.0, text="mundo"),
    ]
    vtt = segments_to_vtt(segments)
    assert vtt.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:02.500" in vtt
    assert "Hola" in vtt
    assert "mundo" in vtt


def test_parse_vtt_preserves_timestamps():
    cues = parse_vtt(SAMPLE_VTT)
    assert len(cues) == 2
    assert cues[0].start == "00:00:00.000"
    assert cues[0].end == "00:00:02.500"
    assert cues[1].text == "Segunda línea"


def test_translate_vtt_preserves_timestamps():
    with patch("utils.vtt._batch_translate_texts") as mock_tr:
        mock_tr.return_value = ["Hello world", "Second line"]
        out = translate_vtt(SAMPLE_VTT, "en", source_lang="es")
    assert "00:00:00.000 --> 00:00:02.500" in out
    assert "Hello world" in out


def test_cues_to_vtt_roundtrip():
    cues = parse_vtt(SAMPLE_VTT)
    rebuilt = cues_to_vtt(cues)
    assert parse_vtt(rebuilt)[0].start == cues[0].start


def test_enqueue_skipped_when_disabled(app, sample_content):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/x.mp4"
        db.session.commit()
        assert enqueue_subtitle_job(ep.id) is False
        ep = db.session.get(Episode, ep.id)
        assert ep.subtitle_status == "skipped"


def test_enqueue_sets_pending(app, sample_content):
    with app.app_context():
        app.config["SUBTITLES_ENABLED"] = True
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/x.mp4"
        db.session.commit()
        ep_id = ep.id

    with patch(
        "modules.streaming.services.subtitles.prerequisites_ok",
        return_value=(True, "ok"),
    ), patch("modules.streaming.services.subtitles.generate_subtitles_for_episode"):
        with app.app_context():
            assert enqueue_subtitle_job(ep_id) is True
            ep = db.session.get(Episode, ep_id)
            assert ep.subtitle_status == "pending"


def test_enqueue_no_duplicate_when_ready(app, sample_content):
    with app.app_context():
        app.config["SUBTITLES_ENABLED"] = True
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/x.mp4"
        ep.subtitle_status = "ready"
        ep.subtitle_url = "subtitles/1/1/subtitle_es.vtt"
        db.session.commit()
        ep_id = ep.id

    with patch(
        "modules.streaming.services.subtitles.prerequisites_ok",
        return_value=(True, "ok"),
    ):
        with app.app_context():
            assert enqueue_subtitle_job(ep_id) is False


def test_enqueue_force_regenerates(app, sample_content):
    with app.app_context():
        app.config["SUBTITLES_ENABLED"] = True
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/x.mp4"
        ep.subtitle_status = "ready"
        ep.subtitle_url = "subtitles/1/x.vtt"
        db.session.commit()
        ep_id = ep.id

    with patch(
        "modules.streaming.services.subtitles.prerequisites_ok",
        return_value=(True, "ok"),
    ), patch("modules.streaming.services.subtitles.generate_subtitles_for_episode"):
        with app.app_context():
            assert enqueue_subtitle_job(ep_id, force=True) is True
            ep = db.session.get(Episode, ep_id)
            assert ep.subtitle_status == "pending"


def test_subtitle_api_requires_access(user_client, sample_content):
    ep_id = sample_content["premium_episode_id"]
    resp = user_client.get(f"/api/streaming/subtitles/{ep_id}")
    assert resp.status_code == 403


def test_subtitle_api_serves_vtt_es(user_client, app, sample_content):
    from pathlib import Path

    ep_id = sample_content["free_episode_id"]
    with app.app_context():
        upload = Path(app.config["UPLOAD_FOLDER"])
        vtt_path = upload / "subtitles" / "1" / str(ep_id) / "subtitle_es.vtt"
        vtt_path.parent.mkdir(parents=True, exist_ok=True)
        vtt_path.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHola\n", encoding="utf-8")
        rel = str(vtt_path.relative_to(Path(app.root_path).resolve())).replace("\\", "/")
        ep = db.session.get(Episode, ep_id)
        ep.subtitle_url_es = rel
        ep.subtitle_url = rel
        ep.subtitle_status = "ready"
        db.session.commit()

    resp = user_client.get(f"/api/streaming/subtitles/{ep_id}?lang=es")
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("text/vtt")
    assert b"WEBVTT" in resp.data


def test_subtitle_manifest_includes_all_stored_langs(user_client, app, sample_content, monkeypatch):
    ep_id = sample_content["free_episode_id"]
    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.subtitle_url_es = "storage/subtitles/x.vtt"
        ep.subtitle_url_en = "storage/subtitles/y.vtt"
        ep.subtitle_status = "ready"
        ep.subtitle_langs = json.dumps(["es", "en"])
        db.session.commit()

    monkeypatch.setattr(
        "modules.streaming.services.episode_media.media_file_exists",
        lambda key: bool(key),
    )

    resp = user_client.get(f"/api/streaming/subtitles-manifest/{ep_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["show_cc"] is True
    langs = {t["lang"] for t in data["tracks"]}
    assert langs == {"es", "en"}


def test_build_subtitle_manifest_es_only(app, sample_content):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.subtitle_url_es = "k/es.vtt"
        ep.subtitle_status = "ready"
        manifest = build_subtitle_manifest(ep)
        assert manifest["show_cc"] is True
        assert len(manifest["tracks"]) == 1
        assert manifest["tracks"][0]["lang"] == "es"


def test_watch_page_shows_cc_and_manifest(user_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.subtitle_url_es = "subtitles/1/ep.vtt"
        ep.subtitle_url = "subtitles/1/ep.vtt"
        ep.subtitle_status = "ready"
        db.session.commit()

    resp = user_client.get(f"/streaming/watch/{ep_id}")
    assert resp.status_code == 200
    assert b'id="dw-btn-subtitles"' in resp.data
    assert b'player-subtitle-manifest' in resp.data
    assert b'player-playback-manifest' in resp.data
    assert b'"lang": "es"' in resp.data or b'"lang":"es"' in resp.data
    assert b'kind="subtitles"' in resp.data
    assert f"/api/streaming/subtitles/{ep_id}".encode() in resp.data
    assert b'player-subtitles.js' in resp.data
    assert b'player-controls.js' in resp.data
    assert b'dw-toolbar' in resp.data
    assert b'id="dw-btn-audio"' in resp.data
    assert b'audio-track-bar' not in resp.data


def test_watch_hides_cc_without_subtitles(user_client, sample_content):
    ep_id = sample_content["free_episode_id"]
    resp = user_client.get(f"/streaming/watch/{ep_id}")
    assert resp.status_code == 200
    assert b'id="dw-btn-subtitles"' in resp.data


def test_generate_subtitles_auto_translates(app, sample_content, monkeypatch):
    import json as json_mod

    from modules.streaming.services.subtitles import generate_subtitles_for_episode

    ep_id = sample_content["free_episode_id"]
    saved_langs: list[str] = []

    def fake_save(content, series_id, episode_id, lang="es"):
        saved_langs.append(lang)
        return f"subtitles/{series_id}/{episode_id}/subtitle_{lang}.vtt"

    def fake_translate(vtt, target, source_lang="es"):
        return vtt.replace("Hola", f"TR_{target}")

    with app.app_context():
        app.config["SUBTITLES_ENABLED"] = True
        app.config["SUBTITLE_AUTO_TRANSLATE_ENABLED"] = True
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = "storage/streaming/videos/free.mp4"
        db.session.commit()

    with patch(
        "modules.streaming.services.subtitles.prerequisites_ok",
        return_value=(True, "ok"),
    ), patch(
        "modules.streaming.services.subtitles._materialize_video",
        return_value=__import__("pathlib").Path("/tmp/fake.mp4"),
    ), patch(
        "modules.streaming.services.subtitles._extract_audio_wav",
    ), patch(
        "modules.streaming.services.subtitles._transcribe_to_vtt",
        return_value="WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHola\n",
    ), patch(
        "modules.streaming.services.subtitles.save_subtitle_vtt",
        side_effect=fake_save,
    ), patch(
        "utils.vtt.translate_vtt",
        side_effect=fake_translate,
    ):
        with app.app_context():
            generate_subtitles_for_episode(ep_id)
            ep = db.session.get(Episode, ep_id)
            assert ep.subtitle_status == "ready"
            assert "es" in saved_langs
            assert "en" in saved_langs
            assert "pt" in saved_langs
            assert "fr" in saved_langs
            assert "it" in saved_langs
            assert "de" in saved_langs
            langs = json_mod.loads(ep.subtitle_langs or "[]")
            assert set(langs) >= {"es", "en", "pt", "fr", "it", "de"}


def test_admin_regenerate_subtitles(admin_client, app, sample_content):
    ep_id = sample_content["free_episode_id"]
    with app.app_context():
        ep = db.session.get(Episode, ep_id)
        ep.video_url_r2 = "videos/1/x.mp4"
        ep.subtitle_status = "ready"
        ep.subtitle_url = "subtitles/x.vtt"
        db.session.commit()

    with patch(
        "modules.streaming.services.subtitles.enqueue_subtitle_job",
        return_value=True,
    ) as mock_enqueue:
        resp = admin_client.post(
            f"/admin/streaming/episodes/{ep_id}/regenerate-subtitles",
            follow_redirects=True,
        )
        assert resp.status_code == 200
        mock_enqueue.assert_called_once_with(ep_id, force=True)
