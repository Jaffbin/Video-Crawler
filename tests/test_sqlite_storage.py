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
