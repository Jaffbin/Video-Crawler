import json
import os
from types import SimpleNamespace

import pytest

import grab
import webui


@pytest.fixture(autouse=True)
def setup_app(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(webui, "UPDATE", {"status": "idle", "extras": "", "lines": [], "error": ""})
    monkeypatch.delenv("VIDEO_GRABBER_PORTABLE_ROOT", raising=False)
    webui.JOB_MANAGER.reset()
    yield
    webui.JOB_MANAGER.reset()


def test_setup_identifies_windows_block_and_does_not_install(monkeypatch):
    monkeypatch.setattr(webui, "collect_doctor", lambda: {"checks": [
        {"id": "ffmpeg", "status": "error", "detail": "Blocked (WinError 4551)"}]})
    assert webui.setup_status()["blocked"] and not webui.setup_status()["can_install"]
    monkeypatch.setattr(webui.threading, "Thread", lambda **kwargs: pytest.fail("Must not install blocked components"))
    ok, message = webui.start_setup()
    assert not ok and "Windows blocked" in message


def test_ready_setup_clears_previous_install_failure(monkeypatch):
    monkeypatch.setattr(webui, "setup_status", lambda: {"ready": True, "blocked": False})
    webui.UPDATE.update(status="error", error="Old install error")
    assert webui.start_setup() == (True, "")
    assert webui.UPDATE["status"] == "done" and not webui.UPDATE["error"]


def test_setup_waits_for_active_downloads():
    webui.JOB_MANAGER.add_restored(webui.Job("https://example.com/video", {}))
    assert not webui.start_setup()[0]


def test_setup_runs_only_missing_tools_and_verifies_launch(monkeypatch):
    monkeypatch.setattr(webui, "setup_status", lambda: {"blocked": False, "issues": ["ffmpeg"]})
    seen = []
    monkeypatch.setattr(webui.subprocess, "run", lambda command, **kw: seen.append(command) or SimpleNamespace(returncode=0, stdout="Tools ready", stderr=""))
    monkeypatch.setattr(webui, "configure_managed_components", lambda: None)
    monkeypatch.setattr(grab, "media_tool_check", lambda name: {"status": "ok"})
    webui.UPDATE.update(status="running", extras="setup")
    webui._do_setup()
    assert seen[0][seen[0].index("--components") + 1] == "ffmpeg"
    assert "--component-root" in seen[0] and "--manifest" in seen[0]
    assert webui.UPDATE["status"] == "done"


def test_setup_reports_failure_instead_of_success(monkeypatch):
    monkeypatch.setattr(webui, "setup_status", lambda: {"blocked": False, "issues": ["ffmpeg"]})
    monkeypatch.setattr(webui.subprocess, "run", lambda *args, **kw: SimpleNamespace(returncode=1, stdout="", stderr="fixture failure"))
    webui._do_setup()
    assert webui.UPDATE["status"] == "error" and "Could not prepare" in webui.UPDATE["error"]


def test_python_component_setup_requires_restart(monkeypatch):
    monkeypatch.setattr(webui, "setup_status", lambda: {"blocked": False, "issues": ["ejs"]})
    monkeypatch.setattr(webui, "_do_update", lambda extras, **kw: webui.UPDATE.update(status="running", extras=extras))
    monkeypatch.setattr(grab, "media_tool_check", lambda name: {"status": "ok"})
    webui._do_setup()
    assert webui.UPDATE["extras"] == "setup" and webui.UPDATE["restart_required"]


def test_managed_tools_are_detected_on_next_start_and_escape_is_rejected(tmp_path, monkeypatch):
    root = webui.managed_component_root()
    tool = root / "runtime" / "components" / "ffmpeg-test" / "ffmpeg.exe"
    tool.parent.mkdir(parents=True)
    tool.write_bytes(b"fixture executable")
    state = root / "runtime" / "components.json"
    state.write_text(json.dumps({"components": {"ffmpeg": {"executable": tool.relative_to(root).as_posix()},
                                                 "deno": {"executable": "../outside.exe"}}}), encoding="utf-8")
    monkeypatch.delenv("GRAB_FFMPEG_LOCATION", raising=False)
    webui.configure_managed_components()
    assert os.environ["PATH"].split(os.pathsep)[0] == str(tool.parent)
    assert grab.ffmpeg_location() == str(tool)


@pytest.mark.parametrize("message,kind", [("ffmpeg: No space left on device", "disk_full"),
                                          ("ffmpeg [WinError 32] used by another process", "file_locked"),
                                          ("[WinError 5] Access is denied", "file_permission"),
                                          ("ffmpeg [WinError 4551] blocked", "app_control")])
def test_file_failure_actions_preserve_actual_cause(message, kind):
    assert webui.error_details(message)["kind"] == kind


@pytest.mark.parametrize("complete", [False, True])
def test_managed_setup_replaces_incomplete_tool_folder_but_keeps_complete_selection(tmp_path, monkeypatch, complete):
    selected = tmp_path / "selected"
    selected.mkdir()
    (selected / "ffmpeg.exe").write_bytes(b"fixture")
    if complete:
        (selected / "ffprobe.exe").write_bytes(b"fixture")
    root = webui.managed_component_root()
    tool = root / "runtime" / "components" / "ffmpeg-test" / "ffmpeg.exe"
    tool.parent.mkdir(parents=True)
    tool.write_bytes(b"fixture")
    (tool.parent / "ffprobe.exe").write_bytes(b"fixture")
    (root / "runtime" / "components.json").write_text(json.dumps({"components": {"ffmpeg": {"executable": tool.relative_to(root).as_posix()}}}), encoding="utf-8")
    monkeypatch.setenv("GRAB_FFMPEG_LOCATION", str(selected))
    webui.configure_managed_components()
    assert grab.ffmpeg_location() == str(selected if complete else tool)
