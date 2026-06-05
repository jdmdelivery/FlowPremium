"""HLS / FFmpeg error handling and even-dimension scale tests."""

import shutil
import subprocess
from pathlib import Path

import pytest

from modules.streaming.services.video_processing import (
    FFmpegError,
    _even_scale_filter,
    _format_ffmpeg_error,
    _run_ffmpeg_hls,
    ffmpeg_path,
)


def test_format_ffmpeg_error_includes_stderr():
    err = FFmpegError(
        "failed",
        stdout="out line",
        stderr="Error splitting the argument list: Option not found\n",
        cmd=["ffmpeg", "-i", "x.mp4"],
        returncode=1,
    )
    text = _format_ffmpeg_error(err)
    assert "ffmpeg exit code 1" in text
    assert "--- STDERR ---" in text
    assert "Option not found" in text
    assert "--- STDOUT ---" in text
    assert "out line" in text
    assert "--- CMD ---" in text
    assert "ffmpeg -i x.mp4" in text


def test_even_scale_filter_480p():
    expr = _even_scale_filter(854, 480)
    assert "trunc(iw*min(854/iw,480/ih)/2)*2" in expr
    assert "trunc(ih*min(854/iw,480/ih)/2)*2" in expr
    assert "force_original_aspect_ratio" not in expr


def test_even_scale_filter_720p_escapes_commas():
    expr = _even_scale_filter(1280, 720, escape_commas=True)
    assert "min(1280/iw\\,720/ih)" in expr


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_hls_vertical_938x912_produces_even_dimensions(tmp_path):
    """Reproduce width-not-divisible-by-2 case (741x720) with 938x912 source."""
    source = tmp_path / "vertical_938x912.mp4"
    out_dir = tmp_path / "hls_out"
    ff = ffmpeg_path()

    gen = subprocess.run(
        [
            ff,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=2:size=938x912:rate=24",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        capture_output=True,
        text=True,
    )
    assert gen.returncode == 0, gen.stderr
    assert source.is_file()

    _run_ffmpeg_hls(source, out_dir, [480, 720])

    assert (out_dir / "master.m3u8").exists()
    assert (out_dir / "v0" / "playlist.m3u8").exists()
    assert (out_dir / "v1" / "playlist.m3u8").exists()
    segments = list(out_dir.glob("v*/segment_*.ts"))
    assert segments, "expected at least one HLS segment"
