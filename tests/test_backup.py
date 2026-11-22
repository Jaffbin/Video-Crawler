import copy
import json
import threading
from unittest.mock import Mock

import pytest

import grab_backup
import webui
from grab_backup import BackupService, document
from test_webui import isolated, call  # noqa: F401 - isolated local API fixtures


@pytest.fixture
def server():
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    thread = threading.Thread(target=srv.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()
    thread.join()


def service():
    return BackupService(webui.LIBRARY, webui.CONFIG_DIR / "desktop.json", threading.RLock())


def source():
    return {"format": "video-grabber-backup", "version": 1,
            "preferences": {"download": {"mode": "mp3", "abr": 320}, "theme": "light", "presets": []},
            "desktop": {"close_behavior": "background", "notifications_enabled": False},
            "library": {"collections": {"a" * 32: "Music"}, "files": [
                {"path": "clip.mp4", "size": 4, "annotations": {"note": "backup note", "favorite": True,
                    "tags": ["music"], "collections": ["a" * 32], "playback": {"position": 2, "duration": 10}}}]}}


def test_export_only_includes_allowlisted_preferences_and_annotations():
    (webui.ROOT / "clip.mp4").write_bytes(b"clip")
    webui.LIBRARY.remember({"clip.mp4": {"source_url": "https://example.invalid/?secret=private", "complete": True}})
    webui.LIBRARY.describe("clip.mp4", ["favorite"], "My note")
    prefs = {"download": {"mode": "mp3", "proxy": "secret-proxy", "referer": "private-referer", "cookies_from_browser": "chrome"},
             "presets": [{"id": "b" * 32, "name": "Mine", "options": {"mode": "mp3", "proxy": "secret-proxy"}}],
             "root": "private-path", "cookies": "secret-cookie"}
    exported = service().export(prefs)
    serialized = json.dumps(exported)
    assert all(secret not in serialized for secret in ("secret-proxy", "private-referer", "secret-cookie", "private-path", "private", "source_url"))
    assert exported["library"]["files"][0]["annotations"] == {"tags": ["favorite"], "note": "My note"}
    assert exported["preferences"]["presets"][0]["options"]["mode"] == "mp3"
    assert (webui.ROOT / "clip.mp4").read_bytes() == b"clip"


def test_preview_is_read_only_and_restore_merges_without_overwriting_existing_values():
    path = webui.ROOT / "clip.mp4"
    path.write_bytes(b"clip")
    current_id = webui.LIBRARY.change_collection("create", "Music")
    webui.LIBRARY.describe("clip.mp4", ["current"], "current note")
    webui.LIBRARY.organize(["clip.mp4"], favorite=False)
    webui.LIBRARY.save_playback("clip.mp4", 1, 10)
    before = webui.LIBRARY.store.path().read_bytes()
    mtime = path.stat().st_mtime_ns
    current = {"download": {"mode": "mp4"}, "theme": "dark"}
    api = service()
    preview = api.preview(source(), current)
    assert webui.LIBRARY.store.path().read_bytes() == before
    assert preview["counts"]["conflicts"] >= 4 and preview["counts"]["collections"] == 0
    assert preview["browser"]["download"] == {"mode": "mp4", "abr": 320}
    api.restore(source(), current, preview["review_token"])
    record = webui.LIBRARY.load()["files"]["clip.mp4"]
    assert record["note"] == "current note" and record["favorite"] is False and record["playback"]["position"] == 1
    assert record["tags"] == ["current", "music"] and record["collections"] == [current_id]
    assert path.read_bytes() == b"clip" and path.stat().st_mtime_ns == mtime
    assert api.preview(source(), current)["counts"]["files"] == 0


def test_unmatched_media_is_reported_and_can_be_restored_after_copying():
    api = service()
    review = api.preview(source(), {})
    assert review["skipped"] == [{"path": "clip.mp4", "reason": "missing"}]
    (webui.ROOT / "clip.mp4").write_bytes(b"different")
    assert api.preview(source(), {})["skipped"][0]["reason"] == "size"
    (webui.ROOT / "clip.mp4").write_bytes(b"clip")
    review = api.preview(source(), {})
    api.restore(source(), {}, review["review_token"])
    assert webui.LIBRARY.load()["files"]["clip.mp4"]["note"] == "backup note"


def test_existing_preset_names_and_ids_win_conflicts():
    data = source()
    preset = {"id": "b" * 32, "name": "My preset", "options": {"mode": "mp3"}}
    data["preferences"]["presets"] = [preset, {**preset, "id": "c" * 32, "name": "Other"}]
    current = {"presets": [{**preset, "id": "d" * 32, "name": "MY PRESET", "options": {"mode": "mp4"}}]}
    review = service().preview(data, current)
    assert review["counts"]["presets"] == 1 and review["browser"]["presets"][0]["options"]["mode"] == "mp4"


def test_smart_collections_export_merge_and_keep_current_conflicts():
    key = webui.LIBRARY.change_smart_collection("create", "Study", rules={"tag": "study", "kind": "video"})
    exported = service().export({})
    assert exported["library"]["smart_collections"][key]["rules"] == {"tag": "study", "kind": "video"}
    incoming = source()
    incoming["library"]["smart_collections"] = {
        key: {"name": "Other name", "rules": {"kind": "audio"}},
        "c" * 32: {"name": "STUDY", "rules": {"favorite": True}},
        "d" * 32: {"name": "Recent", "rules": {"recent_days": 7}},
    }
    review = service().preview(incoming, {})
    assert review["counts"]["smart_collections"] == 1 and review["counts"]["conflicts"] == 2
    service().restore(incoming, {}, review["review_token"])
    assert webui.LIBRARY.load()["smart_collections"] == {
        key: {"name": "Study", "rules": {"tag": "study", "kind": "video"}},
        "d" * 32: {"name": "Recent", "rules": {"recent_days": 7}},
    }
    assert document(source())["library"]["smart_collections"] == {}
    assert service().preview(incoming, {})["counts"]["smart_collections"] == 0


@pytest.mark.parametrize("value", [{"bad": {"name": "Mine", "rules": {"kind": "video"}}},
    {"a" * 32: {"name": "Mine", "rules": {}}}, {"a" * 32: {"name": "Mine", "rules": {"kind": "video", "future": True}}},
    [], {f"{index:032x}": {"name": str(index), "rules": {"kind": "video"}} for index in range(101)}])
def test_invalid_smart_collection_backups_are_rejected(value):
    backup = source()
    backup["library"]["smart_collections"] = value
    with pytest.raises(ValueError):
        document(backup)


def test_smart_rule_edits_invalidate_backup_preview():
    key = webui.LIBRARY.change_smart_collection("create", "Mine", rules={"kind": "video"})
    review = service().preview(source(), {})
    webui.LIBRARY.change_smart_collection("update", "Mine", key, {"kind": "audio"})
    with pytest.raises(ValueError, match="Data changed"):
        service().restore(source(), {}, review["review_token"])


def test_stale_preview_never_writes_after_files_or_annotations_change():
    path = webui.ROOT / "clip.mp4"
    path.write_bytes(b"clip")
    api = service()
    review = api.preview(source(), {})
    webui.LIBRARY.describe("clip.mp4", [], "Changed while previewing")
    before = webui.LIBRARY.store.path().read_bytes()
    with pytest.raises(ValueError, match="Data changed"):
        api.restore(source(), {}, review["review_token"])
    assert webui.LIBRARY.store.path().read_bytes() == before
    review = api.preview(source(), {})
    path.write_bytes(b"new size")
    with pytest.raises(ValueError, match="Data changed"):
        api.restore(source(), {}, review["review_token"])


def test_write_failure_rolls_back_documents_without_touching_media(monkeypatch):
    path = webui.ROOT / "clip.mp4"
    path.write_bytes(b"clip")
    webui.LIBRARY.describe("clip.mp4", [], "existing")
    before = webui.LIBRARY.store.path().read_bytes()
    api = service()
    review = api.preview(source(), {})
    replace = grab_backup.os.replace
    def fail_desktop(src, dst):
        if dst == api.desktop_store.path():
            raise PermissionError("fixture")
        return replace(src, dst)
    monkeypatch.setattr(grab_backup.os, "replace", fail_desktop)
    with pytest.raises(OSError):
        api.restore(source(), {}, review["review_token"])
    assert webui.LIBRARY.store.path().read_bytes() == before
    assert not api.desktop_store.path().exists() and path.read_bytes() == b"clip"
    assert not list(webui.ROOT.glob(".backup-restore-*"))


def test_recovery_copy_is_kept_if_windows_also_blocks_rollback(monkeypatch, caplog):
    (webui.ROOT / "clip.mp4").write_bytes(b"clip")
    webui.LIBRARY.describe("clip.mp4", [], "original")
    before = webui.LIBRARY.store.path().read_bytes()
    api = service()
    review = api.preview(source(), {})
    replace, count = grab_backup.os.replace, 0
    def fail_after_first(src, dst):
        nonlocal count
        count += 1
        if count > 1:
            raise PermissionError("fixture")
        return replace(src, dst)
    monkeypatch.setattr(grab_backup.os, "replace", fail_after_first)
    with pytest.raises(OSError, match="recovery copies"):
        api.restore(source(), {}, review["review_token"])
    copies = list(webui.ROOT.glob(".backup-restore-*"))
    assert len(copies) == 1 and copies[0].read_bytes() == before
    assert "Original recovery copy retained" in caplog.text


@pytest.mark.parametrize("mutation", ["version", "path", "size", "progress", "preset", "collection", "nan"])
def test_malformed_backups_are_rejected(mutation):
    data = copy.deepcopy(source())
    if mutation == "version":
        data["version"] = 99
    elif mutation == "path":
        data["library"]["files"][0]["path"] = "../outside.mp4"
    elif mutation == "size":
        data["library"]["files"][0]["size"] = -1
    elif mutation == "progress":
        data["library"]["files"][0]["annotations"]["playback"]["position"] = 20
    elif mutation == "preset":
        data["preferences"]["presets"] = [{"id": "bad", "name": "test", "options": {}}]
    elif mutation == "collection":
        data["library"]["collections"] = {}
    else:
        data["library"]["files"][0]["size"] = float("nan")
    with pytest.raises(ValueError):
        document(data)


def test_backup_api_requires_auth_and_preserves_root_queue_and_subscriptions(server, monkeypatch):
    monkeypatch.setattr(webui, "WINDOW_MODE", False)
    (webui.ROOT / "clip.mp4").write_bytes(b"clip")
    assert call(server, "/api/backup/export", {"preferences": {}}, token=False)[0] == 401
    root = webui.ROOT
    job_id = webui.create_jobs(["https://example.invalid"], {})[0]
    result = call(server, "/api/backup/preview", {"backup": source(), "current": {}})[1]
    assert call(server, "/api/backup/restore", {"backup": source(), "current": {}})[0] == 400
    assert call(server, "/api/backup/restore", {"backup": source(), "current": {}, "review_token": result["review_token"]})[0] == 200
    assert webui.ROOT == root and webui.JOB_MANAGER.get(job_id).status == "queued"
    assert not webui.SUBSCRIPTION_MANAGER.snapshot()


def test_restored_desktop_preferences_refresh_the_running_controller(server, monkeypatch):
    from grab_desktop import DesktopController
    desktop = DesktopController(Mock(), Mock(), server, preferences_path=webui.CONFIG_DIR / "desktop.json")
    monkeypatch.setattr(webui, "WINDOW_MODE", True)
    monkeypatch.setattr(webui, "NATIVE_DESKTOP", desktop)
    body = {"backup": source(), "current": {}}
    review = call(server, "/api/backup/preview", body)[1]
    assert call(server, "/api/backup/restore", {**body, "review_token": review["review_token"]})[0] == 200
    assert desktop.close_behavior == "background" and not desktop.notifications_enabled


def auto_rule(name="Music from Bili", collections=("a" * 32,)):
    return {"name": name, "enabled": True, "conditions": {"source": "bilibili.com", "kind": "audio"},
            "actions": {"tags": ["B站"], "collections": list(collections), "favorite": True}}


def test_auto_rules_survive_export_and_restore_into_an_empty_library():
    music = webui.LIBRARY.change_collection("create", "Music")
    key = webui.LIBRARY.change_auto_rule("create", rule=auto_rule(collections=[music]))
    exported = service().export({})
    assert exported["library"]["auto_rules"][key]["actions"]["collections"] == [music]
    webui.LIBRARY.change_auto_rule("delete", key)
    webui.LIBRARY.change_collection("delete", collection_id=music)
    review = service().preview(exported, {})
    assert review["counts"]["auto_rules"] == 1 and review["counts"]["collections"] == 1
    service().restore(exported, {}, review["review_token"])
    restored = webui.LIBRARY.auto_rules()
    assert [rule["name"] for rule in restored] == ["Music from Bili"]
    assert restored[0]["actions"]["collections"] == [music] and webui.LIBRARY.collections()[0]["name"] == "Music"


def test_restored_rules_follow_collections_merged_by_name():
    current = webui.LIBRARY.change_collection("create", "music")  # same name, different identifier
    incoming = source()
    incoming["library"]["auto_rules"] = {"b" * 32: auto_rule()}
    review = service().preview(incoming, {})
    assert review["counts"]["collections"] == 0 and review["counts"]["auto_rules"] == 1
    service().restore(incoming, {}, review["review_token"])
    assert webui.LIBRARY.auto_rules()[0]["actions"]["collections"] == [current]


def test_existing_rules_win_and_differences_count_as_conflicts():
    key = webui.LIBRARY.change_auto_rule("create", rule={**auto_rule(collections=[]), "actions": {"tags": ["mine"]}})
    incoming = source()
    incoming["library"]["auto_rules"] = {key: auto_rule(name="Renamed"), "c" * 32: auto_rule(name="MUSIC FROM BILI"),
                                         "d" * 32: auto_rule(name="New one")}
    review = service().preview(incoming, {})
    assert review["counts"]["auto_rules"] == 1 and review["counts"]["conflicts"] >= 2
    service().restore(incoming, {}, review["review_token"])
    rules = {rule["name"]: rule for rule in webui.LIBRARY.auto_rules()}
    assert set(rules) == {"Music from Bili", "New one"} and rules["Music from Bili"]["actions"] == {"tags": ["mine"]}


def test_older_backups_without_auto_rules_still_restore():
    assert document(source())["library"]["auto_rules"] == {}
    review = service().preview(source(), {})
    assert review["counts"]["auto_rules"] == 0


@pytest.mark.parametrize("value", [
    [],
    {"bad": auto_rule()},
    {"b" * 32: auto_rule(collections=["e" * 32])},  # collection not in the backup
    {"b" * 32: {**auto_rule(), "conditions": {}}},
    {"b" * 32: auto_rule(), "c" * 32: auto_rule(name="music from bili")},
    {f"{index:032x}": auto_rule(name=str(index)) for index in range(51)},
])
def test_invalid_auto_rule_backups_are_rejected(value):
    backup = source()
    backup["library"]["auto_rules"] = value
    with pytest.raises(ValueError):
        document(backup)


# ── Subscriptions ──
def live_subscription(url="https://example.com/channel", **changes):
    sub = webui.Subscription(url, {"mode": "mp3", "abr": 320, "proxy": "http://secret-proxy:1",
                                   "cookies_from_browser": "chrome", "referer": "https://private-referer"},
                             "recent", 5, {"include_keywords": ["talk"], "max_duration": 600})
    sub.title = "My channel"
    sub.seen_ids = {"seen-1", "seen-2"}
    sub.initialized = True
    sub.export_media = True
    for key, value in changes.items():
        setattr(sub, key, value)
    return sub


def test_subscriptions_export_without_sign_in_proxy_or_history():
    exported = service().export({}, subscriptions=[live_subscription().to_dict()])
    serialized = json.dumps(exported)
    assert all(secret not in serialized for secret in ("secret-proxy", "chrome", "private-referer", "seen-1"))
    assert exported["subscriptions"] == [{
        "url": "https://example.com/channel", "title": "My channel", "options": {"mode": "mp3", "abr": 320},
        "filters": webui.normalize_subscription_filters({"include_keywords": ["talk"], "max_duration": 600}),
        "enabled": True, "export_media": True}]
    assert document(exported)["subscriptions"] == exported["subscriptions"]


def test_restored_subscriptions_start_fresh_and_existing_links_win(server, monkeypatch):
    monkeypatch.setattr(webui, "WINDOW_MODE", False)
    monkeypatch.setattr(webui, "start_subscription_check", lambda sub: None)
    backup = service().export({}, subscriptions=[
        live_subscription().to_dict(), live_subscription("https://example.com/kept", enabled=False).to_dict()])
    existing = webui.Subscription("https://example.com/kept", {"mode": "mp4"})
    webui.SUBSCRIPTION_MANAGER.add(existing)
    status, review = call(server, "/api/backup/preview", {"backup": backup, "current": {}})
    assert status == 200 and review["counts"]["subscriptions"] == 1
    status, _ = call(server, "/api/backup/restore", {"backup": backup, "current": {},
                                                      "review_token": review["review_token"]})
    assert status == 200
    subs = {sub.url: sub for sub in webui.SUBSCRIPTION_MANAGER.snapshot()}
    assert subs["https://example.com/kept"] is existing and existing.options == {"mode": "mp4"}
    restored = subs["https://example.com/channel"]
    assert restored.options == {"mode": "mp3", "abr": 320} and restored.title == "My channel"
    assert restored.filters["include_keywords"] == ["talk"] and restored.export_media is True
    # A restored subscription behaves like a new one: nothing seen yet, no back-fill of old uploads.
    assert restored.seen_ids == set() and restored.initialized is False and restored.backfill == "none"
    saved = json.loads(webui.SUBSCRIPTIONS_STORE.path().read_text(encoding="utf-8"))
    assert {item["url"] for item in saved["subscriptions"]} == set(subs)
    # Restoring the same backup again adds nothing.
    review = call(server, "/api/backup/preview", {"backup": backup, "current": {}})[1]
    assert review["counts"]["subscriptions"] == 0


def test_adding_a_backed_up_link_after_preview_invalidates_it():
    backup = service().export({}, subscriptions=[live_subscription().to_dict()])
    api = service()
    review = api.preview(backup, {}, [])
    # An unrelated subscription does not change what the restore would add.
    assert api.restore(backup, {}, review["review_token"], ["https://example.com/other"])[1]
    review = api.preview(backup, {}, [])
    with pytest.raises(ValueError, match="changed since preview"):
        api.restore(backup, {}, review["review_token"], ["https://example.com/channel"])


@pytest.mark.parametrize("value", [
    "not a list",
    [{"url": "ftp://example.com/x"}],
    [{"url": "javascript:alert(1)"}],
    [{"url": "https://example.com/a"}, {"url": "https://example.com/a"}],
    [{"url": "https://example.com/a", "options": {"mode": "image"}}],
    [{"url": "https://example.com/a", "options": {"proxy": "http://x"}, "filters": {"include_keywords": "x" * 999}}],
    [{"url": "https://example.com/a", "enabled": "yes"}],
    [{"url": "https://example.com/a", "title": "bad\x00title"}],
    [{"url": f"https://example.com/{i}"} for i in range(grab_backup.SUBSCRIPTION_LIMIT + 1)],
])
def test_invalid_subscription_backups_are_rejected(value):
    backup = source()
    backup["subscriptions"] = value
    with pytest.raises(ValueError):
        document(backup)


def test_older_backups_without_subscriptions_still_restore():
    backup = source()
    assert "subscriptions" not in backup
    assert document(backup)["subscriptions"] == []
