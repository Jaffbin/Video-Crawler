"""Auto rules: validation, matching, persistence, and classification of newly saved downloads."""
import json
import sqlite3
import threading
import urllib.error
import urllib.request

import pytest

import grab_auto_rules as rules_mod
from grab_library import MediaLibrary
from test_library import media
import webui


def kind_of(relative):
    return webui.media_kind("." + relative.rsplit(".", 1)[-1].lower())


@pytest.fixture
def library(tmp_path):
    return MediaLibrary(lambda: tmp_path, {".mp4", ".mp3", ".jpg"})


def rule(name="Bili", conditions=None, actions=None, enabled=True):
    return {"name": name, "enabled": enabled,
            "conditions": {"source": "bilibili.com"} if conditions is None else conditions,
            "actions": {"tags": ["B站"]} if actions is None else actions}


def download(library, relative, url):
    media(library, relative)
    return library.remember({relative: {"source_url": url, "title": relative, "complete": True}})


# ── Validation ──
@pytest.mark.parametrize("raw, expected", [
    ("bilibili.com", "bilibili.com"),
    (" WWW.Bilibili.com ", "bilibili.com"),
    ("https://www.youtube.com/watch?v=1", "youtube.com"),
    ("*.example.org:8080", "example.org"),
])
def test_sites_are_normalized(raw, expected):
    assert rules_mod.normalize_source(raw) == expected


def test_a_valid_rule_is_cleaned_up():
    collections = {"a" * 32: "Music"}
    checked = rules_mod.check_rule({"name": " Music ", "conditions": {"kind": "audio", "format": "MP3", "source": ""},
                                    "actions": {"tags": ["Music", " music ", "Live"], "collections": ["a" * 32] * 2,
                                                "favorite": False}}, collections)
    assert checked == {"name": "Music", "enabled": True, "conditions": {"kind": "audio", "format": ".mp3"},
                       "actions": {"tags": ["Music", "Live"], "collections": ["a" * 32]}}


@pytest.mark.parametrize("value, message", [
    (rule(name=""), "rule name"),
    (rule(conditions={}), "site, a file type or a format"),
    (rule(conditions={"source": "not a site"}), "site such as"),
    (rule(conditions={"kind": "document"}), "video, audio or image"),
    (rule(conditions={"format": ".m p4"}), "format such as"),
    (rule(conditions={"title": "x"}), "site, a file type or a format"),
    (rule(actions={"favorite": False}), "tags, collections or favorite"),
    (rule(actions={"tags": ["x"] * 11}), "up to 10 tags"),
    (rule(actions={"tags": ["bad\n"]}), "up to 10 tags"),
    (rule(actions={"collections": ["b" * 32]}), "no longer exists"),
    (rule(actions={"move_to": "D:/"}), "tags, collections or favorite"),
    ({**rule(), "enabled": "yes"}, "Invalid auto rule"),
])
def test_invalid_rules_are_rejected_with_a_reason(value, message):
    with pytest.raises(ValueError, match=message):
        rules_mod.check_rule(value, {"a" * 32: "Music"})


# ── Lifecycle and persistence ──
def test_rules_survive_a_restart_and_names_stay_unique(library):
    rule_id = library.change_auto_rule("create", rule=rule())
    with pytest.raises(ValueError, match="already exists"):
        library.change_auto_rule("create", rule=rule(name="bili"))
    restarted = MediaLibrary(library.root, library.suffixes)
    assert restarted.auto_rules() == [{"id": rule_id, **rules_mod.check_rule(rule(), {})}]
    restarted.change_auto_rule("update", rule_id, rule(enabled=False))
    assert restarted.auto_rules()[0]["enabled"] is False
    restarted.change_auto_rule("delete", rule_id)
    assert restarted.auto_rules() == []
    with pytest.raises(ValueError, match="no longer exists"):
        restarted.change_auto_rule("delete", rule_id)


def test_rules_are_stored_without_changing_the_database_schema(library):
    library.change_auto_rule("create", rule=rule())
    db = next(library.root().glob("**/*.sqlite*"), None) or next(library.root().glob("**/*.db"))
    with sqlite3.connect(db) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        stored = json.loads(conn.execute("SELECT value FROM meta WHERE key='auto_rules'").fetchone()[0])
    assert tables == {"meta", "files", "trash", "collections", "smart_collections"}
    assert list(stored.values())[0]["name"] == "Bili"


def test_deleting_a_collection_removes_it_from_rules(library):
    music = library.change_collection("create", "Music")
    keep = library.change_auto_rule("create", rule=rule("Keep", actions={"tags": ["x"], "collections": [music]}))
    library.change_auto_rule("create", rule=rule("Only collection", {"kind": "audio"}, {"collections": [music]}))
    library.change_collection("delete", collection_id=music)
    remaining = library.auto_rules()
    assert [item["id"] for item in remaining] == [keep] and remaining[0]["actions"] == {"tags": ["x"]}


def test_rule_limit(library):
    for index in range(rules_mod.RULE_LIMIT):
        library.change_auto_rule("create", rule=rule(name=f"r{index}"))
    with pytest.raises(ValueError, match="up to 50"):
        library.change_auto_rule("create", rule=rule(name="one more"))


# ── Applying to downloads ──
def test_matching_rules_add_tags_collections_and_favorite_without_removing_anything(library):
    music = library.change_collection("create", "Music")
    study = library.change_collection("create", "Study")
    library.change_auto_rule("create", rule=rule("Bili", {"source": "bilibili.com"}, {"tags": ["B站"]}))
    library.change_auto_rule("create", rule=rule("Audio", {"kind": "audio"}, {"collections": [music], "favorite": True}))
    library.change_auto_rule("create", rule=rule("Off", {"kind": "audio"}, {"tags": ["never"]}, enabled=False))
    saved = download(library, "song.mp3", "https://www.bilibili.com/video/1")
    library.organize(saved, collection_id=study)
    library.describe("song.mp3", ["mine"], "")
    applied = library.apply_auto_rules(saved, kind_of)
    assert applied == [("song.mp3", ["Bili", "Audio"])]
    record = library.load()["files"]["song.mp3"]
    assert record["tags"] == ["mine", "B站"] and record["collections"] == [study, music] and record["favorite"] is True
    assert library.apply_auto_rules(saved, kind_of) == [("song.mp3", ["Bili", "Audio"])]
    assert library.load()["files"]["song.mp3"]["tags"] == ["mine", "B站"]  # idempotent


def test_conditions_must_all_match_and_subdomains_count(library):
    library.change_auto_rule("create", rule=rule("Bili video", {"source": "bilibili.com", "kind": "video"}))
    library.change_auto_rule("create", rule=rule("MP3", {"format": ".mp3"}, {"tags": ["mp3"]}))
    video = download(library, "clip.mp4", "https://m.bilibili.com/v/2")
    other = download(library, "other.mp4", "https://notbilibili.com/v/3")
    song = download(library, "song.mp3", "https://www.bilibili.com/a/4")
    assert library.apply_auto_rules(video + other + song, kind_of) == [("clip.mp4", ["Bili video"]),
                                                                        ("song.mp3", ["MP3"])]


def test_a_port_in_the_source_address_still_matches_the_site(library):
    library.change_auto_rule("create", rule=rule("NAS", {"source": "nas.example.com"}, {"tags": ["nas"]}))
    saved = download(library, "clip.mp4", "http://nas.example.com:8080/v/1")
    assert library.load()["files"]["clip.mp4"]["source"] == "nas.example.com:8080"
    assert library.apply_auto_rules(saved, kind_of) == [("clip.mp4", ["NAS"])]


def test_incomplete_downloads_and_unknown_paths_are_skipped(library):
    library.change_auto_rule("create", rule=rule("Any video", {"kind": "video"}))
    media(library, "part.mp4")
    saved = library.remember({"part.mp4": {"source_url": "https://bilibili.com/x", "complete": False}})
    assert library.apply_auto_rules([*saved, "missing.mp4"], kind_of) == []


def test_tags_never_exceed_the_library_limit(library):
    library.change_auto_rule("create", rule=rule("Lots", {"kind": "video"}, {"tags": [f"new{i}" for i in range(10)]}))
    saved = download(library, "clip.mp4", "https://example.com/v")
    library.describe("clip.mp4", [f"old{i}" for i in range(15)], "")
    library.apply_auto_rules(saved, kind_of)
    tags = library.load()["files"]["clip.mp4"]["tags"]
    assert len(tags) == 20 and tags[:15] == [f"old{i}" for i in range(15)]


def test_no_rules_means_no_write(library, monkeypatch):
    saved = download(library, "clip.mp4", "https://example.com/v")
    monkeypatch.setattr(type(library.store), "save", lambda self, value: pytest.fail("must not save"))
    assert library.apply_auto_rules(saved, kind_of) == []


# ── HTTP ──
@pytest.fixture
def server(tmp_path, monkeypatch):
    root = (tmp_path / "dl").resolve()
    root.mkdir()
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(webui, "LIBRARY", MediaLibrary(lambda: root, webui.MEDIA_SUFFIX))
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None):
    request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Token": webui.TOKEN})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def test_routes_create_list_and_reject_invalid_rules(server):
    assert call(server, "/api/library/auto-rules") == (200, {"auto_rules": []})
    status, body = call(server, "/api/library/auto-rules", {"action": "create", "rule": rule()})
    assert status == 200 and body["auto_rules"][0]["id"] == body["id"]
    assert call(server, "/api/library/auto-rules")[1]["auto_rules"][0]["conditions"] == {"source": "bilibili.com"}
    status, body = call(server, "/api/library/auto-rules", {"action": "create", "rule": rule("x", {"source": "?"})})
    assert status == 400 and "site such as" in body["error"]


# ── Applying to existing files ──
def test_existing_files_preview_then_apply_even_when_the_rule_is_off(library):
    rule_id = library.change_auto_rule("create", rule=rule("Bili", {"source": "bilibili.com"}, {"tags": ["B站"]},
                                                            enabled=False))
    download(library, "old.mp4", "https://www.bilibili.com/v/1")
    download(library, "done.mp4", "https://bilibili.com/v/2")
    download(library, "other.mp4", "https://example.com/v/3")
    library.describe("done.mp4", ["B站"], "")
    media(library, "untracked.mp4")  # discovered on disk, no record: no source, so no match
    files = [(name, "video") for name in ("old.mp4", "done.mp4", "other.mp4", "untracked.mp4")]
    before = library.load()
    assert library.apply_auto_rule_to_existing(rule_id, files, dry_run=True) == {"matched": 2, "changed": 1}
    assert library.load() == before
    assert library.apply_auto_rule_to_existing(rule_id, files, dry_run=False) == {"matched": 2, "changed": 1}
    assert library.load()["files"]["old.mp4"]["tags"] == ["B站"]
    assert library.apply_auto_rule_to_existing(rule_id, files, dry_run=False) == {"matched": 2, "changed": 0}


def test_kind_rules_can_classify_files_without_records_and_skip_incomplete_ones(library):
    rule_id = library.change_auto_rule("create", rule=rule("Audio", {"kind": "audio"}, {"favorite": True}))
    media(library, "loose.mp3")
    media(library, "part.mp3")
    library.remember({"part.mp3": {"source_url": "https://e.com", "complete": False}})
    result = library.apply_auto_rule_to_existing(rule_id, [("loose.mp3", "audio"), ("part.mp3", "audio")],
                                                 dry_run=False)
    assert result == {"matched": 1, "changed": 1}
    assert library.load()["files"]["loose.mp3"] == {"favorite": True}


def test_existing_files_need_a_valid_rule(library):
    with pytest.raises(ValueError, match="no longer exists"):
        library.apply_auto_rule_to_existing("f" * 32, [], dry_run=True)
    rule_id = library.change_auto_rule("create", rule=rule())
    with pytest.raises(ValueError, match="preview or apply"):
        library.apply_auto_rule_to_existing(rule_id, [], dry_run="yes")


def test_existing_files_route_uses_the_current_library(server):
    (webui.ROOT / "song.mp3").write_bytes(b"x")
    webui.LIBRARY.remember({"song.mp3": {"source_url": "https://www.bilibili.com/a", "complete": True}})
    rule_id = call(server, "/api/library/auto-rules", {"action": "create", "rule": rule()})[1]["id"]
    assert call(server, "/api/library/auto-rules", {"action": "preview_existing", "id": rule_id}) == \
        (200, {"matched": 1, "changed": 1})
    assert call(server, "/api/library/auto-rules", {"action": "apply_existing", "id": rule_id})[1]["changed"] == 1
    assert webui.LIBRARY.load()["files"]["song.mp3"]["tags"] == ["B站"]
