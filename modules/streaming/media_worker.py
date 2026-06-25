"""
Isolated child process for FFmpeg / Whisper media pipeline.

Running outside the Gunicorn worker frees all model and library RAM when the
process exits (threads keep Whisper heap in the web worker and cause OOM on 512MB).
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FlowPremium media pipeline worker")
    parser.add_argument("episode_id", type=int)
    parser.add_argument("--hls", action="store_true", help="Run HLS transcoding")
    parser.add_argument("--subtitles", action="store_true", help="Run Whisper subtitles")
    parser.add_argument("--force-subtitles", action="store_true")
    args = parser.parse_args(argv)

    if not args.hls and not args.subtitles:
        print("Nothing to run (pass --hls and/or --subtitles)", file=sys.stderr)
        return 2

    from app import create_app
    from modules.streaming.services.media_pipeline import run_media_pipeline
    from modules.streaming.services.memory_diagnostics import log_memory

    app = create_app()
    with app.app_context():
        log_memory("media_worker_start", episode_id=args.episode_id)
        run_media_pipeline(
            args.episode_id,
            run_hls=args.hls,
            run_subtitles=args.subtitles,
            force_subtitles=args.force_subtitles,
        )
        log_memory("media_worker_exit", episode_id=args.episode_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
