import io
import json
import threading

from grab_storage import SqliteLibraryStore
from grab_library import MediaLibrary


def test_sqlite_store_roundtrip(tmp_path):
    store = SqliteLibraryStore(lambda: tmp_path, threading.Lock())
    assert store.load() is None
    assert store.load({"default": True}) == {"default": True}

    sample = {
        "version": 1,
        "files": {
            "movie.mp4": {
                "complete": True,
                "favorite": True,
                "source": "web",
                "format": "mp4",
                "tags": ["cinema", "action"],
                "note": "high quality",
                "playback": {"position": 100, "duration": 500, "finished": False},
            }
        },
        "trash": {
            "rec-1": {"path": "old.mp4", "deleted_at": 123456.78}
        },
        "collections": {"c1": "Favorites"},
        "smart_collections": {"sc1": {"name": "Recent Action", "rules": {"tag": "action"}}},
    }

    store.save(sample)
    loaded = store.load()
    assert loaded == sample
    assert (tmp_path / ".grab-library.db").is_file()


def test_sqlite_store_migrates_existing_json(tmp_path):
    json_path = tmp_path / ".grab-library.json"
    legacy_data = {
        "version": 1,
        "files": {
            "clip.mp4": {"complete": True, "favorite": False, "source": "local", "tags": ["test"]}
        },
        "trash": {},
        "collections": {"col-1": "My Collection"},
        "smart_collections": {},
    }
    json_path.write_text(json.dumps(legacy_data), encoding="utf-8")

    store = SqliteLibraryStore(lambda: tmp_path, threading.Lock())
    assert not (tmp_path / ".grab-library.db").exists()

    loaded = store.load()
    assert loaded["files"]["clip.mp4"]["tags"] == ["test"]
    assert loaded["collections"]["col-1"] == "My Collection"

    # SQLite DB now exists and contains the synced data
    assert (tmp_path / ".grab-library.db").is_file()
    assert (tmp_path / ".grab-library.json").is_file()


def test_sqlite_store_with_media_library(tmp_path):
    lib = MediaLibrary(lambda: tmp_path, {".mp4", ".mp3"})
    media = tmp_path / "video.mp4"
    media.write_bytes(b"sample video bytes")

    result = lib.import_file("video.mp4", io.BytesIO(b"sample video bytes"), len(b"sample video bytes"))
    assert result["duplicate"] is False

    lib.describe("imports/video.mp4", ["4k", "hdr"], "sample note")
    lib.save_playback("imports/video.mp4", 45, 90)

    # Reload through a fresh MediaLibrary instance
    reloaded = MediaLibrary(lambda: tmp_path, {".mp4", ".mp3"})
    rec = reloaded.load()["files"]["imports/video.mp4"]
    assert rec["tags"] == ["4k", "hdr"]
    assert rec["note"] == "sample note"
    assert rec["playback"]["position"] == 45
    assert (tmp_path / ".grab-library.db").is_file()


def test_both_load_paths_return_the_same_document(tmp_path):
    """Load reads the JSON mirror when it is newer, the database otherwise; the result must not differ."""
    import os

    store = SqliteLibraryStore(lambda: tmp_path, threading.Lock())
    sample = {"version": 1, "files": {}, "trash": {}, "collections": {}, "smart_collections": {}}
    store.save(sample)
    json_file, db_file = store._json_path(), store._db_path()
    os.utime(json_file, ns=(1, 1_000_000_000))  # database newer: read from the database
    assert store.load() == sample
    store.save({**sample, "auto_rules": {"a" * 32: {"name": "R"}}})
    os.utime(json_file, ns=(1, 1_000_000_000))
    assert store.load()["auto_rules"] == {"a" * 32: {"name": "R"}}
    os.utime(db_file, ns=(1, 1_000_000_000))  # mirror newer: read the JSON mirror
    assert store.load()["auto_rules"] == {"a" * 32: {"name": "R"}}


def test_a_json_only_write_in_the_same_clock_tick_is_not_lost(tmp_path):
    """Backup restore replaces only the JSON document; equal timestamps must still be read."""
    import json
    import os

    store = SqliteLibraryStore(lambda: tmp_path, threading.Lock())
    store.save({"version": 1, "files": {}, "trash": {}, "collections": {}, "smart_collections": {}})
    restored = {"version": 1, "files": {}, "trash": {}, "collections": {"m" * 32: "Music"}, "smart_collections": {}}
    store._json_path().write_text(json.dumps(restored), encoding="utf-8")
    stamp = store._db_path().stat().st_mtime_ns
    os.utime(store._json_path(), ns=(stamp, stamp))
    assert store.load()["collections"] == {"m" * 32: "Music"}
