"""
webui.py - a local web interface for grab.py

Usage
  python webui.py                                   # opens in its own window; downloads to ./downloads
  python webui.py --ui browser                       # open in your default browser tab instead
  python webui.py --dir D:/videos --port 8765 --workers 2

Notes
  * Listens on 127.0.0.1 only. Requests need a random token created at startup and the Host
    header is checked, so other web pages cannot drive this program through your browser.
  * Needs grab.py in the same folder, plus:  pip install -U "yt-dlp[default]"  and ffmpeg.
    YouTube also needs a JavaScript runtime (Deno). Open "Diagnostics" in the page to check.
  * Uploaded cookies.txt is stored outside the download folder (see "Diagnostics" for the path)
    and is never served back to the browser.
  * The interface is the React app built into webui_dist/ (see frontend/README.md to rebuild it).
    --ui window needs the optional pywebview package; without it, this falls back to your browser.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import hmac
import importlib.metadata
import importlib.util
import json
import mimetypes
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grab  # noqa: E402
import yt_dlp  # noqa: E402
from yt_dlp.utils import DownloadCancelled, DownloadError  # noqa: E402

ROOT = Path("downloads").resolve()
TOKEN = secrets.token_urlsafe(24)
BROWSERS = {"chrome", "edge", "firefox", "brave", "chromium", "opera", "vivaldi", "safari"}
# The React app, built by `npm run build` in frontend/ (see frontend/README.md). Shipped pre-built,
# so running the backend never requires Node. Falls back to the legacy inline page if missing.
UI_DIST = Path(__file__).resolve().parent / "webui_dist"
ALLOWED_STATIC_EXT = {".js", ".css", ".svg", ".png", ".ico", ".woff", ".woff2", ".map", ".json", ".webmanifest", ".txt"}
WINDOW_MODE = False  # set from main(): running inside a pywebview window rather than a browser tab
MEDIA_SUFFIX = {".mp4", ".mp3", ".m4a", ".webm", ".mkv", ".mov", ".aac", ".flac", ".ogg", ".opus"}
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

JOBS: dict[str, "Job"] = {}
JOBS_LOCK = threading.Lock()
QUEUE: "queue.Queue[Job]" = queue.Queue()
FILES_REV = 0
PORT = 0
WORKERS = 2
UI_MODE = "browser"
HISTORY_MAX = 500
_SAVE_LOCK = threading.Lock()
FILES_CACHE: dict = {"rev": None, "ts": 0.0, "data": []}
UPDATE: dict = {"status": "idle", "lines": [], "before": "", "after": "", "error": "", "extras": ""}
UPDATE_LOCK = threading.Lock()
PYPI_CACHE: dict = {"ts": 0.0, "latest": None}
# Settings that must not live in the (possibly synced or shared) download folder, e.g. cookies.txt
CONFIG_DIR = Path(os.environ.get("GRAB_CONFIG_DIR") or (Path(os.environ.get("APPDATA") or (Path.home() / ".config")) / "grab-webui"))
DOCTOR_CACHE: dict = {"ts": 0.0, "data": None}
COOKIES_MAX_BYTES = 3_000_000
BODY_MAX_BYTES = 1_000_000

# Warnings from yt-dlp that deserve a visible note on the job (matched on the lower-cased log line)
NOTE_RULES = [
    (("javascript runtime", "challenge solving failed", "signature solving failed"), "js",
     "YouTube challenge solving failed, so some formats may be missing. Install Deno and yt-dlp-ejs from the Diagnostics panel."),
    (("cookies are no longer valid", "likely been rotated"), "rotated",
     "YouTube rotated or expired your cookies. Export a fresh cookies.txt from a private window and upload it again."),
]

PP_LABEL = {
    "Merger": "Merge audio/video",
    "FFmpegMerger": "Merge audio/video",
    "FFmpegExtractAudio": "Convert to MP3",
    "FFmpegVideoRemuxer": "Remux video",
    "FFmpegEmbedSubtitle": "Embed subtitles",
    "FFmpegSubtitlesConvertor": "Convert subtitles",
    "EmbedThumbnail": "Embed cover art",
    "FFmpegThumbnailsConvertor": "Convert thumbnails",
    "FFmpegMetadata": "Write metadata",
    "MoveFiles": "Organize files",
}


def bump_rev() -> None:
    global FILES_REV
    FILES_REV += 1


# ───────────────────────── Tools ─────────────────────────
def strip_ansi(s: str) -> str:
    return ANSI.sub("", s or "")


def fmt_speed(v) -> str:
    if not v:
        return ""
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if v < 1024:
            return f"{v:.0f} {unit}" if unit == "B/s" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB/s"


def fmt_eta(s) -> str:
    if s is None:
        return ""
    s = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def friendly_error(msg: str) -> str:
    m = re.sub(r"^ERROR:\s*", "", strip_ansi(msg or "").strip())
    # yt-dlp appends "; please report this issue ... Confirm you are on the latest version" to unexpected errors.
    # That boilerplate must not be mistaken for the real cause ("confirm you" once triggered the login message).
    m = re.split(r";\s*please report this issue", m, maxsplit=1)[0].strip()
    low = m.lower()
    if "unsupported url" in low:
        return ("Cannot recognize this page, and no media URLs found in page source. The video might be loaded via JavaScript: "
                "you can enable page rendering in 'Advanced Settings', or open Network in browser F12, find the m3u8 / mp4 URL and paste it.")
    if any(k in low for k in ("javascript runtime", "challenge solving failed", "signature solving failed")):
        return "YouTube needs a JavaScript runtime (Deno) and the yt-dlp-ejs component. Open Diagnostics and click 'Install now'."
    if "cookie" in low and any(k in low for k in ("could not copy", "cookie database", "decrypt", "locked")):
        return ("Could not read the browser's cookies. Close the browser completely and retry, "
                "or upload a cookies.txt file in 'Advanced Settings'.")
    if "cookies are no longer valid" in low or "likely been rotated" in low:
        return ("Your YouTube cookies were rotated or expired. Export a fresh cookies.txt from a private window "
                "and upload it again in 'Advanced Settings'.")
    if any(k in low for k in ("sign in", "log in", "login", "not a bot", "use --cookies", "cookies-from-browser")):
        return "This content requires login or verification: upload a cookies.txt file or pick a browser in 'Advanced Settings' and try again."
    if "ffmpeg" in low or "ffprobe" in low:
        return "ffmpeg not found, please install and add to PATH, then restart this program."
    if any(k in low for k in ("getaddrinfo failed", "name or service not known", "nodename nor servname",
                              "temporary failure in name resolution", "no address associated")):
        return ("Cannot find that site's address. Check the link and your internet connection or proxy. "
                f"(Details: {m[:140]})")
    if "certificate" in low and "verify" in low:
        return ("The site's SSL certificate could not be verified. An antivirus or proxy that inspects HTTPS, "
                "or a wrong system clock, are the usual causes. (Details: " + m[:140] + ")")
    if any(k in low for k in ("timed out", "connection refused", "failed to establish a new connection", "connection reset",
                              "network is unreachable", "proxyerror", "unable to connect to proxy")):
        return ("Cannot reach the site. Check your network, VPN or proxy (Advanced Settings > Proxy), "
                f"or open Diagnostics > Test network. (Details: {m[:140]})")
    if "http error 403" in low or "http error 401" in low:
        return "Server denied access. You can fill in Referer in 'Advanced Settings' or use cookies."
    if "http error 404" in low:
        return "Link has expired (404)."
    return m[:300] or "Download failed, expand log to see the reason."


def http_url(v, schemes=("http", "https")) -> str | None:
    v = str(v or "").strip()
    return v if re.match(rf"^({'|'.join(schemes)})://\S+$", v, re.I) else None


def make_args(o: dict):
    """Organize options submitted from the web page into a parameter object for grab.py, validating item by item."""
    a = grab.parse_args([])
    a.output = str(ROOT)
    a.mode = o.get("mode") if o.get("mode") in ("mp4", "mp3") else "mp4"
    q = str(o.get("quality", "best")).lower().rstrip("p")
    a.quality = q if q == "best" or (q.isdigit() and 100 <= int(q) <= 4320) else "best"
    try:
        abr = int(o.get("abr", 192))
    except (TypeError, ValueError):
        abr = 192
    a.abr = abr if abr in (96, 128, 192, 256, 320) else 192
    a.subs = bool(o.get("subs"))
    langs = re.sub(r"[^\w,.*\-]", "", str(o.get("sub_langs") or ""))[:200]
    a.sub_langs = langs or a.sub_langs
    a.auto_subs = bool(o.get("auto_subs"))
    a.embed_subs = bool(o.get("embed_subs")) and a.mode == "mp4"
    a.cover = bool(o.get("cover"))
    a.keep_cover = bool(o.get("keep_cover"))
    a.no_playlist = bool(o.get("no_playlist"))
    items = str(o.get("items") or "").strip()
    a.items = items if re.fullmatch(r"[\d,\-:]+", items) else None
    a.archive = str(ROOT / ".archive.txt") if o.get("archive") else None
    br = str(o.get("cookies_from_browser") or "")
    a.cookies_from_browser = br if br in BROWSERS else None
    # An uploaded cookies.txt wins over reading a browser
    a.cookies = str(cookies_path()) if o.get("use_cookies_file") and cookies_path().is_file() else None
    if a.cookies:
        a.cookies_from_browser = None
    a.referer = http_url(o.get("referer"))
    a.proxy = http_url(o.get("proxy"), ("http", "https", "socks4", "socks5", "socks5h"))
    rate = str(o.get("limit_rate") or "").strip()
    a.limit_rate = rate if re.fullmatch(r"\d+(\.\d+)?[KkMmGg]?", rate) and float(re.sub(r"\D*$", "", rate)) > 0 else None
    try:
        a.sleep = min(max(float(o.get("sleep") or 0), 0), 60)
        a.threads = min(max(int(o.get("threads") or 4), 1), 16)
    except (TypeError, ValueError):
        a.sleep, a.threads = 0, 4
    a.all_sniffed = bool(o.get("all_sniffed"))
    a.js_render = bool(o.get("js_render"))
    try:
        a.js_wait = min(max(float(o.get("js_wait") or 8), 2), 30)
    except (TypeError, ValueError):
        a.js_wait = 8.0
    jb = str(o.get("js_browser") or "auto")
    a.js_browser = jb if jb in ("auto", "msedge", "chrome", "chromium") else "auto"
    a.list_formats = False
    a.no_sniff = False
    return a


# ───────────────────────── Jobs ─────────────────────────
class Job:
    def __init__(self, url: str, options: dict):
        self.id = uuid.uuid4().hex[:8]
        self.url = url
        self.options = options
        self.status = "queued"       # queued / running / done / error / canceled
        self.stage = "Queued"
        self.title = ""
        self.percent = 0.0
        self.speed = ""
        self.eta = ""
        self.item = ""
        self.error = ""
        self.files: list[str] = []
        self.seen_paths: list[str] = []
        self.log: collections.deque[str] = collections.deque(maxlen=400)
        self.cancel = threading.Event()
        self.created = time.time()
        self._parts_done = 0
        self._cur_id = None
        self.title_locked = False
        self.finished = 0.0
        self.notes: list[str] = []
        self._note_keys: set[str] = set()

    def to_dict(self) -> dict:
        rels = []
        for f in self.files:
            try:
                rels.append(Path(f).resolve().relative_to(ROOT).as_posix())
            except (ValueError, OSError):
                pass
        keep_log = list(self.log)[-30:] if self.status in ("error", "canceled") else []
        return {
            "id": self.id, "url": self.url, "options": self.options, "status": self.status,
            "stage": self.stage, "title": self.title, "percent": self.percent, "item": self.item,
            "error": self.error, "files": rels, "created": self.created, "finished": self.finished,
            "log": [x[:300] for x in keep_log], "notes": self.notes[:3],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Job | None":
        url, jid = http_url(d.get("url")), str(d.get("id") or "")
        if not url or not re.fullmatch(r"[0-9a-f]{8}", jid):
            return None
        opts = d.get("options") if isinstance(d.get("options"), dict) else {}
        job = cls(url, opts)
        job.id = jid
        st = d.get("status")
        interrupted = st in ("queued", "running")
        job.status = st if st in ("done", "error", "canceled") else "canceled"
        job.stage = "Last incomplete" if interrupted else {"done": "Done", "error": "Failed", "canceled": "Canceled"}[job.status]
        job.title = str(d.get("title") or "")[:300]
        job.item = str(d.get("item") or "")[:20]
        job.error = ("This task was incomplete when the program exited, you can click 'Retry'." if interrupted
                     else str(d.get("error") or "")[:600])
        try:
            job.percent = 100.0 if job.status == "done" else float(d.get("percent") or 0)
            job.created = float(d.get("created") or time.time())
            job.finished = float(d.get("finished") or 0)
        except (TypeError, ValueError):
            job.created = time.time()
        if interrupted and not job.finished:
            job.finished = time.time()
        for rel in d.get("files") or []:
            try:
                fp = (ROOT / str(rel)).resolve()
                fp.relative_to(ROOT)
                if fp.is_file():
                    job.files.append(str(fp))
            except (ValueError, OSError):
                continue
        job.log.extend(str(x)[:300] for x in (d.get("log") or [])[-30:])
        job.notes = [str(x)[:300] for x in (d.get("notes") or [])[:3]] if isinstance(d.get("notes"), list) else []
        return job

    def view(self) -> dict:
        files = []
        for f in self.files:
            try:
                files.append({"name": Path(f).name, "path": Path(f).resolve().relative_to(ROOT).as_posix()})
            except (ValueError, OSError):
                pass
        return {
            "id": self.id, "url": self.url, "status": self.status, "stage": self.stage,
            "title": self.title, "percent": round(self.percent, 1), "speed": self.speed,
            "eta": self.eta, "item": self.item, "error": self.error, "files": files,
            "mode": self.options.get("mode", "mp4"),
            "created": self.created, "finished": self.finished, "notes": list(self.notes),
        }


def run_job(job: Job) -> None:
    args = make_args(job.options)

    def log(msg: str) -> None:
        for line in strip_ansi(str(msg)).splitlines():
            if not line.strip():
                continue
            job.log.append(line)
            low = line.lower()
            if not line.startswith("[Hint]"):
                for words, key, text in NOTE_RULES:
                    if key not in job._note_keys and any(w in low for w in words):
                        job._note_keys.add(key)
                        job.notes.append(text)
            if line.startswith("[Render]"):
                job.stage = "Rendering page"
                if any(k in line for k in ("Cannot launch", "not installed", "Page load failed")):
                    job.error = line.split("]", 1)[1].strip()
            elif line.startswith("[Scan]"):
                job.stage = "Scanning page"

    class Logger:
        def debug(self, m): log(m)
        def info(self, m): log(m)
        def warning(self, m): log("Warning: " + m)

        def error(self, m):
            log("Error: " + m)
            job.error = strip_ansi(m)

    def check() -> None:
        if job.cancel.is_set():
            raise DownloadCancelled("Canceled")

    def track(path) -> None:
        if path and path not in job.seen_paths:
            job.seen_paths.append(path)

    def on_progress(d: dict) -> None:
        check()
        info = d.get("info_dict") or {}
        cur = info.get("id")
        if cur != job._cur_id:
            job._cur_id, job._parts_done = cur, 0
        total_items = info.get("n_entries") or info.get("playlist_count")
        if info.get("playlist_index") and total_items:
            job.item = f"{info['playlist_index']}/{total_items}"
        if info.get("title") and not job.title_locked:
            job.title = info["title"]
        parts = len(info.get("requested_formats") or []) or 1
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            if total:
                frac = done / total
            elif d.get("fragment_count"):
                frac = (d.get("fragment_index") or 0) / d["fragment_count"]
            else:
                frac = 0.0
            job.percent = min((job._parts_done + frac) / parts * 100, 99.9)
            job.stage = "Downloading"
            job.speed, job.eta = fmt_speed(d.get("speed")), fmt_eta(d.get("eta"))
        elif d.get("status") == "finished":
            job._parts_done += 1
            job.speed = job.eta = ""
            if job._parts_done >= parts:
                job.percent, job.stage = 100.0, "Processing"
            track(d.get("filename") or info.get("filepath"))

    def on_pp(d: dict) -> None:
        check()
        if d.get("status") == "started":
            job.stage = PP_LABEL.get(d.get("postprocessor", ""), "Processing")
        elif d.get("status") == "finished":
            track((d.get("info_dict") or {}).get("filepath"))

    extra = {
        "logger": Logger(), "noprogress": True,
        "progress_hooks": [on_progress], "postprocessor_hooks": [on_pp],
    }

    def download_one(url: str, referer=None, name=None) -> bool:
        work = grab.begin_work(args)  # Process MP3s in temp dir to avoid overwriting MP4s with the same name
        try:
            opts = grab.build_opts(args, referer, name, work)
            opts.update(extra)
            with cookie_copy(args) as cookiefile:
                if cookiefile:
                    opts["cookiefile"] = cookiefile
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.download([url]) == 0
        except DownloadCancelled:
            raise
        except DownloadError:
            return False
        finally:
            moved = grab.finish_work(work, args)
            if moved:
                job.seen_paths = [moved.get(x, x) for x in job.seen_paths]

    def set_title(t: str) -> None:
        job.title, job.title_locked = t, True

    ok = grab.discover_and_download(job.url, args, download_one, log, set_title, check)

    job.files = [p for p in job.seen_paths if Path(p).suffix.lower() in MEDIA_SUFFIX and Path(p).exists()]
    if ok:
        job.status, job.stage, job.percent, job.error = "done", "Done", 100.0, ""
    else:
        job.status, job.stage = "error", "Failed"
        job.error = ("Partial items failed to download, expand log for details." if job.files
                     else friendly_error(job.error))
    job.speed = job.eta = ""


def worker() -> None:
    while True:
        job = QUEUE.get()
        try:
            if job.cancel.is_set():
                continue
            job.status, job.stage = "running", "Preparing"
            run_job(job)
        except DownloadCancelled:
            job.status, job.stage, job.speed, job.eta = "canceled", "Canceled", "", ""
        except (Exception, SystemExit) as e:  # noqa: BLE001
            job.status, job.stage, job.error = "error", "Failed", friendly_error(str(e))
        finally:
            if job.status in ("done", "error", "canceled"):
                job.finished = time.time()
            bump_rev()
            save_history()
            QUEUE.task_done()


def create_jobs(urls: list[str], options: dict) -> list[str]:
    ids = []
    for u in urls:
        job = Job(u, options)
        with JOBS_LOCK:
            JOBS[job.id] = job
        QUEUE.put(job)
        ids.append(job.id)
    prune_jobs()
    save_history()
    return ids


# ───────────────────────── Parse (No Download) ─────────────────────────
def probe(url: str, options: dict) -> dict:
    args = make_args(options)
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": "in_playlist", "noplaylist": args.no_playlist,
        "socket_timeout": 12, "http_headers": {"User-Agent": grab.UA},
    }
    if args.proxy:
        opts["proxy"] = args.proxy
    if args.cookies_from_browser:
        opts["cookiesfrombrowser"] = (args.cookies_from_browser,)
    opts.update(grab.js_runtime_opts())
    with cookie_copy(args) as cookiefile:
        if cookiefile:
            opts["cookiefile"] = cookiefile
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:  # noqa: BLE001
            info, err = None, str(e)
        else:
            err = "No content parsed"

    if info is None:
        if not grab.has_specific_extractor(url):
            quiet = lambda *_: None  # noqa: E731
            title, cands = grab.sniff_media_urls(url, quiet, proxy=args.proxy)
            rendered = False
            if not cands and args.js_render:
                try:
                    title, cands = grab.render_media_urls(url, args.js_wait, args.js_browser, quiet, proxy=args.proxy)
                    rendered = True
                except grab.JSRenderError as e:
                    return {"error": str(e)}
            if cands:
                return {"kind": "page", "title": title, "sources": cands[:8], "count": len(cands),
                        "rendered": rendered}
        return {"error": friendly_error(err)}

    if info.get("_type") == "playlist":
        entries = list(info.get("entries") or [])
        return {
            "kind": "playlist", "title": info.get("title") or "",
            "count": info.get("playlist_count") or len(entries),
            "items": [(e.get("title") or e.get("url") or "") for e in entries[:10] if e],
        }
    heights = sorted(
        {f["height"] for f in info.get("formats") or [] if f.get("height") and f.get("vcodec") != "none"},
        reverse=True,
    )
    return {
        "kind": "video", "title": info.get("title") or "", "uploader": info.get("uploader") or "",
        "duration": info.get("duration"), "thumbnail": info.get("thumbnail") or "",
        "heights": heights, "extractor": info.get("extractor_key") or "",
    }


# ───────────────────────── Files ─────────────────────────
def list_files() -> list[dict]:
    """Use scandir recursively (max 3 levels, up to 20,000 items checked), and cache for 5 seconds."""
    if FILES_CACHE["rev"] == FILES_REV and time.time() - FILES_CACHE["ts"] < 5:
        return FILES_CACHE["data"]
    rev = FILES_REV
    out: list[dict] = []
    budget = [20000]

    def scan(d: str, depth: int) -> None:
        try:
            it = os.scandir(d)
        except OSError:
            return
        with it:
            for e in it:
                if budget[0] <= 0:
                    return
                budget[0] -= 1
                try:
                    if e.is_dir(follow_symlinks=False):
                        if depth < 3 and not e.name.startswith("."):
                            scan(e.path, depth + 1)
                    elif Path(e.name).suffix.lower() in MEDIA_SUFFIX and e.is_file():
                        st = e.stat()
                        out.append({"name": e.name, "path": Path(e.path).relative_to(ROOT).as_posix(),
                                    "size": st.st_size, "mtime": st.st_mtime})
                except (OSError, ValueError):
                    continue

    scan(str(ROOT), 0)
    out.sort(key=lambda x: x["mtime"], reverse=True)
    FILES_CACHE.update(rev=rev, ts=time.time(), data=out[:200])
    return FILES_CACHE["data"]


def _open_with_os(path: Path) -> None:
    """Open a file or folder with whatever the OS considers its default handler."""
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def open_in_file_manager(path: Path) -> None:
    try:
        _open_with_os(path)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Cannot open folder: {e}")


def open_file(path: Path) -> None:
    try:
        _open_with_os(path)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"Cannot open file: {e}")


# ───────────────────────── Desktop notifications (window mode) ─────────────────────────
def desktop_notifications_supported() -> bool:
    """Whether the backend can show a native notification itself.

    Only relevant in window mode: a browser tab shows its own notifications via the Web
    Notifications API. Inside a native window, Windows' WebView2 supports that API too, so it
    is left to do the job there. WKWebView (macOS) and most GTK WebKit builds (Linux) do not
    support it, so the backend shows one instead, using tools that ship with the OS.
    """
    if not WINDOW_MODE:
        return False
    if sys.platform == "darwin":
        return True  # osascript ships with macOS
    if sys.platform.startswith("win"):
        return False
    return shutil.which("notify-send") is not None


def show_desktop_notification(title: str, message: str) -> bool:
    """Best-effort native notification. Values are passed as argv, never interpolated into a
    shell command, so arbitrary titles (a pasted link, a video's own title) cannot inject code."""
    try:
        if sys.platform == "darwin":
            script = "on run argv\n  display notification (item 2 of argv) with title (item 1 of argv)\nend run"
            subprocess.run(["osascript", "-e", script, title, message], check=True, timeout=5, capture_output=True)
            return True
        if shutil.which("notify-send"):
            subprocess.run(["notify-send", "--app-name=Video Grabber", "--", title, message],
                           check=True, timeout=5, capture_output=True)
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    return False


# ───────────────────────── History ─────────────────────────
def history_file() -> Path:
    return ROOT / ".grab-history.json"


def save_history() -> None:
    with JOBS_LOCK:
        data = [j.to_dict() for j in sorted(JOBS.values(), key=lambda j: j.created)[-HISTORY_MAX:]]
    try:
        with _SAVE_LOCK:
            tmp = history_file().with_suffix(".tmp")
            tmp.write_text(json.dumps({"version": 1, "jobs": data}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, history_file())
    except OSError as e:
        print(f"Cannot save history: {e}")


def load_history() -> None:
    try:
        raw = json.loads(history_file().read_text(encoding="utf-8"))
        items = raw.get("jobs", []) if isinstance(raw, dict) else []
    except (OSError, ValueError):
        return
    for d in items[-HISTORY_MAX:]:
        job = Job.from_dict(d) if isinstance(d, dict) else None
        if job:
            JOBS[job.id] = job


def prune_jobs() -> None:
    """Finished jobs are kept up to HISTORY_MAX, oldest are dropped first."""
    with JOBS_LOCK:
        finished = sorted((j for j in JOBS.values() if j.status in ("done", "error", "canceled")),
                          key=lambda j: j.created)
        for j in finished[: max(0, len(JOBS) - HISTORY_MAX)]:
            JOBS.pop(j.id, None)


def active_jobs() -> int:
    return sum(1 for j in list(JOBS.values()) if j.status in ("queued", "running"))


# ───────────────────────── Update yt-dlp / Restart ─────────────────────────
def installed_version() -> str:
    try:
        return importlib.metadata.version("yt-dlp")
    except importlib.metadata.PackageNotFoundError:
        return yt_dlp.version.__version__


def version_key(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4])


def check_ytdlp(force: bool = False) -> dict:
    running, installed = yt_dlp.version.__version__, installed_version()
    out = {"running": running, "installed": installed,
           "needs_restart": version_key(installed) != version_key(running)}
    latest = PYPI_CACHE["latest"] if not force and time.time() - PYPI_CACHE["ts"] < 6 * 3600 else None
    if latest is None:
        try:
            req = urllib.request.Request("https://pypi.org/pypi/yt-dlp/json", headers={"User-Agent": grab.UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                latest = str(json.load(r)["info"]["version"])
            PYPI_CACHE.update(ts=time.time(), latest=latest)
        except Exception as e:  # noqa: BLE001
            out.update(latest=None, newer=False, error=f"Cannot connect to PyPI: {e}")
            return out
    out.update(latest=latest, newer=version_key(latest) > version_key(installed))
    return out


def start_update(extras: str = "default") -> tuple[bool, str]:
    with UPDATE_LOCK:
        if UPDATE["status"] == "running":
            return False, "Already updating"
        if active_jobs():
            return False, "There are tasks queued or downloading, wait for them to finish (or cancel) before updating."
        UPDATE.update(status="running", lines=[], before=installed_version(), after="", error="", extras=extras)
    threading.Thread(target=_do_update, args=(extras,), daemon=True).start()
    return True, ""


def _do_update(extras: str = "default") -> None:
    # "default" adds yt-dlp-ejs (YouTube challenge solver); "deno" adds the Deno JavaScript runtime
    cmd = [sys.executable, "-m", "pip", "install", "-U", "--disable-pip-version-check", f"yt-dlp[{extras}]"]
    kw: dict = {}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace",
                                env=dict(os.environ, PYTHONIOENCODING="utf-8"), **kw)
        assert proc.stdout is not None
        for line in proc.stdout:
            with UPDATE_LOCK:
                UPDATE["lines"].append(line.rstrip()[:300])
                del UPDATE["lines"][:-200]
        rc = proc.wait()
    except Exception as e:  # noqa: BLE001
        with UPDATE_LOCK:
            UPDATE.update(status="error", error=f"Cannot run pip: {e}")
        return
    with UPDATE_LOCK:
        text = "\n".join(UPDATE["lines"]).lower()
        UPDATE["after"] = installed_version()
        if rc == 0:
            importlib.invalidate_caches()
            DOCTOR_CACHE["ts"] = 0.0
            UPDATE.update(status="done", error="")
        else:
            if "externally-managed" in text:
                hint = "The current Python environment is managed by the system; pip does not allow direct installation. Please use a virtual environment, or update manually in terminal."
            elif "permission" in text or "access is denied" in text:
                hint = 'No write permission, you can run  pip install -U --user "yt-dlp[default]"  in the terminal.'
            else:
                hint = 'Update failed, see log for details. You can also run  pip install -U "yt-dlp[default]"  in the terminal.'
            UPDATE.update(status="error", error=hint)
    PYPI_CACHE["ts"] = 0.0


def restart_self() -> None:
    """Restart this program with the same arguments (required to load the new version after updating yt-dlp)."""
    argv = [sys.executable, str(Path(__file__).resolve()), "--dir", str(ROOT), "--port", str(PORT),
            "--workers", str(WORKERS), "--no-browser"]
    env = dict(os.environ, GRAB_WEBUI_RESTART="1")
    if sys.platform.startswith("win"):
        subprocess.Popen(argv, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)  # type: ignore[attr-defined]
        os._exit(0)
    os.execve(sys.executable, argv, env)


# ───────────────────────── Cookies (uploaded cookies.txt) ─────────────────────────
def cookies_path() -> Path:
    return CONFIG_DIR / "cookies.txt"


def parse_cookies(text: str) -> dict:
    """Validate Netscape-format cookies.txt text. Raises ValueError with a readable reason.

    The returned summary never contains cookie values; "text" is the normalised file content to store.
    """
    if text.lstrip().startswith(("{", "[")):
        raise ValueError("That looks like a JSON export. Export the cookies in Netscape 'cookies.txt' format instead.")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    names: dict[str, set[str]] = {}
    count = expired = bad = 0
    now = time.time()
    for raw in lines:
        if not raw.strip() or (raw.startswith("#") and not raw.startswith("#HttpOnly_")):
            continue
        parts = raw.split("\t")
        try:
            if len(parts) != 7:
                raise ValueError
            exp = int(parts[4] or 0)
        except ValueError:
            bad += 1
            continue
        domain = parts[0].removeprefix("#HttpOnly_").lstrip(".").lower()
        names.setdefault(domain, set()).add(parts[5])
        count += 1
        if 0 < exp < now:
            expired += 1
    if not count:
        raise ValueError("No valid cookie lines found. Export the cookies as a Netscape-format cookies.txt file "
                         "(seven tab-separated columns per line).")

    def names_for(*suffixes: str) -> set[str]:
        return {n for d, ns in names.items() if any(d == x or d.endswith("." + x) for x in suffixes) for n in ns}

    yt, google, bili = names_for("youtube.com"), names_for("youtube.com", "google.com"), names_for("bilibili.com")
    header_ok = bool(lines) and re.search(r"#( Netscape)? HTTP Cookie File", lines[0]) is not None
    body = lines if header_ok else ["# Netscape HTTP Cookie File"] + lines
    return {
        "cookies": count, "expired": expired, "bad_lines": bad, "domains": sorted(names),
        "has_youtube": bool(yt), "youtube_login": "LOGIN_INFO" in yt and bool(
            google & {"SAPISID", "__Secure-3PAPISID", "__Secure-1PAPISID", "__Secure-3PSID"}),
        "has_bilibili": bool(bili), "bilibili_login": "SESSDATA" in bili,
        "text": "\n".join(body).rstrip("\n") + "\n",
    }


def cookies_status() -> dict:
    path = cookies_path()
    if not path.is_file():
        return {"present": False}
    try:
        info = parse_cookies(path.read_text(encoding="utf-8", errors="replace"))
        updated = path.stat().st_mtime
    except (OSError, ValueError):
        return {"present": False}
    info.pop("text", None)
    domains = info.pop("domains")
    return {"present": True, "updated": updated, "domain_count": len(domains), "sample": domains[:6], **info}


def save_cookies(text: str) -> dict:
    info = parse_cookies(text)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = cookies_path()
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(info["text"])
    with contextlib.suppress(OSError):
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    DOCTOR_CACHE["ts"] = 0.0
    return cookies_status()


def delete_cookies() -> None:
    with contextlib.suppress(OSError):
        cookies_path().unlink()
    DOCTOR_CACHE["ts"] = 0.0


@contextlib.contextmanager
def cookie_copy(args):
    """Give every yt-dlp run its own copy of the cookies file.

    yt-dlp writes cookies back to the file when it closes; separate copies stop parallel jobs from
    clobbering each other and keep the uploaded file exactly as the user exported it.
    """
    if not getattr(args, "cookies", None):
        yield None
        return
    tmp = None
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="run-", suffix=".txt", dir=CONFIG_DIR)
        os.close(fd)
        shutil.copyfile(args.cookies, tmp)
        yield tmp
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.remove(tmp)


# ───────────────────────── Diagnostics ─────────────────────────
def collect_doctor(net: bool = False, force: bool = False) -> dict:
    if not net and not force and DOCTOR_CACHE["data"] and time.time() - DOCTOR_CACHE["ts"] < 15:
        return DOCTOR_CACHE["data"]
    checks = grab.run_diagnostics(ROOT, net=net)
    st = cookies_status()
    if st.get("present"):
        bits = [f"{st['cookies']} cookie{'' if st['cookies'] == 1 else 's'} for {st['domain_count']} site{'' if st['domain_count'] == 1 else 's'}"]
        status = "ok"
        if st["expired"]:
            bits.append(f"{st['expired']} already expired")
        if st["has_youtube"]:
            bits.append("YouTube sign-in cookies found" if st["youtube_login"] else "no YouTube sign-in cookies")
            status = "ok" if st["youtube_login"] else "warn"
        if st["has_bilibili"]:
            bits.append("Bilibili sign-in cookie found" if st["bilibili_login"] else "no Bilibili sign-in cookie")
        checks.append(grab.check_item("cookies", "Uploaded cookies.txt", status, "; ".join(bits) + "."))
    else:
        checks.append(grab.check_item("cookies", "Uploaded cookies.txt", "info",
                                      "None uploaded. Only needed for logged-in, member-only or age-restricted videos."))
    checks.append(grab.check_item("server", "Web UI", "info",
                                  f"Port {PORT}, {WORKERS} worker(s), interface: {UI_MODE}. Settings folder: {CONFIG_DIR}"))
    if importlib.util.find_spec("webview"):
        checks.append(grab.check_item("pywebview", "Desktop window (pywebview)", "ok",
                                      "Installed. Start with --ui window for a native window instead of a browser tab."))
    else:
        checks.append(grab.check_item("pywebview", "Desktop window (pywebview)", "info",
                                      "Not installed. Optional: only needed for --ui window.", fix="pip install pywebview"))
    failures = sorted((j for j in list(JOBS.values()) if j.status == "error"),
                      key=lambda j: j.finished or j.created, reverse=True)[:3]
    sections = [(f"Recent failure {i}", [j.url, f"Error: {j.error}"] + [ln[:200] for ln in list(j.log)[-12:]])
                for i, j in enumerate(failures, 1)]
    data = {"checks": checks, "report": grab.format_report(checks, sections), "net": net}
    if not net:
        DOCTOR_CACHE.update(ts=time.time(), data=data)
    return data


# ───────────────────────── Frontend (built React app) ─────────────────────────
def render_dist_index() -> bytes | None:
    """The built frontend's index.html, with this run's token filled in. None if it was not built."""
    index = UI_DIST / "index.html"
    if not index.is_file():
        return None
    return index.read_text(encoding="utf-8").replace("__GRAB_TOKEN__", TOKEN).encode("utf-8")


def read_static_asset(rel: str) -> tuple[bytes, str] | None:
    """rel is the request path with the leading slash removed, e.g. "assets/index-abc123.js"."""
    path = (UI_DIST / rel).resolve()
    try:
        path.relative_to(UI_DIST)
    except ValueError:
        return None
    if not path.is_file() or path.suffix.lower() not in ALLOWED_STATIC_EXT:
        return None
    return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"


# ───────────────────────── HTTP ─────────────────────────
HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$", re.I)


class Handler(BaseHTTPRequestHandler):
    server_version = "grab-webui"

    def log_message(self, *args):  # Silent
        pass

    # —— Output ——
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self, limit: int = BODY_MAX_BYTES) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > limit:
            return {}
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    # —— Validation ——
    def _guard(self) -> bool:
        if not HOST_RE.match(self.headers.get("Host", "")):
            self._json({"error": "forbidden host"}, 403)
            return False
        return True

    def _authed(self, query: dict) -> bool:
        tok = self.headers.get("X-Token") or (query.get("t") or [""])[0]
        if not hmac.compare_digest(tok.encode(), TOKEN.encode()):
            self._json({"error": "Unauthorized, please refresh the page"}, 401)
            return False
        return True

    # —— Routing ——
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._guard():
            return
        if u.path == "/":
            dist_page = render_dist_index()
            if dist_page is not None:
                csp = ("default-src 'self'; img-src http: https: data:; style-src 'self'; "
                       "script-src 'self'; connect-src 'self'; media-src 'self'; frame-ancestors 'none'")
                return self._send(200, dist_page, "text/html; charset=utf-8", {"Content-Security-Policy": csp})
            page = INDEX_HTML.replace("__TOKEN__", TOKEN).encode("utf-8")
            csp = ("default-src 'self'; img-src http: https: data:; style-src 'unsafe-inline'; "
                   "script-src 'unsafe-inline'; connect-src 'self'; media-src 'self'; frame-ancestors 'none'")
            return self._send(200, page, "text/html; charset=utf-8", {"Content-Security-Policy": csp})
        if u.path.startswith("/assets/"):
            # The browser requests these via <script>/<link> tags, which cannot carry X-Token,
            # so this is public like "/" - the files are just the built app, nothing sensitive.
            asset = read_static_asset(u.path.lstrip("/"))
            if asset is None:
                return self._json({"error": "not found"}, 404)
            body, ctype = asset
            return self._send(200, body, ctype, {"Cache-Control": "public, max-age=31536000, immutable"})
        if not self._authed(q):
            return
        if u.path == "/api/state":
            with JOBS_LOCK:
                jobs = sorted(JOBS.values(), key=lambda j: j.created, reverse=True)
                views = [j.view() for j in jobs]
            try:
                client_rev = int((q.get("rev") or ["-1"])[0])
            except ValueError:
                client_rev = -1
            data = {"version": yt_dlp.version.__version__, "ffmpeg": bool(shutil.which("ffmpeg")),
                    "playwright": importlib.util.find_spec("playwright") is not None,
                    "root": str(ROOT), "rev": FILES_REV, "jobs": views,
                    "window": WINDOW_MODE, "desktop_notifications": desktop_notifications_supported()}
            if client_rev != FILES_REV:
                data["files"] = list_files()
            return self._json(data)
        m = re.fullmatch(r"/api/jobs/([0-9a-f]{8})/log", u.path)
        if m:
            job = JOBS.get(m.group(1))
            return self._json({"lines": list(job.log)[-200:] if job else []})
        if u.path == "/api/doctor":
            flag = lambda k: bool((q.get(k) or [""])[0])  # noqa: E731
            return self._json(collect_doctor(net=flag("net"), force=flag("force")))
        if u.path == "/api/cookies":
            return self._json(cookies_status())
        if u.path == "/api/ytdlp/check":
            return self._json(check_ytdlp(force=bool((q.get("force") or [""])[0])))
        if u.path == "/api/ytdlp/update-status":
            with UPDATE_LOCK:
                return self._json({k: (list(v) if isinstance(v, list) else v) for k, v in UPDATE.items()})
        if u.path.startswith("/files/"):
            return self._file(unquote(u.path[len("/files/"):]))
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._guard() or not self._authed(q):
            return
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json({"error": "bad content type"}, 415)
        body = self._body(COOKIES_MAX_BYTES if u.path == "/api/cookies" else BODY_MAX_BYTES)

        if u.path == "/api/probe":
            url = http_url(body.get("url"))
            if not url:
                return self._json({"error": "Please enter an http(s) URL"}, 400)
            return self._json(probe(url, body.get("options") or {}))

        if u.path == "/api/jobs":
            if UPDATE["status"] == "running":
                return self._json({"error": "Currently updating yt-dlp, please add tasks later"}, 409)
            raw = body.get("urls") or []
            urls = list(dict.fromkeys(x.strip() for x in raw if isinstance(x, str) and http_url(x)))[:200]
            if not urls:
                return self._json({"error": "No valid URLs found (requires http:// or https://)"}, 400)
            return self._json({"ids": create_jobs(urls, body.get("options") or {})})

        m = re.fullmatch(r"/api/jobs/([0-9a-f]{8})/(cancel|retry|remove)", u.path)
        if m:
            job, action = JOBS.get(m.group(1)), m.group(2)
            if not job:
                return self._json({"error": "Job not found"}, 404)
            if action == "cancel":
                job.cancel.set()
                if job.status == "queued":
                    job.status, job.stage, job.finished = "canceled", "Canceled", time.time()
                    save_history()
                else:
                    job.stage = "Canceling…"
            elif action == "retry" and job.status in ("error", "canceled"):
                return self._json({"ids": create_jobs([job.url], job.options)})
            elif action == "remove" and job.status in ("done", "error", "canceled"):
                with JOBS_LOCK:
                    JOBS.pop(job.id, None)
                save_history()
            return self._json({"ok": True})

        if u.path == "/api/clear":
            with JOBS_LOCK:
                for jid in [j.id for j in JOBS.values() if j.status in ("done", "error", "canceled")]:
                    JOBS.pop(jid, None)
            save_history()
            return self._json({"ok": True})

        if u.path == "/api/open-folder":
            target = ROOT
            rel = str(body.get("path") or "")
            if rel:
                cand = (ROOT / rel).resolve().parent
                try:
                    cand.relative_to(ROOT)
                    target = cand
                except ValueError:
                    pass
            open_in_file_manager(target)
            return self._json({"ok": True})

        if u.path == "/api/open-file":
            rel = str(body.get("path") or "")
            if not rel:
                return self._json({"error": "No file given"}, 400)
            target = (ROOT / rel).resolve()
            try:
                target.relative_to(ROOT)
            except ValueError:
                return self._json({"error": "forbidden"}, 403)
            if not target.is_file() or target.suffix.lower() not in MEDIA_SUFFIX:
                return self._json({"error": "File not found"}, 404)
            open_file(target)
            return self._json({"ok": True})

        if u.path == "/api/notify":
            if not desktop_notifications_supported():
                return self._json({"ok": False})
            title = str(body.get("title") or "Video Grabber")[:120]
            message = str(body.get("body") or "")[:500]
            return self._json({"ok": show_desktop_notification(title, message)})

        if u.path == "/api/cookies":
            text = body.get("text")
            if not isinstance(text, str) or not text.strip():
                return self._json({"error": "Empty file, or larger than 3 MB."}, 400)
            try:
                return self._json(save_cookies(text))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except OSError as e:
                return self._json({"error": f"Could not save the file: {e}"}, 500)

        if u.path == "/api/cookies/delete":
            delete_cookies()
            return self._json({"present": False})

        if u.path == "/api/ytdlp/update":
            extras = body.get("extras") if body.get("extras") in ("default", "default,deno") else "default"
            ok, why = start_update(extras)
            return self._json({"ok": True} if ok else {"error": why}, 200 if ok else 409)

        if u.path == "/api/restart":
            if active_jobs() or UPDATE["status"] == "running":
                return self._json({"error": "Tasks are still running, wait for them to finish before restarting."}, 409)
            self._json({"ok": True})
            threading.Timer(0.5, restart_self).start()
            return

        self._json({"error": "not found"}, 404)

    def _file(self, rel: str) -> None:
        p = (ROOT / rel).resolve()
        try:
            p.relative_to(ROOT)
        except ValueError:
            return self._json({"error": "forbidden"}, 403)
        if not p.is_file() or p.suffix.lower() not in MEDIA_SUFFIX:
            return self._json({"error": "not found"}, 404)
        size = p.stat().st_size
        start, end, status = 0, size - 1, 200
        rng = (self.headers.get("Range") or "").strip()
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", rng)
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            if start > end or start >= size:
                return self._send(416, b"", "text/plain", {"Content-Range": f"bytes */{size}"})
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", f"inline; filename*=UTF-8''{quote(p.name)}")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with open(p, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows SO_REUSEADDR allows two processes to silently bind to the same port, so only enable on other OS
    allow_reuse_address = not sys.platform.startswith("win")


# ───────────────────────── Page ─────────────────────────
INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Grabber WebUI</title>
<link rel="icon" href="data:,">
<style>
:root{
  --bg:#E7EBEE; --panel:#F6F8F9; --field:#FFFFFF; --ink:#16202A; --muted:#566573; --line:#C5CDD4;
  --fill:#0E7A66; --on-fill:#FFFFFF; --fill-soft:rgba(14,122,102,.15);
  --bad:#B3372B; --warn:#8A5300; --bad-soft:rgba(179,55,43,.12); --idle-soft:rgba(86,101,115,.12);
  --sans:"Noto Sans SC","PingFang SC","Microsoft YaHei UI","Segoe UI",system-ui,sans-serif;
  color-scheme:light dark;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#10161B; --panel:#172027; --field:#0E1418; --ink:#E5EBF0; --muted:#94A2AE; --line:#2B3641;
    --fill:#3FCFA9; --on-fill:#08201A; --fill-soft:rgba(63,207,169,.16);
    --bad:#F08A7E; --warn:#F2B84B; --bad-soft:rgba(240,138,126,.14); --idle-soft:rgba(148,162,174,.12);
  }
}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{background:var(--bg)}
body{margin:0;color:var(--ink);font:15px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
button,input,select,textarea{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--fill);outline-offset:2px}
.muted{color:var(--muted)} .small{font-size:13px}

.top{display:flex;align-items:center;gap:16px;max-width:1180px;margin:0 auto;padding:22px 24px 6px}
.top h1{margin:0;font-size:24px;font-weight:700;letter-spacing:.04em;flex:1}
.banner{max-width:1180px;margin:8px auto 0;padding:10px 24px;background:var(--bad-soft);color:var(--bad);font-weight:600}
.banner p{margin:0}

.layout{display:grid;grid-template-columns:minmax(320px,380px) 1fr;gap:28px;max-width:1180px;margin:0 auto;padding:16px 24px 48px;align-items:start}
@media (max-width:860px){.layout{grid-template-columns:1fr;padding:12px 16px 40px}.top{padding:18px 16px 4px}}

.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;position:sticky;top:16px}
@media (max-width:860px){.panel{position:static}}
h2{margin:0 0 10px;font-size:16px;font-weight:700}
.queue h2{margin-top:0}
.queue section+section{margin-top:34px}
.sec-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
.sec-head h2{margin:0}

textarea,input[type=text],input[type=number],input[type=search],select{width:100%;background:var(--field);border:1px solid var(--line);border-radius:6px;padding:8px 10px}
textarea{resize:vertical;min-height:112px;line-height:1.5}
label.f{display:block;margin:12px 0 4px;font-weight:600;font-size:14px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.check{display:flex;align-items:center;gap:8px;margin:8px 0;cursor:pointer}
.check input{width:16px;height:16px;accent-color:var(--fill)}
.sub{margin:2px 0 0 24px}
.group{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
details.adv{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
details.adv summary{cursor:pointer;font-weight:600}

.seg{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--line);border-radius:6px;overflow:hidden;background:var(--field);margin-top:14px;position:relative}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg label{padding:9px 10px;text-align:center;cursor:pointer;font-weight:600}
.seg input:checked+label{background:var(--fill);color:var(--on-fill)}
.seg input:focus-visible+label{outline:2px solid var(--ink);outline-offset:-3px}
body[data-mode="mp3"] .only-mp4{display:none}
body:not([data-mode="mp3"]) .only-mp3{display:none}

.btn{border:1px solid var(--line);background:var(--field);border-radius:6px;padding:8px 14px;cursor:pointer;font-weight:600}
.btn:hover{border-color:var(--muted)}
.btn.primary{background:var(--fill);border-color:var(--fill);color:var(--on-fill)}
.btn.primary:hover{filter:brightness(1.06)}
.btn.small{padding:4px 10px;font-size:13px}
.btn:disabled{opacity:.5;cursor:default}
.actions{display:flex;gap:10px;margin-top:18px}
.actions .primary{flex:1}

#probe{margin-top:10px;padding:10px 12px;background:var(--field);border:1px solid var(--line);border-radius:6px;font-size:14px}
#probe p{margin:0}
.pr-head{display:flex;gap:10px;align-items:flex-start}
.pr-head img{width:96px;height:54px;object-fit:cover;border-radius:4px;flex:none;background:var(--idle-soft)}
.chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px}
.chip{border:1px solid var(--line);background:var(--panel);border-radius:999px;padding:1px 10px;cursor:pointer;font-size:13px}
.chip:hover{border-color:var(--fill);color:var(--fill)}
#probe ul{margin:6px 0 0;padding-left:18px}
#probe li{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.err{color:var(--bad)}

.list{border:1px solid var(--line);border-radius:8px;background:var(--panel);overflow:hidden}
.empty{padding:18px 16px;color:var(--muted)}
.job{position:relative;padding:14px 16px;border-top:1px solid var(--line);display:grid;grid-template-columns:1fr auto;gap:2px 16px;isolation:isolate}
.job.first{border-top:0}
.job::before{content:"";position:absolute;inset:0 auto 0 0;width:var(--p,0%);background:var(--fill-soft);transition:width .8s linear;z-index:-1}
.job[data-status="error"]::before{width:100%;background:var(--bad-soft)}
.job[data-status="canceled"]::before,.job[data-status="queued"]::before{width:100%;background:var(--idle-soft)}
.job[data-status="done"]::before{width:100%}
.job-title{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.job-meta{display:flex;flex-wrap:wrap;gap:2px 14px;font-size:13px;color:var(--muted);min-height:20px}
.job-err{color:var(--bad);font-size:14px;margin-top:4px}
.job-files{display:flex;flex-direction:column;gap:2px;margin-top:4px;font-size:14px}
.job-files a,.file a{color:var(--fill);font-weight:600;text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.job-files a:hover,.file a:hover{text-decoration:underline}
.job-side{grid-column:2;grid-row:1 / span 3;display:flex;flex-direction:column;align-items:flex-end;justify-content:space-between;gap:8px}
.pct{font-size:28px;font-weight:600;line-height:1;font-variant-numeric:tabular-nums;min-width:3ch;text-align:right}
.pct.word{font-size:15px;font-weight:600;color:var(--muted)}
.job[data-status="error"] .pct{color:var(--bad)}
.job[data-status="done"] .pct{color:var(--fill)}
.job-btns{display:flex;gap:6px}
.job-log{grid-column:1 / -1;margin-top:6px;font-size:13px}
.job-log summary{cursor:pointer;color:var(--muted);width:max-content}
.job-log pre{margin:6px 0 0;padding:10px;max-height:240px;overflow:auto;background:var(--field);border:1px solid var(--line);border-radius:6px;font:12px/1.5 ui-monospace,"Cascadia Mono",Consolas,monospace;white-space:pre-wrap;word-break:break-all}

.file{display:flex;align-items:center;gap:14px;padding:10px 16px;border-top:1px solid var(--line)}
.file:first-child{border-top:0}
.file a{flex:1;min-width:0}
.file span{font-size:13px;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}

.top{flex-wrap:wrap}
.top h1{white-space:nowrap}
.btn.attn{border-color:var(--fill);color:var(--fill)}
.ta-tools{display:flex;align-items:center;gap:10px;margin-top:6px}
.ta-tools span{flex:1;min-width:0}
textarea.flash{animation:flash 1.2s ease-out}
@keyframes flash{0%{box-shadow:0 0 0 3px var(--fill)}100%{box-shadow:0 0 0 0 transparent}}
.upd{grid-column:1 / -1;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px}
.upd-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.upd-row p{margin:0;flex:1;min-width:220px;font-weight:600}
.upd pre{margin:10px 0 0;max-height:200px;overflow:auto;padding:10px;background:var(--field);border:1px solid var(--line);border-radius:6px;font:12px/1.5 ui-monospace,"Cascadia Mono",Consolas,monospace;white-space:pre-wrap;word-break:break-all}
.filters{display:flex;gap:10px;align-items:center;margin-bottom:8px}
.filters input{flex:1;min-width:0}
.filters select{width:auto}
.sec-tools{display:flex;gap:8px;align-items:center}
#drop{position:fixed;inset:0;z-index:20;display:flex;align-items:center;justify-content:center;background:rgba(14,122,102,.86);color:#fff;font-size:22px;font-weight:700;pointer-events:none}
.banner.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.banner.row p{flex:1;min-width:220px}
.banner.warnb{background:rgba(180,120,0,.14);color:var(--warn)}
.badge{display:inline-block;min-width:66px;text-align:center;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;border:1px solid var(--line);color:var(--muted);height:fit-content}
.badge.ok{color:var(--fill);border-color:var(--fill)}
.badge.warn{color:var(--warn);border-color:var(--warn)}
.badge.error{color:var(--bad);border-color:var(--bad)}
.doc-list{margin-top:8px}
.doc-row{display:grid;grid-template-columns:72px 1fr;gap:4px 12px;padding:10px 0;border-top:1px solid var(--line)}
.doc-row:first-child{border-top:0}
.doc-row .lbl{font-weight:600}
.doc-row .det{font-size:14px;color:var(--muted);overflow-wrap:anywhere}
.doc-fix{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:4px}
.doc-fix code{background:var(--field);border:1px solid var(--line);border-radius:6px;padding:2px 8px;font:12px ui-monospace,"Cascadia Mono",Consolas,monospace;overflow-wrap:anywhere}
.job-note{color:var(--warn);font-size:13px;margin-top:4px;white-space:pre-line}
.cookie-box{margin-top:6px;padding:8px 10px;background:var(--field);border:1px solid var(--line);border-radius:6px}
.cookie-box p{margin:0 0 6px}
.cookie-actions{display:flex;gap:8px;align-items:center;margin-bottom:6px}
#toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:9px 16px;border-radius:6px;font-weight:600;max-width:90vw;z-index:10}
#toast.bad{background:var(--bad);color:#fff}
@media (prefers-reduced-motion:reduce){.job::before{transition:none}}
</style>
</head>
<body data-mode="mp4">
<header class="top">
  <h1>Video Grabber WebUI</h1>
  <span id="ver" class="muted small"></span>
  <button class="btn small" id="docBtn" type="button">Diagnostics</button>
  <button class="btn small" id="updBtn" type="button">Check for Updates</button>
  <button class="btn small" id="notifyBtn" type="button">Enable Completion Notifications</button>
  <button class="btn small" id="openDir" type="button">Open Download Folder</button>
</header>
<div class="banner" id="notice" hidden><p>ffmpeg not found: merging audio/video and MP3 conversion will fail. Please restart after installing.</p></div>
<div class="banner warnb row" id="envNotice" hidden>
  <p id="envMsg"></p>
  <button class="btn small" id="envOpen" type="button">Open Diagnostics</button>
  <button class="btn small" id="envDismiss" type="button">Dismiss</button>
</div>
<div class="banner" id="offline" hidden><p>Disconnected from local service, please ensure webui.py is running.</p></div>

<main class="layout">
  <section class="upd" id="upd" hidden aria-label="Update yt-dlp">
    <div class="upd-row">
      <p id="updMsg"></p>
      <button class="btn small primary" id="updDo" type="button" hidden>Update</button>
      <button class="btn small primary" id="updRestart" type="button" hidden>Restart Service</button>
      <button class="btn small" id="updClose" type="button">Collapse</button>
    </div>
    <pre id="updLog" hidden></pre>
  </section>
  <section class="upd" id="doctor" hidden aria-label="Diagnostics">
    <div class="upd-row">
      <p>Diagnostics</p>
      <button class="btn small" id="docRecheck" type="button">Re-check</button>
      <button class="btn small" id="docNet" type="button">Test network</button>
      <button class="btn small" id="docCopy" type="button">Copy report</button>
      <button class="btn small" id="docClose" type="button">Close</button>
    </div>
    <div class="doc-list" id="docList"></div>
    <p class="muted small" style="margin:8px 0 0">The report hides your home folder and proxy passwords, but it includes your most recent failed links and log lines. Read it before sharing.</p>
  </section>
  <section class="panel" aria-label="New Download">
    <h2>New Download</h2>
    <textarea id="urls" placeholder="Paste URLs, one per line. Supports video pages, playlists, mp4 and m3u8 direct links" spellcheck="false"></textarea>
    <div class="ta-tools">
      <button class="btn small" id="pasteBtn" type="button">Read Clipboard</button>
      <span class="muted small">Or press Ctrl+V, or drag and drop txt files/links into the page</span>
    </div>
    <div id="probe" hidden></div>

    <div class="seg" role="radiogroup" aria-label="Output Format">
      <input type="radio" name="mode" id="m-mp4" value="mp4" checked><label for="m-mp4">MP4 Video</label>
      <input type="radio" name="mode" id="m-mp3" value="mp3"><label for="m-mp3">MP3 Audio</label>
    </div>

    <div class="only-mp4">
      <label class="f" for="quality">Max Quality</label>
      <select id="quality">
        <option value="best">Best Quality</option><option value="2160">2160p (4K)</option><option value="1440">1440p</option>
        <option value="1080">1080p</option><option value="720">720p</option><option value="480">480p</option><option value="360">360p</option>
      </select>
    </div>
    <div class="only-mp3">
      <label class="f" for="abr">Audio Quality</label>
      <select id="abr">
        <option value="320">320 kbps</option><option value="256">256 kbps</option><option value="192" selected>192 kbps</option>
        <option value="128">128 kbps</option><option value="96">96 kbps</option>
      </select>
    </div>

    <div class="group">
      <label class="check"><input type="checkbox" id="subs">Download Subtitles</label>
      <div class="sub" id="subOpts" hidden>
        <label class="f" for="subLangs" style="margin-top:4px">Subtitle Languages</label>
        <input type="text" id="subLangs" value="zh-Hans,zh-Hant,zh,en" spellcheck="false">
        <label class="check"><input type="checkbox" id="autoSubs">Use auto-generated if manual subtitles are unavailable</label>
        <label class="check only-mp4"><input type="checkbox" id="embedSubs">Embed into MP4 (keep .srt)</label>
      </div>
      <label class="check"><input type="checkbox" id="cover">Download cover and embed into file</label>
      <label class="check sub" id="keepCoverRow" hidden><input type="checkbox" id="keepCover">Keep an extra jpg cover file</label>
    </div>

    <div class="group">
      <label class="check"><input type="checkbox" id="noPlaylist">If URL contains a playlist, download only this video</label>
      <label class="f" for="items" style="margin-top:6px">Playlist range (leave empty for all)</label>
      <input type="text" id="items" placeholder="e.g., 1-5,8" spellcheck="false">
    </div>

    <details class="adv">
      <summary>Advanced Settings</summary>
      <label class="f" for="cookieSrc">Cookies (for logged-in or member-only videos)</label>
      <select id="cookieSrc">
        <option value="">None</option>
        <option value="file" disabled>Uploaded cookies.txt</option>
        <optgroup label="Read from a browser">
          <option>chrome</option><option>edge</option><option>firefox</option><option>brave</option>
          <option>chromium</option><option>opera</option><option>vivaldi</option><option>safari</option>
        </optgroup>
      </select>
      <div class="cookie-box">
        <p class="muted small" id="cookieStatus">No cookies.txt uploaded.</p>
        <div class="cookie-actions">
          <button class="btn small" id="cookieUp" type="button">Upload cookies.txt</button>
          <button class="btn small" id="cookieDel" type="button" hidden>Remove</button>
          <input type="file" id="cookieFile" accept=".txt,text/plain" hidden>
        </div>
        <p class="muted small">Reading cookies straight from Chrome or Edge can fail on Windows while the browser is open; an exported cookies.txt avoids that. YouTube rotates account cookies, so export from a private window and do not reuse that window afterwards
          (<a href="https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies" target="_blank" rel="noopener">how to export</a>). The file is stored outside your download folder and every run works on its own copy.</p>
      </div>
      <label class="f" for="referer">Referer (for hotlink protection)</label>
      <input type="text" id="referer" placeholder="https://example.com/" spellcheck="false">
      <label class="f" for="proxy">Proxy</label>
      <input type="text" id="proxy" placeholder="http://127.0.0.1:7890" spellcheck="false">
      <div class="row">
        <div><label class="f" for="limit">Rate Limit</label><input type="text" id="limit" placeholder="e.g., 2M" spellcheck="false"></div>
        <div><label class="f" for="threads">Concurrent Fragments</label><input type="number" id="threads" min="1" max="16" value="4"></div>
      </div>
      <label class="f" for="sleep">Wait between downloads (seconds)</label>
      <input type="number" id="sleep" min="0" max="60" step="0.5" value="0">
      <label class="check"><input type="checkbox" id="archive">Skip already downloaded videos</label>
      <label class="check"><input type="checkbox" id="allSniffed">Download all when multiple video URLs are found on the page</label>
      <label class="check"><input type="checkbox" id="jsRender" disabled>If no video is found, render page with headless browser to grab</label>
      <p class="muted small sub" id="jsHint" style="margin-top:0"></p>
    </details>

    <div class="actions">
      <button class="btn" id="probeBtn" type="button">Parse URL</button>
      <button class="btn primary" id="start" type="button">Start Download</button>
    </div>
  </section>

  <div class="queue">
    <section aria-label="Queue">
      <div class="sec-head"><h2>Queue</h2><div class="sec-tools"><span id="count" class="muted small"></span><button class="btn small" id="clearBtn" type="button">Clear Finished</button></div></div>
      <div class="filters">
        <input type="search" id="q" placeholder="Search title, URL, or filename" spellcheck="false">
        <select id="flt" aria-label="Filter by status">
          <option value="all">All</option><option value="active">Active</option><option value="done">Done</option><option value="bad">Failed or Canceled</option>
        </select>
      </div>
      <div class="list">
        <div id="jobsEmpty" class="empty">Queue is empty. Paste a URL and click 'Start Download'.</div>
        <div id="jobsNoMatch" class="empty" hidden>No matching tasks.</div>
        <div id="jobs"></div>
      </div>
    </section>
    <section aria-label="Downloaded Files">
      <div class="sec-head"><h2>Downloaded Files</h2><button class="btn small" id="refreshFiles" type="button">Refresh</button></div>
      <div class="list">
        <div id="filesEmpty" class="empty">No completed files yet.</div>
        <div id="files"></div>
      </div>
    </section>
  </div>
</main>
<div id="drop" hidden>Release mouse to add links inside</div>
<div id="toast" hidden></div>

<script>
const TOKEN = "__TOKEN__";
const $ = s => document.querySelector(s);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

async function api(path, body) {
  const r = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: {"X-Token": TOKEN, "Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

let toastTimer;
function toast(msg, bad) {
  const t = $("#toast");
  t.textContent = msg; t.className = bad ? "bad" : ""; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
}

const fmtSize = n => n >= 1073741824 ? (n / 1073741824).toFixed(2) + " GB" : n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
const fmtDur = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0"); };
const fileUrl = p => "/files/" + p.split("/").map(encodeURIComponent).join("/") + "?t=" + encodeURIComponent(TOKEN);

// ── Form ──
function readOptions() {
  return {
    mode: document.querySelector("input[name=mode]:checked").value,
    quality: $("#quality").value, abr: +$("#abr").value,
    subs: $("#subs").checked, sub_langs: $("#subLangs").value.trim(),
    auto_subs: $("#autoSubs").checked, embed_subs: $("#embedSubs").checked,
    cover: $("#cover").checked, keep_cover: $("#keepCover").checked,
    no_playlist: $("#noPlaylist").checked, items: $("#items").value.trim(),
    archive: $("#archive").checked, cookies_from_browser: ["", "file"].includes($("#cookieSrc").value) ? "" : $("#cookieSrc").value,
    use_cookies_file: $("#cookieSrc").value === "file",
    referer: $("#referer").value.trim(), proxy: $("#proxy").value.trim(),
    limit_rate: $("#limit").value.trim(), threads: +$("#threads").value || 4,
    sleep: +$("#sleep").value || 0, all_sniffed: $("#allSniffed").checked,
    js_render: $("#jsRender").checked && !$("#jsRender").disabled
  };
}
function syncForm() {
  document.body.dataset.mode = document.querySelector("input[name=mode]:checked").value;
  $("#subOpts").hidden = !$("#subs").checked;
  $("#keepCoverRow").hidden = !$("#cover").checked;
}
function saveOptions() { try { localStorage.setItem("grab-options", JSON.stringify(readOptions())); } catch (e) {} }
function setQuality(v) {
  const sel = $("#quality");
  v = String(v);
  if (![...sel.options].some(o => o.value === v)) {
    const o = el("option", null, v + "p"); o.value = v; sel.append(o);
  }
  sel.value = v;
}
function restoreOptions() {
  let o = null;
  try { o = JSON.parse(localStorage.getItem("grab-options") || "null"); } catch (e) {}
  if (!o) return;
  const set = (id, v) => { if (v !== undefined && v !== null) $(id).value = v; };
  const chk = (id, v) => { if (v !== undefined) $(id).checked = !!v; };
  (document.querySelector("input[name=mode][value=" + (o.mode === "mp3" ? "mp3" : "mp4") + "]")).checked = true;
  if (o.quality) setQuality(o.quality);
  set("#abr", o.abr); set("#subLangs", o.sub_langs); set("#items", o.items); wantFileCookies = !!o.use_cookies_file; set("#cookieSrc", o.use_cookies_file ? "" : o.cookies_from_browser);
  set("#referer", o.referer); set("#proxy", o.proxy); set("#limit", o.limit_rate); set("#threads", o.threads); set("#sleep", o.sleep);
  chk("#subs", o.subs); chk("#autoSubs", o.auto_subs); chk("#embedSubs", o.embed_subs); chk("#cover", o.cover);
  chk("#keepCover", o.keep_cover); chk("#noPlaylist", o.no_playlist); chk("#archive", o.archive); chk("#allSniffed", o.all_sniffed);
  chk("#jsRender", o.js_render);
}
document.querySelectorAll("input,select").forEach(e => e.addEventListener("change", () => { syncForm(); saveOptions(); }));

const readUrls = () => $("#urls").value.split("\n").map(s => s.trim()).filter(s => s && !s.startsWith("#"));

$("#start").onclick = async () => {
  const urls = readUrls();
  if (!urls.length) return toast("Paste at least one URL first", true);
  try {
    const r = await api("/api/jobs", {urls, options: readOptions()});
    $("#urls").value = ""; $("#probe").hidden = true;
    toast("Added to queue: " + r.ids.length + " links");
    poll();
  } catch (e) { toast(e.message, true); }
};

$("#probeBtn").onclick = async () => {
  const urls = readUrls();
  if (!urls.length) return toast("Paste a URL first", true);
  const box = $("#probe"); box.hidden = false;
  box.replaceChildren(el("p", "muted", "Parsing " + (urls.length > 1 ? "the first link " : "") + "..." + (readOptions().js_render ? " (Page rendering enabled, this may take a few seconds)" : "")));
  $("#probeBtn").disabled = true;
  try { renderProbe(await api("/api/probe", {url: urls[0], options: readOptions()})); }
  catch (e) { box.replaceChildren(el("p", "err", e.message)); }
  finally { $("#probeBtn").disabled = false; }
};

function renderProbe(r) {
  const box = $("#probe"); box.replaceChildren();
  if (r.error) { box.append(el("p", "err", r.error)); return; }
  if (r.kind === "video") {
    const head = el("div", "pr-head");
    if (r.thumbnail) { const im = el("img"); im.src = r.thumbnail; im.alt = ""; im.referrerPolicy = "no-referrer"; head.append(im); }
    const t = el("div"); t.append(el("strong", null, r.title || "(No title)"));
    const meta = [r.uploader, r.duration ? fmtDur(r.duration) : "", r.extractor].filter(Boolean).join("   ");
    if (meta) t.append(el("div", "muted small", meta));
    head.append(t); box.append(head);
    if (r.heights && r.heights.length) {
      const row = el("div", "chips"); row.append(el("span", "muted small", "Quality Options"));
      r.heights.slice(0, 6).forEach(h => {
        const b = el("button", "chip", h + "p"); b.type = "button";
        b.onclick = () => { setQuality(h); $("#m-mp4").checked = true; syncForm(); saveOptions(); toast("Max quality set to " + h + "p"); };
        row.append(b);
      });
      box.append(row);
    }
  } else if (r.kind === "playlist") {
    box.append(el("strong", null, r.title || "Playlist"));
    box.append(el("div", "muted small", "Total " + r.count + " items. You can limit the range in 'Playlist range' below."));
    if (r.items && r.items.length) { const ul = el("ul"); r.items.forEach(x => ul.append(el("li", null, x))); box.append(ul); }
  } else if (r.kind === "page") {
    box.append(el("strong", null, r.title || "Webpage"));
    box.append(el("div", "muted small", r.rendered
      ? "Captured " + r.count + " media requests when loading page with headless browser, will try each sequentially when downloading."
      : "yt-dlp lacks a dedicated extractor, but found " + r.count + " media URLs in the page, will try each sequentially when downloading."));
    const ul = el("ul"); r.sources.forEach(x => ul.append(el("li", null, x))); box.append(ul);
  }
}

// ── Queue ──
const nodes = new Map(), openLogs = new Set();

function makeJob(j) {
  const n = el("article", "job"); n.dataset.id = j.id;
  const main = el("div"); main.style.minWidth = "0";
  main.append(el("div", "job-title"), el("div", "job-meta"), el("div", "job-files"), el("div", "job-err"), el("div", "job-note"));
  const side = el("div", "job-side"); side.append(el("div", "pct"), el("div", "job-btns"));
  const log = el("details", "job-log"); log.append(el("summary", null, "Log"), el("pre"));
  log.addEventListener("toggle", () => { if (log.open) { openLogs.add(j.id); refreshLog(j.id); } else openLogs.delete(j.id); });
  n.append(main, side, log);
  return n;
}
async function refreshLog(id) {
  const n = nodes.get(id); if (!n) return;
  try {
    const r = await api("/api/jobs/" + id + "/log");
    const pre = n.querySelector("pre");
    const atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
    pre.textContent = r.lines.join("\n");
    if (atEnd) pre.scrollTop = pre.scrollHeight;
  } catch (e) {}
}
async function act(id, what, msg) {
  try { await api("/api/jobs/" + id + "/" + what, {}); if (msg) toast(msg); poll(); } catch (e) { toast(e.message, true); }
}
const fmtTime = t => new Date(t * 1000).toLocaleString([], {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"});
function updateJob(n, j) {
  n._job = j;
  n.dataset.status = j.status;
  n.style.setProperty("--p", (j.status === "done" ? 100 : j.percent) + "%");
  const title = n.querySelector(".job-title"); title.textContent = j.title || j.url; title.title = j.url;

  const meta = n.querySelector(".job-meta"); meta.replaceChildren();
  const bits = j.status === "running" ? [j.stage, j.item && "Item " + j.item, j.speed, j.eta && "ETA " + j.eta]
    : [j.status === "queued" ? "Queued" : j.item && "Total " + j.item.split("/")[1], j.stage === "Last incomplete" && j.stage, j.finished && fmtTime(j.finished)];
  bits.filter(Boolean).forEach(t => meta.append(el("span", null, t)));

  const pct = n.querySelector(".pct");
  const word = {queued: "Wait", done: "Done", error: "Failed", canceled: "Canceled"}[j.status];
  pct.textContent = word || Math.round(j.percent) + "%";
  pct.classList.toggle("word", !!word && j.status !== "done");

  n.querySelector(".job-err").textContent = j.status === "error" ? j.error : "";
  n.querySelector(".job-note").textContent = (j.notes || []).map(t => "Note: " + t).join("\n");

  const fk = JSON.stringify(j.files), files = n.querySelector(".job-files");
  if (files.dataset.k !== fk) {
    files.dataset.k = fk; files.replaceChildren();
    j.files.forEach(f => { const a = el("a", null, f.name); a.href = fileUrl(f.path); a.target = "_blank"; a.rel = "noopener"; a.title = "Play in new tab"; files.append(a); });
  }

  const btns = n.querySelector(".job-btns"), bk = j.status + (j.stage === "Canceling…" ? "!" : "");
  if (btns.dataset.k !== bk) {
    btns.dataset.k = bk; btns.replaceChildren();
    const add = (label, fn, dis) => { const b = el("button", "btn small", label); b.type = "button"; b.disabled = !!dis; b.onclick = fn; btns.append(b); };
    if (j.status === "queued" || j.status === "running") add(j.stage === "Canceling…" ? "Canceling" : "Cancel", () => act(j.id, "cancel"), j.stage === "Canceling…");
    if (j.status === "done" && j.files.length) add("Open Folder", () => api("/api/open-folder", {path: j.files[0].path}).catch(e => toast(e.message, true)));
    if (j.status === "error" || j.status === "canceled") add("Retry", () => act(j.id, "retry", "Re-added to queue"));
    if (["done", "error", "canceled"].includes(j.status)) add("Remove", () => act(j.id, "remove"));
  }
}
function renderJobs(list) {
  const wrap = $("#jobs");
  const seen = new Set(list.map(j => j.id));
  list.forEach(j => { let n = nodes.get(j.id); if (!n) { n = makeJob(j); nodes.set(j.id, n); } updateJob(n, j); });
  for (const [id, n] of nodes) if (!seen.has(id)) { n.remove(); nodes.delete(id); openLogs.delete(id); }
  let ref = wrap.firstElementChild;
  for (const j of list) { const n = nodes.get(j.id); if (n === ref) ref = ref.nextElementSibling; else wrap.insertBefore(n, ref); }
  openLogs.forEach(refreshLog);
  applyFilter();
}
let filterQ = "", filterS = "all", lastFiles = [];
function renderFiles(list) { lastFiles = list; renderFileRows(); }
function renderFileRows() {
  const box = $("#files"); box.replaceChildren();
  const q = filterQ.trim().toLowerCase();
  const list = q ? lastFiles.filter(f => f.path.toLowerCase().includes(q)) : lastFiles;
  const empty = $("#filesEmpty");
  empty.hidden = list.length > 0;
  empty.textContent = lastFiles.length && !list.length ? "No matching files." : "No completed files yet.";
  list.forEach(f => {
    const row = el("div", "file"); const a = el("a", null, f.path); a.href = fileUrl(f.path); a.target = "_blank"; a.rel = "noopener"; a.title = "Play in new tab";
    row.append(a, el("span", null, fmtSize(f.size)), el("span", null, new Date(f.mtime * 1000).toLocaleString()));
    box.append(row);
  });
}

let rev = -1, restarting = false, lastPw = null;
async function poll() {
  if (restarting) return;
  try {
    const s = await api("/api/state?rev=" + rev);
    $("#ver").textContent = "yt-dlp " + s.version;
    $("#openDir").title = s.root;
    $("#notice").hidden = s.ffmpeg;
    $("#offline").hidden = true;
    if (lastPw !== s.playwright) {
      lastPw = s.playwright;
      $("#jsRender").disabled = !s.playwright;
      $("#jsHint").textContent = s.playwright
        ? "Playwright detected. On Windows, system built-in Edge will be prioritized, no need to download additional browser."
        : "Playwright not detected. Run pip install playwright and restart to enable (No need to download browser if Edge is installed on Windows).";
    }
    renderJobs(s.jobs);
    trackCompletion(s.jobs);
    if (s.files) renderFiles(s.files);
    rev = s.rev;
  } catch (e) { $("#offline").hidden = false; }
}

$("#openDir").onclick = () => api("/api/open-folder", {}).catch(e => toast(e.message, true));
$("#clearBtn").onclick = async () => { try { await api("/api/clear", {}); poll(); } catch (e) { toast(e.message, true); } };


// ── Search & Filters ──
const matches = j => {
  const q = filterQ.trim().toLowerCase();
  if (q && !((j.title || "").toLowerCase().includes(q) || j.url.toLowerCase().includes(q))) return false;
  if (filterS === "active") return j.status === "queued" || j.status === "running";
  if (filterS === "done") return j.status === "done";
  if (filterS === "bad") return j.status === "error" || j.status === "canceled";
  return true;
};
function applyFilter() {
  let shown = 0, first = null;
  for (const n of $("#jobs").children) {
    const ok = !n._job || matches(n._job);
    n.hidden = !ok; n.classList.remove("first");
    if (ok) { shown++; if (!first) first = n; }
  }
  if (first) first.classList.add("first");
  const total = nodes.size;
  $("#jobsEmpty").hidden = total > 0;
  $("#jobsNoMatch").hidden = !(total > 0 && shown === 0);
  $("#count").textContent = !total ? "" : shown === total ? total + " tasks" : "Showing " + shown + " / " + total;
  renderFileRows();
}
$("#q").addEventListener("input", e => { filterQ = e.target.value; applyFilter(); });
$("#flt").addEventListener("change", e => { filterS = e.target.value; applyFilter(); });
$("#refreshFiles").onclick = () => { rev = -1; poll(); };

// ── Paste & Drag-Drop ──
const extractUrls = text => [...new Set((String(text).match(/https?:\/\/[^\s"'<>\\)\]，。）】]+/gi) || []).map(u => u.replace(/[.,;、]+$/, "")))];
function addUrls(list, source) {
  if (!list.length) { toast("No links found", true); return 0; }
  const have = new Set(readUrls()), fresh = list.filter(u => !have.has(u));
  if (!fresh.length) { toast("These links are already in the input box"); return 0; }
  const ta = $("#urls");
  ta.value = (ta.value.trim() ? ta.value.replace(/\s*$/, "\n") : "") + fresh.join("\n") + "\n";
  ta.classList.remove("flash"); void ta.offsetWidth; ta.classList.add("flash");
  toast("Added " + fresh.length + " link(s)" + (source ? " (" + source + ")" : ""));
  return fresh.length;
}
document.addEventListener("paste", e => {
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
  const urls = extractUrls((e.clipboardData && e.clipboardData.getData("text")) || "");
  if (urls.length) { e.preventDefault(); addUrls(urls, "from clipboard"); }
});
$("#pasteBtn").onclick = async () => {
  try { addUrls(extractUrls(await navigator.clipboard.readText()), "from clipboard"); }
  catch (e) { toast("Browser clipboard access denied, please press Ctrl+V directly", true); }
};
let dragDepth = 0;
const hasPayload = e => e.dataTransfer && [...e.dataTransfer.types].some(t => t === "Files" || t === "text/uri-list" || t === "text/plain");
window.addEventListener("dragenter", e => { if (!hasPayload(e)) return; e.preventDefault(); dragDepth++; $("#drop").hidden = false; });
window.addEventListener("dragover", e => { if (hasPayload(e)) e.preventDefault(); });
window.addEventListener("dragleave", e => { if (!hasPayload(e)) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $("#drop").hidden = true; });
window.addEventListener("drop", async e => {
  if (!hasPayload(e)) return;
  e.preventDefault(); dragDepth = 0; $("#drop").hidden = true;
  const dt = e.dataTransfer, urls = [];
  for (const f of [...dt.files].slice(0, 20)) {
    if (!(f.type.startsWith("text/") || /\.(txt|csv|md|list|url|webloc|json|html?)$/i.test(f.name))) { toast(f.name + " is not a text file, skipped", true); continue; }
    if (f.size > 2e6) { toast(f.name + " is too large, skipped", true); continue; }
    try { urls.push(...extractUrls(await f.text())); } catch (_) {}
  }
  if (!dt.files.length) urls.push(...extractUrls(dt.getData("text/uri-list") + "\n" + dt.getData("text/plain")));
  if (dt.files.length || urls.length) addUrls([...new Set(urls)], dt.files.length ? "from dropped files" : "from dropped links");
});

// ── Notifications ──
const lastStatus = new Map();
let wasActive = false, batch = {ok: 0, bad: 0, title: ""}, doneMark = false;
const notifyState = () => ("Notification" in window) ? Notification.permission : "unsupported";
function refreshNotifyBtn() {
  const b = $("#notifyBtn"), st = notifyState();
  if (st === "unsupported") { b.hidden = true; return; }
  b.textContent = st === "granted" ? "Notifications: Enabled" : st === "denied" ? "Notifications Blocked by Browser" : "Enable Completion Notifications";
  b.disabled = st === "denied";
}
$("#notifyBtn").onclick = async () => {
  if (notifyState() === "granted") return toast("Already enabled: you'll be notified when queue finishes and page is not in foreground");
  try { await Notification.requestPermission(); } catch (e) {}
  refreshNotifyBtn();
  if (notifyState() === "granted") { try { new Notification("Video Grabber WebUI", {body: "Notifications Enabled"}); } catch (e) {} }
};
function announceDone(b) {
  const msg = b.bad ? "Completed " + b.ok + ", failed " + b.bad : b.ok === 1 ? "Download complete: " + b.title : b.ok + " downloads completed";
  const away = document.hidden || !document.hasFocus();
  if (away) doneMark = true;
  toast(msg, !!b.bad && !b.ok);
  if (away && notifyState() === "granted") {
    try { const n = new Notification("Video Grabber WebUI", {body: msg, tag: "grab-done"}); n.onclick = () => { window.focus(); n.close(); }; } catch (e) {}
  }
}
function trackCompletion(jobs) {
  let active = 0;
  for (const j of jobs) {
    const prev = lastStatus.get(j.id), was = prev === "queued" || prev === "running";
    if (was && j.status === "done") { batch.ok++; batch.title = j.title || j.url; }
    if (was && j.status === "error") batch.bad++;
    lastStatus.set(j.id, j.status);
    if (j.status === "queued" || j.status === "running") active++;
  }
  if (wasActive && !active && batch.ok + batch.bad > 0) { announceDone(batch); batch = {ok: 0, bad: 0, title: ""}; }
  wasActive = active > 0;
  document.title = active ? "Downloading (" + active + ") - Video Grabber WebUI" : doneMark ? "Done - Video Grabber WebUI" : "Video Grabber WebUI";
}
window.addEventListener("focus", () => { doneMark = false; });

// ── Update yt-dlp ──
function showUpd(text, o) {
  o = o || {};
  $("#upd").hidden = false; $("#updMsg").textContent = text;
  $("#updDo").hidden = !o.canUpdate; $("#updRestart").hidden = !o.canRestart;
}
async function checkUpdate(force, silent) {
  try {
    const r = await api("/api/ytdlp/check" + (force ? "?force=1" : ""));
    const b = $("#updBtn");
    b.classList.toggle("attn", !!(r.newer || r.needs_restart));
    b.textContent = r.needs_restart ? "Restart to complete update" : r.newer ? "Update yt-dlp (new version available)" : "Check for Updates";
    if (r.needs_restart) { if (!silent) showUpd("yt-dlp updated to " + r.installed + ", restart service to apply. A new terminal window may pop up, you can close the old one.", {canRestart: true}); }
    else if (r.error) { if (!silent) showUpd(r.error); }
    else if (r.newer) { if (!silent) showUpd("New version " + r.latest + " available (current " + r.installed + "). Updating often fixes download issues due to site changes.", {canUpdate: true}); }
    else if (!silent) showUpd("Already on the latest version (" + r.installed + ").");
    return r;
  } catch (e) { if (!silent) toast(e.message, true); }
}
$("#updBtn").onclick = () => checkUpdate(true, false);
$("#updClose").onclick = () => { $("#upd").hidden = true; };
let updTimer = null;
async function pollUpdate() {
  clearTimeout(updTimer);
  let s;
  try { s = await api("/api/ytdlp/update-status"); } catch (e) { return; }
  const log = $("#updLog"); log.hidden = false; log.textContent = s.lines.join("\n"); log.scrollTop = log.scrollHeight;
  if (s.status === "running") { updTimer = setTimeout(pollUpdate, 800); return; }
  $("#updDo").disabled = false;
  if (s.status === "error") { showUpd(s.error || "Update failed"); return; }
  if (s.extras && s.extras.includes("deno")) {
    showUpd("Components installed. Restart the service so yt-dlp picks them up.", {canRestart: true});
    loadDoctor(false, true);
    return;
  }
  await checkUpdate(true, false);
  loadDoctor(false, true);
}
async function runUpdate(extras) {
  try { await api("/api/ytdlp/update", extras ? {extras} : {}); } catch (e) { return toast(e.message, true); }
  $("#upd").hidden = false; $("#updDo").hidden = true; $("#updRestart").hidden = true; $("#updDo").disabled = true;
  $("#updMsg").textContent = extras ? "Installing components…" : "Updating yt-dlp…";
  $("#updLog").textContent = ""; $("#updLog").hidden = false;
  pollUpdate();
}
$("#updDo").onclick = () => runUpdate();
$("#updRestart").onclick = async () => {
  try { await api("/api/restart", {}); } catch (e) { return toast(e.message, true); }
  restarting = true; $("#offline").hidden = true; toast("Restarting, please wait a few seconds...");
  setTimeout(() => {
    const t = setInterval(async () => {
      try { const r = await fetch("/", {cache: "no-store"}); if (r.ok) { clearInterval(t); location.reload(); } } catch (e) {}
    }, 1000);
  }, 1500);
};


// ── Cookies (uploaded cookies.txt) ──
let wantFileCookies = false;
function applyCookieStatus(st, select) {
  $("#cookieSrc option[value=file]").disabled = !st.present;
  $("#cookieDel").hidden = !st.present;
  const box = $("#cookieStatus");
  if (!st.present) {
    box.textContent = "No cookies.txt uploaded.";
    if ($("#cookieSrc").value === "file") { $("#cookieSrc").value = ""; saveOptions(); }
    return;
  }
  const bits = [st.cookies + (st.cookies === 1 ? " cookie" : " cookies") + " for " + st.domain_count + (st.domain_count === 1 ? " site" : " sites")];
  if (st.expired) bits.push(st.expired + " already expired");
  if (st.has_youtube) bits.push(st.youtube_login ? "YouTube sign-in found" : "no YouTube sign-in cookies");
  if (st.has_bilibili) bits.push(st.bilibili_login ? "Bilibili sign-in found" : "no Bilibili sign-in cookie");
  box.textContent = bits.join("; ") + ".";
  if (select || wantFileCookies) { $("#cookieSrc").value = "file"; wantFileCookies = false; saveOptions(); }
}
async function loadCookies() { try { applyCookieStatus(await api("/api/cookies")); } catch (e) {} }
$("#cookieUp").onclick = () => $("#cookieFile").click();
$("#cookieFile").addEventListener("change", async e => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  if (f.size > 3e6) return toast("That file is larger than 3 MB, so it is probably not a cookies.txt.", true);
  try { applyCookieStatus(await api("/api/cookies", {text: await f.text()}), true); toast("cookies.txt uploaded"); }
  catch (err) { toast(err.message, true); }
});
$("#cookieDel").onclick = async () => {
  try { applyCookieStatus(await api("/api/cookies/delete", {})); toast("cookies.txt removed"); } catch (e) { toast(e.message, true); }
};

// ── Diagnostics ──
let lastDoctor = null;
const STATUS_TEXT = {ok: "OK", info: "Info", warn: "Warning", error: "Problem"};
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {}
  const ta = el("textarea"); ta.value = text; ta.style.cssText = "position:fixed;opacity:0";
  document.body.append(ta); ta.select();
  let ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
  ta.remove(); return ok;
}
function renderDoctor(d) {
  const list = $("#docList"); list.replaceChildren();
  d.checks.forEach(c => {
    const row = el("div", "doc-row"), main = el("div");
    main.append(el("div", "lbl", c.label), el("div", "det", c.detail));
    if (c.fix || c.action) {
      const fix = el("div", "doc-fix");
      if (c.fix) {
        fix.append(el("code", null, c.fix));
        const cp = el("button", "btn small", "Copy"); cp.type = "button";
        cp.onclick = async () => toast((await copyText(c.fix)) ? "Copied" : "Could not copy", false);
        fix.append(cp);
      }
      if (c.action) {
        const go = el("button", "btn small primary", "Install now"); go.type = "button";
        go.onclick = () => runUpdate(c.action === "install_components" ? "default,deno" : "default");
        fix.append(go);
      }
      main.append(fix);
    }
    row.append(el("span", "badge " + c.status, STATUS_TEXT[c.status] || c.status), main);
    list.append(row);
  });
}
async function loadDoctor(net, silent) {
  if (!silent) { $("#doctor").hidden = false; $("#docList").replaceChildren(el("p", "muted", net ? "Testing the network…" : "Checking…")); }
  try {
    const d = await api("/api/doctor?" + (net ? "net=1" : silent ? "" : "force=1"));
    lastDoctor = d;
    if (!$("#doctor").hidden) renderDoctor(d);
    updateEnvNotice(d);
    return d;
  } catch (e) { if (!silent) $("#docList").replaceChildren(el("p", "err", e.message)); }
}
function updateEnvNotice(d) {
  const bad = d.checks.filter(c => (c.id === "js_runtime" || c.id === "ejs") && (c.status === "warn" || c.status === "error"));
  const sig = bad.map(c => c.id).join(",");
  let dismissed = ""; try { dismissed = localStorage.getItem("grab-env-dismissed") || ""; } catch (e) {}
  if (!bad.length || dismissed === sig) { $("#envNotice").hidden = true; return; }
  $("#envMsg").textContent = "YouTube setup incomplete: " + bad.map(c => c.label).join(" and ") + " not detected. Some YouTube formats may be unavailable.";
  $("#envNotice").dataset.sig = sig; $("#envNotice").hidden = false;
}
$("#docBtn").onclick = () => loadDoctor(false, false);
$("#docRecheck").onclick = () => loadDoctor(false, false);
$("#docNet").onclick = () => loadDoctor(true, false);
$("#docCopy").onclick = async () => {
  if (!lastDoctor) return toast("Run a check first", true);
  toast((await copyText(lastDoctor.report)) ? "Report copied. Read it before you share it." : "Could not copy", false);
};
$("#docClose").onclick = () => { $("#doctor").hidden = true; };
$("#envOpen").onclick = () => loadDoctor(false, false);
$("#envDismiss").onclick = () => {
  try { localStorage.setItem("grab-env-dismissed", $("#envNotice").dataset.sig || ""); } catch (e) {}
  $("#envNotice").hidden = true;
};

restoreOptions(); syncForm(); refreshNotifyBtn(); poll(); checkUpdate(false, true); loadCookies(); loadDoctor(false, true);
setInterval(() => { if (!document.hidden) poll(); }, 1000);
</script>
</body>
</html>
"""


# ───────────────────────── Entry Point ─────────────────────────
def open_native_window(url: str) -> bool:
    """Try to open url in its own pywebview window. Returns False if pywebview is not installed
    (the caller then falls back to a browser tab). Blocks until the window is closed."""
    try:
        import webview
    except ImportError:
        return False
    webview.create_window("Video Grabber", url, width=1180, height=860, min_size=(760, 560))
    webview.start()
    return True


def main() -> None:
    global ROOT, PORT, WORKERS, WINDOW_MODE, UI_MODE
    ap = argparse.ArgumentParser(description="Local Web UI for grab.py")
    ap.add_argument("--dir", default="downloads", help="Download directory (default: ./downloads)")
    ap.add_argument("--port", type=int, default=8765, help="Starting port, will auto-increment if occupied (default: 8765)")
    ap.add_argument("--workers", type=int, default=2, help="Concurrent download task count (default: 2)")
    ap.add_argument("--ui", choices=("window", "browser", "none"), default="window",
                    help="window: a native app window (needs pywebview, the default); "
                         "browser: open your default browser instead; "
                         "none: do not open anything (for `npm run dev` against this backend)")
    ap.add_argument("--no-browser", dest="ui", action="store_const", const="none",
                    help=argparse.SUPPRESS)  # kept for older scripts; same as --ui none
    a = ap.parse_args()

    ROOT = Path(a.dir).expanduser().resolve()
    ROOT.mkdir(parents=True, exist_ok=True)
    load_history()
    WORKERS = max(1, min(a.workers, 6))
    for _ in range(WORKERS):
        threading.Thread(target=worker, daemon=True).start()

    restarting = os.environ.get("GRAB_WEBUI_RESTART") == "1"
    ui_mode = "none" if restarting else a.ui  # a restart only replaces the server; the old window/tab is kept
    ports = [a.port] if restarting else list(range(a.port, a.port + 20))
    srv = None
    for _attempt in range(30 if restarting else 1):  # When restarting, the old process might still hold the port, wait a bit
        for port in ports:
            try:
                srv = Server(("127.0.0.1", port), Handler)
                break
            except OSError:
                continue
        if srv:
            break
        time.sleep(0.5)
    if srv is None:
        sys.exit(f"Ports {ports[0]}-{ports[-1]} are all occupied, please use --port to specify another port.")

    PORT = srv.server_port
    WINDOW_MODE = ui_mode == "window"
    UI_MODE = ui_mode
    url = f"http://127.0.0.1:{PORT}/"
    print(("Restarted:" if restarting else "Video Grabber WebUI started:") + url)
    print(f"Download Directory: {ROOT}")
    if not shutil.which("ffmpeg"):
        print("Hint: ffmpeg not found, merging audio/video and MP3 conversion will fail.")

    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        if ui_mode == "window":
            print("Close the window to stop.")
            if not open_native_window(url):
                print("Hint: pywebview is not installed, opening your browser instead. Run: pip install pywebview")
                WINDOW_MODE = False
                UI_MODE = "browser"
                webbrowser.open(url)
                threading.Event().wait()
        else:
            if ui_mode == "browser":
                webbrowser.open(url)
            print("Press Ctrl+C to stop.")
            threading.Event().wait()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
