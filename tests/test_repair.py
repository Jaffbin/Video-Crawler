import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from yt_dlp.utils import DownloadCancelled

import grab
import grab_repair
from grab_library import MediaLibrary


@pytest.fixture
def local_media(tmp_path, media_site):
    library = MediaLibrary(lambda: tmp_path, {".mp4", ".m4a", ".mp3"})
    source = tmp_path / "video.mp4"
    shutil.copy2(media_site["root"] / "clip.mp4", source)
    location = Path(grab.ffmpeg_location())
    ffmpeg = location / "ffmpeg.exe" if location.is_dir() else location
    record = {"complete": False, "source_url": "https://example.com/video", "title": "Video",
              "repair_options": {"mode": "mp4"}}
    library.remember({source.name: record})
    return library, source, ffmpeg


def do_repair(fixture, **options):
    library, source, ffmpeg = fixture
    return grab_repair.repair(library, source.name, library.load()["files"], {"mode": "mp4", **options}, ffmpeg,
                              check=lambda: None, log=lambda message: None)


def test_local_repair_remuxes_and_marks_complete(local_media):
    library, source, ffmpeg = local_media
    assert do_repair(local_media) == "video.mp4"
    assert library.load()["files"]["video.mp4"]["complete"] is True
    assert grab_repair.probe(source, ffmpeg.with_name("ffprobe.exe"))["audio"]
    assert not list(library.root().glob(".repair-*"))


def test_repair_preserves_classification_changes_made_during_processing(local_media, monkeypatch):
    library, source, _ = local_media
    old = library.change_collection("create", "Old")
    new = library.change_collection("create", "New")
    library.organize([source.name], favorite=False, collection_id=old)
    original = grab_repair.process

    def process(*args):
        original(*args)
        library.organize([source.name], favorite=True, collection_id=new)
        library.change_collection("delete", collection_id=old)

    monkeypatch.setattr(grab_repair, "process", process)
    do_repair(local_media)
    record = library.load()["files"][source.name]
    assert record["favorite"] is True and record["collections"] == [new] and record["complete"] is True


def test_local_repair_embeds_cover_and_subtitles(local_media):
    library, source, ffmpeg = local_media
    cover = source.with_suffix(".jpg")
    subprocess.run([str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "color=blue:s=64x64", "-frames:v", "1", str(cover)], check=True)
    source.with_suffix(".en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
    do_repair(local_media, cover=True, embed_subs=True)
    result = subprocess.run([str(ffmpeg.with_name("ffprobe.exe")), "-v", "error", "-show_streams", "-of", "json", str(source)],
                            capture_output=True, text=True, check=True)
    import json
    streams = json.loads(result.stdout)["streams"]
    assert any(stream.get("disposition", {}).get("attached_pic") for stream in streams)
    assert any(stream["codec_type"] == "subtitle" for stream in streams)
    assert cover.is_file()
    # A later failure may leave only the already embedded assets, with no sidecar files.
    cover.unlink()
    source.with_suffix(".en.srt").unlink()
    record = library.load()["files"][source.name]
    record["complete"] = False
    library.remember({source.name: record})
    do_repair(local_media, cover=True, embed_subs=True)
    preserved = grab_repair.probe(source, ffmpeg.with_name("ffprobe.exe"))
    assert preserved["cover_indexes"] and preserved["subtitle_indexes"]


def test_local_repair_merges_split_files_and_keeps_originals_in_recovery(local_media):
    library, source, ffmpeg = local_media
    video, audio = source.with_name("video.f400.mp4"), source.with_name("video.f140-1.m4a")
    for path, stream in ((video, "0:v:0"), (audio, "0:a:0")):
        subprocess.run([str(ffmpeg), "-v", "error", "-i", str(source), "-map", stream, "-c", "copy", str(path)], check=True)
    source.unlink()
    record = library.load()["files"][source.name]
    library.remember({video.name: record, audio.name: record})
    assert do_repair((library, video, ffmpeg)) == "video.mp4"
    assert source.is_file() and not video.exists() and not audio.exists()
    assert len(library.trash_items()) == 2
    assert library.load()["files"][source.name]["complete"] is True


def test_local_repair_converts_to_mp3(local_media):
    library, source, ffmpeg = local_media
    assert do_repair(local_media, mode="mp3", abr=128) == "video.mp3"
    assert (source.with_suffix(".mp3")).is_file()
    assert len(library.trash_items()) == 1


def test_mp3_repair_keeps_cover_with_output_and_recovers_only_original_media(local_media):
    library, source, ffmpeg = local_media
    cover = source.with_suffix(".jpg")
    subprocess.run([str(ffmpeg), "-v", "error", "-f", "lavfi", "-i", "color=blue:s=64x64", "-frames:v", "1", str(cover)], check=True)
    assert do_repair(local_media, mode="mp3", cover=True) == "video.mp3"
    assert cover.is_file() and not source.exists()
    assert len(library.trash_items()) == 1
    result = grab_repair.probe(source.with_suffix(".mp3"), ffmpeg.with_name("ffprobe.exe"))
    assert result["audio"] and result["cover_indexes"]


@pytest.mark.parametrize("failure", ["process", "save", "cancel"])
def test_failed_or_canceled_repair_preserves_original(local_media, monkeypatch, failure):
    library, source, ffmpeg = local_media
    content = source.read_bytes()
    if failure == "save":
        monkeypatch.setattr(type(library.store), "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    else:
        error = DownloadCancelled("Canceled") if failure == "cancel" else ValueError("Fixture encoder failure")
        monkeypatch.setattr(grab_repair, "process", lambda *args: (_ for _ in ()).throw(error))
    with pytest.raises((OSError, ValueError, DownloadCancelled)):
        do_repair(local_media)
    assert source.read_bytes() == content
    assert library.load()["files"][source.name]["complete"] is False
    assert not list(library.root().glob(".repair-*"))


def test_missing_cover_and_output_collision_do_not_modify_files(local_media):
    library, source, ffmpeg = local_media
    before = source.read_bytes()
    with pytest.raises(ValueError, match="cover file is missing"):
        do_repair(local_media, cover=True)
    occupied = source.with_suffix(".mp3")
    occupied.write_bytes(b"existing completed file")
    with pytest.raises(FileExistsError):
        do_repair(local_media, mode="mp3")
    assert source.read_bytes() == before and occupied.read_bytes() == b"existing completed file"


def test_repair_rejects_completed_and_outside_paths(local_media):
    library, source, ffmpeg = local_media
    records = library.load()["files"]
    records[source.name]["complete"] = True
    with pytest.raises(ValueError, match="unfinished"):
        grab_repair.repair(library, source.name, records, {}, ffmpeg, check=lambda: None, log=lambda m: None)
    with pytest.raises(ValueError):
        grab_repair.repair(library, "../outside.mp4", {}, {}, ffmpeg, check=lambda: None, log=lambda m: None)


def test_missing_audio_does_not_mark_video_complete(local_media):
    library, source, ffmpeg = local_media
    video = source.with_name("video.f400.mp4")
    subprocess.run([str(ffmpeg), "-v", "error", "-i", str(source), "-an", "-c:v", "copy", str(video)], check=True)
    record = library.load()["files"][source.name]
    source.unlink()
    library.remember({video.name: record})
    content = video.read_bytes()
    with pytest.raises(ValueError, match="missing or ambiguous"):
        do_repair((library, video, ffmpeg))
    assert video.read_bytes() == content and not source.exists()
    assert library.load()["files"][video.name]["complete"] is False


def test_cancel_stops_the_owned_processing_child(monkeypatch):
    children = []
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        child = real_popen(*args, **kwargs)
        children.append(child)
        return child

    count = 0

    def check():
        nonlocal count
        count += 1
        if count > 1:
            raise DownloadCancelled("Canceled")

    monkeypatch.setattr(grab_repair.subprocess, "Popen", popen)
    with pytest.raises(DownloadCancelled):
        grab_repair.process([sys.executable, "-c", "import time; time.sleep(60)"], check, lambda message: None)
    assert children[0].poll() is not None
