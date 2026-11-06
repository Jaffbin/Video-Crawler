import copy

import pytest

from grab_library import MediaLibrary, checked_smart_collection, smart_collection_records
from test_library import media


@pytest.fixture
def library(tmp_path):
    return MediaLibrary(lambda: tmp_path, {".mp4", ".mp3"})


def test_smart_collection_lifecycle_preserves_manual_membership_and_media(library):
    path = media(library)
    manual = library.change_collection("create", "Study")
    library.organize([path.name], collection_id=manual, favorite=True)
    library.describe(path.name, ["my tag"], "Keep this note")
    before = library.load()["files"]
    stamp = path.stat().st_mtime_ns
    key = library.change_smart_collection("create", "Study", rules={"kind": "video", "tag": " my tag ", "favorite": True})
    assert library.smart_collections() == [{"id": key, "name": "Study", "rules": {"kind": "video", "tag": "my tag", "favorite": True}}]
    restarted = MediaLibrary(library.root, library.suffixes)
    assert restarted.smart_collections() == library.smart_collections()
    restarted.change_smart_collection("update", "Recent study", key, {"recent_days": 30, "favorite": False})
    assert restarted.smart_collections()[0]["rules"] == {"recent_days": 30, "favorite": False}
    assert restarted.load()["files"] == before and restarted.collections() == [{"id": manual, "name": "Study"}]
    restarted.change_smart_collection("delete", collection_id=key)
    assert restarted.smart_collections() == [] and restarted.load()["files"] == before
    assert path.read_bytes() == b"media content" and path.stat().st_mtime_ns == stamp


@pytest.mark.parametrize("rules", [None, [], {}, {"kind": "bad"}, {"kind": []}, {"source": " "},
    {"source": "x" * 201}, {"tag": "x" * 41}, {"tag": "bad\n"}, {"format": "mp4"}, {"format": ".*"},
    {"format": ".MP4"}, {"favorite": 1}, {"recent_days": True}, {"recent_days": 0}, {"recent_days": 3651},
    {"recent_days": 1.5}, {"playback": "external"}, {"playback": {}}, {"kind": "video", "unknown": True}])
def test_invalid_smart_rules_never_write(library, rules):
    before = library.load()
    with pytest.raises(ValueError):
        library.change_smart_collection("create", "Mine", rules=rules)
    assert library.load() == before and not library.store.path().exists()


@pytest.mark.parametrize("name", ["", " ", "x" * 81, "bad\nname", None, []])
def test_invalid_smart_names(library, name):
    with pytest.raises(ValueError):
        library.change_smart_collection("create", name, rules={"kind": "video"})


def test_smart_collection_conflicts_limits_and_invalid_actions(library):
    key = library.change_smart_collection("create", "Mine", rules={"favorite": True})
    for action, name, target in [("create", " MINE ", None), ("create", "Mine", key), ("update", "Other", "builtin:recent"),
                                  ("rename", "Other", key), ("delete", None, []), ("update", "Other", "bad")]:
        with pytest.raises(ValueError):
            library.change_smart_collection(action, name, target, {"kind": "audio"})
    data = library.load()
    data["smart_collections"] = {f"{index:032x}": {"name": f"Group {index}", "rules": {"favorite": True}} for index in range(100)}
    library.store.save(data)
    with pytest.raises(ValueError, match="100"):
        library.change_smart_collection("create", "Extra", rules={"kind": "video"})
    library.change_smart_collection("update", "Renamed", "0" * 32, {"kind": "audio"})
    assert len(library.smart_collections()) == 100


def test_invalid_persisted_rules_are_not_broadened_to_all_files(library):
    valid = {"name": "Good", "rules": {"kind": "video"}}
    invalid = {"name": "Unsafe", "rules": {"kind": "video", "future_rule": True}}
    stored = {"a" * 32: valid, "b" * 32: invalid}
    library.store.save({"smart_collections": stored})
    assert library.smart_collections() == [{"id": "a" * 32, **valid}]
    with pytest.raises(ValueError):
        smart_collection_records(stored, strict=True)
    with pytest.raises(ValueError):
        smart_collection_records({1: valid}, strict=True)


def test_smart_collection_write_failure_keeps_persisted_data(library, monkeypatch):
    key = library.change_smart_collection("create", "Mine", rules={"kind": "video"})
    before = library.store.path().read_bytes()
    monkeypatch.setattr(type(library.store), "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    for action in ("create", "update", "delete"):
        with pytest.raises(OSError):
            library.change_smart_collection(action, "Other", key, {"kind": "audio"})
        assert library.store.path().read_bytes() == before


def test_all_rule_types_validate_without_mutating_input():
    value = {"name": " My collection ", "rules": {"kind": "video", "source": "example.com", "format": ".mp4",
             "tag": " Study ", "favorite": False, "recent_days": 7, "playback": "unplayed"}}
    before = copy.deepcopy(value)
    result = checked_smart_collection(value)
    assert result["name"] == "My collection" and result["rules"]["tag"] == "Study"
    assert result["rules"]["favorite"] is False and value == before
