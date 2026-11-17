"""Media server export: layout, NFO files, hard link or copy, and never overwriting."""
import datetime
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import grab_mediaexport as mx
from grab_library import MediaLibrary, clean_media_info
import webui

RECORD = {
    "title": "How to: build a <shed>?", "source": "www.youtube.com",
    "source_url": "https://www.youtube.com/watch?v=abc123", "downloaded": 1_700_000_000,
    "media_info": {"id": "abc123", "channel": "Wood/Works", "upload_date": "20261115",
                   "description": "Step by step & safe.", "duration": 754, "extractor": "Youtube"},
}


@pytest.fixture
def library(tmp_path):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "shed.mp4").write_bytes(b"video-bytes")
    (lib / "shed.jpg").write_bytes(b"jpg")
    (lib / "shed.en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    (lib / "shed.transcript.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    return lib


def test_names_are_safe_for_windows_and_media_servers():
    assert mx.safe_name('A/B: "c"?  ') == "A B c"
    assert mx.safe_name("...") == "Untitled"
    assert len(mx.safe_name("x" * 500)) == 120


def test_episode_info_uses_site_facts_and_falls_back_for_older_downloads():
    info = mx.episode_info(RECORD, "shed.mp4")
    assert info["show"] == "Wood Works" and info["date"] == datetime.date(2026, 11, 15) and info["key"] == "abc123"
    old = mx.episode_info({"title": "Old", "source": "vimeo.com", "downloaded": 1_700_000_000}, "old.mp4")
    assert old["show"] == "vimeo.com" and old["date"] == datetime.date.fromtimestamp(1_700_000_000)
    assert len(old["key"]) == 11  # stable key from the Library path
    assert mx.episode_info({}, "x.mp4")["show"] == "Other"


def test_export_builds_the_show_season_episode_layout(library, tmp_path):
    out = tmp_path / "media"
    result = mx.export_video(library / "shed.mp4", RECORD, "shed.mp4", out)
    season = out / "Wood Works" / "Season 2026"
    base = "Wood Works - S2026E111501 - How to build a shed [abc123]"
    assert result == {"status": "exported", "method": "hardlink", "target": str(season / f"{base}.mp4")}
    assert sorted(p.name for p in season.iterdir()) == sorted([
        f"{base}.mp4", f"{base}.nfo", f"{base}-thumb.jpg", f"{base}.en.srt", f"{base}.transcript.srt"])
    assert os.path.samefile(season / f"{base}.mp4", library / "shed.mp4")  # no extra disk space
    assert (out / "Wood Works" / "poster.jpg").read_bytes() == b"jpg"
    episode = ET.parse(season / f"{base}.nfo").getroot()
    assert episode.tag == "episodedetails"
    assert episode.findtext("title") == "How to: build a <shed>?"  # escaped, not stripped
    assert episode.findtext("season") == "2026" and episode.findtext("episode") == "111501"
    assert episode.findtext("aired") == "2026-11-15" and episode.findtext("plot") == "Step by step & safe."
    assert episode.findtext("runtime") == "13" and episode.find("uniqueid").attrib["type"] == "youtube"
    assert ET.parse(out / "Wood Works" / "tvshow.nfo").getroot().findtext("title") == "Wood Works"


def test_exporting_again_reuses_the_episode_and_new_videos_get_the_next_number(library, tmp_path):
    out = tmp_path / "media"
    first = mx.export_video(library / "shed.mp4", RECORD, "shed.mp4", out)
    again = mx.export_video(library / "shed.mp4", {**RECORD, "title": "Renamed later"}, "shed.mp4", out)
    assert again["status"] == "exists" and again["target"] == first["target"]
    (library / "fence.mp4").write_bytes(b"other")
    second = {**RECORD, "title": "Fence", "media_info": {**RECORD["media_info"], "id": "def456"}}
    result = mx.export_video(library / "fence.mp4", second, "fence.mp4", out)
    assert " - S2026E111502 - Fence [def456].mp4" in result["target"]


def test_a_different_file_is_never_overwritten(library, tmp_path):
    out = tmp_path / "media"
    target = Path(mx.export_video(library / "shed.mp4", RECORD, "shed.mp4", out)["target"])
    os.unlink(target)
    target.write_bytes(b"someone else's edit")
    with pytest.raises(mx.ExportError, match="different file"):
        mx.export_video(library / "shed.mp4", RECORD, "shed.mp4", out)
    assert target.read_bytes() == b"someone else's edit"


def test_another_disk_gets_a_copy(library, tmp_path, monkeypatch):
    def cross_device(source, target):
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(mx.os, "link", cross_device)
    result = mx.export_video(library / "shed.mp4", RECORD, "shed.mp4", tmp_path / "media")
    assert result["method"] == "copy" and Path(result["target"]).read_bytes() == b"video-bytes"
    assert not os.path.samefile(result["target"], library / "shed.mp4")
    assert not list((tmp_path / "media").rglob("*.part"))


def test_a_missing_file_is_reported(tmp_path):
    with pytest.raises(mx.ExportError, match="no longer exists"):
        mx.export_video(tmp_path / "gone.mp4", RECORD, "gone.mp4", tmp_path / "media")


def test_the_export_folder_must_be_absolute_and_outside_the_download_folder(tmp_path):
    library = tmp_path / "lib"
    library.mkdir()
    assert mx.check_folder(str(tmp_path / "media"), library) == (tmp_path / "media").resolve()
    for bad in ("", "  ", "relative/path", str(library), str(library / "inside"), None):
        with pytest.raises(mx.ExportError):
            mx.check_folder(bad, library)


# ── Recording the facts at download time ──
def test_site_facts_are_kept_bounded_with_the_library_record(tmp_path):
    assert webui.media_info({"id": "abc", "uploader": "Chan", "upload_date": "20261115", "title": "x",
                             "description": "", "duration": 12}) == {
        "id": "abc", "channel": "Chan", "upload_date": "20261115", "duration": 12}
    assert clean_media_info({"description": "d" * 9000, "upload_date": "2026-11", "duration": -5,
                             "channel": "bad\x00name"}) == {"description": "d" * 5000, "channel": "badname"}
    library = MediaLibrary(lambda: tmp_path, {".mp4"})
    (tmp_path / "v.mp4").write_bytes(b"x")
    library.remember({"v.mp4": {"source_url": "https://www.youtube.com/watch?v=abc", "title": "V",
                                "complete": True, "media_info": {"id": "abc", "channel": "Chan"}}})
    assert library.load()["files"]["v.mp4"]["media_info"] == {"id": "abc", "channel": "Chan"}


# ── Settings, subscriptions, rules and the post-download step ──
import json  # noqa: E402
import threading  # noqa: E402
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

import grab_auto_rules  # noqa: E402
from grab_models import Job, Subscription  # noqa: E402

SESSION = {"Cookie": f"{webui.SESSION_COOKIE}={webui.SESSION_SECRET}"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    root = (tmp_path / "dl").resolve()
    root.mkdir()
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(webui, "LIBRARY", MediaLibrary(lambda: root, webui.MEDIA_SUFFIX))
    monkeypatch.setattr(webui, "FILES_CACHE", {"rev": None, "ts": 0.0, "data": []})
    webui.SUBSCRIPTION_MANAGER.reset()
    for name in ("shed.mp4", "song.mp3"):
        (root / name).write_bytes(b"bytes-" + name.encode())
    webui.LIBRARY.remember({
        "shed.mp4": {**RECORD, "complete": True},
        "song.mp3": {"source_url": "https://www.youtube.com/watch?v=s1", "title": "Song", "complete": True},
    })
    yield root, tmp_path / "media"
    webui.SUBSCRIPTION_MANAGER.reset()


def test_subscription_flag_round_trips():
    sub = Subscription("https://www.youtube.com/@wood", {"mode": "mp4"})
    assert sub.export_media is False and sub.view(3600, False)["export_media"] is False
    sub.export_media = True
    again = Subscription.from_dict(sub.to_dict())
    assert again.export_media is True and again.view(3600, False)["export_media"] is True


def test_rules_can_export_and_validation_stays_strict():
    rule = grab_auto_rules.check_rule({"name": "To NAS", "conditions": {"kind": "video"}, "actions": {"export": True}},
                                      {})
    assert rule["actions"] == {"export": True}
    with pytest.raises(ValueError):
        grab_auto_rules.check_rule({"name": "x", "conditions": {"kind": "video"}, "actions": {"export": "yes"}}, {})


def test_folder_setting_is_validated_and_export_is_off_until_set(app):
    root, media = app
    assert webui.media_export_status() == {"folder": "", "ready": False, "error": ""}
    with pytest.raises(mx.ExportError, match="outside the download folder"):
        webui.save_media_export_folder(str(root / "nas"))
    with pytest.raises(mx.ExportError, match="Choose a media server folder"):
        webui.export_to_media_server(["shed.mp4"])
    assert webui.save_media_export_folder(str(media))["ready"] is True
    assert webui.save_media_export_folder("")["folder"] == ""


def test_export_counts_videos_and_skips_audio_and_missing_files(app):
    root, media = app
    webui.save_media_export_folder(str(media))
    lines = []
    result = webui.export_to_media_server(["shed.mp4", "song.mp3", "gone.mp4"], lines.append)
    assert result["exported"] == 1 and result["skipped"] == 1 and result["failed"][0]["path"] == "gone.mp4"
    assert webui.export_to_media_server(["shed.mp4"])["existing"] == 1
    assert any("Exported shed.mp4 (hardlink)" in line for line in lines)
    assert (media / "Wood Works" / "tvshow.nfo").is_file()


def test_new_downloads_export_for_a_flagged_subscription_or_a_matching_rule(app):
    root, media = app
    webui.save_media_export_folder(str(media))
    sub = Subscription("https://www.youtube.com/@wood", {"mode": "mp4"})
    webui.SUBSCRIPTION_MANAGER.add(sub)
    job = Job("https://www.youtube.com/watch?v=abc123", {"mode": "mp4"})
    job.source = sub.id
    lines = []
    webui.export_new_download(job, ["shed.mp4"], lines.append)
    assert lines == [] and not media.exists()  # subscription not flagged, no rule
    sub.export_media = True
    webui.export_new_download(job, ["shed.mp4"], lines.append)
    assert any("Exported shed.mp4" in line for line in lines)
    plain = Job("https://example.com/x", {"mode": "mp4"})
    webui.LIBRARY.change_auto_rule("create", rule={"name": "NAS", "conditions": {"source": "youtube.com"},
                                                   "actions": {"export": True}})
    webui.export_new_download(plain, ["shed.mp4"], lines.append)
    assert any("Already exported shed.mp4" in line for line in lines)


def test_a_missing_folder_is_logged_instead_of_failing_the_download(app):
    sub = Subscription("https://www.youtube.com/@wood", {"mode": "mp4"})
    sub.export_media = True
    webui.SUBSCRIPTION_MANAGER.add(sub)
    job = Job("https://www.youtube.com/watch?v=abc123", {"mode": "mp4"})
    job.source = sub.id
    lines = []
    webui.export_new_download(job, ["shed.mp4"], lines.append)
    assert any("Not exported to the media server folder" in line for line in lines)


@pytest.fixture
def server(app):
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", app
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None, headers=None):
    request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Token": webui.TOKEN,
                                              **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def test_only_the_app_window_can_choose_the_folder_or_export(server):
    base, (root, media) = server
    extension = {"X-Grab-Client": "extension"}
    assert call(base, "/api/media-export", headers=extension)[0] == 403
    assert call(base, "/api/media-export", {"action": "folder", "folder": str(media)}, extension)[0] == 403
    assert call(base, "/api/media-export", {"action": "export", "paths": ["shed.mp4"]}, extension)[0] == 403
    status, body = call(base, "/api/media-export", {"action": "folder", "folder": str(media)}, SESSION)
    assert status == 200 and body["ready"] is True
    status, body = call(base, "/api/media-export", {"action": "export", "paths": ["shed.mp4", "song.mp3"]}, SESSION)
    assert status == 200 and body["exported"] == 1 and body["skipped"] == 1
    assert call(base, "/api/media-export", {"action": "export", "paths": []}, SESSION)[0] == 400


def test_existing_files_preview_and_export_through_a_rule(server):
    base, (root, media) = server
    call(base, "/api/media-export", {"action": "folder", "folder": str(media)}, SESSION)
    rule_id = call(base, "/api/library/auto-rules", {"action": "create", "rule": {
        "name": "NAS", "conditions": {"source": "youtube.com"}, "actions": {"export": True}}})[1]["id"]
    status, body = call(base, "/api/library/auto-rules", {"action": "preview_existing", "id": rule_id})
    assert status == 200 and body == {"matched": 2, "changed": 0, "export": 1}
    assert not media.exists()
    status, body = call(base, "/api/library/auto-rules", {"action": "apply_existing", "id": rule_id})
    assert body["exported"] == 1 and body["export_failed"] == 0
    assert list((media / "Wood Works" / "Season 2026").glob("*.mp4"))


def test_the_site_name_stands_in_for_a_missing_channel_without_port_or_www(library, tmp_path):
    assert mx.episode_info({"source": "www.example.com:8080"}, "x.mp4")["show"] == "example.com"
    result = mx.export_video(library / "shed.mp4", {"title": "Shed", "source": "127.0.0.1:8961"}, "shed.mp4",
                             tmp_path / "media")
    assert "/127.0.0.1/" in result["target"].replace("\\", "/")
    nfo = Path(result["target"]).with_suffix(".nfo")
    assert ET.parse(nfo).getroot().find("trailer") is None  # Kodi would offer it as a playable trailer
