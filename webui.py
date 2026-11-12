"""
webui.py - a local web interface for grab.py

Usage
  python webui.py                                   # opens in its own window; downloads to ./downloads
  python webui.py --ui browser                       # open in your default browser tab instead
  python webui.py --dir D:/videos --port 8765 --workers 2

Notes
  * Listens on 127.0.0.1 only. Requests need a random token created at startup and the Host
    header is checked, so other web pages cannot drive this program through your browser.
  * The start page that carries the token is only served to our own window or browser tab (they open
    the launch link printed at startup, which sets an HttpOnly session cookie), and to the Chrome
    extension when "Allow the Chrome extension to connect" is switched on. Other programs on this
    computer get an empty "locked" page.
  * Needs grab.py in the same folder, plus:  pip install -U "yt-dlp[default]"  and ffmpeg.
    YouTube also needs a JavaScript runtime (Deno). Open "Diagnostics" in the page to check.
  * Uploaded cookies.txt is stored outside the download folder (see "Diagnostics" for the path)
    and is never served back to the browser.
  * The interface is the React app built into webui_dist/ (see frontend/README.md to rebuild it).
    --ui window needs the optional pywebview package; without it, this falls back to your browser.
"""
from __future__ import annotations

import hmac
import http.cookies
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
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grab  # noqa: E402
from grab_config import parse_web_config  # noqa: E402
from grab_models import BACKFILL_MAX, Job, Subscription, http_url, normalize_subscription_filters, output_complete  # noqa: E402,F401
from grab_state import JobManager, SubscriptionManager  # noqa: E402
from grab_storage import JsonStore  # noqa: E402
from grab_library import IMPORT_MAX_BYTES, MediaLibrary  # noqa: E402,F401  (IMPORT_MAX_BYTES is read by the library routes)
from grab_organizer import LibraryOrganizer  # noqa: E402
from grab_backup import BACKUP_MAX_BYTES, BackupService  # noqa: E402,F401  (BackupService is used by the library routes)
from grab_repair import repair, repair_options  # noqa: E402
from grab_archive import seed_archive  # noqa: E402
from grab_errors import error_details, fmt_eta, fmt_speed, friendly_error, strip_ansi  # noqa: E402
import grab_cookies  # noqa: E402
import webui_routes_library  # noqa: E402
import webui_routes_jobs  # noqa: E402
import webui_routes_subscriptions  # noqa: E402
import webui_routes_system  # noqa: E402
from grab_subscriptions import (  # noqa: E402
    filter_subscription_entries, normalize_flat_entries, split_backfill, subscription_filter_reason,
)
from grab_cookies import parse_cookies  # noqa: E402,F401
from grab_download import optional_video_cover_downloader, tracking_downloader  # noqa: E402
from grab_images import IMAGE_SUFFIXES, download_image, image_title, probe_image, thumbnail_downloader  # noqa: E402
import yt_dlp  # noqa: E402
from yt_dlp.utils import DownloadCancelled, DownloadError  # noqa: E402

ROOT = Path("downloads").resolve()
TOKEN = secrets.token_urlsafe(24)
# The page that carries TOKEN is only handed to clients that prove they were launched by this app:
# either the launch link (?n=...) given to our own window or browser tab, or the session cookie that
# link sets. A restart keeps the session secret so an already open tab can reload.
LAUNCH_SECRET = secrets.token_urlsafe(24)
_inherited_session = os.environ.pop("GRAB_SESSION_SECRET", "")
SESSION_SECRET = (_inherited_session if re.fullmatch(r"[A-Za-z0-9_-]{16,64}", _inherited_session)
                  else secrets.token_urlsafe(24))
SESSION_COOKIE = "grab_session"
BROWSERS = {"chrome", "edge", "firefox", "brave", "chromium", "opera", "vivaldi", "safari"}
# The React app, built by `npm run build` in frontend/ (see frontend/README.md). Shipped pre-built,
# so running the backend never requires Node. Falls back to the legacy inline page if missing.
UI_DIST = Path(__file__).resolve().parent / "webui_dist"
ALLOWED_STATIC_EXT = {".js", ".css", ".svg", ".png", ".ico", ".woff", ".woff2", ".map", ".json", ".webmanifest", ".txt"}
WINDOW_MODE = False  # set from main(): running inside a pywebview window rather than a browser tab
NATIVE_WINDOW = None
NATIVE_DESKTOP = None
PENDING_ROOT = None
FOLDER_PICK_LOCK = threading.Lock()
SETTINGS_LOCK = threading.Lock()
MEDIA_SUFFIX = {".mp4", ".webm", ".mkv", ".mov"} | grab.AUDIO_SUFFIXES | IMAGE_SUFFIXES
LIBRARY = MediaLibrary(lambda: ROOT, MEDIA_SUFFIX)

FILES_REV = 0
PORT = 0
WORKERS = 2
UI_MODE = "browser"
HISTORY_MAX = 500
JOB_MANAGER = JobManager(HISTORY_MAX)
# Compatibility aliases for existing integrations and tests. New code goes through JOB_MANAGER.
JOBS = JOB_MANAGER.jobs
QUEUE = JOB_MANAGER.queue
ORGANIZER = LibraryOrganizer(LIBRARY, lambda: library_records(),
                             lambda: any(job.status == "running" for job in JOB_MANAGER.snapshot()))
STOP_EVENT = threading.Event()
_SAVE_LOCK = threading.Lock()
_HISTORY_SNAPSHOT_LOCK = threading.Lock()
FILES_CACHE: dict = {"rev": None, "ts": 0.0, "data": []}
FILE_SCAN_MAX_ENTRIES = 20000
FILE_SCAN_MAX_DEPTH = 3
_FILES_SCAN_LOCK = threading.Lock()
UPDATE: dict = {"status": "idle", "lines": [], "before": "", "after": "", "error": "", "extras": ""}
UPDATE_LOCK = threading.Lock()
PYPI_CACHE: dict = {"ts": 0.0, "latest": None}
# Settings that must not live in the (possibly synced or shared) download folder, e.g. cookies.txt
CONFIG_DIR = Path(os.environ.get("GRAB_CONFIG_DIR") or (Path(os.environ.get("APPDATA") or (Path.home() / ".config")) / "grab-webui"))
DOCTOR_CACHE: dict = {"ts": 0.0, "data": None}
LOCKED_PAGE = (b"<!doctype html><meta charset=utf-8><title>Video Grabber</title>"
               b'<body style="font:16px system-ui;max-width:34rem;margin:4rem auto;padding:0 1rem">'
               b"<h1>Video Grabber is running</h1>"
               b"<p>This page can only be opened by the app itself. Use the Video Grabber window, "
               b"or the link printed in the terminal where it was started.</p>")
COOKIES_MAX_BYTES = 3_000_000
BODY_MAX_BYTES = 1_000_000

# Warnings from yt-dlp that deserve a visible note on the job (matched on the lower-cased log line)
NOTE_RULES = [
    (("javascript runtime", "challenge solving failed", "signature solving failed"), "js",
     "YouTube challenge solving failed, so some formats may be missing. Install Deno and yt-dlp-ejs from the Diagnostics panel."),
    (("cookies are no longer valid", "likely been rotated"), "rotated",
     "YouTube rotated or expired your cookies. Export a fresh cookies.txt from a private window and upload it again."),
    (("attempting impersonation", "no impersonate target"), "impersonation",
     "This site may require browser impersonation. Install the recommended yt-dlp components from Diagnostics."),
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


def set_job_error(job: Job, msg: str) -> None:
    details = error_details(msg)
    job.error = details["message"]
    job.error_kind = details["kind"]
    job.error_hint = details["hint"]


def make_args(o: dict):
    """Organize options submitted from the web page into a parameter object for grab.py, validating item by item."""
    a = grab.parse_args([])
    a.output = str(ROOT)
    a.mode = o.get("mode") if o.get("mode") in ("mp4", "mp3", "original", "cover", "image") else "mp4"
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
    # Library needs the sidecar even after yt-dlp embeds the cover into an MP4.
    a.cover = a.mode == "mp4" or bool(o.get("cover"))
    a.keep_cover = a.mode in ("mp4", "original") or bool(o.get("keep_cover"))
    a.no_playlist = bool(o.get("no_playlist"))
    items = str(o.get("items") or "").strip()
    a.items = items if re.fullmatch(r"[\d,\-:]+", items) else None
    # Video and audio keep separate skip lists, so having a video as MP3 never hides it from an MP4 request.
    a.archive = (str(ROOT / (".archive-audio.txt" if a.mode in ("mp3", "original") else ".archive.txt"))
                 if o.get("archive") else None)
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


def download_profile(args) -> dict:
    profile = {"mode": args.mode}
    if args.mode == "mp4":
        profile.update(quality=args.quality, subs=args.subs, embed_subs=args.embed_subs)
        if args.subs or args.embed_subs:
            profile.update(sub_langs=args.sub_langs, auto_subs=args.auto_subs)
    elif args.mode == "mp3":
        profile["abr"] = args.abr
    if args.mode in ("mp3", "original"):
        profile.update(cover=args.cover, keep_cover=args.keep_cover)
    return profile


def source_identity(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return ""
    if "@" in parsed.netloc:
        return parsed._replace(fragment="").geturl()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
        video = parsed.path.strip("/") if host == "youtu.be" else (parse_qs(parsed.query).get("v") or [""])[0]
        if not video and parsed.path.startswith(("/shorts/", "/live/")):
            video = parsed.path.split("/")[2]
        if re.fullmatch(r"[\w-]{11}", video):
            return "youtube:" + video
    return parsed._replace(fragment="", netloc=parsed.netloc.lower()).geturl()


def downloaded_matches(urls: list[str], options: dict) -> list[dict]:
    """Offer existing complete files, never infer that one entry represents an entire playlist."""
    args = make_args(options)
    wanted = download_profile(args)
    if args.items or args.all_sniffed:
        return []
    targets = {}
    for url in urls:
        identity = source_identity(url)
        if identity and (args.no_playlist or "list" not in parse_qs(urlparse(url).query)):
            targets.setdefault(identity, []).append(url)
    known = {}
    for job in JOB_MANAGER.snapshot():
        if job.status == "done":
            for path in job.files:
                known[str(Path(path).resolve())] = download_profile(make_args(job.options))
    matches = []
    for relative, record in LIBRARY.load()["files"].items():
        if not isinstance(record, dict) or record.get("complete") is not True:
            continue
        matched_urls = targets.get(source_identity(http_url(record.get("source_url")) or ""), [])
        if not matched_urls:
            continue
        try:
            path = LIBRARY.media_path(relative)
            if not path.stat().st_size:
                continue
        except (OSError, ValueError):
            continue
        profile = record.get("download_profile") or known.get(str(path.resolve()))
        if not isinstance(profile, dict):
            profile = None
        suffix = path.suffix.lower()
        if ((args.mode == "mp4" and suffix != ".mp4") or
                (args.mode == "mp3" and suffix != ".mp3") or
                (args.mode == "original" and suffix not in grab.AUDIO_SUFFIXES) or
                (args.mode in ("cover", "image") and suffix not in IMAGE_SUFFIXES)):
            continue
        for url in matched_urls:
            matches.append({"url": url, "path": relative, "name": path.name, "profile_known": bool(profile),
                            "settings_match": profile == wanted,
                            "profile": {key: profile[key] for key in ("mode", "quality", "abr") if key in profile} if isinstance(profile, dict) else {}})
    return matches


# ───────────────────────── Jobs ─────────────────────────
def _library_file_is_complete(relative: str) -> bool:
    try:
        return LIBRARY.media_path(relative).stat().st_size > 0
    except (OSError, ValueError):
        return False


def run_job(job: Job) -> None:
    if "_repair_path" in job.options:
        return run_repair_job(job)
    args = make_args(job.options)
    # A differently configured task may have finished while this one was waiting.
    copy_download = job.options.get("_download_copy") is True or any(
        item["profile_known"] and not item["settings_match"]
        for item in downloaded_matches([job.url], job.options)
    )
    if copy_download:
        job.options["_download_copy"] = True
    job.failed_items = []
    if job.cancel.is_set():
        raise DownloadCancelled("Canceled")
    if args.mode in ("mp4", "mp3", "original"):
        status = grab.media_tool_check("ffmpeg")
        if status["status"] != "ok":
            message = "[ffmpeg preflight] " + status["detail"]
            job.log.append(message)
            job.status, job.stage, job.percent, job.speed, job.eta = "error", "Failed", 0.0, "", ""
            set_job_error(job, message)
            return

    if args.archive and args.mode in ("mp4", "mp3", "original") and not copy_download:
        # yt-dlp only skips what it recorded itself, so tell it about files the Library already has.
        try:
            seed_archive(Path(args.archive), library_records(),
                         kind="video" if args.mode == "mp4" else "audio",
                         audio_suffixes=grab.AUDIO_SUFFIXES, is_complete_file=_library_file_is_complete)
        except OSError as error:
            job.log.append(f"Warning: Could not prepare the skip list: {error}")

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

    def track(path, info=None, *, complete=False) -> None:
        if path and path not in job.seen_paths:
            job.seen_paths.append(path)
        if path:
            info = info or {}
            job.media_metadata[path] = {
                "source_url": http_url(info.get("webpage_url")) or job.url,
                "title": info.get("title") or job.title,
                "role": "image" if args.mode in ("cover", "image") else "media",
                "complete": complete,
                "repair_options": repair_options(vars(args)),
                "download_profile": download_profile(args),
            }

    def image_progress(data):
        on_progress({**data, "status": "downloading"})

    def image_done(path, info):
        check()
        track(path, info, complete=True)
        job.title = info.get("title") or job.title
        if info.get("playlist_index"):
            job.item = f"{info['playlist_index']}/{info.get('playlist_count') or info.get('n_entries') or '?'}"

    def on_progress(d: dict) -> None:
        check()
        if d.get("retry_attempt"):
            job.stage, job.speed, job.eta = f"Reconnecting ({d['retry_attempt']}/2)", "", ""
            return
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
            track(d.get("filename") or info.get("filepath"), info)

    def on_pp(d: dict) -> None:
        check()
        if d.get("status") == "started":
            job.stage = PP_LABEL.get(d.get("postprocessor", ""), "Processing")
        elif d.get("status") == "finished":
            info = d.get("info_dict") or {}
            track(info.get("filepath"), info)

    def on_complete(path: str) -> None:
        check()
        if path not in job.media_metadata:
            track(path)
        job.media_metadata[path]["complete"] = True

    extra = {
        "logger": Logger(), "noprogress": True,
        "retries": 0, "fragment_retries": 0, "extractor_retries": 0,
        "progress_hooks": [on_progress], "postprocessor_hooks": [on_pp],
        "post_hooks": [on_complete] if args.mode in ("mp4", "mp3", "original") else [],
    }

    def download_one(url: str, referer=None, name=None) -> bool:
        work = grab.begin_work(args, job.work_key)
        successful = False
        previous_failures = [dict(item) for item in job.failed_items]
        try:
            opts = grab.build_opts(args, referer, name, work)
            if copy_download:
                opts["outtmpl"] = opts["outtmpl"].replace(".%(ext)s", f" [copy-{job.work_key}].%(ext)s")
            opts.update(extra)
            with cookie_copy(args) as cookiefile:
                if cookiefile:
                    opts["cookiefile"] = cookiefile
                downloader = tracking_downloader(yt_dlp.YoutubeDL, job)
                if args.mode == "mp4":
                    downloader = optional_video_cover_downloader(downloader)
                if args.mode == "original":
                    downloader = grab.original_audio_downloader(downloader)
                if args.mode == "cover":
                    downloader = thumbnail_downloader(downloader, ROOT, check, image_progress, image_done)
                with downloader(opts) as ydl:
                    successful = ydl.download([url]) == 0
                    if not successful and job.failed_items == previous_failures:
                        job.failed_items.append({"url": url, "index": None, "title": name or "",
                                                 "error": job.error})
                    return successful
        except DownloadCancelled:
            raise
        except DownloadError:
            return False
        finally:
            moved = grab.finish_work(work, args, preserve_incomplete=not successful)
            if moved:
                job.seen_paths = [moved.get(x, x) for x in job.seen_paths]
                job.media_metadata = {moved.get(path, path): info for path, info in job.media_metadata.items()}

    def set_title(t: str) -> None:
        job.title, job.title_locked = t, True

    if args.mode == "image":
        job.title, job.stage = image_title(job.url), "Downloading image"
        opts = grab.build_opts(args)
        opts.update(extra)
        with cookie_copy(args) as cookiefile:
            if cookiefile:
                opts["cookiefile"] = cookiefile
            with yt_dlp.YoutubeDL(opts) as ydl:
                base = ROOT / "images" / f"{image_title(job.url)} [copy-{job.work_key}]" if copy_download else None
                path = download_image(ydl, job.url, ROOT, base=base, check=check, progress=image_progress)
        image_done(str(path), {"webpage_url": job.url, "title": job.title})
        ok = True
    else:
        ok = grab.discover_and_download(job.url, args, download_one, log, set_title, check)

    job.files = [p for p in job.seen_paths if Path(p).suffix.lower() in MEDIA_SUFFIX and Path(p).exists()]
    records = {}
    for path in job.files:
        try:
            records[Path(path).resolve().relative_to(ROOT).as_posix()] = job.media_metadata.get(path, {
                "source_url": job.url, "title": job.title,
            })
        except (ValueError, OSError):
            continue
    if records:
        try:
            LIBRARY.remember(records)
        except OSError as e:
            log(f"Warning: Could not save Library metadata: {e}")
    if ok:
        job.status, job.stage, job.percent, job.error = "done", "Done", 100.0, ""
        job.error_kind = job.error_hint = ""
    else:
        job.status, job.stage = "error", "Failed"
        if job.files and error_details(job.error)["kind"] != "ffmpeg":
            job.error = "Some items downloaded, but at least one item failed."
            job.error_kind = "partial"
            job.error_hint = "Retry downloads only the recorded failed items when their identifiers are available."
        else:
            set_job_error(job, job.error)
    job.speed = job.eta = ""


def worker(stop_event: threading.Event | None = None) -> None:
    stop_event = stop_event or STOP_EVENT
    while not stop_event.is_set():
        try:
            job = QUEUE.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            if job.cancel.is_set():
                continue
            save_history()
            run_job(job)
        except DownloadCancelled:
            job.status, job.stage, job.speed, job.eta = "canceled", "Canceled", "", ""
        except (Exception, SystemExit) as e:  # noqa: BLE001
            job.status, job.stage = "error", "Failed"
            set_job_error(job, str(e))
        finally:
            if job.status in ("done", "error", "canceled"):
                job.finished = time.time()
            bump_rev()
            save_history()
            QUEUE.task_done()


def create_jobs(urls: list[str], options: dict, source: str = "") -> list[str]:
    ids = JOB_MANAGER.enqueue(urls, options, source)
    save_history()
    return ids


# ───────────────────────── Parse (No Download) ─────────────────────────
def estimate_media_size(info: dict, args) -> dict:
    """Estimate selected output, keeping unknown sizes distinct from zero."""
    duration = info.get("duration")
    if args.mode == "mp3":
        size = int(duration * args.abr * 1000 / 8) if isinstance(duration, (int, float)) and duration > 0 else None
        return {"bytes": size, "approximate": True}
    formats = info.get("requested_formats") or [info]
    sizes, approximate = [], False
    for fmt in formats:
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        approximate |= not bool(fmt.get("filesize"))
        if not size and isinstance(duration, (int, float)) and duration > 0 and fmt.get("tbr"):
            size = duration * fmt["tbr"] * 1000 / 8
        if not isinstance(size, (int, float)) or size <= 0:
            return {"bytes": None, "approximate": True}
        sizes.append(size)
    return {"bytes": int(sum(sizes)), "approximate": approximate}


def probe(url: str, options: dict) -> dict:
    args = make_args(options)
    if args.mode == "image":
        opts = grab.build_opts(args)
        opts.update(quiet=True, no_warnings=True, socket_timeout=12)
        try:
            with cookie_copy(args) as cookiefile:
                if cookiefile:
                    opts["cookiefile"] = cookiefile
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return probe_image(ydl, url)
        except Exception as error:  # noqa: BLE001 - probe returns a user-visible failure, not a successful result
            return {"error": str(error)}
    opts = {
        "quiet": True, "no_warnings": True, "skip_download": True,
        "extract_flat": "in_playlist", "noplaylist": args.no_playlist,
        "playlistend": 100,
        "format": "bestaudio/best" if args.mode in ("mp3", "original") else grab.video_format(args.quality),
        "socket_timeout": 12, "http_headers": {"User-Agent": grab.UA},
    }
    if args.proxy:
        opts["proxy"] = args.proxy
    if args.cookies_from_browser:
        opts["cookiesfrombrowser"] = (args.cookies_from_browser,)
    if args.referer:
        opts["http_headers"]["Referer"] = args.referer
    opts.update(grab.js_runtime_opts())
    if args.mode == "cover":
        opts.update(ignore_no_formats_error=True)
        opts.pop("format", None)
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
        if args.mode != "cover" and not grab.has_specific_extractor(url):
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
            "playlist_entries": [
                {"index": e.get("playlist_index") or index,
                 "title": e.get("title") or e.get("url") or "", "duration": e.get("duration")}
                for index, e in enumerate(entries[:100], 1) if e
            ],
        }
    heights = sorted(
        {f["height"] for f in info.get("formats") or [] if f.get("height") and f.get("vcodec") != "none"},
        reverse=True,
    )
    return {
        "kind": "cover" if args.mode == "cover" else "video", "title": info.get("title") or "", "uploader": info.get("uploader") or "",
        "duration": info.get("duration"), "thumbnail": info.get("thumbnail") or "",
        "heights": heights if args.mode != "cover" else [], "extractor": info.get("extractor_key") or "",
        "size": estimate_media_size(info, args) if args.mode != "cover" else {"bytes": None, "approximate": False},
        "selection": {"mode": args.mode, "quality": args.quality, "abr": args.abr},
    }


# ───────────────────────── Files ─────────────────────────
def list_files(*, force: bool = False) -> list[dict]:
    with _FILES_SCAN_LOCK:
        return scan_files(force=force)


def library_records():
    with LIBRARY.lock:
        metadata = LIBRARY.load()["files"]
    # Old installations can still associate files with retained job history.
    for job in JOB_MANAGER.snapshot():
        for filename in job.files:
            try:
                relative = Path(filename).resolve().relative_to(ROOT).as_posix()
                record = metadata.setdefault(relative, {"source_url": job.url, "title": job.title,
                                                        "source": urlparse(job.url).hostname or ""})
                if isinstance(record, dict) and "complete" not in record:
                    record["complete"] = output_complete(Path(filename), job.status,
                                                         job.media_metadata.get(filename, {}).get("complete"))
                if isinstance(record, dict) and "repair_options" not in record and "_repair_path" not in job.options:
                    record["repair_options"] = repair_options(vars(make_args(job.options)))
            except (ValueError, OSError):
                continue
    return metadata


def run_repair_job(job):
    def check():
        if job.cancel.is_set():
            raise DownloadCancelled("Canceled")

    check()
    for program in ("ffmpeg", "ffprobe"):
        status = grab.media_tool_check(program)
        if status["status"] != "ok":
            raise ValueError("Media processing is unavailable. " + status["detail"])
    executable = Path(grab.ffmpeg_location())
    if executable.is_dir():
        executable /= "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    relative = str(job.options["_repair_path"])
    records = library_records()
    record = records.get(relative, {})
    options = record.get("repair_options")
    if not isinstance(options, dict):
        raise ValueError("The original settings are missing. Download this item again.")
    job.stage, job.title = "Repairing", str(record.get("title") or Path(relative).stem)
    result = repair(LIBRARY, relative, records, options, executable, check=check, log=job.log.append)
    absolute = str(ROOT / result)
    job.files, job.seen_paths = [absolute], [absolute]
    job.media_metadata[absolute] = {**record, "complete": True}
    job.status, job.stage, job.percent = "done", "Done", 100.0


def scan_files(*, force: bool = False) -> list[dict]:
    """Bound filesystem work, report incomplete scans, and keep every discovered media file."""
    if not force and FILES_CACHE["rev"] == FILES_REV and time.time() - FILES_CACHE["ts"] < 5:
        return FILES_CACHE["data"]
    rev = FILES_REV
    out: list[dict] = []
    metadata = library_records()
    candidates = []
    media_paths = set()
    companion_fallback = [False]
    budget = [FILE_SCAN_MAX_ENTRIES]
    reasons = set()

    def scan(d: str, depth: int) -> None:
        try:
            it = os.scandir(d)
        except OSError:
            reasons.add("unreadable")
            return
        with it:
            for e in it:
                if budget[0] <= 0:
                    reasons.add("entry_limit")
                    return
                budget[0] -= 1
                try:
                    if e.is_dir(follow_symlinks=False):
                        if not e.name.startswith("."):
                            if depth < FILE_SCAN_MAX_DEPTH:
                                scan(e.path, depth + 1)
                            else:
                                reasons.add("depth_limit")
                    elif not e.name.startswith(".") and Path(e.name).suffix.lower() in MEDIA_SUFFIX:
                        if not e.is_file(follow_symlinks=False):
                            if e.is_symlink():
                                companion_fallback[0] = True
                            continue
                        path = Path(e.path)
                        st = e.stat()
                        candidates.append((path, st))
                        media_paths.add(path)
                except (OSError, ValueError):
                    reasons.add("unreadable")
                    continue

    scan(str(ROOT), 0)
    # Reuse the bounded, symlink-free scan snapshot for companion checks instead of probing
    # every possible extension on disk for every file. UI and file-management rules stay shared.
    # Incomplete directories or symbolic media need the existing filesystem fallback so a
    # cover discovered before its video is never misclassified as an independent image.
    companion_paths = None if companion_fallback[0] or reasons & {"entry_limit", "unreadable"} else media_paths
    for path, st in candidates:
        relative = path.relative_to(ROOT).as_posix()
        record = metadata.get(relative)
        record = record if isinstance(record, dict) else {}
        suffix = path.suffix.lower()
        if suffix in IMAGE_SUFFIXES and LIBRARY.is_attachment(path, metadata, media_paths=companion_paths):
            continue
        out.append({
            "name": path.name, "path": relative, "size": st.st_size, "mtime": st.st_mtime,
            "source_url": http_url(record.get("source_url")) or "",
            "source": str(record.get("source") or "")[:200],
            "title": str(record.get("title") or "")[:300],
            "complete": record.get("complete") is not False,
            "can_repair": record.get("complete") is False and isinstance(record.get("repair_options"), dict)
                          and record["repair_options"].get("mode", "mp4") in ("mp4", "mp3"),
            "favorite": record.get("favorite") is True, **LIBRARY.details_view(record),
            "thumbnail": LIBRARY.cover_path(path, metadata, media_paths=companion_paths) if suffix not in IMAGE_SUFFIXES else "",
            "collections": [key for key in record.get("collections", []) if isinstance(key, str)]
                           if isinstance(record.get("collections"), list) else [],
            "kind": "image" if suffix in IMAGE_SUFFIXES else "audio" if suffix in grab.AUDIO_SUFFIXES else "video",
            "downloaded": record.get("downloaded") if isinstance(record.get("downloaded"), (int, float)) else st.st_mtime,
        })
    out.sort(key=lambda x: x["downloaded"], reverse=True)
    FILES_CACHE.update(rev=rev, ts=time.time(), data=out, scan={
        "checked": FILE_SCAN_MAX_ENTRIES - budget[0], "media_count": len(out),
        "entry_limit": FILE_SCAN_MAX_ENTRIES, "max_depth": FILE_SCAN_MAX_DEPTH + 1,
        "incomplete": bool(reasons), "reasons": sorted(reasons),
    })
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


def open_completed_download(action: str, relative: str) -> None:
    """Revalidate a captured notification target; it may have moved since completion."""
    if action not in {"play", "folder"}:
        raise ValueError("Unknown notification action.")
    path = LIBRARY.media_path(relative)
    record = LIBRARY.load()["files"].get(path.relative_to(ROOT.resolve()).as_posix(), {})
    if record.get("complete") is False or not path.stat().st_size:
        raise ValueError("The completed file is no longer available.")
    _open_with_os(path if action == "play" else path.parent)


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


HISTORY_STORE = JsonStore(history_file, _SAVE_LOCK)


def save_history() -> None:
    with _HISTORY_SNAPSHOT_LOCK:
        with QUEUE.mutex:
            jobs = JOB_MANAGER.snapshot()
            finished = [job for job in jobs if job.status not in ("queued", "running") and not job.resume_pending]
            retained = {job.id for job in finished[-HISTORY_MAX:]}
            data = [job.to_dict(ROOT) for job in jobs
                    if job.status in ("queued", "running") or job.resume_pending or job.id in retained]
            pending = [job.id for job in QUEUE.queue if job.status == "queued" and not job.cancel.is_set()]
            running = [job.id for job in jobs if job.status == "running" or job.resume_pending]
            state = {"version": 2, "jobs": data, "queue_order": list(dict.fromkeys(running + pending)),
                     "queue_paused": QUEUE.paused}
        try:
            HISTORY_STORE.save(state)
        except OSError as e:
            print(f"Cannot save history: {e}")


def load_history() -> None:
    raw = HISTORY_STORE.load()
    items = raw.get("jobs", []) if isinstance(raw, dict) else []
    items = items if isinstance(items, list) else []
    restored = []
    for d in items:
        job = Job.from_dict(d, ROOT) if isinstance(d, dict) else None
        if job and JOB_MANAGER.get(job.id) is None:
            JOB_MANAGER.add_restored(job)
            if job.status == "queued":
                restored.append(job)
    order = raw.get("queue_order", []) if isinstance(raw, dict) else []
    order = order if isinstance(order, list) else []
    positions = {job_id: i for i, job_id in enumerate(order) if isinstance(job_id, str)}
    QUEUE.set_paused(raw.get("queue_paused") is True if isinstance(raw, dict) else False)
    for job in sorted(restored, key=lambda item: (positions.get(item.id, len(order)), item.created)):
        QUEUE.put(job)
    JOB_MANAGER.prune()


def active_jobs() -> int:
    return JOB_MANAGER.active_count()


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


def managed_component_root():
    return Path(os.environ.get("VIDEO_GRABBER_PORTABLE_ROOT") or CONFIG_DIR / "managed")


def configure_managed_components():
    root = managed_component_root().resolve()
    state = JsonStore(lambda: root / "runtime" / "components.json", threading.Lock()).load({})
    components = state.get("components", {}) if isinstance(state, dict) else {}
    if not isinstance(components, dict):
        return
    for name in ("ffmpeg", "deno"):
        record = components.get(name, {})
        relative = record.get("executable") if isinstance(record, dict) else None
        if not isinstance(relative, str):
            continue
        path = (root / relative).resolve()
        try:
            path.relative_to(root / "runtime" / "components")
        except ValueError:
            continue
        if not path.is_file():
            continue
        os.environ["PATH"] = str(path.parent) + os.pathsep + os.environ.get("PATH", "")
        selected = grab.ffmpeg_location()
        if name == "ffmpeg":
            selected_path = Path(selected) if selected else None
            if selected_path and selected_path.is_dir():
                selected_path /= "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
            probe = selected_path.with_name(re.sub("ffmpeg", "ffprobe", selected_path.name, flags=re.IGNORECASE)) if selected_path else None
            if not selected_path or not selected_path.is_file() or not probe.is_file():
                os.environ["GRAB_FFMPEG_LOCATION"] = str(path)


def setup_status():
    checks = collect_doctor()["checks"]
    required = {"python", "ytdlp", "ffmpeg", "ffprobe", "js_runtime", "ejs", "impersonation"}
    issues = [item for item in checks if item["id"] in required and item["status"] in ("error", "warn")]
    blocked = any("WinError 4551" in item["detail"] for item in issues)
    return {"ready": not issues, "blocked": blocked,
            "can_install": not blocked and os.name == "nt" and sys.maxsize > 2**32 and
                           (Path(__file__).resolve().parent / "portable_manifest.json").is_file() and
                           (Path(__file__).resolve().parent / "portable_bootstrap.py").is_file(),
            "restart_required": UPDATE.get("extras") == "setup" and UPDATE["status"] == "done" and bool(UPDATE.get("restart_required")),
            "issues": [item["id"] for item in issues]}


def start_setup():
    with UPDATE_LOCK:
        if UPDATE["status"] == "running" or active_jobs():
            return False, "Finish or cancel your downloads before preparing the app."
        status = setup_status()
        if status["blocked"]:
            return False, "Windows blocked a media component. Open technical details to see which file was blocked."
        if status["ready"]:
            UPDATE.update(status="done", extras="setup", error="")
            return True, ""
        if not status["can_install"]:
            return False, "Automatic preparation is available in the Windows app. Open technical details for this device."
        UPDATE.update(status="running", lines=[], before=installed_version(), after="", error="", extras="setup",
                      restart_required=False, setup_stage="checking")
    threading.Thread(target=_do_setup, daemon=True).start()
    return True, ""


def _do_setup():
    try:
        status = setup_status()
        if status["blocked"]:
            raise ValueError("Windows blocked a media component. Open technical details to see which file was blocked.")
        names = []
        if any(name in status["issues"] for name in ("ffmpeg", "ffprobe")):
            names.append("ffmpeg")
        if "js_runtime" in status["issues"]:
            names.append("deno")
        if names:
            UPDATE["setup_stage"] = "media"
            folder = Path(__file__).resolve().parent
            command = [sys.executable, str(folder / "portable_bootstrap.py"), "--component-root", str(managed_component_root()),
                       "--manifest", str(folder / "portable_manifest.json"), "--components", ",".join(names)]
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                    timeout=900, creationflags=0x08000000 if os.name == "nt" else 0)
            UPDATE["lines"].extend((result.stdout + result.stderr).splitlines()[-100:])
            if result.returncode:
                raise ValueError("Could not prepare the media tools. Check your connection and try again.")
            configure_managed_components()
        if any(name in status["issues"] for name in ("ytdlp", "ejs", "impersonation")):
            UPDATE["setup_stage"] = "sites"
            _do_update("default,deno", preparing=True)
            UPDATE["extras"] = "setup"
            if UPDATE["status"] == "error":
                return
            UPDATE["restart_required"] = True
        UPDATE["setup_stage"] = "verifying"
        for name in ("ffmpeg", "ffprobe"):
            if grab.media_tool_check(name)["status"] != "ok":
                raise ValueError("The media tools could not start. Open technical details for help.")
        DOCTOR_CACHE["ts"] = 0.0
        UPDATE.update(status="done", error="", setup_stage="ready")
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        UPDATE.update(status="error", error=str(error))


def _do_update(extras: str = "default", *, preparing: bool = False) -> None:
    # curl-cffi enables yt-dlp's browser impersonation for Iwara and anti-bot protected sites.
    selected = {item for item in extras.split(",") if item in {"default", "deno"}}
    selected.update({"curl-cffi", "default"})
    package = f"yt-dlp[{','.join(sorted(selected))}]"
    cmd = [sys.executable, "-m", "pip", "install", "-U", "--disable-pip-version-check", package]
    if os.environ.get("VIDEO_GRABBER_PORTABLE_ROOT"):
        package_dir = Path(sys.executable).resolve().parent / "Lib" / "site-packages"
        cmd[-1:-1] = ["--ignore-installed", "--target", str(package_dir)]
    elif preparing and sys.prefix == sys.base_prefix and not sys.flags.no_user_site:
        # Source installations should not need permission to modify a system-wide Python.
        cmd.insert(-1, "--user")
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
            UPDATE.update(status="running" if preparing else "done", error="")
        else:
            if "externally-managed" in text:
                hint = "The current Python environment is managed by the system; pip does not allow direct installation. Please use a virtual environment, or update manually in terminal."
            elif "permission" in text or "access is denied" in text:
                hint = 'No write permission, you can run  pip install -U --user "yt-dlp[default]"  in the terminal.'
            else:
                hint = 'Update failed, see log for details. You can also run  pip install -U "yt-dlp[default]"  in the terminal.'
            UPDATE.update(status="error", error=hint)
    PYPI_CACHE["ts"] = 0.0


def saved_download_root(default: Path) -> Path:
    data = JsonStore(lambda: CONFIG_DIR / "settings.json", SETTINGS_LOCK).load({})
    value = data.get("download_dir") if isinstance(data, dict) else None
    if isinstance(value, str) and Path(value).is_absolute() and Path(value).is_dir():
        return Path(value).resolve()
    return default


def choose_download_folder() -> str | None:
    if NATIVE_WINDOW is not None:
        import webview
        try:
            selected = NATIVE_WINDOW.create_file_dialog(webview.FileDialog.FOLDER, directory=str(ROOT))
        except Exception as error:  # GUI toolkit failures must leave an actionable response.
            raise ValueError("Could not open the folder chooser. Please try again.") from error
        return str(selected[0]) if selected else None
    if sys.platform == "win32":
        script = """[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Choose where to save downloads'
$dialog.SelectedPath = $env:GRAB_CURRENT_DOWNLOAD_DIR
try { if ($dialog.ShowDialog() -eq 'OK') { [Console]::Write($dialog.SelectedPath) } }
finally { $dialog.Dispose() }
"""
        result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", script],
                                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
                                env=dict(os.environ, GRAB_CURRENT_DOWNLOAD_DIR=str(ROOT)), creationflags=0x08000000)
        if result.returncode:
            raise ValueError("Could not open the folder chooser. Please try again.")
        return result.stdout.strip() or None
    raise ValueError("Folder selection is available in the desktop app or on Windows.")


def select_download_folder() -> dict:
    global PENDING_ROOT
    if not FOLDER_PICK_LOCK.acquire(blocking=False):
        raise ValueError("A file import or folder chooser is already running.")
    try:
        if active_jobs() or UPDATE["status"] == "running":
            raise ValueError("Finish or cancel queued downloads before changing the save folder.")
        selected = choose_download_folder()
        if not selected:
            return {"canceled": True, "restart_required": False, "root": str(ROOT)}
        target = Path(selected)
        if not target.is_absolute() or not target.is_dir():
            raise ValueError("Choose an existing folder.")
        target = target.resolve()
        if target == ROOT:
            if PENDING_ROOT is not None:
                store = JsonStore(lambda: CONFIG_DIR / "settings.json", SETTINGS_LOCK)
                data = store.load({})
                data = data if isinstance(data, dict) else {}
                store.save({**data, "download_dir": str(ROOT)})
                PENDING_ROOT = None
            return {"canceled": False, "restart_required": False, "root": str(ROOT)}
        with QUEUE.mutex:
            if active_jobs() or UPDATE["status"] == "running":
                raise ValueError("Finish or cancel queued downloads before changing the save folder.")
            try:
                with tempfile.TemporaryFile(dir=target):
                    pass
            except OSError as error:
                raise ValueError("The app cannot save to this folder. Choose another folder.") from error
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            store = JsonStore(lambda: CONFIG_DIR / "settings.json", SETTINGS_LOCK)
            data = store.load({})
            data = data if isinstance(data, dict) else {}
            store.save({**data, "download_dir": str(target)})
            PENDING_ROOT = target
        return {"canceled": False, "restart_required": True, "root": str(target)}
    finally:
        FOLDER_PICK_LOCK.release()


def restart_self() -> None:
    """Restart this program with the same arguments (required to load the new version after updating yt-dlp)."""
    argv = [sys.executable, str(Path(__file__).resolve()), "--dir", str(PENDING_ROOT or ROOT), "--port", str(PORT),
            "--workers", str(WORKERS), "--ui", "window" if WINDOW_MODE else "none"]
    env = dict(os.environ, GRAB_WEBUI_RESTART="1", GRAB_RESTART_WINDOW="1" if WINDOW_MODE else "0",
               GRAB_SESSION_SECRET=SESSION_SECRET)
    if sys.platform.startswith("win"):
        subprocess.Popen(argv, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)  # type: ignore[attr-defined]
        if NATIVE_DESKTOP is not None:
            NATIVE_DESKTOP.stop()
        os._exit(0)
    os.execve(sys.executable, argv, env)


# ───────────────────────── Cookies (uploaded cookies.txt) ─────────────────────────
def cookies_path() -> Path:
    return CONFIG_DIR / "cookies.txt"


def cookies_status() -> dict:
    return grab_cookies.cookies_status(cookies_path())


def save_cookies(text: str) -> dict:
    result = grab_cookies.save_cookies(text, cookies_path())
    DOCTOR_CACHE["ts"] = 0.0
    return result


def delete_cookies() -> None:
    grab_cookies.delete_cookies(cookies_path())
    DOCTOR_CACHE["ts"] = 0.0


def cookie_copy(args):
    """A context manager giving this yt-dlp run its own copy of the cookies file (see grab_cookies)."""
    return grab_cookies.cookie_copy(args, CONFIG_DIR)


# ───────────────────────── Access settings ─────────────────────────
def launch_url(port: int) -> str:
    """The address our own window or browser tab opens; it proves the client was started by this app."""
    return f"http://127.0.0.1:{port}/?n={LAUNCH_SECRET}"


def _access_store() -> JsonStore:
    return JsonStore(lambda: CONFIG_DIR / "access.json", SETTINGS_LOCK)


def extension_access_enabled() -> bool:
    data = _access_store().load({})
    return isinstance(data, dict) and data.get("extension") is True


def set_extension_access(enabled: bool) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    store = _access_store()
    data = store.load({})
    store.save({**(data if isinstance(data, dict) else {}), "extension": enabled})


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
    dist_ok, dist_problem = check_dist()
    if dist_ok:
        checks.append(grab.check_item("interface", "Interface files (webui_dist)", "ok", f"Complete, served from {UI_DIST}."))
    else:
        checks.append(grab.check_item(
            "interface", "Interface files (webui_dist)", "warn",
            f"Incomplete ({dist_problem}), so this page is the basic fallback. "
            "webui_dist/ needs index.html and an assets/ folder next to webui.py.",
            fix="Copy the whole webui_dist folder from the release, keeping its assets/ subfolder."))
    if importlib.util.find_spec("webview"):
        checks.append(grab.check_item("pywebview", "Desktop window (pywebview)", "ok",
                                      "Installed. Start with --ui window for a native window instead of a browser tab."))
    else:
        checks.append(grab.check_item("pywebview", "Desktop window (pywebview)", "info",
                                      "Not installed. Optional: only needed for --ui window.", fix="pip install pywebview"))
    subscriptions = SUBSCRIPTION_MANAGER.snapshot()
    active = sum(1 for subscription in subscriptions if subscription.enabled)
    total = len(subscriptions)
    if total:
        checks.append(grab.check_item("subscriptions", "Subscriptions", "ok" if active else "info",
                                      f"{active} of {total} active, checked every {SUB_INTERVAL_SECONDS // 60} minutes."))
    failures = sorted((job for job in JOB_MANAGER.snapshot() if job.status == "error"),
                      key=lambda j: j.finished or j.created, reverse=True)[:3]
    sections = [(f"Recent failure {i}", [j.url, f"Error: {j.error}"] + [ln[:200] for ln in list(j.log)[-12:]])
                for i, j in enumerate(failures, 1)]
    data = {"checks": checks, "report": grab.format_report(checks, sections), "net": net}
    if not net:
        DOCTOR_CACHE.update(ts=time.time(), data=data)
    return data


# ───────────────────────── Subscriptions (auto-download new videos) ─────────────────────────
SUB_INTERVAL_SECONDS = 3600  # how often a subscription is re-checked; set from --sub-interval in main()
SUB_TICK_SECONDS = 300       # how often the scheduler thread wakes up to see what is due

SUBSCRIPTION_MANAGER = SubscriptionManager()
# Compatibility aliases for existing integrations and tests. New code goes through the manager.
SUBS = SUBSCRIPTION_MANAGER.subscriptions
_CHECKING = SUBSCRIPTION_MANAGER.checking


def subs_path() -> Path:
    return ROOT / ".grab-subscriptions.json"


SUBSCRIPTIONS_STORE = JsonStore(subs_path, _SAVE_LOCK)


def subscription_view(subscription: Subscription) -> dict:
    return subscription.view(SUB_INTERVAL_SECONDS, SUBSCRIPTION_MANAGER.is_checking(subscription.id))


def save_subscriptions() -> None:
    data = [subscription.to_dict() for subscription in SUBSCRIPTION_MANAGER.snapshot()]
    try:
        SUBSCRIPTIONS_STORE.save({"version": 1, "subscriptions": data})
    except OSError as e:
        print(f"Could not save subscriptions: {e}")


def load_subscriptions() -> None:
    raw = SUBSCRIPTIONS_STORE.load()
    items = raw.get("subscriptions", []) if isinstance(raw, dict) else []
    for d in items:
        sub = Subscription.from_dict(d) if isinstance(d, dict) else None
        if sub:
            SUBSCRIPTION_MANAGER.add(sub)


def list_flat_entries(url: str, args) -> tuple[str, list[dict]]:
    """Newest-first (usually) list of {id, url, title} without downloading anything.

    Raises on network/extractor errors - the caller decides how to report those.
    """
    opts = {
        "quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "socket_timeout": 20,
        "http_headers": {"User-Agent": grab.UA}, **grab.js_runtime_opts(),
    }
    if args.proxy:
        opts["proxy"] = args.proxy
    if args.cookies_from_browser:
        opts["cookiesfrombrowser"] = (args.cookies_from_browser,)
    with cookie_copy(args) as cookiefile:
        if cookiefile:
            opts["cookiefile"] = cookiefile
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    if info is None:
        return "", []
    return str(info.get("title") or ""), normalize_flat_entries(info, url)


def preview_subscription(sub: Subscription, filters: dict) -> dict:
    """Inspect candidates without changing seen IDs or queuing work."""
    title, entries = list_flat_entries(sub.url, make_args(sub.options))
    candidates = (
        entries[:sub.backfill_count] if sub.backfill == "recent" else []
    ) if not sub.initialized else [entry for entry in entries if entry["id"] not in sub.seen_ids]
    candidate_ids = {entry["id"] for entry in candidates}
    normalized = normalize_subscription_filters(filters)
    matched = sum(subscription_filter_reason(entry, normalized) is None for entry in candidates)
    displayed = candidates[:30]
    if len(displayed) < 30:
        displayed += [entry for entry in entries if entry["id"] not in candidate_ids][:30 - len(displayed)]
    return {
        "title": title,
        "total_candidates": len(candidates),
        "would_queue": matched,
        "filtered": len(candidates) - matched,
        "items": [{
            "id": entry["id"], "title": entry["title"], "url": entry["url"],
            "duration": entry.get("duration"),
            "reason": subscription_filter_reason(entry, normalized),
            "eligible": entry["id"] in candidate_ids,
        } for entry in displayed],
    }


def check_subscription(sub: "Subscription") -> None:
    if not SUBSCRIPTION_MANAGER.begin_check(sub.id):
        return
    try:
        args = make_args(sub.options)
        try:
            title, entries = list_flat_entries(sub.url, args)
        except Exception as e:  # noqa: BLE001
            sub.last_error = friendly_error(str(e))
            sub.last_error_kind = error_details(str(e))["kind"]
            sub.last_checked = time.time()
            return
        if title:
            sub.title = title[:300]
        # A manual check may still be waiting on the network when the user
        # removes the subscription. Removal must prevent any later downloads.
        if sub.removed:
            return
        current_ids = {e["id"] for e in entries}

        if not sub.initialized:
            to_queue, rest = split_backfill(entries, sub.backfill_count if sub.backfill == "recent" else 0)
            sub.seen_ids = current_ids
            sub.initialized = True
        else:
            to_queue = [e for e in entries if e["id"] not in sub.seen_ids]
            sub.seen_ids |= current_ids

        sub.last_found = len(to_queue)
        to_queue, filtered = filter_subscription_entries(to_queue, sub.filters)
        sub.last_queued = len(to_queue)
        sub.last_filtered = len(filtered)
        sub.total_filtered += len(filtered)
        if to_queue:
            urls = [e["url"] for e in to_queue]
            create_jobs(urls, sub.options, source=sub.id)
            sub.total_queued += len(urls)
        sub.last_error = ""
        sub.last_error_kind = ""
        sub.last_checked = time.time()
    finally:
        SUBSCRIPTION_MANAGER.end_check(sub.id)
        save_subscriptions()
        bump_rev()


def start_subscription_check(sub: Subscription) -> None:
    threading.Thread(
        target=check_subscription,
        args=(sub,),
        name=f"subscription-check-{sub.id}",
        daemon=True,
    ).start()


def subscription_scheduler(stop_event: threading.Event | None = None) -> None:
    stop_event = stop_event or STOP_EVENT
    while not stop_event.wait(SUB_TICK_SECONDS):
        for sub in SUBSCRIPTION_MANAGER.due(SUB_INTERVAL_SECONDS):
            try:
                check_subscription(sub)
            except Exception as e:  # noqa: BLE001
                sub.last_error, sub.last_checked = f"Unexpected error: {friendly_error(str(e))}", time.time()
                sub.last_error_kind = error_details(str(e))["kind"]
                save_subscriptions()
                bump_rev()


# ───────────────────────── Frontend (built React app) ─────────────────────────
def render_dist_index() -> bytes | None:
    """The built frontend's index.html, with this run's token filled in. None if it was not built."""
    index = UI_DIST / "index.html"
    if not index.is_file():
        return None
    return index.read_text(encoding="utf-8").replace("__GRAB_TOKEN__", TOKEN).encode("utf-8")


def check_dist() -> tuple[bool, str]:
    """Is the built interface complete? If not, the second value says what is missing.

    Without this check, an incomplete webui_dist/ (say, the JS file saved next to grab.py instead of
    inside webui_dist/assets/) silently shows the basic built-in page and looks like "nothing changed".
    """
    index = UI_DIST / "index.html"
    if not index.is_file():
        return False, f"{index} was not found"
    referenced = re.findall(r'(?:src|href)="/(assets/[^"]+)"', index.read_text(encoding="utf-8"))
    missing = [name for name in referenced if not (UI_DIST / name).is_file()]
    if missing:
        return False, "missing " + ", ".join(f"webui_dist/{m}" for m in missing)
    return True, ""


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
    def _discard_rejected_body(self) -> None:
        """Avoid Windows resetting a rejected POST before the client receives its response."""
        if self.command != "POST":
            return
        self.close_connection = True
        try:
            remaining = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if not 0 < remaining <= BODY_MAX_BYTES or self.headers.get("Transfer-Encoding"):
            return
        previous_timeout = self.connection.gettimeout()
        deadline = time.monotonic() + 1
        try:
            while remaining:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    break
                self.connection.settimeout(min(timeout, previous_timeout) if previous_timeout is not None else timeout)
                chunk = self.rfile.read1(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass  # An incomplete rejected body must never reach an API handler.
        finally:
            self.connection.settimeout(previous_timeout)

    def _guard(self) -> bool:
        if not HOST_RE.match(self.headers.get("Host", "")):
            self._discard_rejected_body()
            self._json({"error": "forbidden host"}, 403)
            return False
        return True

    def _session_cookie_ok(self) -> bool:
        try:
            jar = http.cookies.SimpleCookie(self.headers.get("Cookie") or "")
        except http.cookies.CookieError:
            return False
        morsel = jar.get(SESSION_COOKIE)
        return morsel is not None and hmac.compare_digest(morsel.value.encode(), SESSION_SECRET.encode())

    def _root_access(self, query: dict) -> str | None:
        nonce = (query.get("n") or [""])[0]
        if nonce and hmac.compare_digest(nonce.encode(), LAUNCH_SECRET.encode()):
            return "launch"
        if self._session_cookie_ok():
            return "session"
        if self.headers.get("X-Grab-Client") == "extension" and extension_access_enabled():
            return "extension"
        return None

    def _authed(self, query: dict) -> bool:
        tok = self.headers.get("X-Token") or ""
        if not tok and self.command == "GET":  # A token in a URL is read-only legacy access.
            tok = (query.get("t") or [""])[0]
        if not hmac.compare_digest(tok.encode(), TOKEN.encode()):
            self._discard_rejected_body()
            self._json({"error": "Unauthorized, please refresh the page"}, 401)
            return False
        return True

    # —— Routing ——
    def _handle_root_page(self, query: dict):
        access = self._root_access(query)
        if access is None:
            if self.headers.get("X-Grab-Client") == "extension":
                return self._json({"error": "extension_access_off"}, 403)
            return self._send(403, LOCKED_PAGE, "text/html; charset=utf-8", {"Referrer-Policy": "no-referrer"})
        extra = {"Referrer-Policy": "no-referrer"}
        if access == "launch":
            extra["Set-Cookie"] = f"{SESSION_COOKIE}={SESSION_SECRET}; Path=/; HttpOnly; SameSite=Strict"
        dist_page = render_dist_index()
        if dist_page is not None:
            csp = ("default-src 'self'; img-src http: https: data:; style-src 'self'; "
                   "script-src 'self'; connect-src 'self'; media-src 'self'; frame-ancestors 'none'")
            return self._send(200, dist_page, "text/html; charset=utf-8", {**extra, "Content-Security-Policy": csp})
        page = INDEX_HTML.replace("__TOKEN__", TOKEN).encode("utf-8")
        csp = ("default-src 'self'; img-src http: https: data:; style-src 'unsafe-inline'; "
               "script-src 'unsafe-inline'; connect-src 'self'; media-src 'self'; frame-ancestors 'none'")
        return self._send(200, page, "text/html; charset=utf-8", {**extra, "Content-Security-Policy": csp})

    def _handle_library_get(self, path: str) -> bool:
        return webui_routes_library.library_get(sys.modules[__name__], self, path)

    def _handle_jobs_get(self, path: str, q: dict) -> bool:
        return webui_routes_jobs.jobs_get(sys.modules[__name__], self, path, q)

    def _handle_subscriptions_get(self, path: str) -> bool:
        return webui_routes_subscriptions.subscriptions_get(sys.modules[__name__], self, path)

    def _handle_system_get(self, path: str, q: dict) -> bool:
        return webui_routes_system.system_get(sys.modules[__name__], self, path, q)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._guard():
            return
        if u.path == "/":
            return self._handle_root_page(q)
        if u.path.startswith("/assets/"):
            asset = read_static_asset(u.path.lstrip("/"))
            if asset is None:
                return self._json({"error": "not found"}, 404)
            body, ctype = asset
            return self._send(200, body, ctype, {"Cache-Control": "public, max-age=31536000, immutable"})
        if u.path.startswith("/files/") and self._session_cookie_ok():
            # Media elements cannot send headers; the HttpOnly same-site cookie replaces a token in the URL.
            return self._file(unquote(u.path[len("/files/"):]))
        if not self._authed(q):
            return
        if self._handle_library_get(u.path):
            return
        if self._handle_jobs_get(u.path, q):
            return
        if self._handle_system_get(u.path, q):
            return
        if self._handle_subscriptions_get(u.path):
            return
        if u.path.startswith("/files/"):
            return self._file(unquote(u.path[len("/files/"):]))
        self._json({"error": "not found"}, 404)

    def _handle_library_import(self, q: dict) -> bool:
        return webui_routes_library.library_import(sys.modules[__name__], self, q)

    def _handle_backup_post(self, path: str, body: dict) -> bool:
        return webui_routes_library.backup_post(sys.modules[__name__], self, path, body)

    def _handle_library_post(self, path: str, body: dict) -> bool:
        return webui_routes_library.library_post(sys.modules[__name__], self, path, body)

    def _handle_jobs_post(self, path: str, body: dict) -> bool:
        return webui_routes_jobs.jobs_post(sys.modules[__name__], self, path, body)

    def _handle_subscriptions_post(self, path: str, body: dict) -> bool:
        return webui_routes_subscriptions.subscriptions_post(sys.modules[__name__], self, path, body)

    def _handle_system_post(self, path: str, body: dict) -> bool:
        return webui_routes_system.system_post(sys.modules[__name__], self, path, body)

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._guard() or not self._authed(q):
            return
        if u.path == "/api/library/import":
            return self._handle_library_import(q)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._json({"error": "bad content type"}, 415)
        limit = BACKUP_MAX_BYTES + BODY_MAX_BYTES if u.path.startswith("/api/backup/") else COOKIES_MAX_BYTES if u.path == "/api/cookies" else BODY_MAX_BYTES
        body = self._body(limit)

        if self._handle_backup_post(u.path, body):
            return
        if self._handle_library_post(u.path, body):
            return
        if self._handle_jobs_post(u.path, body):
            return
        if self._handle_subscriptions_post(u.path, body):
            return
        if self._handle_system_post(u.path, body):
            return

        self._json({"error": "not found"}, 404)

    def _file(self, rel: str) -> None:
        p = (ROOT / rel).resolve()
        try:
            relative = p.relative_to(ROOT)
        except ValueError:
            return self._json({"error": "forbidden"}, 403)
        if any(part.startswith(".") for part in relative.parts) or not p.is_file() or p.suffix.lower() not in MEDIA_SUFFIX:
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
        self.send_header("X-Content-Type-Options", "nosniff")
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
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows SO_REUSEADDR allows two processes to silently bind to the same port, so only enable on other OS
    allow_reuse_address = not sys.platform.startswith("win")


# ───────────────────────── Page ─────────────────────────
from webui_legacy_html import INDEX_HTML  # noqa: E402


# ───────────────────────── Entry Point ─────────────────────────
def open_native_window(url: str) -> bool:
    """Try to open url in its own pywebview window. Returns False if pywebview is not installed
    or WebView2 cannot start (the caller then falls back to a browser tab). Blocks until the
    desktop session exits. On Windows, closing the main window asks or follows the saved tray preference."""
    global NATIVE_WINDOW, NATIVE_DESKTOP
    desktop = None
    try:
        import webview
    except ImportError:
        return False
    try:
        # External documentation links use target=_blank and must leave the trusted local app
        # surface instead of navigating this window away from its token-protected origin.
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
        # Backup exports use a Blob download and need WebView2's native save dialog.
        webview.settings["ALLOW_DOWNLOADS"] = True
        storage_path = CONFIG_DIR / "webview"
        storage_path.mkdir(parents=True, exist_ok=True)
        NATIVE_WINDOW = webview.create_window(
            "Video Grabber", url, width=1180, height=860, min_size=(680, 520),
            background_color="#0b0d10", text_select=True,
        )
        if sys.platform == "win32":
            from grab_desktop import DesktopBridge, DesktopController
            desktop = DesktopController(webview, NATIVE_WINDOW, url, preferences_path=CONFIG_DIR / "desktop.json",
                                        pending_downloads=active_jobs,
                                        notification_jobs=lambda since: [job.view(ROOT) for job in JOB_MANAGER.snapshot()
                                            if job.finished > since or job.status in {"queued", "running"}
                                            or (job.status in {"done", "error"} and not job.finished)],
                                        notification_action=open_completed_download)
            NATIVE_DESKTOP = desktop
            bridge = DesktopBridge(desktop)
            NATIVE_WINDOW.expose(bridge.sync_locale, bridge.close_settings, bridge.set_close_behavior,
                                 bridge.close_action)
            NATIVE_WINDOW.events.closing += desktop.close_main
        start_options = {"private_mode": False, "storage_path": str(storage_path)}
        if sys.platform == "win32":
            start_options["gui"] = "edgechromium"
        if desktop:
            webview.start(desktop.start, **start_options)
        else:
            webview.start(**start_options)
    except Exception as exc:  # noqa: BLE001 - GUI/runtime failures must retain the browser fallback
        print(f"Could not start the native app window: {exc}")
        if sys.platform == "win32":
            print("Install or repair Microsoft Edge WebView2 Runtime, or start with --ui browser.")
        return False
    finally:
        if desktop:
            desktop.stop()
        NATIVE_DESKTOP = None
    return True


def main(argv=None) -> None:
    global ROOT, PORT, WORKERS, WINDOW_MODE, UI_MODE
    config = parse_web_config(argv)
    if config.ffmpeg_location:
        os.environ["GRAB_FFMPEG_LOCATION"] = str(Path(config.ffmpeg_location).expanduser().resolve())
    configure_managed_components()

    global SUB_INTERVAL_SECONDS
    ROOT = config.download_dir if config.download_dir_explicit else saved_download_root(config.download_dir)
    ROOT.mkdir(parents=True, exist_ok=True)
    load_history()
    load_subscriptions()
    SUB_INTERVAL_SECONDS = config.subscription_interval_seconds
    WORKERS = config.workers
    STOP_EVENT.clear()

    restarting = os.environ.get("GRAB_WEBUI_RESTART") == "1"
    ui_mode = ("window" if os.environ.get("GRAB_RESTART_WINDOW") == "1" else "none") if restarting else config.ui
    ports = [config.port] if restarting else list(range(config.port, config.port + 20))
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
    url = launch_url(PORT)
    print(("Restarted:" if restarting else "Video Grabber WebUI started:") + url)
    print(f"Download Directory: {ROOT}")
    if not grab.ffmpeg_available():
        print("Hint: " + grab.media_tool_check("ffmpeg")["detail"])

    dist_ok, dist_problem = check_dist()
    if not dist_ok:
        print(f"WARNING: the new interface cannot be shown ({dist_problem}).")
        print("         Showing the basic built-in page instead. webui_dist/ must contain index.html")
        print("         and an assets/ folder with the .js and .css files that index.html refers to.")

    worker_threads = [
        threading.Thread(target=worker, name=f"download-worker-{index + 1}", daemon=True)
        for index in range(WORKERS)
    ]
    scheduler_thread = threading.Thread(
        target=subscription_scheduler, name="subscription-scheduler", daemon=True,
    )
    server_thread = threading.Thread(target=srv.serve_forever, name="http-server", daemon=True)
    for thread in [*worker_threads, scheduler_thread, server_thread]:
        thread.start()
    try:
        if ui_mode == "window":
            print("Closing the window asks to run in the tray or exit; change this in Close behavior."
                  if sys.platform == "win32" else "Close the window to stop.")
            if not open_native_window(url):
                print("Hint: pywebview is not installed, opening your browser instead. Run: pip install pywebview")
                WINDOW_MODE = False
                UI_MODE = "browser"
                webbrowser.open(url)
                STOP_EVENT.wait()
        else:
            if ui_mode == "browser":
                webbrowser.open(url)
            print("Press Ctrl+C to stop.")
            STOP_EVENT.wait()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        QUEUE.stop()
        ORGANIZER.stop()
        STOP_EVENT.set()
        with QUEUE.mutex:
            for job in JOB_MANAGER.snapshot():
                if job.status == "running" and not job.cancel.is_set():
                    job.resume_pending = True
                    job.cancel.set()
        save_history()
        srv.shutdown()
        srv.server_close()
        for thread in [*worker_threads, scheduler_thread, server_thread]:
            thread.join(timeout=2)
        save_history()


if __name__ == "__main__":
    main()
