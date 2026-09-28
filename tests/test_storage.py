import json
import threading

import pytest

from grab_storage import JsonStore


def test_json_store_round_trips_unicode_and_replaces_existing_data(tmp_path):
    path = tmp_path / "state.json"
    store = JsonStore(lambda: path, threading.Lock())
    store.save({"title": "第一个", "items": [1]})
    store.save({"title": "第二个", "items": [2, 3]})
    assert store.load() == {"title": "第二个", "items": [2, 3]}
    assert json.loads(path.read_text(encoding="utf-8"))["title"] == "第二个"
    assert not (tmp_path / "state.json.tmp").exists()


def test_json_store_returns_the_default_for_missing_or_invalid_data(tmp_path):
    path = tmp_path / "state.json"
    store = JsonStore(lambda: path, threading.Lock())
    assert store.load({"items": []}) == {"items": []}
    path.write_text("not json", encoding="utf-8")
    assert store.load(None) is None


def test_json_store_keeps_the_previous_document_when_replace_fails(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    store = JsonStore(lambda: path, threading.Lock())
    store.save({"version": 1})

    def fail_replace(source, target):
        raise OSError("replace failed")

    monkeypatch.setattr("grab_storage.os.replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        store.save({"version": 2})
    assert store.load() == {"version": 1}
    assert not (tmp_path / "state.json.tmp").exists()
