"""Entry point included in the Windows Portable ZIP."""

from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_ROOT))
import portable_bootstrap  # noqa: E402 - embedded Python does not add the script directory to sys.path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--with-playwright", action="store_true")
    options, webui_args = parser.parse_known_args(argv)
    portable_bootstrap.configure_portable()
    portable_bootstrap.ensure_runtime(with_playwright=options.with_playwright)

    default_args = ["--ui", "window", "--dir", str(APP_ROOT / "downloads")]
    sys.argv = [str(APP_ROOT / "webui.py"), *default_args, *webui_args]
    runpy.run_path(str(APP_ROOT / "webui.py"), run_name="__main__")


if __name__ == "__main__":
    main(sys.argv[1:])
