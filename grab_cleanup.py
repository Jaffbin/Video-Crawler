"""Remove temporary files that a forced shutdown (power loss, kill, crash) can leave behind.

Runs once at startup, before downloads start. It only touches names this app creates for work in
progress, and only files untouched for MIN_AGE_SECONDS, so another running copy of the app is not
disturbed:

* ``<library>/.library-imports/*.tmp``: imports being copied in
* ``<library>/**/.image-*.part``: image downloads in progress (bounded walk, no symlinks)
* ``<library>/.repair-*/``: staging folders of local repairs
* ``<settings>/run-*.txt``: per-run copies of the uploaded cookies, which hold sign-in data

It never removes yt-dlp ``.part`` files, which Repair uses to resume, or ``.backup-restore-*``
files, which a failed restore keeps on purpose as recovery copies.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import stat
import time

LOG = logging.getLogger(__name__)
MIN_AGE_SECONDS = 3600
WALK_MAX_DEPTH = 4
WALK_MAX_ENTRIES = 20000


def _stale(info: os.stat_result, now: float) -> bool:
    return now - info.st_mtime >= MIN_AGE_SECONDS


def _remove_file(path: Path, now: float, removed: list[str], failed: list[str]) -> None:
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or not _stale(info, now):
            return
        path.unlink()
        removed.append(str(path))
    except FileNotFoundError:
        return
    except OSError:
        failed.append(str(path))


def _image_parts(root: Path):
    """`.image-*.part` files under root, skipping symlinks and other hidden folders."""
    budget = [WALK_MAX_ENTRIES]

    def walk(directory: Path, depth: int):
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    budget[0] -= 1
                    if budget[0] < 0:
                        return
                    if entry.is_symlink():
                        continue
                    if entry.is_file(follow_symlinks=False):
                        if entry.name.startswith(".image-") and entry.name.endswith(".part"):
                            yield Path(entry.path)
                    elif entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".") and depth < WALK_MAX_DEPTH:
                        yield from walk(Path(entry.path), depth + 1)
        except OSError:
            return

    yield from walk(root, 0)


def cleanup(library_root: Path, settings_dir: Path, now: float | None = None) -> dict:
    """Remove stale temporary files. Returns {"removed": [...], "failed": [...]}; never raises OSError."""
    now = time.time() if now is None else now
    removed: list[str] = []
    failed: list[str] = []
    library_root, settings_dir = Path(library_root), Path(settings_dir)

    imports = library_root / ".library-imports"
    if imports.is_dir() and not imports.is_symlink():
        for path in imports.glob("*.tmp"):
            _remove_file(path, now, removed, failed)

    for path in _image_parts(library_root):
        _remove_file(path, now, removed, failed)

    try:
        repairs = [path for path in library_root.glob(".repair-*") if path.is_dir() and not path.is_symlink()]
    except OSError:
        repairs = []
    for path in repairs:
        try:
            if not _stale(path.lstat(), now):
                continue
            shutil.rmtree(path)  # does not follow symlinks inside the folder
            removed.append(str(path))
        except OSError:
            failed.append(str(path))

    if settings_dir.is_dir():
        for path in settings_dir.glob("run-*.txt"):
            _remove_file(path, now, removed, failed)

    if removed:
        LOG.info("Removed %d temporary file(s) left by an earlier forced shutdown.", len(removed))
    if failed:
        LOG.warning("Could not remove %d temporary file(s); they will be retried at the next start.", len(failed))
    return {"removed": removed, "failed": failed}
