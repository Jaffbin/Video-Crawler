import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import types
from pathlib import Path

import pytest

import grab
import webui
from conftest import HAVE_FFMPEG


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own download folder, settings folder and empty job list."""
    root = (tmp_path / "dl").resolve()
    root.mkdir()
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(webui, "PORT", 0)
    monkeypatch.setattr(webui, "PENDING_ROOT", None)
    monkeypatch.setattr(webui, "NATIVE_WINDOW", None)
    monkeypatch.setattr(webui, "FILES_CACHE", {"rev": None, "ts": 0.0, "data": []})
    monkeypatch.setattr(webui, "UPDATE", {"status": "idle", "lines": [], "before": "", "after": "", "error": "", "extras": ""})
    webui.JOB_MANAGER.reset()
    webui.SUBSCRIPTION_MANAGER.reset()
    webui.DOCTOR_CACHE.update(ts=0.0, data=None)
    yield


@pytest.fixture
def server():
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None, *, token=True, host=None, ctype="application/json"):
    headers = {}
    if token:
        headers["X-Token"] = webui.TOKEN
    if host:
        headers["Host"] = host
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = ctype
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=headers), timeout=20) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in b"{[" else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw[:1] in b"{[" else raw)


def test_native_window_uses_webview2_and_persistent_app_storage(monkeypatch, tmp_path):
    seen = {}
    fake = types.SimpleNamespace(settings={})

    def create_window(*args, **kwargs):
        seen["window"] = (args, kwargs)
        class Closing:
            def __iadd__(self, handler):
                seen["closing"] = handler
                return self
        return types.SimpleNamespace(expose=lambda *functions: seen.update(exposed=functions),
                                     events=types.SimpleNamespace(closing=Closing()))

    def start(*args, **kwargs):
        seen["start"] = kwargs
        seen["startup"] = args

    fake.create_window = create_window
    fake.start = start
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(webui.sys, "platform", "win32")

    assert webui.open_native_window("http://127.0.0.1:8765/")
    assert seen["window"][0][1] == "http://127.0.0.1:8765/"
    assert seen["start"]["gui"] == "edgechromium"
    assert seen["start"]["private_mode"] is False
    assert seen["start"]["storage_path"] == str(tmp_path / "webview")
    assert fake.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is True
    assert fake.settings["ALLOW_DOWNLOADS"] is True
    assert len(seen["startup"]) == 1
    assert {fn.__name__ for fn in seen["exposed"]} == {"sync_locale", "close_settings", "set_close_behavior", "close_action"}
    assert seen["closing"]() is True  # The completed GUI loop has already stopped the desktop controller.


def test_native_window_failure_keeps_browser_fallback(monkeypatch, tmp_path):
    fake = types.SimpleNamespace(
        settings={},
        create_window=lambda *args, **kwargs: None,
        start=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("WebView2 unavailable")),
    )
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path)
    assert webui.open_native_window("http://127.0.0.1:8765/") is False


def test_native_notification_preferences_require_auth_and_a_running_desktop(server, monkeypatch):
    from grab_desktop import DesktopController
    from unittest.mock import Mock
    desktop = DesktopController(Mock(), Mock(), server)
    monkeypatch.setattr(webui, "WINDOW_MODE", True)
    monkeypatch.setattr(webui, "NATIVE_DESKTOP", desktop)
    assert call(server, "/api/desktop/notifications", {"enabled": False}, token=False)[0] == 401
    assert call(server, "/api/desktop/notifications", {"enabled": "false"})[0] == 400
    assert call(server, "/api/desktop/notifications", {"enabled": False}) == (200, {"ok": True})
    state = call(server, "/api/state")[1]
    assert state["native_notifications"] == {"enabled": False, "available": False}
    desktop.exiting.set()
    assert call(server, "/api/desktop/notifications", {"enabled": True})[0] == 409


def test_notification_file_actions_revalidate_paths_and_completion(monkeypatch):
    from unittest.mock import Mock
    opener = Mock()
    monkeypatch.setattr(webui, "_open_with_os", opener)
    file = webui.ROOT / "video.mp4"
    file.write_bytes(b"video")
    webui.open_completed_download("play", "video.mp4")
    opener.assert_called_with(file)
    webui.open_completed_download("folder", "video.mp4")
    opener.assert_called_with(webui.ROOT)
    webui.LIBRARY.remember({"video.mp4": {"complete": False}})
    with pytest.raises(ValueError):
        webui.open_completed_download("play", "video.mp4")
    with pytest.raises(ValueError):
        webui.open_completed_download("play", "../outside.mp4")
    with pytest.raises(ValueError):
        webui.open_completed_download("shell", "video.mp4")
    file.unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        webui.open_completed_download("play", "video.mp4")
    assert opener.call_count == 2


def test_extension_can_only_focus_known_desktop_views_with_authentication(server, monkeypatch):
    from unittest.mock import Mock
    desktop = types.SimpleNamespace(exiting=threading.Event(), show_main=Mock())
    monkeypatch.setattr(webui, "WINDOW_MODE", True)
    monkeypatch.setattr(webui, "NATIVE_DESKTOP", desktop)
    assert call(server, "/api/desktop/show", {"view": "queue"}, token=False)[0] == 401
    assert call(server, "/api/desktop/show", {"view": "https://example.com"})[0] == 400
    assert call(server, "/api/desktop/show", {"view": "queue"}) == (200, {"opened": True})
    desktop.show_main.assert_called_once_with("queue")
    desktop.exiting.set()
    assert call(server, "/api/desktop/show", {"view": "queue"}) == (200, {"opened": False})


def test_extension_queue_falls_back_in_browser_mode_and_reports_native_failures(server, monkeypatch):
    from unittest.mock import Mock
    desktop = types.SimpleNamespace(exiting=threading.Event(), show_main=Mock(side_effect=RuntimeError("window closed")))
    monkeypatch.setattr(webui, "NATIVE_DESKTOP", desktop)
    monkeypatch.setattr(webui, "WINDOW_MODE", False)
    assert call(server, "/api/desktop/show", {"view": "queue"}) == (200, {"opened": False})
    desktop.show_main.assert_not_called()
    monkeypatch.setattr(webui, "WINDOW_MODE", True)
    assert call(server, "/api/desktop/show", {"view": "queue"})[0] == 503


# ───────────────────────── URL extraction (the regression that was found in review) ─────────────────────────
def _extract_line():
    m = re.search(r"const extractUrls = .*\n", webui.INDEX_HTML)
    assert m, "extractUrls not found in the page"
    return m.group(0)


CASES = [
    ("see https://example.com/v/1 and https://a.org/x.m3u8", ["https://example.com/v/1", "https://a.org/x.m3u8"]),
    ("看这个https://example.com/watch?v=1，谢谢", ["https://example.com/watch?v=1"]),
    ("(read https://x.com/a/b.html)", ["https://x.com/a/b.html"]),
    ("https://x.com/a.", ["https://x.com/a"]),
    ("no links here", []),
    ("dup https://a.io/1 https://a.io/1", ["https://a.io/1"]),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_extract_urls_python_equivalent(text, expected):
    """Same pattern in Python's re. Cheap, and it runs even where Node.js is not installed."""
    pattern = re.search(r"match\(/(.*?)/gi\)", _extract_line()).group(1).replace(r"\/", "/")
    found = [re.sub(r"[.,;、]+$", "", u) for u in re.findall(pattern, text, re.I)]
    assert list(dict.fromkeys(found)) == expected


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")
@pytest.mark.parametrize("text,expected", CASES)
def test_extract_urls_in_node(text, expected):
    """The real JavaScript, executed."""
    script = _extract_line() + f"console.log(JSON.stringify(extractUrls({json.dumps(text)})));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == expected


def test_page_javascript_has_valid_syntax():
    if shutil.which("node") is None:
        pytest.skip("Node.js is not installed")
    js = re.search(r"<script>(.*?)</script>", webui.INDEX_HTML, re.S).group(1)
    # Windows' locale encoding may be unable to encode the non-ASCII strings in
    # the fallback UI.  When the subprocess writer thread fails, Node keeps
    # waiting for EOF forever, so make both the encoding and timeout explicit.
    r = subprocess.run(
        ["node", "--check", "-"],
        input=js,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert r.returncode == 0, r.stderr


# ───────────────────────── error messages ─────────────────────────
@pytest.mark.parametrize("raw,needle", [
    ("ERROR: Unsupported URL: https://x", "Cannot recognize this page"),
    ("WARNING: [youtube] No supported JavaScript runtime could be found", "Deno"),
    ("[youtube] n challenge solving failed: Some formats may be missing", "Deno"),
    ("ERROR: Could not copy Chrome cookie database. See https://github.com/yt-dlp/yt-dlp/issues/7271", "Close the browser"),
    ("ERROR: The provided YouTube account cookies are no longer valid. They have likely been rotated", "rotated"),
    ("ERROR: Sign in to confirm you're not a bot. Use --cookies-from-browser or --cookies", "requires login"),
    ("ERROR: HTTP Error 403: Forbidden", "denied access"),
    ("ERROR: HTTP Error 404: Not Found", "expired"),
    ("ERROR: [Errno 11001] getaddrinfo failed", "Cannot find that site's address"),
    ("ERROR: <urlopen error [Errno -2] Name or service not known>", "Cannot find that site's address"),
    ("ERROR: Unable to download webpage: HTTPConnection(host='x', port=9): Failed to establish a new connection: [Errno 111] Connection refused", "Cannot reach the site"),
    ("ERROR: The read operation timed out", "Cannot reach the site"),
    ("ERROR: [generic] x: Unable to download webpage: ('Unable to connect to proxy', NewConnectionError('refused')) "
     "(caused by ProxyError('x')); please report this issue on  https://github.com/yt-dlp/yt-dlp/issues?q= , "
     "filling out the appropriate issue template. Confirm you are on the latest version using  yt-dlp -U", "Cannot reach the site"),
    ("ERROR: Sign in to confirm you\u2019re not a bot", "requires login"),
    ("ERROR: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed", "SSL certificate"),
])
def test_friendly_error(raw, needle):
    assert needle in webui.friendly_error(raw)


def test_error_details_are_structured_and_actionable():
    details = webui.error_details("ERROR: The read operation timed out")
    assert details["kind"] == "network"
    assert details["message"] and "Diagnostics" in details["hint"]


def test_missing_impersonation_has_a_distinct_fix(monkeypatch):
    monkeypatch.setattr(webui.importlib.util, "find_spec", lambda name: None)
    details = webui.error_details("ERROR: HTTP Error 403: Forbidden")
    assert details["kind"] == "impersonation_missing"
    assert "install" in details["hint"]


def test_a_random_mention_of_cookies_is_not_reported_as_a_login_problem():
    assert "requires login" not in webui.friendly_error("Unable to download webpage: cookies jar is fine but the DNS failed")


# ───────────────────────── option validation ─────────────────────────
def test_make_args_rejects_bad_values():
    a = webui.make_args({"mode": "exe", "quality": "9999999", "abr": "12", "sleep": "-5", "threads": "999",
                         "limit_rate": "fast", "items": "1;rm -rf", "proxy": "javascript:alert(1)",
                         "cookies_from_browser": "../../etc", "js_browser": "/bin/sh"})
    assert (a.mode, a.quality, a.abr) == ("mp4", "best", 192)
    assert a.sleep == 0 and a.threads == 16
    assert a.limit_rate is None and a.items is None and a.proxy is None
    assert a.cookies_from_browser is None and a.js_browser == "auto"


def test_uploaded_cookies_win_over_browser_and_need_the_file_to_exist():
    o = {"use_cookies_file": True, "cookies_from_browser": "chrome"}
    assert webui.make_args(o).cookies is None and webui.make_args(o).cookies_from_browser == "chrome"
    webui.save_cookies(_cookies_text())
    a = webui.make_args(o)
    assert a.cookies == str(webui.cookies_path()) and a.cookies_from_browser is None


# ───────────────────────── history ─────────────────────────
def test_job_from_dict_rejects_bad_ids_urls_and_paths_outside_the_download_folder(tmp_path):
    outside = tmp_path / "secret.mp4"
    outside.write_text("x")
    good = {"id": "abcd1234", "url": "https://example.com/v", "status": "done", "files": ["../secret.mp4"]}
    job = webui.Job.from_dict(good, webui.ROOT)
    assert job and job.files == []
    assert webui.Job.from_dict({**good, "id": "../../x"}, webui.ROOT) is None
    assert webui.Job.from_dict({**good, "url": "file:///etc/passwd"}, webui.ROOT) is None


def test_interrupted_jobs_come_back_as_queued():
    job = webui.Job.from_dict(
        {"id": "abcd1234", "url": "https://example.com/v", "status": "running"},
        webui.ROOT,
    )
    assert job.status == "queued" and job.stage == "Restored queue" and not job.error
    assert job.percent == 0 and job.finished == 0


def test_history_restores_running_and_reordered_waiting_jobs_with_pause():
    ids = webui.create_jobs([f"https://example.com/{i}" for i in range(4)], {})
    claimed = webui.QUEUE.get_nowait()
    assert claimed.id == ids[0]
    assert webui.QUEUE.move(ids[3], -1)
    webui.QUEUE.set_paused(True)
    claimed.resume_pending = True
    claimed.status = "canceled"  # graceful shutdown canceled its transfer, not the task
    webui.save_history()
    webui.QUEUE.task_done()
    webui.JOB_MANAGER.reset()
    webui.load_history()
    assert webui.QUEUE.paused
    assert webui.QUEUE.pending_ids() == [ids[0], ids[1], ids[3], ids[2]]
    assert all(job.status == "queued" and not job.cancel.is_set() for job in webui.JOB_MANAGER.snapshot())


def test_history_keeps_all_pending_jobs_even_above_finished_history_limit(monkeypatch):
    monkeypatch.setattr(webui, "HISTORY_MAX", 2)
    ids = webui.create_jobs([f"https://example.com/{i}" for i in range(5)], {})
    webui.JOB_MANAGER.reset()
    webui.load_history()
    assert webui.QUEUE.pending_ids() == ids


def test_legacy_history_loads_and_invalid_order_is_ignored():
    job = webui.Job("https://example.com/video", {})
    webui.HISTORY_STORE.save({"version": 1, "jobs": [job.to_dict(webui.ROOT)], "queue_order": {"invalid": 1}})
    webui.load_history()
    assert not webui.QUEUE.paused and webui.QUEUE.pending_ids() == [job.id]
    webui.load_history()
    assert webui.QUEUE.pending_ids() == [job.id]


def test_explicit_cancel_during_shutdown_is_not_automatically_recovered():
    job = webui.Job("https://example.com/video", {})
    job.status = "running"
    job.cancel.set()
    restored = webui.Job.from_dict(job.to_dict(webui.ROOT), webui.ROOT)
    assert restored.status == "canceled"


def test_repeated_enqueue_and_retry_report_duplicates(server):
    _, first = call(server, "/api/jobs", {"urls": ["https://example.com/video"], "options": {"quality": "720"}})
    _, duplicate = call(server, "/api/jobs", {"urls": ["https://example.com/video"], "options": {"quality": "720"}})
    assert duplicate == {"ids": [], "duplicates": 1}
    original = webui.JOB_MANAGER.get(first["ids"][0])
    original.status = "error"
    original.failed_items = [{"index": 2, "url": "https://example.com/2", "title": "Second", "error": "unavailable"}]
    status, retry = call(server, f"/api/jobs/{original.id}/retry", {})
    assert status == 200 and len(retry["ids"]) == 1
    assert webui.JOB_MANAGER.get(retry["ids"][0]).options["items"] == "2"
    _, repeated = call(server, f"/api/jobs/{original.id}/retry", {})
    assert repeated["ids"] == [] and repeated["duplicates"]


def test_browser_retry_requires_valid_browser_and_preserves_original_options(server):
    ids = webui.create_jobs(["https://example.com/video"], {"quality": "720", "use_cookies_file": True})
    job = webui.JOB_MANAGER.get(ids[0])
    job.status = "error"
    job.failed_items = [{"index": 2, "url": "https://example.com/2", "title": "Second", "error": "Login required"}]
    path = f"/api/jobs/{job.id}/retry-browser"
    assert call(server, path, {"browser": "chrome"}, token=False)[0] == 401
    assert call(server, path, {"browser": "unknown"})[0] == 400
    assert call(server, path, {"browser": []})[0] == 400
    status, result = call(server, path, {"browser": "chrome"})
    assert status == 200 and len(result["ids"]) == 1
    retry = webui.JOB_MANAGER.get(result["ids"][0])
    assert retry.options["cookies_from_browser"] == "chrome"
    assert not retry.options["use_cookies_file"] and retry.options["items"] == "2"
    assert job.options["use_cookies_file"] and not job.options.get("cookies_from_browser")
    assert call(server, path, {"browser": "chrome"})[1]["duplicates"]


def test_setup_endpoints_require_token_and_report_preparation_failure(server, monkeypatch):
    assert call(server, "/api/setup", {}, token=False)[0] == 401
    monkeypatch.setattr(webui, "start_setup", lambda: (False, "Preparation unavailable"))
    status, result = call(server, "/api/setup", {})
    assert status == 409 and result["error"] == "Preparation unavailable"
    monkeypatch.setattr(webui, "setup_status", lambda: {"ready": True, "issues": []})
    assert call(server, "/api/setup")[1]["ready"]


def test_folder_selection_is_authenticated_persisted_and_does_not_move_files(server, tmp_path, monkeypatch):
    original = webui.ROOT
    (original / "keep.mp4").write_bytes(b"original")
    target = tmp_path / "new folder 中文"
    target.mkdir()
    monkeypatch.setattr(webui, "choose_download_folder", lambda: str(target))
    assert call(server, "/api/download-folder/select", {}, token=False)[0] == 401
    status, result = call(server, "/api/download-folder/select", {})
    assert status == 200 and result == {"canceled": False, "restart_required": True, "root": str(target.resolve())}
    assert webui.ROOT == original and (original / "keep.mp4").read_bytes() == b"original"
    assert webui.PENDING_ROOT == target.resolve() and webui.saved_download_root(original) == target.resolve()


def test_folder_selection_cancel_and_same_folder_keep_settings(server, monkeypatch):
    monkeypatch.setattr(webui, "choose_download_folder", lambda: None)
    assert call(server, "/api/download-folder/select", {})[1]["canceled"]
    monkeypatch.setattr(webui, "choose_download_folder", lambda: str(webui.ROOT))
    assert not call(server, "/api/download-folder/select", {})[1]["restart_required"]
    assert not (webui.CONFIG_DIR / "settings.json").exists() and webui.PENDING_ROOT is None


def test_selecting_original_folder_clears_a_previous_pending_change(server, tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "choose_download_folder", lambda: str(tmp_path))
    assert call(server, "/api/download-folder/select", {})[1]["restart_required"]
    monkeypatch.setattr(webui, "choose_download_folder", lambda: str(webui.ROOT))
    assert not call(server, "/api/download-folder/select", {})[1]["restart_required"]
    assert webui.PENDING_ROOT is None and webui.saved_download_root(tmp_path) == webui.ROOT


def test_folder_selection_rechecks_pending_jobs_after_dialog(server, tmp_path, monkeypatch):
    def select():
        webui.JOB_MANAGER.enqueue(["https://example.com/video"], {})
        return str(tmp_path)

    monkeypatch.setattr(webui, "choose_download_folder", select)
    assert call(server, "/api/download-folder/select", {})[0] == 409
    assert not (webui.CONFIG_DIR / "settings.json").exists()
    monkeypatch.setattr(webui, "choose_download_folder", lambda: pytest.fail("Do not open a dialog while jobs are pending"))
    assert call(server, "/api/download-folder/select", {})[0] == 409


def test_folder_selection_rejects_unwritable_directory(server, tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "choose_download_folder", lambda: str(tmp_path))
    monkeypatch.setattr(webui.tempfile, "TemporaryFile", lambda **kw: (_ for _ in ()).throw(PermissionError("locked")))
    status, result = call(server, "/api/download-folder/select", {})
    assert status == 409 and "cannot save" in result["error"]
    assert webui.PENDING_ROOT is None


def test_native_folder_picker_uses_current_root(monkeypatch):
    seen = []
    fake_window = types.SimpleNamespace(create_file_dialog=lambda kind, **kw: seen.append((kind, kw)) or (str(webui.ROOT),))
    monkeypatch.setattr(webui, "NATIVE_WINDOW", fake_window)
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(FileDialog=types.SimpleNamespace(FOLDER=20)))
    assert webui.choose_download_folder() == str(webui.ROOT)
    assert seen == [(20, {"directory": str(webui.ROOT)})]


def test_saved_folder_keeps_explicit_cli_override(tmp_path, monkeypatch):
    from grab_config import parse_web_config
    monkeypatch.delenv("GRAB_DEFAULT_DOWNLOAD_DIR", raising=False)
    assert not parse_web_config([]).download_dir_explicit
    config = parse_web_config(["--dir", str(tmp_path)])
    assert config.download_dir_explicit and config.download_dir == tmp_path.resolve()
    assert webui.saved_download_root(tmp_path) == tmp_path


def test_restart_applies_pending_folder_and_reopens_native_window(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(webui, "PENDING_ROOT", tmp_path)
    monkeypatch.setattr(webui, "WINDOW_MODE", True)
    monkeypatch.setattr(webui.sys, "platform", "win32")
    monkeypatch.setattr(webui.subprocess, "Popen", lambda args, **kw: seen.update(args=args, env=kw["env"]))
    monkeypatch.setattr(webui.os, "_exit", lambda code: (_ for _ in ()).throw(RuntimeError("exit intercepted")))
    with pytest.raises(RuntimeError, match="exit intercepted"):
        webui.restart_self()
    assert seen["args"][seen["args"].index("--dir") + 1] == str(tmp_path)
    assert seen["args"][seen["args"].index("--ui") + 1] == "window"
    assert seen["env"]["GRAB_RESTART_WINDOW"] == "1"


def test_batch_trash_returns_only_successful_ids_for_undo(server):
    for name in ("video.mp4", "video.jpg", "video.en.srt"):
        (webui.ROOT / name).write_bytes(name.encode())
    status, result = call(server, "/api/library/batch", {"items": ["video.mp4", "missing.mp4"], "action": "trash"})
    assert status == 200 and result["processed"] == ["video.mp4"]
    assert len(result["recovery_ids"]) == len(result["failed"]) == 1
    _, restored = call(server, "/api/library/batch", {"items": result["recovery_ids"], "action": "restore"})
    assert restored["processed"] == result["recovery_ids"]
    for name in ("video.mp4", "video.jpg", "video.en.srt"):
        assert (webui.ROOT / name).read_bytes() == name.encode()


@pytest.mark.parametrize("locked", [False, True])
def test_batch_trash_bounds_library_writes_and_undo_after_partial_failure(server, monkeypatch, locked):
    names = ["one.mp4", "two.mp4", "three.mp4"]
    for name in names:
        (webui.ROOT / name).write_bytes(name.encode())
    (webui.ROOT / "two.jpg").write_bytes(b"cover")
    save, move = type(webui.LIBRARY.store).save, webui.LIBRARY.move_without_overwrite
    saves = []

    def counted_save(store, value):
        if store.path() == webui.LIBRARY.store.path():
            saves.append(len(value["trash"]))
        save(store, value)

    def locked_move(source, target):
        if locked and source.name == "two.jpg":
            raise PermissionError("File locked")
        move(source, target)

    with monkeypatch.context() as context:
        context.setattr(type(webui.LIBRARY.store), "save", counted_save)
        context.setattr(webui.LIBRARY, "move_without_overwrite", locked_move)
        status, result = call(server, "/api/library/batch", {"items": names, "action": "trash"})
    assert status == 200 and saves == ([3, 2] if locked else [3])
    assert result["processed"] == (["one.mp4", "three.mp4"] if locked else names)
    assert len(result["recovery_ids"]) == len(result["processed"])
    assert [failure["item"] for failure in result["failed"]] == (["two.mp4"] if locked else [])
    _, restored = call(server, "/api/library/batch", {"items": result["recovery_ids"], "action": "restore"})
    assert restored["processed"] == result["recovery_ids"] and not restored["failed"]
    assert all((webui.ROOT / name).read_bytes() == name.encode() for name in names)
    assert (webui.ROOT / "two.jpg").read_bytes() == b"cover"


def test_batch_trash_persistence_failure_is_reported_without_moving_files(server, monkeypatch):
    names = ["one.mp4", "two.mp4"]
    for name in names:
        (webui.ROOT / name).write_bytes(b"media")
    save = type(webui.LIBRARY.store).save

    def fail_library_save(store, value):
        if store.path() == webui.LIBRARY.store.path():
            raise OSError("disk full")
        save(store, value)

    monkeypatch.setattr(type(webui.LIBRARY.store), "save", fail_library_save)
    status, result = call(server, "/api/library/batch", {"items": names, "action": "trash"})
    assert status == 200 and result["processed"] == result["recovery_ids"] == []
    assert [failure["item"] for failure in result["failed"]] == names
    assert all((webui.ROOT / name).read_bytes() == b"media" for name in names)
    assert webui.LIBRARY.load()["trash"] == {}


@pytest.mark.parametrize("failure", ["503", "interrupted"])
def test_video_download_recovers_from_temporary_http_failure(media_site, monkeypatch, failure):
    import http.server
    import grab_download
    monkeypatch.setattr(grab_download, "RETRY_DELAYS", (0, 0))
    requests = []
    clip = (media_site["root"] / "clip.mp4").read_bytes()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if failure == "503" and len(requests) == 1:
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(clip)))
            self.end_headers()
            if failure == "interrupted" and len(requests) == 2:
                self.wfile.write(clip[:1024])
                self.close_connection = True
                return
            self.wfile.write(clip)

        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        job = webui.Job(f"http://127.0.0.1:{srv.server_port}/clip.mp4", {"mode": "mp4"})
        webui.run_job(job)
        assert job.status == "done" and not job.failed_items, list(job.log)
        assert any("[Retry]" in line for line in job.log)
        assert len(job.files) == 1 and Path(job.files[0]).is_file()
        details = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", job.files[0],
        ], text=True))
        assert float(details["format"]["duration"]) >= 1.9
        assert {stream["codec_type"] for stream in details["streams"]} == {"video", "audio"}
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(2)


def test_pause_and_order_changes_are_saved_immediately(server):
    ids = webui.create_jobs(["https://example.com/1", "https://example.com/2"], {})
    call(server, "/api/queue", {"paused": True})
    call(server, f"/api/jobs/{ids[1]}/move-up", {})
    webui.JOB_MANAGER.reset()
    webui.load_history()
    assert webui.QUEUE.paused and webui.QUEUE.pending_ids() == ids[::-1]


def test_scan_reports_entry_and_depth_limits(server, monkeypatch):
    for i in range(3):
        (webui.ROOT / f"{i}.mp4").write_bytes(b"media")
    monkeypatch.setattr(webui, "FILE_SCAN_MAX_ENTRIES", 2)
    _, state = call(server, "/api/state?rev=-1")
    assert len(state["files"]) == 2
    scan = state["library_scan"]
    assert scan["incomplete"] and scan["reasons"] == ["entry_limit"] and scan["checked"] == 2
    monkeypatch.setattr(webui, "FILE_SCAN_MAX_ENTRIES", 20000)
    nested = webui.ROOT / "a" / "b" / "c" / "d"
    nested.mkdir(parents=True)
    (nested / "deep.mp4").write_bytes(b"media")
    _, state = call(server, "/api/state?rev=-1")
    assert len(state["files"]) == 3
    assert state["library_scan"]["reasons"] == ["depth_limit"]


def test_scan_snapshot_preserves_cover_and_independent_image_rules():
    for name in ("video.mp4", "video.jpg", "audio.mp3", "audio.png", "explicit.mp4", "explicit.jpg", "standalone.jpg"):
        (webui.ROOT / name).write_bytes(b"fixture")
    webui.LIBRARY.remember({"explicit.jpg": {"role": "image"}})
    files = {item["path"]: item for item in webui.list_files(force=True)}
    assert set(files) == {"video.mp4", "audio.mp3", "explicit.mp4", "explicit.jpg", "standalone.jpg"}
    assert files["video.mp4"]["thumbnail"] == "video.jpg"
    assert files["audio.mp3"]["thumbnail"] == "audio.png"
    assert files["explicit.mp4"]["thumbnail"] == ""
    assert files["standalone.jpg"]["kind"] == "image"


def test_truncated_scan_does_not_expose_a_cover_as_an_independent_image(monkeypatch):
    (webui.ROOT / "video.jpg").write_bytes(b"cover")
    (webui.ROOT / "video.mp4").write_bytes(b"media")
    monkeypatch.setattr(webui, "FILE_SCAN_MAX_ENTRIES", 1)
    result = webui.list_files(force=True)
    assert not any(file["path"] == "video.jpg" for file in result)
    assert webui.FILES_CACHE["scan"]["incomplete"]


def test_scan_keeps_more_than_5000_discovered_files(tmp_path, monkeypatch):
    class Entry:
        name = "video.mp4"

        def __init__(self, i):
            self.name = f"{i}.mp4"
            self.path = str(webui.ROOT / self.name)

        def is_dir(self, **kwargs):
            return False

        def is_file(self, **kwargs):
            return True

        def stat(self):
            return types.SimpleNamespace(st_size=10, st_mtime=1)

    class Scan:
        def __iter__(self):
            return iter(Entry(i) for i in range(5002))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(webui.os, "scandir", lambda path: Scan())
    assert len(webui.list_files(force=True)) == 5002
    assert not webui.FILES_CACHE["scan"]["incomplete"]


# ───────────────────────── cookies.txt ─────────────────────────
def _cookies_text(header=True, eol="\n", youtube_login=True):
    rows = ["#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\tSECRET-LOGIN-VALUE",
            ".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSAPISID\tSECRET-SID-VALUE",
            ".bilibili.com\tTRUE\t/\tFALSE\t1999999999\tSESSDATA\tSECRET-BILI-VALUE",
            ".old.example\tTRUE\t/\tFALSE\t1000\tgone\tv"]
    if not youtube_login:
        rows = rows[2:]
    return eol.join((["# Netscape HTTP Cookie File"] if header else []) + rows) + eol


def test_parse_cookies_summary_never_contains_values():
    info = webui.parse_cookies(_cookies_text())
    assert info["cookies"] == 4 and info["expired"] == 1
    assert info["youtube_login"] and info["bilibili_login"]
    status = json.dumps({k: v for k, v in info.items() if k != "text"})
    assert "SECRET" not in status


def test_parse_cookies_adds_missing_header_and_accepts_windows_newlines():
    info = webui.parse_cookies(_cookies_text(header=False, eol="\r\n"))
    assert info["text"].startswith("# Netscape HTTP Cookie File\n")
    assert "\r" not in info["text"]


def test_parse_cookies_detects_missing_youtube_login():
    info = webui.parse_cookies(_cookies_text(youtube_login=False))
    assert not info["has_youtube"] and not info["youtube_login"] and info["bilibili_login"]


@pytest.mark.parametrize("bad", ["", "hello world", '{"cookies": []}', "# Netscape HTTP Cookie File\nnot\tenough\tfields\n"])
def test_parse_cookies_rejects_things_that_are_not_cookie_files(bad):
    with pytest.raises(ValueError):
        webui.parse_cookies(bad)


def test_cookies_are_stored_outside_the_download_folder_and_can_be_deleted():
    st = webui.save_cookies(_cookies_text())
    assert st["present"] and st["cookies"] == 4
    assert webui.cookies_path().parent == webui.CONFIG_DIR
    assert webui.ROOT not in webui.cookies_path().parents
    if os.name == "posix":
        assert (webui.cookies_path().stat().st_mode & 0o077) == 0
    webui.delete_cookies()
    assert webui.cookies_status() == {"present": False}


def test_each_run_gets_its_own_cookie_copy_and_the_original_is_untouched():
    webui.save_cookies(_cookies_text())
    original = webui.cookies_path().read_bytes()
    a = webui.make_args({"use_cookies_file": True})
    with webui.cookie_copy(a) as one, webui.cookie_copy(a) as two:
        assert one != two and Path(one).read_bytes() == original
        Path(one).write_text("yt-dlp rewrote this")          # what yt-dlp does when it closes
    assert not Path(one).exists() and not Path(two).exists()
    assert webui.cookies_path().read_bytes() == original
    with webui.cookie_copy(webui.make_args({})) as nothing:
        assert nothing is None


# ───────────────────────── diagnostics ─────────────────────────
def test_collect_doctor_includes_cookies_and_recent_failures():
    webui.save_cookies(_cookies_text())
    job = webui.Job("https://example.com/watch?v=1", {})
    job.status, job.error, job.finished = "error", "HTTP Error 403", 1.0
    job.log.extend(["line one", "line two"])
    webui.JOBS[job.id] = job
    d = webui.collect_doctor(force=True)
    ids = {c["id"] for c in d["checks"]}
    assert {"python", "ytdlp", "ffmpeg", "js_runtime", "ejs", "cookies", "output_dir"} <= ids
    assert "Recent failure 1:" in d["report"] and "https://example.com/watch?v=1" in d["report"]
    assert "SECRET" not in d["report"]


# ───────────────────────── job notes ─────────────────────────
def test_a_missing_js_runtime_warning_becomes_a_visible_note(monkeypatch):
    monkeypatch.setattr(grab, "media_tool_check", lambda *args: {"status": "ok"})
    def fake_discover(url, args, download_one, log, on_title, check):
        log("Warning: [youtube] No supported JavaScript runtime could be found. Only deno is enabled by default")
        log("Warning: [youtube] n challenge solving failed: Some formats may be missing")   # same rule, one note
        log("[Hint] If the video is loaded dynamically by JavaScript, enable rendering")      # our own hint: ignored
        return True

    monkeypatch.setattr(grab, "discover_and_download", fake_discover)
    job = webui.Job("https://www.youtube.com/watch?v=x", {})
    webui.run_job(job)
    assert job.status == "done"
    assert len(job.notes) == 1 and "Diagnostics" in job.notes[0]
    assert webui.Job.from_dict(job.to_dict(webui.ROOT) | {"status": "done"}, webui.ROOT).notes == job.notes


# ───────────────────────── update / install components ─────────────────────────
class FakeProc:
    def __init__(self, cmd):
        FakeProc.cmd = cmd
        self.stdout = iter(["Collecting yt-dlp\n", "Successfully installed\n"])

    def wait(self):
        return 0


@pytest.mark.parametrize("extras", ["default", "default,deno"])
def test_update_installs_the_right_extras(monkeypatch, extras):
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: FakeProc(cmd))
    webui._do_update(extras)
    expected = "yt-dlp[curl-cffi,default,deno]" if "deno" in extras else "yt-dlp[curl-cffi,default]"
    assert FakeProc.cmd[-1] == expected and FakeProc.cmd[1:3] == ["-m", "pip"]


def test_portable_update_targets_embedded_site_packages(monkeypatch, tmp_path):
    class FakeProc:
        stdout = iter(())
        cmd = []

        def __init__(self, cmd, **kwargs):
            type(self).cmd = cmd

        def wait(self): return 0

    python_dir = tmp_path / "python"
    python_dir.mkdir()
    executable = python_dir / "python.exe"
    executable.write_bytes(b"")
    monkeypatch.setenv("VIDEO_GRABBER_PORTABLE_ROOT", str(tmp_path))
    monkeypatch.setattr(webui.sys, "executable", str(executable))
    monkeypatch.setattr(webui.subprocess, "Popen", FakeProc)
    webui._do_update("default")
    assert "--ignore-installed" in FakeProc.cmd
    assert FakeProc.cmd[FakeProc.cmd.index("--target") + 1] == str(python_dir / "Lib" / "site-packages")
    assert webui.UPDATE["status"] == "done"


def test_setup_package_install_stays_running_until_final_tool_checks(monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: FakeProc(cmd))
    webui.UPDATE["status"] = "running"
    webui._do_update("default,deno", preparing=True)
    assert webui.UPDATE["status"] == "running"


@pytest.mark.parametrize("virtual", [False, True])
def test_preparation_installs_for_current_user_only_outside_a_virtualenv(monkeypatch, virtual):
    monkeypatch.delenv("VIDEO_GRABBER_PORTABLE_ROOT", raising=False)
    monkeypatch.setattr(sys, "prefix", "venv" if virtual else "system")
    monkeypatch.setattr(sys, "base_prefix", "system")
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: FakeProc(cmd))
    webui._do_update("default,deno", preparing=True)
    assert ("--user" in FakeProc.cmd) is (not virtual and not sys.flags.no_user_site)
    assert FakeProc.cmd[0] == sys.executable


def test_preparation_reports_real_stages_and_finishes_after_verification(monkeypatch):
    stages = []
    monkeypatch.setattr(webui, "setup_status", lambda: {"issues": ["ffmpeg", "ejs"], "blocked": False})
    monkeypatch.setattr(webui, "configure_managed_components", lambda: None)
    def install_tools(*args, **kwargs):
        stages.append(webui.UPDATE["setup_stage"])
        return types.SimpleNamespace(returncode=0, stdout="Prepared", stderr="")
    monkeypatch.setattr(subprocess, "run", install_tools)
    def install_sites(*args, **kwargs):
        stages.append(webui.UPDATE["setup_stage"])
        assert kwargs["preparing"] is True
    monkeypatch.setattr(webui, "_do_update", install_sites)
    def verify(*args):
        stages.append(webui.UPDATE["setup_stage"])
        return {"status": "ok"}
    monkeypatch.setattr(grab, "media_tool_check", verify)
    webui.UPDATE.update(status="running", lines=[], setup_stage="checking")
    webui._do_setup()
    assert stages == ["media", "sites", "verifying", "verifying"]
    assert webui.UPDATE["status"] == "done" and webui.UPDATE["setup_stage"] == "ready"
    assert webui.UPDATE["restart_required"] is True


def test_update_is_refused_while_jobs_are_active():
    job = webui.Job("https://example.com/v", {})
    webui.JOBS[job.id] = job                                # queued
    ok, why = webui.start_update()
    assert not ok and "queued or downloading" in why


def test_background_loops_stop_without_waiting_for_their_normal_interval():
    stop = threading.Event()
    stop.set()
    worker_thread = threading.Thread(target=webui.worker, args=(stop,))
    scheduler_thread = threading.Thread(target=webui.subscription_scheduler, args=(stop,))
    worker_thread.start()
    scheduler_thread.start()
    worker_thread.join(1.0)
    scheduler_thread.join(1.0)
    assert not worker_thread.is_alive() and not scheduler_thread.is_alive()


# ───────────────────────── the HTTP server ─────────────────────────
def test_requests_without_the_token_are_rejected(server):
    assert call(server, "/api/state", token=False)[0] == 401
    assert call(server, "/api/state")[0] == 200


def test_requests_with_a_foreign_host_header_are_rejected(server):
    assert call(server, "/api/state", host="evil.example:80")[0] == 403
    assert call(server, "/api/state", host="localhost:1234")[0] == 200


def test_posts_must_be_json(server):
    assert call(server, "/api/jobs", {"urls": ["https://example.com"]}, ctype="text/plain")[0] == 415


def test_only_http_urls_can_be_queued(server):
    assert call(server, "/api/jobs", {"urls": ["file:///etc/passwd", "ftp://x/y"]})[0] == 400


@pytest.mark.parametrize(
    "status,action",
    [("done", "cancel"), ("done", "retry"), ("running", "remove")],
)
def test_job_actions_reject_invalid_state_transitions(server, status, action):
    job = webui.Job("https://example.com/video", {})
    job.status = status
    job.stage = "Done" if status == "done" else "Downloading"
    webui.JOBS[job.id] = job
    response_status, _ = call(server, f"/api/jobs/{job.id}/{action}", {})
    assert response_status == 409
    assert job.status == status
    assert job.stage == ("Done" if status == "done" else "Downloading")


@pytest.mark.parametrize("path", ["../secret.mp4", "..%2Fsecret.mp4", "%2e%2e/secret.mp4", "/etc/passwd"])
def test_files_cannot_escape_the_download_folder(server, tmp_path, path):
    (tmp_path / "secret.mp4").write_text("top secret")
    status, body = call(server, f"/files/{path}?t={webui.TOKEN}", token=False)
    assert status in (403, 404) and b"top secret" not in (body if isinstance(body, bytes) else b"")


def test_files_are_served_with_range_support(server):
    (webui.ROOT / "a.mp4").write_bytes(bytes(range(100)))
    req = urllib.request.Request(f"{server}/files/a.mp4?t={webui.TOKEN}", headers={"Range": "bytes=10-19"})
    with urllib.request.urlopen(req) as r:
        assert r.status == 206 and r.read() == bytes(range(10, 20))


def test_media_preview_disconnect_closes_its_file_without_reporting_failure():
    path = webui.ROOT / "preview.mp4"
    path.write_bytes(b"media preview")
    handler = object.__new__(webui.Handler)
    handler.headers = {}
    handler.send_response = lambda *args: None
    handler.send_header = lambda *args: None
    handler.end_headers = lambda: None
    handler.wfile = types.SimpleNamespace(write=lambda *args: (_ for _ in ()).throw(ConnectionAbortedError("preview closed")))
    handler._file(path.name)
    path.unlink()
    assert not path.exists()


def test_cookies_endpoints_and_the_file_is_never_served_back(server):
    assert call(server, "/api/cookies")[1] == {"present": False}
    status, st = call(server, "/api/cookies", {"text": _cookies_text()})
    assert status == 200 and st["present"] and "SECRET" not in json.dumps(st)
    assert call(server, "/api/cookies", {"text": "not cookies"})[0] == 400
    assert call(server, f"/files/cookies.txt?t={webui.TOKEN}", token=False)[0] == 404
    assert call(server, "/api/cookies/delete", {})[1] == {"present": False}


def test_doctor_endpoint(server):
    status, d = call(server, "/api/doctor?force=1")
    assert status == 200 and {"checks", "report"} <= set(d)
    assert all({"id", "label", "status", "detail"} <= set(c) for c in d["checks"])


def test_installing_components_only_accepts_known_extras(server, monkeypatch):
    seen = []
    monkeypatch.setattr(webui, "_do_update", lambda extras="default": seen.append(extras))
    assert call(server, "/api/ytdlp/update", {"extras": "default,deno"})[0] == 200
    webui.UPDATE["status"] = "idle"
    assert call(server, "/api/ytdlp/update", {"extras": "evil; rm -rf /"})[0] == 200
    threading.Event().wait(0.3)
    assert seen == ["default,deno", "default"]


def test_restart_is_refused_while_jobs_are_active(server):
    job = webui.Job("https://example.com/v", {})
    job.status = "running"
    webui.JOBS[job.id] = job
    assert call(server, "/api/restart", {})[0] == 409


# ───────────────────────── probe: no pre-check that can contradict yt-dlp ─────────────────────────
def test_probe_of_an_unreachable_address_gives_a_network_message():
    result = webui.probe("http://127.0.0.1:9/video.mp4", {})
    assert "Cannot reach the site" in result["error"]


def test_probe_does_not_pre_check_with_a_direct_socket(monkeypatch):
    """The old pre-check connected directly and ignored proxies, so it could reject links that yt-dlp could open."""
    import socket
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(AssertionError("direct connect")))
    monkeypatch.setattr(webui.yt_dlp, "YoutubeDL", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop here")))
    assert "error" in webui.probe("https://blocked-without-proxy.example/v", {"proxy": ""})


def test_probe_passes_the_proxy_setting_to_page_scanning(monkeypatch):
    seen = {}
    monkeypatch.setattr(webui.yt_dlp, "YoutubeDL", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no extractor")))
    monkeypatch.setattr(webui.grab, "has_specific_extractor", lambda u: False)
    monkeypatch.setattr(webui.grab, "sniff_media_urls",
                        lambda u, log=print, proxy=None: seen.setdefault("proxy", proxy) and ("T", ["http://x/a.m3u8"]))
    result = webui.probe("https://example.com/page", {"proxy": "socks5://127.0.0.1:1080"})
    assert seen["proxy"] == "socks5://127.0.0.1:1080" and result["kind"] == "page"


def test_the_report_this_issue_boilerplate_is_not_a_login_problem():
    raw = ("ERROR: [generic] x: Something unexpected happened; please report this issue on  https://github.com/yt-dlp/yt-dlp/issues?q= , "
           "filling out the appropriate issue template. Confirm you are on the latest version using  yt-dlp -U")
    msg = webui.friendly_error(raw)
    assert "requires login" not in msg and "please report" not in msg and "Something unexpected happened" in msg


def test_probe_size_accounts_for_separate_streams_and_mp3_bitrate():
    args = webui.make_args({"mode": "mp4"})
    assert webui.estimate_media_size({"requested_formats": [{"filesize": 100}, {"filesize": 20}]}, args) == {
        "bytes": 120, "approximate": False,
    }
    assert webui.estimate_media_size({"requested_formats": [{"filesize": 100}, {}]}, args)["bytes"] is None
    assert webui.estimate_media_size({"duration": 10, "tbr": 800}, args) == {"bytes": 1_000_000, "approximate": True}
    assert webui.estimate_media_size({"duration": 10}, webui.make_args({"mode": "mp3", "abr": 128}))["bytes"] == 160_000


def test_original_audio_uses_source_size_and_preserves_settings():
    args = webui.make_args({"mode": "original", "abr": 96, "quality": "720", "cover": True})
    assert args.mode == "original" and args.keep_cover is True
    assert webui.estimate_media_size({"filesize": 12345}, args) == {"bytes": 12345, "approximate": False}


def test_organization_api_auth_validation_and_state_refresh(server):
    (webui.ROOT / "clip.mp4").write_bytes(b"video")
    assert call(server, "/api/library/collections", {"action": "create", "name": "学习"}, token=False)[0] == 401
    status, result = call(server, "/api/library/collections", {"action": "create", "name": "学习"})
    assert status == 200
    key = result["id"]
    status, organized = call(server, "/api/library/organize", {
        "items": ["clip.mp4", "../outside.mp4"], "favorite": True, "collection_id": key,
    })
    assert status == 200 and organized["processed"] == ["clip.mp4"] and len(organized["failed"]) == 1
    state = call(server, "/api/state")[1]
    assert state["collections"] == [{"id": key, "name": "学习"}]
    assert state["files"][0]["favorite"] is True and state["files"][0]["collections"] == [key]
    assert call(server, "/api/library/organize", {"items": ["clip.mp4"], "favorite": "false"})[0] == 400
    assert call(server, "/api/library/collections", {"action": "delete", "id": []})[0] == 400
    assert call(server, "/api/library/organize", {"items": ["clip.mp4"], "collection_id": []})[0] == 400
    assert call(server, "/api/library/collections", {"action": "delete", "id": key})[0] == 200
    updated = call(server, "/api/state?rev=" + str(state["rev"]))[1]
    assert updated["rev"] != state["rev"] and updated["collections"] == []
    assert updated["files"][0]["collections"] == [] and updated["files"][0]["favorite"] is True


def test_library_import_api_streams_authenticates_and_deduplicates(server):
    def upload(name, token=True, ctype="application/octet-stream", host=None):
        headers = {"Content-Type": ctype}
        if token:
            headers["X-Token"] = webui.TOKEN
        if host:
            headers["Host"] = host
        request = urllib.request.Request(server + "/api/library/import?name=" + urllib.parse.quote(name),
                                         data=b"local media", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())
    assert upload("clip.mp4", token=False)[0] == 401
    assert upload("clip.mp4", host="example.com")[0] == 403
    assert upload("clip.mp4", ctype="text/plain")[0] == 415
    assert upload("../outside.mp4")[0] == 400
    status, result = upload("clip.mp4")
    assert status == 200 and result == {"path": "imports/clip.mp4", "duplicate": False}
    assert (webui.ROOT / result["path"]).read_bytes() == b"local media"
    assert upload("other.mp4")[1]["duplicate"] is True
    state = call(server, "/api/state")[1]
    assert len(state["files"]) == 1 and state["files"][0]["source"] == "local"


def test_library_details_and_playback_api_validate_and_refresh(server):
    (webui.ROOT / "video.mp4").write_bytes(b"video")
    (webui.ROOT / "video.jpg").write_bytes(b"cover")
    data = {"path": "video.mp4", "tags": ["学习"], "note": "Review audio settings"}
    assert call(server, "/api/library/details", data, token=False)[0] == 401
    assert call(server, "/api/library/details", data)[0] == 200
    assert call(server, "/api/library/playback", {"path": "video.mp4", "position": 30, "duration": 120})[0] == 200
    state = call(server, "/api/state")[1]
    item = state["files"][0]
    assert len(state["files"]) == 1 and item["tags"] == ["学习"] and item["note"] == data["note"]
    assert item["thumbnail"] == "video.jpg" and item["playback"]["position"] == 30
    assert call(server, "/api/library/playback", {"path": "video.mp4", "position": True, "duration": 120})[0] == 400
    assert call(server, "/api/library/details", {**data, "path": "../outside.mp4"})[0] == 400


def test_library_import_and_restart_are_blocked_during_folder_operations(server):
    with webui.FOLDER_PICK_LOCK:
        request = urllib.request.Request(server + "/api/library/import?name=clip.mp4", data=b"video",
                                         headers={"X-Token": webui.TOKEN, "Content-Type": "application/octet-stream"})
        with pytest.raises(urllib.error.HTTPError) as failed:
            urllib.request.urlopen(request, timeout=10)
        assert failed.value.code == 409
        assert call(server, "/api/restart", {})[0] == 409


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg is not installed")
def test_original_audio_queue_finishes_and_library_remembers_audio(media_site):
    job = webui.Job(media_site["base"] + "/clip.mp4", {"mode": "original"})
    webui.run_job(job)
    assert job.status == "done" and not job.failed_items
    assert len(job.files) == 1 and Path(job.files[0]).suffix == ".m4a"
    assert job.media_metadata[job.files[0]]["complete"] is True
    files = webui.list_files(force=True)
    assert len(files) == 1 and files[0]["kind"] == "audio" and files[0]["complete"] is True


def test_video_download_always_keeps_website_cover_options():
    args = webui.make_args({"mode": "mp4", "cover": False, "keep_cover": False})
    opts = grab.build_opts(args)
    assert opts["writethumbnail"] is True
    assert next(pp for pp in opts["postprocessors"] if pp["key"] == "EmbedThumbnail")["already_have_thumbnail"] is True
    assert webui.make_args({"mode": "mp3"}).cover is False


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg is not installed")
def test_video_download_saves_original_website_cover_and_embeds_it(media_site):
    from PIL import Image
    from conftest import FFMPEG_EXE
    image = media_site["root"] / "website-cover.jpg"
    Image.new("RGB", (640, 480), "red").save(image)
    page = media_site["root"] / "with-cover.html"
    base = media_site["base"]
    page.write_text(f'<html><head><title>Website cover</title><meta property="og:image" content="{base}/website-cover.jpg">'
                    f'</head><body><video poster="{base}/website-cover.jpg" src="{base}/clip.mp4"></video></body></html>',
                    encoding="utf-8")
    job = webui.Job(media_site["base"] + "/with-cover.html", {"mode": "mp4"})
    webui.run_job(job)
    assert job.status == "done", list(job.log)
    files = webui.list_files(force=True)
    video = next(file for file in files if file["kind"] == "video")
    assert video["thumbnail"].endswith(".jpg")
    with Image.open(webui.ROOT / video["thumbnail"]) as cover:
        assert cover.size == (640, 480)
        assert cover.getpixel((320, 240))[0] > 240
    probe = subprocess.run([str(FFMPEG_EXE.with_name("ffprobe" + FFMPEG_EXE.suffix)), "-v", "error", "-show_streams", "-of", "json",
                            str(webui.ROOT / video["path"])], capture_output=True, text=True, check=True)
    assert any(stream["disposition"]["attached_pic"] for stream in json.loads(probe.stdout)["streams"])


def test_probe_keeps_playlist_indices_and_limits_preview_work(monkeypatch):
    seen = {}

    class FakeYdl:
        def __init__(self, opts): seen.update(opts)
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def extract_info(self, *args, **kwargs):
            return {"_type": "playlist", "playlist_count": 300, "entries": [None, {"title": "Second", "duration": 90}]}

    monkeypatch.setattr(webui.yt_dlp, "YoutubeDL", FakeYdl)
    result = webui.probe("https://example.com/playlist", {"quality": "720", "referer": "https://example.com/"})
    assert result["playlist_entries"] == [{"index": 2, "title": "Second", "duration": 90}]
    assert result["count"] == 300 and seen["playlistend"] == 100
    assert seen["format"] == grab.video_format("720") and seen["http_headers"]["Referer"] == "https://example.com/"


def test_batch_controls_and_waiting_order_endpoints(server):
    ids = call(server, "/api/jobs", {"urls": ["https://example.com/1", "https://example.com/2"]})[1]["ids"]
    assert call(server, "/api/queue", {"paused": True})[0] == 200
    assert call(server, f"/api/jobs/{ids[1]}/move-up", {})[0] == 200
    state = call(server, "/api/state")[1]
    assert state["queue_paused"] and state["queue_order"] == ids[::-1]
    status, result = call(server, "/api/jobs/batch", {"ids": [ids[0], ids[0], "deadbeef"], "action": "cancel"})
    assert status == 200 and result == {"processed": [ids[0]], "skipped": ["deadbeef"]}
    assert call(server, "/api/jobs/batch", {"ids": ["../x"], "action": "remove"})[0] == 400
    assert call(server, "/api/queue", {"paused": "false"})[0] == 400


@pytest.mark.parametrize("incomplete", [False, True])
def test_library_endpoints_update_job_paths_and_recover_files(server, incomplete):
    path = webui.ROOT / "video.mp4"
    path.write_bytes(b"media")
    job = webui.Job("https://example.com/video", {})
    job.status, job.files = "done", [str(path)]
    if incomplete:
        job.status = "error"
        job.media_metadata[str(path)] = {"complete": False}
    webui.JOB_MANAGER.add_restored(job)
    webui.LIBRARY.remember({"video.mp4": {"source_url": job.url}})
    assert call(server, "/api/library/rename", {"path": "video.mp4", "name": "new.mp4"})[0] == 200
    assert job.view(webui.ROOT)["files"][0]["path"] == "new.mp4"
    assert job.view(webui.ROOT)["files"][0]["complete"] is not incomplete
    recovery_id = call(server, "/api/library/trash", {"path": "new.mp4"})[1]["id"]
    assert job.view(webui.ROOT)["files"] == [] and webui.list_files() == []
    stored = next((webui.ROOT / ".grab-trash").iterdir())
    assert call(server, "/files/.grab-trash/" + stored.name)[0] == 404
    assert call(server, "/api/library/trash")[1]["items"][0]["id"] == recovery_id
    assert call(server, "/api/library/restore", {"id": recovery_id})[0] == 200
    assert job.view(webui.ROOT)["files"][0]["path"] == "new.mp4"
    assert webui.list_files()[0]["complete"] is not incomplete
    assert webui.list_files()[0]["source_url"] == job.url
    job.status = "running"
    assert call(server, "/api/library/trash", {"path": "new.mp4"})[0] == 409
    assert (webui.ROOT / "new.mp4").is_file()


def test_library_batch_partial_failure_and_recovery(server):
    for name in ("one.mp4", "two.mp4"):
        (webui.ROOT / name).write_bytes(b"media")
    status, result = call(server, "/api/library/batch", {"action": "trash", "items": ["one.mp4", "one.mp4", "missing.mp4", "../outside.mp4", "two.mp4"]})
    assert status == 200 and result["processed"] == ["one.mp4", "two.mp4"]
    assert len(result["failed"]) == 2
    items = call(server, "/api/library/trash")[1]["items"]
    assert sum(item["size"] for item in items) == 10
    assert call(server, "/api/library/batch", {"action": "restore", "items": [items[0]["id"]]})[1]["processed"] == [items[0]["id"]]
    assert call(server, "/api/library/batch", {"action": "purge", "items": [items[1]["id"]]})[1]["processed"] == [items[1]["id"]]
    assert call(server, "/api/library/trash")[1]["items"] == []


def test_smart_collection_api_is_authenticated_persistent_and_preserves_files(server):
    path = webui.ROOT / "clip.mp4"
    path.write_bytes(b"media")
    body = {"action": "create", "name": "Study", "rules": {"tag": "study", "favorite": False}}
    assert call(server, "/api/library/smart-collections", body, token=False)[0] == 401
    status, result = call(server, "/api/library/smart-collections", body)
    assert status == 200
    key = result["id"]
    _, state = call(server, "/api/state?rev=-1")
    assert state["smart_collections"] == [{"id": key, "name": "Study", "rules": body["rules"]}]
    assert state["collections"] == [] and state["files"][0]["path"] == path.name
    assert call(server, "/api/library/smart-collections", {"action": "update", "id": key, "name": "Recent", "rules": {"recent_days": 7}})[0] == 200
    assert call(server, "/api/library/smart-collections", {**body, "rules": {"future": True}})[0] == 400
    assert call(server, "/api/library/organize", {"items": [path.name], "collection_id": key})[0] == 400
    assert call(server, "/api/library/smart-collections", {"action": "delete", "id": key})[0] == 200
    assert webui.LIBRARY.smart_collections() == [] and path.read_bytes() == b"media"


@pytest.mark.parametrize("body", [{"action": "purge", "items": []}, {"action": "delete", "items": ["one.mp4"]}, {"action": "trash", "items": [3]}, {"action": "trash", "items": ["one.mp4"] * 201}])
def test_library_batch_rejects_invalid_input(server, body):
    assert call(server, "/api/library/batch", body)[0] == 400


def test_repair_request_uses_saved_settings_and_prevents_duplicates(server):
    (webui.ROOT / "video.mp4").write_bytes(b"media")
    webui.LIBRARY.remember({"video.mp4": {"complete": False, "source_url": "https://example.com/video", "repair_options": {"mode": "mp4", "cover": True}}})
    assert webui.list_files(force=True)[0]["can_repair"]
    result = call(server, "/api/library/repair", {"path": "video.mp4"})[1]
    assert len(result["ids"]) == 1
    job = webui.JOB_MANAGER.get(result["ids"][0])
    assert job.options["_repair_path"] == "video.mp4"
    assert call(server, "/api/library/repair", {"path": "video.mp4"})[1]["duplicates"]
    assert call(server, "/api/library/repair", {"path": "../outside.mp4"})[0] == 400
    webui.LIBRARY.remember({"video.mp4": {"complete": True}})
    assert call(server, "/api/library/repair", {"path": "video.mp4"})[0] == 400


def test_recovery_purge_endpoint(server):
    path = webui.ROOT / "video.mp4"
    path.write_bytes(b"media")
    recovery_id = call(server, "/api/library/trash", {"path": path.name})[1]["id"]
    job = webui.Job("https://example.com/video", {})
    job.status = "running"
    webui.JOB_MANAGER.add_restored(job)
    assert call(server, "/api/library/purge", {"id": recovery_id})[0] == 409
    assert webui.LIBRARY.trash_items()
    job.status = "done"
    assert call(server, "/api/library/purge", {"id": "../other.mp4"})[0] == 404
    assert call(server, "/api/library/purge", {"id": recovery_id}) == (200, {"ok": True})
    assert not webui.LIBRARY.trash_items()
    assert call(server, "/api/library/restore", {"id": recovery_id})[0] == 404


def test_legacy_fragment_flag_survives_rename_history_removal_and_recovery(server):
    path = webui.ROOT / "video.f400.mp4"
    path.write_bytes(b"unfinished video")
    job = webui.Job("https://example.com/video", {})
    job.status, job.files = "error", [str(path)]
    webui.JOB_MANAGER.add_restored(job)
    assert call(server, "/api/library/rename", {"path": path.name, "name": "renamed.mp4"})[0] == 200
    assert job.view(webui.ROOT)["files"][0]["complete"] is False
    recovery_id = call(server, "/api/library/trash", {"path": "renamed.mp4"})[1]["id"]
    webui.JOB_MANAGER.reset()
    assert call(server, "/api/library/restore", {"id": recovery_id})[0] == 200
    assert webui.list_files(force=True)[0]["complete"] is False


def test_library_metadata_survives_history_removal_and_refresh_detects_external_files(server):
    assert call(server, "/api/state?rev=-1")[1]["files"] == []
    (webui.ROOT / "external.mp4").write_bytes(b"media")
    webui.LIBRARY.remember({"external.mp4": {"source_url": "https://example.com/video", "title": "Original"}})
    webui.JOB_MANAGER.reset()
    files = call(server, "/api/state?rev=-1")[1]["files"]
    assert files[0]["source_url"] == "https://example.com/video" and files[0]["title"] == "Original"


def test_open_source_url_only_accepts_http_urls(server, monkeypatch):
    opened = []
    monkeypatch.setattr(webui.webbrowser, "open", lambda url: opened.append(url) or True)
    assert call(server, "/api/open-url", {"url": "file:///C:/private.txt"})[0] == 400
    assert opened == []
    assert call(server, "/api/open-url", {"url": "https://example.com/video"})[1] == {"ok": True}
    assert opened == ["https://example.com/video"]


# ───────────────────────── Subscriptions ─────────────────────────
def entry(vid, title=""):
    return {"id": vid, "url": f"https://example.com/watch?v={vid}", "title": title or vid}


def test_split_backfill_slices_newest_first():
    entries = [entry("a"), entry("b"), entry("c"), entry("d")]
    to_queue, rest = webui.split_backfill(entries, 2)
    assert [e["id"] for e in to_queue] == ["a", "b"]
    assert [e["id"] for e in rest] == ["c", "d"]


def test_flat_entries_prefer_webpage_urls_and_drop_bare_ids():
    info = {
        "_type": "playlist",
        "entries": [
            {"id": "a", "url": "bare-id", "webpage_url": "https://example.com/watch/a", "title": "A"},
            {"id": "b", "url": "still-a-bare-id", "title": "B"},
            {"id": "c", "url": "https://example.com/watch/c", "title": "C"},
        ],
    }
    entries = webui.normalize_flat_entries(info, "https://example.com/playlist")
    assert [(item["id"], item["url"]) for item in entries] == [
        ("a", "https://example.com/watch/a"),
        ("c", "https://example.com/watch/c"),
    ]


def test_split_backfill_zero_queues_nothing():
    to_queue, rest = webui.split_backfill([entry("a"), entry("b")], 0)
    assert to_queue == [] and len(rest) == 2


def test_subscription_from_dict_rejects_bad_ids_and_urls():
    good = {"id": "abcd1234", "url": "https://example.com/c"}
    assert webui.Subscription.from_dict(good) is not None
    assert webui.Subscription.from_dict({**good, "id": "../x"}) is None
    assert webui.Subscription.from_dict({**good, "url": "file:///etc/passwd"}) is None


def test_subscription_from_dict_tolerates_corrupted_optional_fields():
    sub = webui.Subscription.from_dict({
        "id": "abcd1234",
        "url": "https://example.com/c",
        "backfill_count": "not-a-number",
        "seen_ids": "not-a-list",
    })
    assert sub is not None
    assert sub.backfill_count == 5 and sub.seen_ids == set()


def test_subscription_round_trips_through_to_dict_and_from_dict():
    sub = webui.Subscription("https://example.com/c", {"mode": "mp3"}, backfill="recent", backfill_count=3)
    sub.seen_ids = {"a", "b"}
    sub.initialized = True
    sub.total_queued = 2
    sub.last_error_kind = "network"
    restored = webui.Subscription.from_dict(sub.to_dict())
    assert restored.id == sub.id and restored.seen_ids == {"a", "b"}
    assert restored.initialized and restored.backfill == "recent" and restored.backfill_count == 3
    assert restored.total_queued == 2
    assert restored.last_error_kind == "network"
    assert restored.view(300, False)["last_error_kind"] == "network"


def test_backfill_count_is_clamped_on_construction():
    assert webui.Subscription("https://example.com/c", {}, backfill_count=0).backfill_count == 1
    assert webui.Subscription("https://example.com/c", {}, backfill_count=9999).backfill_count == webui.BACKFILL_MAX


def test_subscription_filters_are_normalized_and_round_trip():
    sub = webui.Subscription("https://example.com/c", {}, filters={
        "include_keywords": "Cat, cat, Dog",
        "exclude_keywords": ["spoiler"],
        "exclude_live": True,
        "min_duration": 600,
        "max_duration": 60,
    })
    assert sub.filters["include_keywords"] == ["Cat", "Dog"]
    assert (sub.filters["min_duration"], sub.filters["max_duration"]) == (60, 600)
    restored = webui.Subscription.from_dict(sub.to_dict())
    assert restored.filters == sub.filters


def test_subscription_filter_matches_title_kind_and_duration():
    entries = [
        {**entry("a", "Weekly cat"), "duration": 120, "is_live": False, "is_short": False},
        {**entry("b", "Weekly dog"), "duration": 120, "is_live": False, "is_short": False},
        {**entry("c", "Cat livestream"), "duration": None, "is_live": True, "is_short": False},
        {**entry("d", "Cat clip"), "duration": 20, "is_live": False, "is_short": True},
    ]
    accepted, skipped = webui.filter_subscription_entries(entries, {
        "include_keywords": ["cat"], "exclude_live": True, "exclude_shorts": True, "min_duration": 60,
    })
    assert [item["id"] for item in accepted] == ["a"]
    assert [item["id"] for item in skipped] == ["b", "c", "d"]


def test_preview_subscription_is_read_only_and_explains_filter_reason(monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: (
        "Channel", [entry("a", "Cat tutorial"), entry("b", "Dog tutorial")],
    ))
    sub = webui.Subscription("https://example.com/c", {}, backfill="recent", backfill_count=2)
    before = sub.to_dict()
    preview = webui.preview_subscription(sub, {"include_keywords": ["cat"]})
    assert preview["total_candidates"] == 2
    assert (preview["would_queue"], preview["filtered"]) == (1, 1)
    assert [(item["eligible"], item["reason"]) for item in preview["items"]] == [
        (True, None), (True, "include_keywords"),
    ]
    assert sub.to_dict() == before and len(webui.JOBS) == 0


def test_preview_without_backfill_shows_baseline_without_queuing(monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", [entry("a")]))
    sub = webui.Subscription("https://example.com/c", {}, backfill="none")
    preview = webui.preview_subscription(sub, {})
    assert preview["total_candidates"] == 0
    assert (preview["would_queue"], preview["filtered"]) == (0, 0)
    assert preview["items"][0]["eligible"] is False


def test_filtered_new_subscription_items_are_seen_but_not_queued(monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: (
        "", [{**entry("a", "Keep this"), "duration": 90, "is_live": False, "is_short": False},
             {**entry("b", "Skip this"), "duration": 90, "is_live": False, "is_short": False}],
    ))
    sub = webui.Subscription(
        "https://example.com/c", {}, backfill="recent", backfill_count=2,
        filters={"include_keywords": ["keep"]},
    )
    webui.check_subscription(sub)
    assert sub.seen_ids == {"a", "b"}
    assert sub.total_queued == 1 and sub.total_filtered == 1
    assert [job.url for job in webui.JOBS.values()] == ["https://example.com/watch?v=a"]


def test_first_check_with_no_backfill_only_records_a_baseline(monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("My Channel", [entry("a"), entry("b")]))
    sub = webui.Subscription("https://example.com/c", {}, backfill="none")
    webui.check_subscription(sub)
    assert sub.title == "My Channel" and sub.initialized and sub.seen_ids == {"a", "b"}
    assert sub.total_queued == 0 and sub.last_error == "" and sub.last_checked > 0
    assert len(webui.JOBS) == 0


def test_first_check_with_backfill_queues_only_the_requested_count(monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries",
                        lambda url, args: ("", [entry("a"), entry("b"), entry("c")]))
    sub = webui.Subscription("https://example.com/c", {}, backfill="recent", backfill_count=2)
    webui.check_subscription(sub)
    assert sub.total_queued == 2 and sub.seen_ids == {"a", "b", "c"}
    queued_urls = {j.url for j in webui.JOBS.values()}
    assert queued_urls == {"https://example.com/watch?v=a", "https://example.com/watch?v=b"}
    assert all(j.source == sub.id for j in webui.JOBS.values())


def test_later_check_only_queues_ids_not_seen_before(monkeypatch):
    sub = webui.Subscription("https://example.com/c", {}, backfill="none")
    sub.initialized = True
    sub.seen_ids = {"a", "b"}
    monkeypatch.setattr(webui, "list_flat_entries",
                        lambda url, args: ("", [entry("a"), entry("b"), entry("c")]))
    webui.check_subscription(sub)
    assert sub.seen_ids == {"a", "b", "c"} and sub.total_queued == 1
    assert [j.url for j in webui.JOBS.values()] == ["https://example.com/watch?v=c"]


def test_a_failed_check_records_the_error_without_crashing(monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: (_ for _ in ()).throw(RuntimeError("boom")))
    sub = webui.Subscription("https://example.com/c", {})
    webui.check_subscription(sub)
    assert "boom" in sub.last_error and not sub.initialized and sub.last_checked > 0
    assert sub.last_error_kind == "unknown"


def test_check_subscription_is_reentrant_safe(monkeypatch):
    """A check already in progress for a subscription is skipped, not run twice."""
    calls = []
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: (calls.append(1), ("", []))[1])
    sub = webui.Subscription("https://example.com/c", {})
    webui._CHECKING.add(sub.id)
    webui.check_subscription(sub)
    assert calls == []  # skipped entirely
    webui._CHECKING.discard(sub.id)


def test_concurrent_subscription_checks_only_run_once(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def slow_list(url, args):
        calls.append(1)
        entered.set()
        assert release.wait(1.0)
        return "", []

    monkeypatch.setattr(webui, "list_flat_entries", slow_list)
    sub = webui.Subscription("https://example.com/c", {})
    first = threading.Thread(target=webui.check_subscription, args=(sub,))
    first.start()
    assert entered.wait(1.0)
    second = threading.Thread(target=webui.check_subscription, args=(sub,))
    second.start()
    second.join(1.0)
    release.set()
    first.join(1.0)
    assert not first.is_alive() and not second.is_alive()
    assert calls == [1]


def test_subscriptions_persist_across_a_save_and_load_cycle():
    sub = webui.Subscription("https://example.com/c", {"mode": "mp3"}, backfill="recent", backfill_count=4)
    sub.seen_ids = {"x", "y"}
    webui.SUBS[sub.id] = sub
    webui.save_subscriptions()
    webui.SUBS.clear()
    webui.load_subscriptions()
    assert sub.id in webui.SUBS and webui.SUBS[sub.id].seen_ids == {"x", "y"}


def test_job_records_the_subscription_that_queued_it_and_it_survives_history_reload():
    job = webui.Job("https://example.com/v", {})
    job.source = "abcd1234"
    restored = webui.Job.from_dict(job.to_dict(webui.ROOT) | {"status": "done"}, webui.ROOT)
    assert restored.source == "abcd1234"
    assert job.view(webui.ROOT)["source"] == "abcd1234"


# ── HTTP endpoints ──
def test_add_subscription_validates_the_url(server):
    assert call(server, "/api/subscriptions", {"url": "not a url"})[0] == 400


def test_add_subscription_ignores_options_that_are_not_an_object(server, monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", []))
    status, view = call(server, "/api/subscriptions", {
        "url": "https://example.com/c",
        "options": "mp3",
    })
    assert status == 200 and view["options"] == {}


def test_add_subscription_starts_an_immediate_background_check(server, monkeypatch):
    checked = threading.Event()

    def list_entries(url, args):
        checked.set()
        return "Channel Name", [entry("a")]

    monkeypatch.setattr(webui, "list_flat_entries", list_entries)
    status, sub = call(server, "/api/subscriptions", {"url": "https://example.com/c", "backfill": "none"})
    assert status == 200 and sub["id"] in webui.SUBS
    assert checked.wait(1.0)
    for _ in range(100):
        if not webui.SUBSCRIPTION_MANAGER.is_checking(sub["id"]):
            break
        threading.Event().wait(0.01)
    assert not webui.SUBSCRIPTION_MANAGER.is_checking(sub["id"])


def test_add_subscription_does_not_wait_for_a_slow_remote_check(server, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def slow_list(url, args):
        entered.set()
        assert release.wait(1.0)
        return "", []

    monkeypatch.setattr(webui, "list_flat_entries", slow_list)
    status, sub = call(server, "/api/subscriptions", {"url": "https://example.com/c"})
    assert status == 200 and sub["id"] in webui.SUBS
    assert entered.wait(1.0)
    release.set()
    for _ in range(100):
        if not webui.SUBSCRIPTION_MANAGER.is_checking(sub["id"]):
            break
        threading.Event().wait(0.01)
    assert not webui.SUBSCRIPTION_MANAGER.is_checking(sub["id"])


def test_update_subscription_toggles_enabled_and_clamps_backfill_count(server, monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", []))
    sub_id = call(server, "/api/subscriptions", {"url": "https://example.com/c"})[1]["id"]
    status, updated = call(server, f"/api/subscriptions/{sub_id}/update", {"enabled": False, "backfill_count": 9999})
    assert status == 200 and updated["enabled"] is False
    assert webui.SUBS[sub_id].backfill_count == webui.BACKFILL_MAX


def test_add_and_update_subscription_filters(server, monkeypatch):
    monkeypatch.setattr(webui, "start_subscription_check", lambda sub: None)
    status, created = call(server, "/api/subscriptions", {
        "url": "https://example.com/c",
        "filters": {"include_keywords": "cat, dog", "exclude_live": True, "min_duration": 120},
    })
    assert status == 200
    assert created["filters"]["include_keywords"] == ["cat", "dog"]
    status, updated = call(server, f"/api/subscriptions/{created['id']}/update", {
        "filters": {"exclude_keywords": ["trailer"], "max_duration": 3600},
    })
    assert status == 200
    assert updated["filters"]["exclude_keywords"] == ["trailer"]
    assert updated["filters"]["max_duration"] == 3600


def test_update_subscription_rejects_non_object_filters(server, monkeypatch):
    monkeypatch.setattr(webui, "start_subscription_check", lambda sub: None)
    sub_id = call(server, "/api/subscriptions", {"url": "https://example.com/c"})[1]["id"]
    assert call(server, f"/api/subscriptions/{sub_id}/update", {"filters": "all"})[0] == 400


def test_subscription_preview_endpoint_does_not_save_or_enqueue(server, monkeypatch):
    monkeypatch.setattr(webui, "start_subscription_check", lambda sub: None)
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("Channel", [entry("a", "Cat")]))
    sub_id = call(server, "/api/subscriptions", {
        "url": "https://example.com/c", "backfill": "recent", "backfill_count": 1,
    })[1]["id"]
    before = webui.SUBS[sub_id].to_dict()
    status, preview = call(server, f"/api/subscriptions/{sub_id}/preview", {"filters": {"exclude_keywords": ["Cat"]}})
    assert status == 200 and preview["items"][0]["reason"] == "exclude_keywords"
    assert webui.SUBS[sub_id].to_dict() == before and not webui.JOBS


def test_update_subscription_rejects_non_boolean_enabled(server, monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", []))
    sub_id = call(server, "/api/subscriptions", {"url": "https://example.com/c"})[1]["id"]
    status, _ = call(server, f"/api/subscriptions/{sub_id}/update", {"enabled": "false"})
    assert status == 400
    assert webui.SUBS[sub_id].enabled is True


def test_check_now_runs_in_the_background_without_blocking_the_request(server, monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", []))
    sub_id = call(server, "/api/subscriptions", {"url": "https://example.com/c"})[1]["id"]
    started = threading.Event()

    def slow_list(url, args):
        started.set()
        threading.Event().wait(0.3)
        return "", []

    monkeypatch.setattr(webui, "list_flat_entries", slow_list)
    status, _ = call(server, f"/api/subscriptions/{sub_id}/check-now", {})
    assert status == 200
    assert started.wait(1.0)


def test_remove_subscription(server, monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", []))
    sub_id = call(server, "/api/subscriptions", {"url": "https://example.com/c"})[1]["id"]
    assert call(server, f"/api/subscriptions/{sub_id}/remove", {})[0] == 200
    assert sub_id not in webui.SUBS


def test_removing_a_subscription_while_it_is_checking_prevents_new_jobs(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    sub = webui.Subscription("https://example.com/c", {}, backfill="recent", backfill_count=1)
    webui.SUBSCRIPTION_MANAGER.add(sub)

    def slow_list(url, args):
        entered.set()
        assert release.wait(1.0)
        return "", [entry("new")]

    monkeypatch.setattr(webui, "list_flat_entries", slow_list)
    check = threading.Thread(target=webui.check_subscription, args=(sub,))
    check.start()
    assert entered.wait(1.0)
    assert webui.SUBSCRIPTION_MANAGER.remove(sub.id)
    release.set()
    check.join(1.0)
    assert not check.is_alive()
    assert webui.JOB_MANAGER.snapshot() == []


def test_actions_on_an_unknown_subscription_id_return_404(server):
    assert call(server, "/api/subscriptions/deadbeef/check-now", {})[0] == 404


def test_list_subscriptions_endpoint(server, monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("Chan", []))
    call(server, "/api/subscriptions", {"url": "https://example.com/c"})
    deadline = time.monotonic() + 2
    while True:
        status, data = call(server, "/api/subscriptions")
        if data["subscriptions"][0]["last_checked"] or time.monotonic() >= deadline:
            break
        threading.Event().wait(0.01)
    assert status == 200 and len(data["subscriptions"]) == 1 and data["subscriptions"][0]["title"] == "Chan"


# ── editing a subscription's download settings ──
def test_subscription_view_includes_the_full_settings(server, monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", []))
    opts = {"mode": "mp3", "abr": 320, "subs": True, "proxy": "http://127.0.0.1:7890"}
    view = call(server, "/api/subscriptions", {"url": "https://example.com/c", "options": opts})[1]
    assert view["options"] == opts and view["mode"] == "mp3"
    listed = call(server, "/api/subscriptions")[1]["subscriptions"][0]
    assert listed["options"] == opts


def test_updating_options_replaces_the_whole_settings_object_and_persists(server, monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", []))
    sub_id = call(server, "/api/subscriptions", {"url": "https://example.com/c", "options": {"mode": "mp4", "quality": "1080"}})[1]["id"]
    new = {"mode": "mp3", "abr": 128}
    status, view = call(server, f"/api/subscriptions/{sub_id}/update", {"options": new})
    assert status == 200 and view["options"] == new and view["mode"] == "mp3"
    # survives a restart
    webui.SUBS.clear()
    webui.load_subscriptions()
    assert webui.SUBS[sub_id].options == new


def test_an_options_update_that_is_not_an_object_is_ignored(server, monkeypatch):
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", []))
    sub_id = call(server, "/api/subscriptions", {"url": "https://example.com/c", "options": {"mode": "mp4"}})[1]["id"]
    call(server, f"/api/subscriptions/{sub_id}/update", {"options": "mp3"})
    assert webui.SUBS[sub_id].options == {"mode": "mp4"}


def test_videos_queued_after_an_edit_use_the_new_settings_but_earlier_jobs_keep_theirs(server, monkeypatch):
    sub = webui.Subscription("https://example.com/c", {"mode": "mp4", "quality": "1080"}, backfill="recent", backfill_count=1)
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", [entry("a")]))
    webui.check_subscription(sub)                                 # first check backfills video "a" with the old settings
    webui.SUBS[sub.id] = sub
    call(server, f"/api/subscriptions/{sub.id}/update", {"options": {"mode": "mp3", "abr": 128}})
    monkeypatch.setattr(webui, "list_flat_entries", lambda url, args: ("", [entry("b"), entry("a")]))
    webui.check_subscription(sub)                                 # a new video "b" appears
    by_url = {j.url: j.options for j in webui.JOBS.values()}
    assert by_url["https://example.com/watch?v=a"] == {"mode": "mp4", "quality": "1080"}
    assert by_url["https://example.com/watch?v=b"] == {"mode": "mp3", "abr": 128}


# ── an incomplete webui_dist must be reported, not silently ignored ──
def make_dist(root, *, index=True, assets=("index-abc.js", "index-abc.css")):
    root.mkdir(parents=True, exist_ok=True)
    if index:
        (root / "index.html").write_text(
            '<html><head><script type="module" src="/assets/index-abc.js"></script>'
            '<link rel="stylesheet" href="/assets/index-abc.css"></head></html>', encoding="utf-8")
    (root / "assets").mkdir(exist_ok=True)
    for name in assets:
        (root / "assets" / name).write_text("x", encoding="utf-8")
    return root


def test_check_dist_accepts_a_complete_build(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "UI_DIST", make_dist(tmp_path / "webui_dist"))
    assert webui.check_dist() == (True, "")


def test_check_dist_reports_a_missing_index(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "UI_DIST", make_dist(tmp_path / "webui_dist", index=False))
    ok, why = webui.check_dist()
    assert not ok and "index.html" in why


def test_check_dist_names_the_asset_that_is_in_the_wrong_place(tmp_path, monkeypatch):
    """The real mistake: the .js file ended up beside grab.py instead of inside webui_dist/assets/."""
    monkeypatch.setattr(webui, "UI_DIST", make_dist(tmp_path / "webui_dist", assets=("index-abc.css",)))
    ok, why = webui.check_dist()
    assert not ok and "webui_dist/assets/index-abc.js" in why and "index-abc.css" not in why


def test_diagnostics_warn_when_the_interface_files_are_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "UI_DIST", make_dist(tmp_path / "webui_dist", assets=()))
    item = {c["id"]: c for c in webui.collect_doctor(force=True)["checks"]}["interface"]
    assert item["status"] == "warn" and "assets" in item["detail"]


def test_diagnostics_are_happy_when_the_interface_files_are_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(webui, "UI_DIST", make_dist(tmp_path / "webui_dist"))
    assert {c["id"]: c for c in webui.collect_doctor(force=True)["checks"]}["interface"]["status"] == "ok"
