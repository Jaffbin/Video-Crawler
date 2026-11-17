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
