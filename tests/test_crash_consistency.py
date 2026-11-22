"""Hard-kill injection: an operation dies at a chosen point, then the library is opened again.

Each scenario runs in a child process that calls os._exit at the injection point, which, like a
kill -9 or a power cut, skips every finally block and cleanup handler. The parent then checks that
no media was lost, the library still loads, and the user can finish or undo what was interrupted.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

import grab_cleanup
from grab_library import MediaLibrary

REPO = Path(__file__).resolve().parents[1]
SUFFIXES = {".mp4", ".mp3", ".jpg"}
CHILD = r"""
import io, os, sys
from pathlib import Path
import grab_library, grab_storage

root, scenario = Path(sys.argv[1]), sys.argv[2]
library = grab_library.MediaLibrary(lambda: root, {".mp4", ".mp3", ".jpg"})

def die():
    os._exit(137)  # no finally blocks, no cleanup: like a hard kill

if scenario == "import-mid-stream":
    class Stream:
        sent = 0
        def read(self, size):
            if self.sent:
                die()
            self.sent = size
            return b"x" * min(size, 1024)
    library.import_file("clip.mp4", Stream(), 4096)
elif scenario == "import-before-metadata":
    original = grab_storage.SqliteLibraryStore.save
    def save(self, data):
        if any(key.startswith("imports/") for key in data["files"]):
            die()
        original(self, data)
    grab_storage.SqliteLibraryStore.save = save
    library.import_file("clip.mp4", io.BytesIO(b"y" * 4096), 4096)
elif scenario.startswith("recovery-"):
    stop = int(scenario.split("-")[1])  # die before this move; 0 = right after the intent is saved
    moves = [0]
    original = grab_library.MediaLibrary.move_without_overwrite
    def move(source, target):
        if moves[0] == stop:
            die()
        moves[0] += 1
        original(source, target)
    grab_library.MediaLibrary.move_without_overwrite = staticmethod(move)
    library.trash_many(["clip.mp4"])
elif scenario == "save":
    original_replace = os.replace
    def replace(source, target):
        die()
    os.replace = replace
    library.describe("clip.mp4", ["changed"], "changed note")
print("finished without the injected crash")
"""


def crash(root: Path, scenario: str) -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    result = subprocess.run([sys.executable, "-c", CHILD, str(root), scenario], cwd=REPO, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 137, (result.returncode, result.stdout, result.stderr)


def library_at(root: Path) -> MediaLibrary:
    return MediaLibrary(lambda: root, SUFFIXES)


def video_with_companions(root: Path) -> dict[str, bytes]:
    files = {"clip.mp4": b"video-bytes", "clip.jpg": b"cover-bytes", "clip.en.srt": b"subtitle-bytes"}
    for name, content in files.items():
        (root / name).write_bytes(content)
    library = library_at(root)
    library.remember({"clip.mp4": {"title": "Clip", "complete": True}})
    library.describe("clip.mp4", ["keep"], "my note")
    return files


def all_bytes(root: Path) -> list[bytes]:
    return sorted(path.read_bytes() for path in root.rglob("*")
                  if path.is_file() and not path.name.startswith(".grab-library"))


def test_an_import_killed_mid_copy_leaves_only_a_temporary_file_that_startup_removes(tmp_path):
    crash(tmp_path, "import-mid-stream")
    library = library_at(tmp_path)
    assert library.load()["files"] == {}
    assert not any((tmp_path / "imports").glob("*")) if (tmp_path / "imports").exists() else True
    leftovers = list((tmp_path / ".library-imports").glob("*.tmp"))
    assert len(leftovers) == 1
    # A fresh leftover may belong to another running copy, so it is kept until it is stale.
    assert grab_cleanup.cleanup(tmp_path, tmp_path / "cfg")["removed"] == []
    result = grab_cleanup.cleanup(tmp_path, tmp_path / "cfg", now=time.time() + grab_cleanup.MIN_AGE_SECONDS + 1)
    assert result == {"removed": [str(leftovers[0])], "failed": []}
    assert not leftovers[0].exists()


def test_an_import_killed_before_its_record_keeps_the_file_visible(tmp_path):
    crash(tmp_path, "import-before-metadata")
    published = tmp_path / "imports" / "clip.mp4"
    assert published.read_bytes() == b"y" * 4096  # the copy is complete and not lost
    assert library_at(tmp_path).load()["files"] == {}  # no record pointing at a missing file
    assert not list((tmp_path / ".library-imports").glob("*.tmp"))


@pytest.mark.parametrize("stop", [0, 1, 2])
def test_a_move_to_recovery_killed_part_way_loses_nothing_and_can_be_undone(tmp_path, stop):
    files = video_with_companions(tmp_path)
    before = all_bytes(tmp_path)
    crash(tmp_path, f"recovery-{stop}")
    assert all_bytes(tmp_path) == before  # every byte is still somewhere: original place or Recovery
    library = library_at(tmp_path)
    data = library.load()
    (recovery_id, record), = data["trash"].items()
    assert record["path"] == "clip.mp4" and record["metadata"]["note"] == "my note"
    assert library.restore(recovery_id) == "clip.mp4"
    for name, content in files.items():
        assert (tmp_path / name).read_bytes() == content
    data = library.load()
    assert data["trash"] == {} and data["files"]["clip.mp4"]["note"] == "my note"
    assert not any(path.is_file() for path in library.trash_directory().glob("*"))


def test_a_save_killed_between_the_database_and_its_json_mirror_stays_consistent(tmp_path):
    """SQLite commits first, then the JSON mirror is replaced; dying in between keeps a whole version."""
    video_with_companions(tmp_path)
    crash(tmp_path, "save")
    library = library_at(tmp_path)
    record = library.load()["files"]["clip.mp4"]
    # The committed database wins over the older mirror, and never a mix of old and new fields.
    assert (record["note"], record["tags"]) == ("changed note", ["changed"])
    # The next save brings the stale mirror back in line.
    library.describe("clip.mp4", ["final"], "final note")
    mirror = json.loads((tmp_path / ".grab-library.json").read_text(encoding="utf-8"))
    assert mirror["files"]["clip.mp4"]["note"] == "final note"
    assert library_at(tmp_path).load()["files"]["clip.mp4"]["note"] == "final note"


def test_startup_cleanup_removes_only_stale_temporaries_it_owns(tmp_path):
    settings = tmp_path / "cfg"
    settings.mkdir()
    old = time.time() - grab_cleanup.MIN_AGE_SECONDS - 10

    def make(path: Path, content=b"x"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        os.utime(path, (old, old))
        return path

    removable = [
        make(tmp_path / ".library-imports" / "abc.tmp"),
        make(tmp_path / "channel" / "2026" / ".image-1a2b.part"),
        make(settings / "run-xyz.txt", b"# Netscape HTTP Cookie File"),
    ]
    repair = tmp_path / ".repair-123"
    make(repair / "0.mp4")
    os.utime(repair, (old, old))
    kept = [
        make(tmp_path / "video.mp4.part"),  # yt-dlp partial download: Repair resumes it
        make(tmp_path / "video.f137.mp4"),
        make(settings / ".backup-restore-1.tmp"),  # a failed restore keeps this recovery copy on purpose
        make(settings / "cookies.txt"),
        make(tmp_path / "notes.tmp"),
        make(tmp_path / ".grab-trash" / ".image-x.part"),  # Recovery is never walked
    ]
    fresh = tmp_path / ".library-imports" / "fresh.tmp"
    fresh.write_bytes(b"in progress")
    result = grab_cleanup.cleanup(tmp_path, settings)
    assert sorted(result["removed"]) == sorted(map(str, removable + [repair])) and result["failed"] == []
    assert all(path.exists() for path in kept) and fresh.exists() and not repair.exists()


def test_startup_cleanup_does_not_follow_symlinks(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    victim = outside / ".image-victim.part"
    victim.write_bytes(b"x")
    old = time.time() - grab_cleanup.MIN_AGE_SECONDS - 10
    os.utime(victim, (old, old))
    library = tmp_path / "library"
    library.mkdir()
    try:
        (library / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory links is unavailable")
    grab_cleanup.cleanup(library, tmp_path / "cfg")
    assert victim.exists()


def test_startup_cleanup_survives_missing_folders(tmp_path):
    assert grab_cleanup.cleanup(tmp_path / "missing", tmp_path / "also-missing") == {"removed": [], "failed": []}
