"""Download hooks: settings validation, what a program receives, and who may reach the settings."""
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

import grab_hooks
from grab_hooks import HookRunner, build_env, build_payload, load_config, parse_config
from grab_models import Job
import webui


def make_job(root, status="done", files=(), **options):
    job = Job("https://example.com/watch?v=1", {"mode": "mp4", "proxy": "http://user:secret@proxy:8080", **options})
    job.status = status
    job.title = "A title"
    job.files = [str(root / name) for name in files]
    job.finished = 1234.5
    return job


def write_config(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def wait_for(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("timed out")


# ── Settings ──
def test_valid_settings_fill_in_the_default_timeout_and_ignore_comment_keys():
    config = parse_config({"_help": "notes", "enabled": True,
                           "hooks": {"download_failed": {"command": ["notify.exe", "--failed"]}}})
    assert config == {"enabled": True, "hooks": {"download_failed": {"command": ["notify.exe", "--failed"],
                                                                     "timeout_seconds": 60}},
                      "notifications": [], "language": "en"}


@pytest.mark.parametrize("raw, message", [
    ([], "JSON object"),
    ({"enabled": "yes"}, "enabled must be true or false"),
    ({"surprise": 1}, "Unknown settings: surprise"),
    ({"hooks": []}, "hooks must be an object"),
    ({"hooks": {"subscription_found": {"command": ["x"]}}}, "Unknown events: subscription_found"),
    ({"hooks": {"download_completed": "run.bat"}}, "must be an object"),
    ({"hooks": {"download_completed": {"command": "run.bat"}}}, "must be a list"),
    ({"hooks": {"download_completed": {"command": []}}}, "must be a list"),
    ({"hooks": {"download_completed": {"command": ["run.bat", ""]}}}, "must be a list"),
    ({"hooks": {"download_completed": {"command": ["run\0.bat"]}}}, "must be a list"),
    ({"hooks": {"download_completed": {"command": ["x"] * 33}}}, "must be a list"),
    ({"hooks": {"download_completed": {"command": ["x"], "timeout_seconds": 0}}}, "timeout_seconds"),
    ({"hooks": {"download_completed": {"command": ["x"], "timeout_seconds": 601}}}, "timeout_seconds"),
    ({"hooks": {"download_completed": {"command": ["x"], "timeout_seconds": True}}}, "timeout_seconds"),
    ({"hooks": {"download_completed": {"command": ["x"], "shell": True}}}, "unknown keys: shell"),
])
def test_invalid_settings_are_rejected_with_a_specific_reason(raw, message):
    with pytest.raises(grab_hooks.HookConfigError, match=message):
        parse_config(raw)


def test_missing_broken_and_oversized_files_run_nothing(tmp_path):
    path = tmp_path / "hooks.json"
    assert load_config(path) == {"enabled": False, "hooks": {}, "notifications": [], "language": "en",
                                 "exists": False, "error": None}
    path.write_text("{ not json", encoding="utf-8")
    broken = load_config(path)
    assert broken["exists"] and broken["error"] and broken["enabled"] is False and broken["hooks"] == {}
    path.write_text(" " * (grab_hooks.MAX_CONFIG_BYTES + 1), encoding="utf-8")
    assert "64 KB" in load_config(path)["error"]


def test_files_saved_with_a_byte_order_mark_still_load(tmp_path):
    # Windows Notepad may add a BOM when saving as UTF-8.
    path = tmp_path / "hooks.json"
    path.write_text(json.dumps({"enabled": True}), encoding="utf-8-sig")
    assert load_config(path)["error"] is None and load_config(path)["enabled"] is True


def test_template_is_disabled_valid_and_never_overwrites(tmp_path):
    path = tmp_path / "cfg" / "hooks.json"
    assert grab_hooks.ensure_config_file(path) is True
    config = load_config(path)
    assert config["error"] is None and config["enabled"] is False and "download_completed" in config["hooks"]
    path.write_text('{"enabled": true}', encoding="utf-8")
    assert grab_hooks.ensure_config_file(path) is False
    assert path.read_text(encoding="utf-8") == '{"enabled": true}'


# ── What a program receives ──
def test_payload_describes_the_job_without_download_options(tmp_path):
    job = make_job(tmp_path, files=["clip.mp4", "clip.jpg"])
    job.source = "sub-1"
    payload = build_payload("download_completed", job, tmp_path)
    assert payload["job"] == {"id": job.id, "url": job.url, "title": "A title", "status": "done", "mode": "mp4",
                              "subscription_id": "sub-1", "finished": 1234.5, "repair": False}
    assert payload["files"] == [{"path": str(tmp_path / "clip.mp4"), "relative": "clip.mp4"},
                                {"path": str(tmp_path / "clip.jpg"), "relative": "clip.jpg"}]
    assert "secret" not in json.dumps(payload)


def test_failed_payload_carries_the_error(tmp_path):
    job = make_job(tmp_path, status="error")
    job.error, job.error_kind = "HTTP Error 403", "forbidden"
    payload = build_payload("download_failed", job, tmp_path)
    assert payload["job"]["error"] == "HTTP Error 403" and payload["job"]["error_kind"] == "forbidden"
    env = build_env(payload, base={})
    assert env["VG_EVENT"] == "download_failed" and env["VG_ERROR"] == "HTTP Error 403"
    assert env["VG_FILE"] == "" and env["VG_FILE_COUNT"] == "0"


def test_environment_points_at_media_rather_than_its_cover_and_is_sanitized(tmp_path):
    job = make_job(tmp_path, files=["clip.mp4", "clip.jpg", "clip.en.srt"])
    job.title = "bad\0title" + "x" * 5000
    env = build_env(build_payload("download_completed", job, tmp_path), base={"KEEP": "1"})
    assert env["KEEP"] == "1"
    assert env["VG_FILE"] == str(tmp_path / "clip.mp4") and env["VG_FILE_COUNT"] == "3"
    assert "\0" not in env["VG_TITLE"] and len(env["VG_TITLE"]) == grab_hooks.ENV_VALUE_MAX
    assert "VG_ERROR" not in env


def test_cover_downloads_point_at_the_image(tmp_path):
    job = make_job(tmp_path, files=["cover.jpg"], mode="cover")
    assert build_env(build_payload("download_completed", job, tmp_path), base={})["VG_FILE"].endswith("cover.jpg")


# ── Running ──
def test_enabled_hook_runs_once_with_json_on_stdin_and_environment(tmp_path):
    out = tmp_path / "received.json"
    script = ("import json, os, sys; data = json.load(sys.stdin); "
              "open(sys.argv[1], 'w', encoding='utf-8').write(json.dumps({'data': data, 'event': os.environ['VG_EVENT'], "
              "'file': os.environ['VG_FILE']}))")
    config = tmp_path / "hooks.json"
    write_config(config, {"enabled": True, "hooks": {"download_completed": {
        "command": [sys.executable, "-c", script, str(out)], "timeout_seconds": 30}}})
    runner = HookRunner(lambda: config)
    runner.start()
    try:
        assert runner.dispatch(make_job(tmp_path, files=["clip.mp4"]), tmp_path) is True
        wait_for(lambda: runner.status()["recent"])
    finally:
        runner.stop()
    result = runner.status()["recent"][0]
    assert result["outcome"] == "ok" and result["exit_code"] == 0 and result["event"] == "download_completed"
    received = json.loads(out.read_text(encoding="utf-8"))
    assert received["event"] == "download_completed" and received["file"] == str(tmp_path / "clip.mp4")
    assert received["data"]["job"]["title"] == "A title"


def test_nothing_runs_when_disabled_unconfigured_canceled_or_broken(tmp_path):
    calls = []
    config = tmp_path / "hooks.json"
    runner = HookRunner(lambda: config, run=lambda *a, **k: calls.append(a))
    assert runner.dispatch(make_job(tmp_path), tmp_path) is False  # no file
    write_config(config, {"enabled": False, "hooks": {"download_completed": {"command": ["x"]}}})
    assert runner.dispatch(make_job(tmp_path), tmp_path) is False
    write_config(config, {"enabled": True, "hooks": {"download_completed": {"command": ["x"]}}})
    assert runner.dispatch(make_job(tmp_path, status="error"), tmp_path) is False  # no failed hook configured
    assert runner.dispatch(make_job(tmp_path, status="canceled"), tmp_path) is False
    config.write_text("{", encoding="utf-8")
    assert runner.dispatch(make_job(tmp_path), tmp_path) is False
    assert runner.status()["pending"] == 0 and not calls


def test_queued_work_keeps_the_command_from_when_the_download_finished(tmp_path):
    seen = []
    config = tmp_path / "hooks.json"
    write_config(config, {"enabled": True, "hooks": {"download_completed": {"command": ["first"]}}})
    runner = HookRunner(lambda: config, run=lambda command, **k: seen.append(command) or
                        subprocess.CompletedProcess(command, 0))
    runner.dispatch(make_job(tmp_path), tmp_path)
    write_config(config, {"enabled": True, "hooks": {"download_completed": {"command": ["second"]}}})
    runner.start()
    try:
        wait_for(lambda: seen)
    finally:
        runner.stop()
    assert seen == [["first"]]


def test_failure_records_the_exit_code_and_the_end_of_stderr(tmp_path):
    runner = HookRunner(lambda: tmp_path / "unused.json")
    script = "import sys; sys.stderr.write('x' * 5000 + 'LAST LINE'); sys.exit(3)"
    payload = build_payload("download_completed", make_job(tmp_path), tmp_path)
    runner.run_now("download_completed", "job1", {"command": [sys.executable, "-c", script], "timeout_seconds": 30},
                   payload)
    result = runner.status()["recent"][0]
    assert result["outcome"] == "failed" and result["exit_code"] == 3
    assert result["detail"].endswith("LAST LINE") and len(result["detail"]) <= grab_hooks.STDERR_TAIL_BYTES


def test_missing_program_and_timeout_are_reported(tmp_path):
    def too_slow(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    payload = build_payload("download_completed", make_job(tmp_path), tmp_path)
    runner = HookRunner(lambda: tmp_path / "unused.json")
    runner.run_now("download_completed", "job1", {"command": [str(tmp_path / "missing.exe")], "timeout_seconds": 5},
                   payload)
    runner._run = too_slow
    runner.run_now("download_completed", "job2", {"command": ["slow"], "timeout_seconds": 7}, payload)
    newest, oldest = runner.status()["recent"]
    assert oldest["outcome"] == "not_started" and "missing.exe" in oldest["detail"]
    assert newest["outcome"] == "timeout" and "7 seconds" in newest["detail"]


def test_a_real_timeout_stops_the_program(tmp_path):
    runner = HookRunner(lambda: tmp_path / "unused.json")
    payload = build_payload("download_completed", make_job(tmp_path), tmp_path)
    started = time.monotonic()
    runner.run_now("download_completed", "job1",
                   {"command": [sys.executable, "-c", "import time; time.sleep(30)"], "timeout_seconds": 1}, payload)
    assert time.monotonic() - started < 15
    assert runner.status()["recent"][0]["outcome"] == "timeout"


def test_a_full_queue_skips_and_reports_instead_of_blocking(tmp_path):
    config = tmp_path / "hooks.json"
    write_config(config, {"enabled": True, "hooks": {"download_completed": {"command": ["x"]}}})
    runner = HookRunner(lambda: config, max_pending=1)
    assert runner.dispatch(make_job(tmp_path), tmp_path) is True
    assert runner.dispatch(make_job(tmp_path), tmp_path) is False
    assert runner.status()["pending"] == 1 and runner.status()["recent"][0]["outcome"] == "skipped"


def test_an_unexpected_error_is_recorded_and_the_next_hook_still_runs(tmp_path):
    calls = []

    def flaky(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return subprocess.CompletedProcess(command, 0)

    config = tmp_path / "hooks.json"
    write_config(config, {"enabled": True, "hooks": {"download_completed": {"command": ["x"]}}})
    runner = HookRunner(lambda: config, run=flaky)
    runner.dispatch(make_job(tmp_path), tmp_path)
    runner.dispatch(make_job(tmp_path), tmp_path)
    runner.start()
    try:
        wait_for(lambda: len(runner.status()["recent"]) == 2)
    finally:
        runner.stop()
    newest, oldest = runner.status()["recent"]
    assert oldest["outcome"] == "failed" and "boom" in oldest["detail"] and newest["outcome"] == "ok"


def test_a_stopped_runner_accepts_no_more_work(tmp_path):
    config = tmp_path / "hooks.json"
    write_config(config, {"enabled": True, "hooks": {"download_completed": {"command": ["x"]}}})
    runner = HookRunner(lambda: config)
    runner.start()
    runner.stop()
    assert runner.dispatch(make_job(tmp_path), tmp_path) is False


def test_worker_survives_a_hook_error(monkeypatch, tmp_path):
    class Broken:
        def dispatch(self, job, root):
            raise RuntimeError("boom")

    monkeypatch.setattr(webui, "HOOKS", Broken())
    webui.dispatch_download_hooks(make_job(tmp_path))  # must not raise


# ── HTTP access ──
@pytest.fixture
def server(tmp_path, monkeypatch):
    root = (tmp_path / "dl").resolve()
    root.mkdir()
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path / "cfg")
    opened = []
    monkeypatch.setattr(webui, "_open_with_os", opened.append)
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", opened
    srv.shutdown()
    srv.server_close()


def call(base, path, headers, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data,
                                     headers={"Content-Type": "application/json", "X-Token": webui.TOKEN, **headers})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


SESSION = {"Cookie": f"{webui.SESSION_COOKIE}={webui.SESSION_SECRET}"}


def test_token_alone_cannot_read_or_open_hook_settings(server, tmp_path):
    base, opened = server
    extension = {"X-Grab-Client": "extension"}
    assert call(base, "/api/hooks", extension)[0] == 403
    assert call(base, "/api/hooks/open-config", extension, {})[0] == 403
    assert not (tmp_path / "cfg" / "hooks.json").exists() and not opened


def test_app_window_sees_status_and_opening_creates_a_disabled_template(server, tmp_path):
    base, opened = server
    status, body = call(base, "/api/hooks", SESSION)
    assert status == 200 and body["exists"] is False and body["enabled"] is False and body["recent"] == []
    status, body = call(base, "/api/hooks/open-config", SESSION, {})
    path = tmp_path / "cfg" / "hooks.json"
    assert status == 200 and body["exists"] is True and body["enabled"] is False and body["error"] is None
    assert body["path"] == str(path) and opened == [path]
