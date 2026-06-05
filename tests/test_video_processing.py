"""HLS / FFmpeg error handling tests."""

from modules.streaming.services.video_processing import FFmpegError, _format_ffmpeg_error


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
