"""Distinguish transferred streams from finished media without deleting either."""

import pytest

import grab
import webui
from grab_models import Job


@pytest.fixture
def output_app(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "ROOT", tmp_path)
    monkeypatch.setattr(webui, "FILES_CACHE", {"rev": None, "ts": 0, "data": []})
    webui.JOB_MANAGER.reset()
    yield tmp_path
    webui.JOB_MANAGER.reset()


@pytest.mark.parametrize("mode", ["mp4", "mp3", "original"])
def test_blocked_ffmpeg_fails_before_source_requests_or_files(output_app, monkeypatch, mode):
    monkeypatch.setattr(grab, "media_tool_check", lambda *args:
                        {"status": "error", "detail": "Cannot start ffmpeg: WinError 4551."})
    monkeypatch.setattr(grab, "discover_and_download", lambda *args:
                        pytest.fail("Source requests must not start when ffmpeg is blocked"))
    job = Job("https://example.com/video", {"mode": mode, "cover": True})
    webui.run_job(job)
    assert job.status == "error" and job.error_kind == "app_control" and job.percent == 0
    assert "WinError 4551" in job.log[-1]
    assert not list(output_app.iterdir())


@pytest.mark.parametrize("succeed", [False, True])
def test_postprocessing_completion_is_recorded_and_survives_restart(output_app, monkeypatch, succeed):
    monkeypatch.setattr(grab, "media_tool_check", lambda *args: {"status": "ok"})
    final = output_app / "video.mp4"
    job = Job("https://fixture.invalid/video", {"mode": "mp4", "cover": True})

    class Downloader:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, urls):
            final.write_bytes(b"fixture merged video")
            info = {"title": "Fixture", "filepath": str(final)}
            for hook in self.options["progress_hooks"]:
                hook({"status": "finished", "filename": str(final), "info_dict": info})
            for hook in self.options["postprocessor_hooks"]:
                hook({"status": "finished", "postprocessor": "FFmpegMetadata", "info_dict": info})
            if succeed:
                for hook in self.options["post_hooks"]:
                    hook(str(final))
                return 0
            self.options["logger"].error("Postprocessing: ffmpeg cover embedding failed")
            return 1

    monkeypatch.setattr(webui.yt_dlp, "YoutubeDL", Downloader)
    webui.run_job(job)
    assert job.status == ("done" if succeed else "error")
    assert job.view(output_app)["files"][0]["complete"] is succeed
    assert webui.LIBRARY.load()["files"]["video.mp4"]["complete"] is succeed
    restored = Job.from_dict(job.to_dict(output_app), output_app)
    assert restored.view(output_app)["files"][0]["complete"] is succeed
    assert webui.list_files(force=True)[0]["complete"] is succeed
    assert final.read_bytes() == b"fixture merged video"


def test_legacy_failed_fragments_are_labeled_but_imported_files_are_not(output_app):
    paths = [output_app / name for name in ("video.f400.mp4", "video.f140-1.m4a", "import.f400.mp4", "audio.mp3")]
    for path in paths:
        path.write_bytes(b"fixture media")
    job = Job("https://example.com/video", {"mode": "mp4"})
    job.status, job.files = "error", [str(path) for path in paths[:2]]
    webui.JOB_MANAGER.add_restored(job)
    webui.LIBRARY.remember({path.name: {"source_url": job.url} for path in paths[:2]})
    items = {item["name"]: item for item in webui.list_files(force=True)}
    assert items["video.f400.mp4"]["complete"] is False
    assert items["video.f140-1.m4a"]["complete"] is False
    assert items["import.f400.mp4"]["complete"] is True
    assert items["audio.mp3"]["complete"] is True
    assert all(path.is_file() for path in paths)


def test_completion_metadata_follows_rename_and_recovery(output_app):
    path = output_app / "video.mp4"
    path.write_bytes(b"unfinished postprocessing")
    webui.LIBRARY.remember({path.name: {"complete": False}})
    renamed = webui.LIBRARY.rename(path.name, "renamed.mp4")
    recovery = webui.LIBRARY.trash(renamed)
    webui.LIBRARY.restore(recovery)
    assert webui.list_files(force=True)[0]["complete"] is False
    assert (output_app / renamed).read_bytes() == b"unfinished postprocessing"


def test_successful_playlist_output_stays_complete_when_another_entry_fails(output_app, monkeypatch):
    monkeypatch.setattr(grab, "media_tool_check", lambda *args: {"status": "ok"})
    job = Job("https://fixture.invalid/list", {"mode": "mp4"})

    class Downloader:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, urls):
            for name, complete in (("ready.mp4", True), ("unfinished.mp4", False)):
                path = output_app / name
                path.write_bytes(b"fixture media")
                for hook in self.options["progress_hooks"]:
                    hook({"status": "finished", "filename": str(path), "info_dict": {"title": name}})
                if complete:
                    for hook in self.options["post_hooks"]:
                        hook(str(path))
            self.options["logger"].error("Postprocessing: ffmpeg failed for second entry")
            return 1

    monkeypatch.setattr(webui.yt_dlp, "YoutubeDL", Downloader)
    webui.run_job(job)
    assert job.status == "error"
    assert {item["name"]: item["complete"] for item in job.view(output_app)["files"]} == {
        "ready.mp4": True, "unfinished.mp4": False,
    }
