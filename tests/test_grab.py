import argparse
import os
import shutil
import sys
from pathlib import Path

import pytest

import grab
from conftest import HAVE_FFMPEG


def args_for(tmp_path, **kw):
    a = grab.parse_args([])
    a.output = str(tmp_path)
    for k, v in kw.items():
        setattr(a, k, v)
    return a


# ── classifying network responses (used by --js-render) ──
@pytest.mark.parametrize("url,ctype,expected", [
    ("https://cdn.example/a/master.m3u8?token=1", "", (True, True)),
    ("https://cdn.example/a/stream.mpd", "", (True, True)),
    ("https://cdn.example/x", "application/vnd.apple.mpegurl", (True, True)),
    ("https://cdn.example/x", "application/dash+xml", (True, True)),
    ("https://cdn.example/video.mp4", "video/mp4", (True, False)),
    ("https://cdn.example/audio", "audio/mpeg", (True, False)),
    ("https://cdn.example/seg-1.ts", "video/mp2t", (False, False)),   # a fragment cannot be downloaded alone
    ("https://cdn.example/seg-1.m4s", "video/mp4", (False, False)),
    ("https://cdn.example/app.js", "application/javascript", (False, False)),
    ("blob:https://example.com/123", "", (False, False)),
    ("data:video/mp4;base64,AAAA", "", (False, False)),
])
def test_classify_media(url, ctype, expected):
    assert grab.classify_media(url, ctype) == expected


# ── options ──
def test_quality_type():
    assert grab.quality_type("1080p") == "1080"
    assert grab.quality_type("BEST") == "best"
    with pytest.raises(argparse.ArgumentTypeError):
        grab.quality_type("hd")


def test_video_format_caps_height_but_accepts_unknown_heights():
    fmt = grab.video_format("720")
    assert "height<=?720" in fmt and fmt.endswith("/b")
    assert grab.video_format("best").startswith("bv*[ext=mp4]+ba[ext=m4a]")


def test_build_opts_mp3_and_subtitles(tmp_path):
    a = args_for(tmp_path, mode="mp3", subs=True, embed_subs=True, cover=True, abr=320)
    o = grab.build_opts(a)
    keys = [p["key"] for p in o["postprocessors"]]
    assert "FFmpegExtractAudio" in keys and "EmbedThumbnail" in keys
    assert o["postprocessors"][keys.index("FFmpegExtractAudio")]["preferredquality"] == "320"
    assert o["writesubtitles"] and o["writethumbnail"]


# ── JavaScript runtime detection (YouTube) ──
def test_find_deno_prefers_path(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/opt/bin/deno" if name == "deno" else None)
    assert grab.find_deno() == "/opt/bin/deno"
    assert grab.js_runtime_opts() == {"js_runtimes": {"deno": {"path": "/opt/bin/deno"}}}


def test_find_deno_next_to_python_when_not_on_path(monkeypatch, tmp_path):
    exe = "deno.exe" if os.name == "nt" else "deno"
    (tmp_path / exe).write_text("")
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    assert grab.find_deno() == str(tmp_path / exe)


def test_no_deno_means_no_js_runtime_option(monkeypatch):
    monkeypatch.setattr(grab, "find_deno", lambda: None)
    assert grab.js_runtime_opts() == {}


# ── diagnostics ──
def test_diagnostics_flags_missing_ffmpeg_and_deno(monkeypatch, tmp_path):
    real_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda n, *a, **k: None if n in ("ffmpeg", "ffprobe", "deno") else real_which(n))
    monkeypatch.setattr(grab, "find_deno", lambda: None)
    by_id = {c["id"]: c for c in grab.run_diagnostics(tmp_path)}
    assert by_id["ffmpeg"]["status"] == "error"
    assert by_id["js_runtime"]["status"] == "warn"
    assert by_id["js_runtime"]["action"] == "install_components"
    assert "yt-dlp[default,deno]" in by_id["js_runtime"]["fix"]
    assert by_id["output_dir"]["status"] in ("ok", "warn")


def test_diagnostics_when_everything_is_present(monkeypatch, tmp_path):
    monkeypatch.setattr(grab, "find_deno", lambda: "/usr/bin/deno")
    monkeypatch.setattr(grab, "_first_line_of", lambda cmd, timeout=6.0: "deno 2.6.6")
    monkeypatch.setattr(grab.importlib.util, "find_spec", lambda name: object() if name == "yt_dlp_ejs" else None)
    by_id = {c["id"]: c for c in grab.run_diagnostics(tmp_path)}
    assert by_id["js_runtime"]["status"] == "ok"
    assert by_id["ejs"]["status"] == "ok"


def test_ejs_missing_with_deno_offers_the_smaller_fix(monkeypatch, tmp_path):
    monkeypatch.setattr(grab, "find_deno", lambda: "/usr/bin/deno")
    monkeypatch.setattr(grab.importlib.util, "find_spec", lambda name: None)
    ejs = {c["id"]: c for c in grab.run_diagnostics(tmp_path)}["ejs"]
    assert ejs["status"] == "warn" and ejs["action"] == "install_default"
    assert 'yt-dlp[default]"' in ejs["fix"]


def test_diagnostics_reports_unwritable_output_folder(tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    by_id = {c["id"]: c for c in grab.run_diagnostics(blocker / "sub")}
    assert by_id["output_dir"]["status"] == "error"


def test_report_masks_home_and_proxy_credentials():
    checks = [grab.check_item("proxy", "Proxy", "info", "http=http://user:secret@127.0.0.1:7890"),
              grab.check_item("output_dir", "Folder", "ok", f"{Path.home()}/Videos")]
    text = grab.format_report(checks, [("Recent failure 1", ["https://example.com/watch?v=1"])])
    assert "secret" not in text and "***:***@127.0.0.1" in text
    assert str(Path.home()) not in text and "~/Videos" in text
    assert "Recent failure 1:" in text and "[INFO]" in text and "[OK]" in text


def test_doctor_cli_exit_code(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(grab, "run_diagnostics", lambda *a, **k: [grab.check_item("x", "X", "error", "boom")])
    assert grab.doctor_cli(args_for(tmp_path, net=False)) == 1
    monkeypatch.setattr(grab, "run_diagnostics", lambda *a, **k: [grab.check_item("x", "X", "warn", "meh")])
    assert grab.doctor_cli(args_for(tmp_path, net=False)) == 0


# ── discover_and_download: order of attempts, without any network ──
def test_discover_falls_back_from_scan_to_render(monkeypatch, tmp_path):
    monkeypatch.setattr(grab, "has_specific_extractor", lambda u: False)
    monkeypatch.setattr(grab, "sniff_media_urls", lambda u, log=print, proxy=None: ("Page", ["http://a/1.mp4"]))
    monkeypatch.setattr(grab, "render_media_urls",
                        lambda *a, **k: ("Page", ["http://a/1.mp4", "http://a/master.m3u8"]))
    tried = []

    def download_one(url, referer=None, name=None):
        tried.append(url)
        return url.endswith(".m3u8")

    a = args_for(tmp_path, js_render=True, list_formats=False, no_sniff=False, all_sniffed=False)
    assert grab.discover_and_download("http://page", a, download_one, log=lambda m: None)
    # the page URL, then the scanned candidate, then only the NEW candidate from the browser
    assert tried == ["http://page", "http://a/1.mp4", "http://a/master.m3u8"]


def test_discover_without_js_render_gives_a_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(grab, "has_specific_extractor", lambda u: False)
    monkeypatch.setattr(grab, "sniff_media_urls", lambda u, log=print, proxy=None: ("", []))
    logs = []
    a = args_for(tmp_path, js_render=False, list_formats=False, no_sniff=False, all_sniffed=False)
    assert not grab.discover_and_download("http://page", a, lambda *x, **k: False, log=logs.append)
    assert any("--js-render" in m for m in logs)


# ── MP3 work directory: must never touch a same-named MP4 ──
def test_finish_work_moves_only_finished_files(tmp_path):
    a = args_for(tmp_path, mode="mp3", list_formats=False)
    (tmp_path / "clip.mp4").write_bytes(b"original mp4")
    work = grab.begin_work(a)
    (work / "clip.mp4").write_bytes(b"intermediate")     # would clobber the original if moved
    (work / "clip.mp3").write_bytes(b"mp3")
    (work / "clip.en.srt").write_text("sub")
    moved = grab.finish_work(work, a)
    assert (tmp_path / "clip.mp3").read_bytes() == b"mp3"
    assert (tmp_path / "clip.en.srt").exists()
    assert (tmp_path / "clip.mp4").read_bytes() == b"original mp4"
    assert not (tmp_path / ".work").exists()
    assert set(Path(v).name for v in moved.values()) == {"clip.mp3", "clip.en.srt"}


def test_begin_work_only_for_mp3(tmp_path):
    assert grab.begin_work(args_for(tmp_path, mode="mp4", list_formats=False)) is None


# ── end to end against the local site (needs ffmpeg) ──
@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg is not installed")
def test_direct_link_mp4_then_mp3_keeps_both(media_site, tmp_path):
    url = media_site["base"] + "/clip.mp4"
    assert grab.attempt(url, args_for(tmp_path, mode="mp4", list_formats=False))
    assert grab.attempt(url, args_for(tmp_path, mode="mp3", list_formats=False))
    names = sorted(p.name for p in tmp_path.iterdir() if not p.name.startswith("."))
    assert names == ["clip [clip].mp3", "clip [clip].mp4"]


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg is not installed")
def test_sniff_finds_media_urls_in_page_source(media_site):
    title, urls = grab.sniff_media_urls(media_site["base"] + "/page.html", lambda m: None)
    assert title == "Test Page"
    assert urls[0].endswith(".m3u8")            # manifests first
    assert any(u.endswith("clip.mp4") for u in urls)


# ── proxies: page fetching goes through yt-dlp's networking, so socks works and system settings are used ──
def test_fetch_page_through_an_http_proxy_from_the_environment(monkeypatch, http_proxy):
    proxy_url, seen = http_proxy
    monkeypatch.setenv("http_proxy", proxy_url)
    ctype, body, charset = grab.fetch_page("http://proxied.example/watch")
    assert ctype == "text/html" and b"Proxied page" in body and charset == "utf-8"
    assert seen == ["http://proxied.example/watch"]           # the proxy saw the full URL, so it really was used


def test_fetch_page_through_a_socks5_proxy(socks5_proxy):
    proxy_url, seen = socks5_proxy
    _, body, _ = grab.fetch_page("http://socks-target.example/page.html", proxy=proxy_url)
    assert b"Proxied page" in body
    assert seen and seen[0][0] == "socks-target.example"       # socks5h: the host name is resolved by the proxy


def test_sniff_reports_a_readable_error_when_the_page_cannot_be_fetched():
    logs = []
    assert grab.sniff_media_urls("http://127.0.0.1:9/nothing", logs.append) == ("", [])
    assert logs and logs[0].startswith("[Scan] Cannot fetch page")


def test_system_proxy_is_used_when_none_is_given(monkeypatch):
    monkeypatch.setattr(grab.urllib.request, "getproxies", lambda: {"http": "http://h:1", "https": "http://h:2"})
    assert grab._system_proxy() == "http://h:2"
    monkeypatch.setattr(grab.urllib.request, "getproxies", lambda: {})
    assert grab._system_proxy() is None


@pytest.mark.parametrize("proxy,expected", [
    ("http://127.0.0.1:7890", {"server": "http://127.0.0.1:7890"}),
    ("127.0.0.1:7890", {"server": "http://127.0.0.1:7890"}),
    ("socks5h://user:p%40ss@10.0.0.1:1080", {"server": "socks5://10.0.0.1:1080", "username": "user", "password": "p@ss"}),
    ("ftp://x:1", None), ("", None), (None, None),
])
def test_playwright_proxy_puts_credentials_in_their_own_fields(proxy, expected):
    assert grab._playwright_proxy(proxy) == expected


def test_report_timestamp_is_plain_ascii():
    """%Z prints a localised time zone name on Windows, which showed up as ???? in a real report."""
    first = grab.format_report([]).splitlines()[1]
    assert first.isascii() and __import__("re").fullmatch(r"Generated \d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", first)


def test_console_encoding_problems_do_not_crash(monkeypatch, capsys):
    class Narrow:
        def __init__(self):
            self.errors = "strict"

        def reconfigure(self, errors):
            self.errors = errors

    fake_out, fake_err = Narrow(), Narrow()
    monkeypatch.setattr(sys, "stdout", fake_out)
    monkeypatch.setattr(sys, "stderr", fake_err)
    grab._safe_console()
    assert fake_out.errors == fake_err.errors == "replace"
