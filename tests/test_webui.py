import json
import os
import re
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
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
    webui.JOBS.clear()
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
    r = subprocess.run(["node", "--check", "-"], input=js, capture_output=True, text=True)
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
    job = webui.Job.from_dict(good)
    assert job and job.files == []
    assert webui.Job.from_dict({**good, "id": "../../x"}) is None
    assert webui.Job.from_dict({**good, "url": "file:///etc/passwd"}) is None


def test_interrupted_jobs_come_back_as_retryable():
    job = webui.Job.from_dict({"id": "abcd1234", "url": "https://example.com/v", "status": "running"})
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
    assert webui.Job.from_dict(job.to_dict() | {"status": "done"}).notes == job.notes


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
    assert FakeProc.cmd[-1] == f"yt-dlp[{extras}]" and FakeProc.cmd[1:3] == ["-m", "pip"]
    assert webui.UPDATE["status"] == "done"


def test_update_is_refused_while_jobs_are_active():
    job = webui.Job("https://example.com/v", {})
    webui.JOBS[job.id] = job                                # queued
    ok, why = webui.start_update()
    assert not ok and "queued or downloading" in why


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
