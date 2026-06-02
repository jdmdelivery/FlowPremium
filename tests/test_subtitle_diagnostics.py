"""Subtitle diagnostics and VTT validation tests."""

from modules.streaming.services.subtitle_diagnostics import validate_vtt_content

VALID = """WEBVTT

00:00:00.000 --> 00:00:02.500
Hola mundo
"""


def test_validate_vtt_ok():
    ok, msg = validate_vtt_content(VALID)
    assert ok is True
    assert msg == "ok"


def test_validate_vtt_missing_header():
    ok, msg = validate_vtt_content("00:00:00.000 --> 00:00:01.000\nHi")
    assert ok is False
    assert "WEBVTT" in msg


def test_validate_vtt_no_cues():
    ok, msg = validate_vtt_content("WEBVTT\n\nNOTE test")
    assert ok is False
