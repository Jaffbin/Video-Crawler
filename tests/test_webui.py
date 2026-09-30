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


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own download folder, settings folder and empty job list."""
    root = (tmp_path / "dl").resolve()
    root.mkdir()
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(webui, "PORT", 0)
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

    def start(**kwargs):
        seen["start"] = kwargs

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


def test_native_window_failure_keeps_browser_fallback(monkeypatch, tmp_path):
    fake = types.SimpleNamespace(
        settings={},
        create_window=lambda *args, **kwargs: None,
        start=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("WebView2 unavailable")),
    )
    monkeypatch.setitem(sys.modules, "webview", fake)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path)
    assert webui.open_native_window("http://127.0.0.1:8765/") is False


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


def test_interrupted_jobs_come_back_as_retryable():
    job = webui.Job.from_dict(
        {"id": "abcd1234", "url": "https://example.com/v", "status": "running"},
        webui.ROOT,
    )
    assert job.status == "canceled" and job.stage == "Last incomplete" and "Retry" in job.error


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
