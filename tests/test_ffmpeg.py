"""Executable detection must verify launchability and use the same path as yt-dlp."""

import subprocess
from pathlib import Path

import pytest

import grab
import webui
from grab_config import parse_web_config


@pytest.fixture
def executable(tmp_path, monkeypatch):
    path = tmp_path / "ffmpeg.exe"
    path.write_bytes(b"fixture executable")
    monkeypatch.delenv("GRAB_FFMPEG_LOCATION", raising=False)
    monkeypatch.setattr(grab.shutil, "which", lambda name: str(path) if name == "ffmpeg" else None)
    return path


def test_download_options_pass_resolved_ffmpeg_path(executable, tmp_path):
    args = grab.parse_args(["-o", str(tmp_path), "--cover"])
    options = grab.build_opts(args)
    assert options["ffmpeg_location"] == str(executable.resolve())
    assert "EmbedThumbnail" in {item["key"] for item in options["postprocessors"]}


def test_explicit_path_overrides_environment_and_path(executable, tmp_path, monkeypatch):
    monkeypatch.setenv("GRAB_FFMPEG_LOCATION", str(tmp_path / "environment"))
    assert grab.ffmpeg_location() == str(tmp_path / "environment")
    args = grab.parse_args(["-o", str(tmp_path), "--ffmpeg-location", str(executable)])
    assert grab.build_opts(args)["ffmpeg_location"] == str(executable)
    assert parse_web_config(["--ffmpeg-location", str(executable)]).ffmpeg_location == str(executable)


def test_diagnostics_reports_application_control_block_instead_of_ok(executable, monkeypatch):
    error = OSError("Fixture policy restriction")
    error.winerror = 4551

    def blocked(*args, **kwargs):
        raise error

    monkeypatch.setattr(grab.subprocess, "run", blocked)
    check = grab.media_tool_check("ffmpeg")
    assert check["status"] == "error"
    assert str(executable) in check["detail"] and "WinError 4551" in check["detail"]
    assert "application control" in check["fix"]


@pytest.mark.parametrize("returncode,output", [(1, "Fixture failure"), (0, "unrelated executable")])
def test_diagnostics_rejects_failed_or_invalid_version_output(executable, monkeypatch, returncode, output):
    monkeypatch.setattr(grab.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args[0], returncode, stdout=output, stderr=""))
    assert grab.media_tool_check("ffmpeg")["status"] == "error"


def test_diagnostics_checks_ffmpeg_and_companion_ffprobe(executable, monkeypatch):
    executable.with_name("ffprobe.exe").write_bytes(b"fixture probe")
    invoked = []

    def run(command, **kwargs):
        invoked.append(command)
        name = Path(command[0]).stem
        return subprocess.CompletedProcess(command, 0, stdout=f"{name} version 9.0.1", stderr="")

    monkeypatch.setattr(grab.subprocess, "run", run)
    for program in ("ffmpeg", "ffprobe"):
        assert grab.media_tool_check(program)["status"] == "ok"
    assert invoked == [[str(executable), "-version"], [str(executable.with_name("ffprobe.exe")), "-version"]]


def test_state_polling_caches_checks_but_rechecks_changed_paths(executable, monkeypatch):
    grab._ffmpeg_available.cache_clear()
    calls = []
    monkeypatch.setattr(grab.time, "monotonic", lambda: 1)
    monkeypatch.setattr(grab, "media_tool_check", lambda program, location:
                        calls.append(location) or {"status": "ok"})
    try:
        assert grab.ffmpeg_available() and grab.ffmpeg_available()
        monkeypatch.setenv("GRAB_FFMPEG_LOCATION", str(executable.parent / "other"))
        assert grab.ffmpeg_available()
        assert len(calls) == 2
    finally:
        grab._ffmpeg_available.cache_clear()


def test_partial_stream_files_do_not_hide_ffmpeg_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "ROOT", tmp_path)
    monkeypatch.setattr(grab, "media_tool_check", lambda *args: {"status": "ok"})
    job = webui.Job("https://example.com/video", {"cover": True})
    partial = tmp_path / "video.f400.mp4"
    partial.write_bytes(b"fixture unmerged video")

    def download(*args):
        job.seen_paths.append(str(partial))
        job.error = "Postprocessing: ffmpeg not found."
        return False

    monkeypatch.setattr(grab, "discover_and_download", download)
    webui.run_job(job)
    assert job.status == "error" and job.error_kind == "ffmpeg"
    assert "application control" in job.error_hint and partial.is_file()
