"""Playback manifest and admin language filtering."""

import json

from extensions import db
from modules.streaming.models import Episode
from modules.streaming.services.languages import parse_admin_language_list
from modules.streaming.services.playback_manifest import build_playback_manifest
from utils.srt import srt_to_vtt


def test_parse_admin_languages():
    names = parse_admin_language_list(["Español", "Inglés", "bad"])
    assert names == ["Español", "Inglés"]


def test_playback_manifest_admin_audio_only_checked(app, sample_content, monkeypatch):
    with app.app_context():
        ep = db.session.get(Episode, sample_content["free_episode_id"])
        ep.video_url_r2 = "videos/1/es.mp4"
        ep.video_url_r2_en = "videos/1/en.mp4"
        ep.audio_languages = json.dumps(["Español"])
        ep.subtitle_languages = json.dumps([])
        monkeypatch.setattr(
            "modules.streaming.services.playback_manifest.media_file_exists",
            lambda key: bool(key),
        )
        manifest = build_playback_manifest(ep)
        assert len(manifest["audio"]["tracks"]) == 1
        assert manifest["audio"]["tracks"][0]["lang"] == "es"


def test_srt_to_vtt_conversion():
    srt = "1\n00:00:01,000 --> 00:00:02,000\nHola\n"
    vtt = srt_to_vtt(srt)
    assert vtt.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:02.000" in vtt
    assert "Hola" in vtt
