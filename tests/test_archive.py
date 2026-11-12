"""'Skip videos that were already downloaded' must also cover files the Library had before the option was on."""
import pytest
import yt_dlp

import grab
import grab_archive
import webui
from grab_models import Job

VIDEO = "https://www.youtube.com/watch?v=WCgcSFC1GsU"
SHORT = "https://www.youtube.com/shorts/bF37dDg3Y7U"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    root = (tmp_path / "dl").resolve()
    root.mkdir()
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(webui, "FILES_CACHE", {"rev": None, "ts": 0.0, "data": []})
    webui.JOB_MANAGER.reset()


def seed(archive, records, kind, existing=lambda relative: True):
    return grab_archive.seed_archive(
        archive, records, kind=kind, audio_suffixes=grab.AUDIO_SUFFIXES, is_complete_file=existing,
    )


def test_archive_ids_match_what_yt_dlp_writes():
    assert grab_archive.archive_id(VIDEO) == "youtube WCgcSFC1GsU"
    assert grab_archive.archive_id("https://youtu.be/bF37dDg3Y7U") == "youtube bF37dDg3Y7U"
    assert grab_archive.archive_id(SHORT) == "youtube bF37dDg3Y7U"
    assert grab_archive.archive_id("https://example.invalid/clip.mp4") == ""
    assert grab_archive.archive_id("not a url") == ""
    ydl = yt_dlp.YoutubeDL({"quiet": True})
    assert grab_archive.archive_id(VIDEO) == ydl._make_archive_id({"extractor_key": "Youtube", "id": "WCgcSFC1GsU"})


def test_seeded_lines_are_recognized_by_yt_dlp(tmp_path):
    archive = tmp_path / ".archive.txt"
    assert seed(archive, {"a [WCgcSFC1GsU].mp4": {"source_url": VIDEO, "complete": True}}, "video") == 1
    with yt_dlp.YoutubeDL({"quiet": True, "download_archive": str(archive)}) as ydl:
        assert ydl.in_download_archive({"extractor_key": "Youtube", "id": "WCgcSFC1GsU"})
        assert not ydl.in_download_archive({"extractor_key": "Youtube", "id": "bF37dDg3Y7U"})


def test_only_complete_existing_files_of_the_requested_kind_are_seeded(tmp_path):
    archive = tmp_path / ".archive.txt"
    records = {
        "ok.mp4": {"source_url": VIDEO, "complete": True},
        "unfinished.mp4": {"source_url": "https://youtu.be/AAAAAAAAAAA", "complete": False},
        "gone.mp4": {"source_url": "https://youtu.be/BBBBBBBBBBB", "complete": True},
        "audio.mp3": {"source_url": "https://youtu.be/CCCCCCCCCCC", "complete": True},
        "cover.jpg": {"source_url": "https://youtu.be/DDDDDDDDDDD", "complete": True, "role": "image"},
        "other.mp4": {"source_url": "https://example.invalid/clip.mp4", "complete": True},
        "nourl.mp4": {"source_url": "", "complete": True},
        "broken.mp4": "not a record",
    }
    assert seed(archive, records, "video", existing=lambda relative: relative != "gone.mp4") == 1
    assert archive.read_text(encoding="utf-8").splitlines() == ["youtube WCgcSFC1GsU"]
    audio = tmp_path / ".archive-audio.txt"
    assert seed(audio, records, "audio") == 1
    assert audio.read_text(encoding="utf-8").splitlines() == ["youtube CCCCCCCCCCC"]


def test_seeding_keeps_existing_entries_and_never_repeats_them(tmp_path):
    archive = tmp_path / ".archive.txt"
    archive.write_text("youtube OLDOLDOLD00", encoding="utf-8")  # yt-dlp may leave no trailing newline
    records = {"a.mp4": {"source_url": VIDEO, "complete": True}}
    assert seed(archive, records, "video") == 1
    assert seed(archive, records, "video") == 0
    assert archive.read_text(encoding="utf-8").splitlines() == ["youtube OLDOLDOLD00", "youtube WCgcSFC1GsU"]


def test_video_and_audio_use_separate_skip_lists():
    video = webui.make_args({"mode": "mp4", "archive": True}).archive
    assert video.endswith(".archive.txt")
    for mode in ("mp3", "original"):
        assert webui.make_args({"mode": mode, "archive": True}).archive.endswith(".archive-audio.txt")
    assert webui.make_args({"mode": "mp4"}).archive is None


def test_a_task_with_the_option_on_seeds_the_archive_from_the_library(monkeypatch):
    (webui.ROOT / "old [WCgcSFC1GsU].mp4").write_bytes(b"x" * 2000)
    webui.LIBRARY.remember({"old [WCgcSFC1GsU].mp4": {"source_url": VIDEO, "title": "Old", "complete": True}})
    monkeypatch.setattr(grab, "media_tool_check", lambda program, location=None: {"status": "ok", "detail": ""})
    monkeypatch.setattr(grab, "discover_and_download", lambda *args, **kwargs: True)
    job = Job(SHORT, {"mode": "mp4", "archive": True})
    webui.run_job(job)
    assert job.status == "done"
    assert (webui.ROOT / ".archive.txt").read_text(encoding="utf-8").splitlines() == ["youtube WCgcSFC1GsU"]
    # Without the option nothing is written, and a deleted file is not remembered as downloaded.
    (webui.ROOT / ".archive.txt").unlink()
    webui.run_job(Job(SHORT, {"mode": "mp4"}))
    assert not (webui.ROOT / ".archive.txt").exists()
    (webui.ROOT / "old [WCgcSFC1GsU].mp4").unlink()
    webui.run_job(Job(SHORT, {"mode": "mp4", "archive": True}))
    assert not (webui.ROOT / ".archive.txt").exists()
