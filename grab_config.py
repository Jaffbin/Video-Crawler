"""Validated configuration for the local Web UI process."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WebConfig:
    download_dir: Path
    port: int
    workers: int
    ui: str
    subscription_interval_seconds: int


def parse_web_config(argv=None) -> WebConfig:
    parser = argparse.ArgumentParser(description="Local Web UI for grab.py")
    parser.add_argument("--dir", default="downloads", help="Download directory (default: ./downloads)")
    parser.add_argument(
        "--port", type=int, default=8765,
        help="Starting port, will auto-increment if occupied (default: 8765)",
    )
    parser.add_argument("--workers", type=int, default=2, help="Concurrent download task count (default: 2)")
    parser.add_argument(
        "--ui", choices=("window", "browser", "none"), default="window",
        help=("window: a native app window (needs pywebview, the default); "
              "browser: open your default browser instead; "
              "none: do not open anything (for `npm run dev` against this backend)"),
    )
    parser.add_argument("--no-browser", dest="ui", action="store_const", const="none",
                        help=argparse.SUPPRESS)  # kept for older scripts; same as --ui none
    parser.add_argument(
        "--sub-interval", type=int, default=60,
        help="How often subscriptions are re-checked for new videos, in minutes (default: 60)",
    )
    args = parser.parse_args(argv)
    return WebConfig(
        download_dir=Path(args.dir).expanduser().resolve(),
        port=args.port,
        workers=max(1, min(args.workers, 6)),
        ui=args.ui,
        subscription_interval_seconds=max(300, args.sub_interval * 60),
    )

