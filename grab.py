"""
grab.py - universal web video / audio downloader (yt-dlp + ffmpeg)

What it does
  * Mainstream video sites, playlists and channels (everything yt-dlp supports)
  * Direct mp4 links embedded in web pages, and m3u8 / mpd streams
  * Pages yt-dlp does not recognise: scans the page source for media URLs
  * Pages that load their video with JavaScript: --js-render captures the media
    requests with a headless browser (Playwright)
  * Output as MP4 (with a quality cap) or MP3 (with a bitrate)
  * Batch downloads, subtitles (optionally embedded) and cover art
  * --doctor checks your setup (ffmpeg, JavaScript runtime, cookies, network)

Requirements
  pip install -U "yt-dlp[default]"      # "default" adds the components YouTube needs
  ffmpeg                                # merging audio/video and MP3 conversion, must be on PATH
  YouTube also needs a JavaScript runtime, Deno is the one yt-dlp enables by default:
      pip install -U "yt-dlp[default,deno]"   or   winget install DenoLand.Deno
  Optional: pip install playwright      # only for --js-render

Only download content you have the right to download, and follow the terms of the
sites you use and your local copyright law. This tool cannot and does not bypass DRM.
"""
from __future__ import annotations

import argparse
import datetime
import html
import importlib.metadata as importlib_metadata
import importlib.util
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

try:
    import yt_dlp
    from yt_dlp.utils import DownloadError, parse_bytes, sanitize_filename
except ImportError:
    sys.exit('Missing dependency: please run  pip install -U "yt-dlp[default]"  first')

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MEDIA_EXT = r"(?:m3u8|mpd|mp4|webm|mov|m4v|mp3|m4a|aac|flac|ogg)"

FFMPEG_HELP = """ffmpeg not found (required for merging audio/video and MP3 conversion). Installation:
  Windows : winget install Gyan.FFmpeg     (reopen terminal after installation)
  macOS   : brew install ffmpeg
  Ubuntu  : sudo apt install ffmpeg"""

EXAMPLES = """Examples:
  python grab.py URL                              # Download highest quality MP4
  python grab.py URL -m mp3 --abr 320             # Audio only, 320kbps MP3
  python grab.py URL -q 720                       # MP4, max 720p
  python grab.py -i urls.txt -o D:/videos         # Batch (one URL per line)
  python grab.py PLAYLIST_URL --items 1-10        # First 10 items of a playlist
  python grab.py URL --subs --embed-subs --cover  # Subtitles(embedded) + Cover(embedded)
  python grab.py URL --list-formats               # Only list available formats, do not download
  python grab.py PAGE_URL --js-render             # Use headless browser to capture media stream if static scan fails
  python grab.py URL --cookies-from-browser chrome  # Requires login / premium content
"""


# ───────────────────────── Parameters ─────────────────────────
def quality_type(v: str) -> str:
    v = v.lower().rstrip("p")
    if v == "best" or v.isdigit():
        return v
    raise argparse.ArgumentTypeError("Please enter 'best' or a number, e.g., 1080 / 720")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="grab.py",
        description="Universal web video / audio downloader (MP4 / MP3)",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("urls", nargs="*", help="Video page / playlist / direct link / m3u8 address (multiple allowed)")
    p.add_argument("-i", "--input-file", metavar="FILE",
                   help="Read URLs from a text file (one per line, lines starting with # are comments)")
    p.add_argument("-o", "--output", default="downloads", help="Save directory (default: ./downloads)")

    g = p.add_argument_group("Format and Quality")
    g.add_argument("-m", "--mode", choices=["mp4", "mp3"], default="mp4", help="Output type (default: mp4)")
    g.add_argument("-q", "--quality", type=quality_type, default="best",
                   help="Max MP4 quality: best or 2160/1440/1080/720/480/360 (default: best)")
    g.add_argument("--abr", type=int, choices=(96, 128, 192, 256, 320), default=192,
                   help="MP3 bitrate kbps (default: 192)")
    g.add_argument("--list-formats", action="store_true", help="Only list available formats, do not download")

    g = p.add_argument_group("Subtitles and Covers")
    g.add_argument("--subs", action="store_true", help="Download subtitles")
    g.add_argument("--sub-langs", default="zh-Hans,zh-Hant,zh,en",
                   help="Subtitle languages, comma-separated, 'all' available (default: zh-Hans,zh-Hant,zh,en)")
    g.add_argument("--auto-subs", action="store_true", help="Download auto-generated subtitles if manual ones are unavailable")
    g.add_argument("--sub-format", choices=["srt", "vtt", "ass"], default="srt", help="Subtitle format (default: srt)")
    g.add_argument("--embed-subs", action="store_true", help="Embed subtitles into MP4 (also keeps subtitle file)")
    g.add_argument("--cover", action="store_true", help="Download cover and embed into file")
    g.add_argument("--keep-cover", action="store_true", help="Keep separate jpg cover file after embedding")

    g = p.add_argument_group("Batch and Network")
    g.add_argument("--no-playlist", action="store_true", help="If URL contains both video and playlist, download only the video")
    g.add_argument("--items", metavar="SPEC", help="Playlist range, e.g., 1-5,8,10-")
    g.add_argument("--archive", metavar="FILE", help="Record downloaded items, automatically skip on rerun")
    g.add_argument("--cookies-from-browser", metavar="BROWSER", help="Read browser login state: chrome / edge / firefox …")
    g.add_argument("--cookies", metavar="FILE", help="Netscape format cookies.txt")
    g.add_argument("--referer", help="Manually specify Referer (for hotlink protection sites)")
    g.add_argument("--proxy", help="Proxy, e.g., http://127.0.0.1:7890")
    g.add_argument("--limit-rate", metavar="RATE", help="Rate limit, e.g., 2M, 500K")
    g.add_argument("--sleep", type=float, default=0, metavar="SEC", help="Wait seconds between each download (more polite for batches)")
    g.add_argument("--threads", type=int, default=4, help="Concurrent fragment threads, speeds up m3u8 / DASH (default: 4)")

    g = p.add_argument_group("Page Scanning (for pages yt-dlp doesn't recognize)")
    g.add_argument("--no-sniff", action="store_true", help="Disable page source scanning fallback")
    g.add_argument("--all-sniffed", action="store_true", help="Download all when multiple media addresses are scanned (default: only download the first successful one)")
    g.add_argument("--js-render", action="store_true",
                   help="If static scan fails, use headless browser to load page and capture media stream from network requests (requires pip install playwright)")
    g.add_argument("--js-wait", type=float, default=8.0, metavar="SEC", help="Max wait seconds for headless browser (default: 8)")
    g.add_argument("--js-browser", default="auto", metavar="NAME|PATH",
                   help="auto (Edge first, then Chrome, finally Playwright's Chromium) / msedge / chrome / chromium / browser executable path")

    g = p.add_argument_group("Diagnostics")
    g.add_argument("--doctor", action="store_true",
                   help="Check ffmpeg, the JavaScript runtime YouTube needs, Playwright, the output folder, then exit")
    g.add_argument("--net", action="store_true", help="With --doctor: also test whether YouTube, Bilibili and PyPI are reachable")
    return p.parse_args(argv)


def collect_urls(args) -> list[str]:
    urls = list(args.urls)
    if args.input_file:
        try:
            text = Path(args.input_file).read_text(encoding="utf-8-sig")
        except OSError as e:
            sys.exit(f"Cannot read URL file: {e}")
        urls += [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not urls and sys.stdin.isatty():
        print("Paste URLs (one per line), empty line to finish:")
        while True:
            ln = input("> ").strip()
            if not ln:
                break
            urls.append(ln)
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


# ───────────────────────── yt-dlp Options ─────────────────────────
def video_format(quality: str) -> str:
    """Prioritize mp4/m4a (no re-encoding needed), fallback if not found; <=? accepts unknown heights."""
    if quality == "best":
        return "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"
    h = int(quality)
    return (
        f"bv*[height<=?{h}][ext=mp4]+ba[ext=m4a]/b[height<=?{h}][ext=mp4]/"
        f"bv*[height<=?{h}]+ba/b[height<=?{h}]/b"
    )


def build_opts(args, referer: str | None = None, name: str | None = None, work_dir: Path | None = None) -> dict:
    out = Path(args.output).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    base = str(work_dir or out).replace("%", "%%")   # Process MP3s in a temp dir first, see begin_work

    if name:  # Direct links from page scan: name with page title
        safe = sanitize_filename(name)[:120].replace("%", "%%") or "video"
        tmpl = f"{base}/{safe}.%(ext)s"
    else:     # Playlists automatically create subfolders and numbers
        tmpl = (f"{base}/%(playlist_title|)s/"
                "%(playlist_index&{:02d}. |)s%(title).120B [%(id)s].%(ext)s")

    opts: dict = {
        **js_runtime_opts(),
        "outtmpl": tmpl,
        "noplaylist": args.no_playlist,
        "retries": 5,
        "fragment_retries": 10,
        "extractor_retries": 3,
        "concurrent_fragment_downloads": max(1, args.threads),
        "ignoreerrors": "only_download",   # Failure in one playlist item doesn't affect the rest
        "continuedl": True,
        "windowsfilenames": True,
    }
    if args.list_formats:
        opts["listformats"] = True
        return opts

    pps: list[dict] = []

    # Covers / Subtitles: convert to common format first
    if args.cover:
        opts["writethumbnail"] = True
        pps.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
    if args.subs or args.embed_subs:
        opts["writesubtitles"] = True
        opts["subtitleslangs"] = [s.strip() for s in args.sub_langs.split(",") if s.strip()]
        if args.auto_subs:
            opts["writeautomaticsub"] = True
        pps.append({"key": "FFmpegSubtitlesConvertor", "format": args.sub_format, "when": "before_dl"})

    # Formats
    if args.mode == "mp3":
        opts["format"] = "bestaudio/best"
        pps.append({"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                    "preferredquality": str(args.abr)})
    else:
        opts["format"] = video_format(args.quality)
        opts["merge_output_format"] = "mp4"
        pps.append({"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"})  # Lossless remux if not mp4 container
        if args.embed_subs:
            pps.append({"key": "FFmpegEmbedSubtitle", "already_have_subtitle": True})

    pps.append({"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": True})
    if args.cover:
        pps.append({"key": "EmbedThumbnail", "already_have_thumbnail": args.keep_cover})
    opts["postprocessors"] = pps

    # Network / Login
    headers = {"User-Agent": UA}
    ref = referer or args.referer
    if ref:
        headers["Referer"] = ref
    opts["http_headers"] = headers
    if args.proxy:
        opts["proxy"] = args.proxy
    if args.limit_rate:
        rate = parse_bytes(args.limit_rate)
        if rate is None:
            sys.exit(f"Unrecognized rate limit value: {args.limit_rate} (Examples: 2M, 500K)")
        opts["ratelimit"] = rate
    if args.sleep:
        opts["sleep_interval"] = args.sleep
    if args.cookies:
        opts["cookiefile"] = args.cookies
    if args.cookies_from_browser:
        opts["cookiesfrombrowser"] = (args.cookies_from_browser,)
    if args.archive:
        opts["download_archive"] = args.archive
    if args.items:
        opts["playlist_items"] = args.items
    return opts


# ───────────────────────── Download Workflow ─────────────────────────

WORK_KEEP = {".mp3", ".srt", ".vtt", ".ass", ".jpg", ".jpeg", ".png", ".webp"}


def begin_work(args) -> Path | None:
    """MP3 mode first downloads and converts in a temp directory, then moves to target directory.

    Otherwise, if the direct link is itself an .mp4, converting to MP3 would delete an existing MP4 with the same name.
    """
    if args.mode != "mp3" or getattr(args, "list_formats", False):
        return None
    work = Path(args.output).expanduser().resolve() / ".work" / uuid.uuid4().hex[:8]
    work.mkdir(parents=True, exist_ok=True)
    return work


def finish_work(work: Path | None, args) -> dict[str, str]:
    """Move finished files (MP3, subtitles, cover) from temp directory to target directory, return {old path: new path}, and clean up temp files."""
    moved: dict[str, str] = {}
    if work is None:
        return moved
    out = Path(args.output).expanduser().resolve()
    try:
        for f in sorted(work.rglob("*")):
            if f.is_file() and f.suffix.lower() in WORK_KEEP:
                dest = out / f.relative_to(work)
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(f, dest)
                moved[str(f)] = str(dest)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        try:
            work.parent.rmdir()  # delete .work if empty
        except OSError:
            pass
    return moved


def attempt(url: str, args, referer: str | None = None, name: str | None = None) -> bool:
    work = begin_work(args)
    try:
        with yt_dlp.YoutubeDL(build_opts(args, referer, name, work)) as ydl:
            return ydl.download([url]) == 0
    except DownloadError:
        return False  # yt-dlp has already printed the error reason
    finally:
        finish_work(work, args)


def has_specific_extractor(url: str) -> bool:
    """Check if a non-generic dedicated extractor recognizes this link (if so, no need to scan page source)."""
    for ie in yt_dlp.extractor.gen_extractors():
        if ie.IE_NAME != "generic" and ie.suitable(url):
            return True
    return False


# ───────────────────────── Page Scanning ─────────────────────────
def fetch_page(url: str, proxy: str | None = None, limit: int = 5_000_000, timeout: float = 20.0) -> tuple[str, bytes, str]:
    """Download a page with yt-dlp's own networking, so it behaves like the downloads do.

    That means http, https and socks proxies all work, and the system proxy settings are used when no
    proxy is given (urllib's ProxyHandler cannot speak socks). Returns (content type, body, charset).
    """
    params = {"quiet": True, "no_warnings": True, "socket_timeout": timeout, "http_headers": {"User-Agent": UA}}
    if proxy:
        params["proxy"] = proxy
    with yt_dlp.YoutubeDL(params) as ydl:
        resp = ydl.urlopen(url)
        try:
            return resp.headers.get_content_type(), resp.read(limit), resp.headers.get_content_charset() or "utf-8"
        finally:
            resp.close()


def sniff_media_urls(page_url: str, log=print, proxy: str | None = None) -> tuple[str, list[str]]:
    """Fetch page HTML, find <video>/<source>/og:video and media direct links appearing in the source code."""
    try:
        ctype, raw, enc = fetch_page(page_url, proxy)
        if "html" not in ctype and not ctype.startswith("text/"):
            return "", []
    except Exception as e:  # noqa: BLE001
        log(f"[Scan] Cannot fetch page: {e}")
        return "", []

    text = html.unescape(raw.decode(enc, errors="replace")).replace("\\/", "/")
    m = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    found: list[str] = []
    pat = rf"""https?://[^\s"'<>\\()]+?\.{MEDIA_EXT}(?![A-Za-z0-9_])(?:\?[^\s"'<>\\]*)?"""
    found += [x.group(0) for x in re.finditer(pat, text, re.I)]
    for x in re.finditer(r"""<(?:video|source|audio)\b[^>]*?\bsrc=["']([^"']+)["']""", text, re.I):
        found.append(urljoin(page_url, x.group(1)))
    for x in re.finditer(
        r"""<meta[^>]+property=["']og:video(?::url|:secure_url)?["'][^>]+content=["']([^"']+)["']""",
        text, re.I,
    ):
        found.append(urljoin(page_url, x.group(1)))

    uniq = list(dict.fromkeys(u for u in found if u.startswith("http")))
    uniq.sort(key=lambda u: 0 if re.search(r"\.(m3u8|mpd)\b", u, re.I) else 1)  # Streaming manifests have most complete quality
    return title, uniq


# ───────────────────────── Headless Browser Rendering (Optional) ─────────────────────────
class JSRenderError(RuntimeError):
    """Headless browser is unavailable or page failed to load."""


_SEGMENT = re.compile(r"\.(?:ts|m4s|aac|cmfv|cmfa|vtt|webvtt|srt|key)$", re.I)
_MEDIA_PATH = re.compile(r"\.(?:mp4|webm|mov|m4v|mp3|m4a|flac|ogg)$", re.I)

# Inside the page (including all iframes): click common large play buttons, and mute <video>/<audio> while playing,
# and return their current http(s) addresses.
_PLAY_JS = """() => {
  // '播放' means 'play': kept for Chinese-language players
  const sels = ['.vjs-big-play-button','.plyr__control--overlaid','.jw-icon-display','.ytp-large-play-button',
    '.dplayer-play-icon','.xgplayer-start','.bpx-player-ctrl-play','.bilibili-player-video-btn-start',
    '[class*="big-play" i]','[class*="play-btn" i]','[class*="playBtn" i]','[class*="play_btn" i]',
    '[aria-label*="play" i]','[title*="play" i]','[aria-label*="播放"]','[title*="播放"]','button.play','.play'];
  for (const s of sels) {
    const e = document.querySelector(s);
    if (e && (e.offsetParent !== null || e.getClientRects().length)) { try { e.click(); } catch (_) {} break; }
  }
  const out = [];
  document.querySelectorAll('video, audio').forEach(v => {
    try { v.muted = true; const p = v.play(); if (p && p.catch) p.catch(() => {}); } catch (_) {}
    const u = v.currentSrc || v.src; if (u && /^https?:/i.test(u)) out.push(u);
  });
  return out;
}"""


def classify_media(url: str, ctype: str = "") -> tuple[bool, bool]:
    """Check if a network response is downloadable media, returns (is_media, is_manifest m3u8/mpd)."""
    if not url.startswith(("http://", "https://")):
        return False, False
    path = url.split("?", 1)[0].split("#", 1)[0].lower()
    ct = (ctype or "").split(";")[0].strip().lower()
    if path.endswith((".m3u8", ".mpd")) or "mpegurl" in ct or "dash+xml" in ct:
        return True, True
    if "mp2t" in ct or _SEGMENT.search(path):  # Fragments cannot be downloaded individually
        return False, False
    if _MEDIA_PATH.search(path) or ct.startswith(("video/", "audio/")):
        return True, False
    return False, False


def _launch_browser(p, browser: str, log):
    args = ["--disable-gpu", "--mute-audio", "--autoplay-policy=no-user-gesture-required"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:  # Required for Docker / root environments
        args.append("--no-sandbox")
    choice = (browser or "auto").strip()
    low = choice.lower()
    if low == "auto":
        attempts = [{"channel": "msedge"}, {"channel": "chrome"}, {}]
    elif low == "chromium":
        attempts = [{}]
    elif low in ("msedge", "chrome"):
        attempts = [{"channel": low}]
    else:
        attempts = [{"executable_path": choice}]
    last = None
    for kw in attempts:
        try:
            return p.chromium.launch(headless=True, args=args, **kw)
        except Exception as e:  # noqa: BLE001
            last = e
    reason = str(last).strip().splitlines()[0] if last else "Unknown reason"
    raise JSRenderError(
        f"Cannot launch browser ({reason}). Please install Edge or Chrome, or run  python -m playwright install chromium."
    )


def _system_proxy() -> str | None:
    """The proxy Python would use for HTTPS: environment variables, or the Windows / macOS system settings."""
    proxies = urllib.request.getproxies()
    return proxies.get("https") or proxies.get("http") or proxies.get("all") or None


def _playwright_proxy(proxy: str | None) -> dict | None:
    """Playwright wants credentials as separate fields, not inside the server URL."""
    if not proxy:
        return None
    parts = urlparse(proxy if "://" in proxy else f"http://{proxy}")
    if parts.scheme not in ("http", "https", "socks4", "socks5", "socks5h") or not parts.hostname:
        return None
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    cfg = {"server": f"{'socks5' if parts.scheme == 'socks5h' else parts.scheme}://{host}"
                     + (f":{parts.port}" if parts.port else "")}
    if parts.username:
        cfg["username"], cfg["password"] = unquote(parts.username), unquote(parts.password or "")
    return cfg


def render_media_urls(page_url: str, wait: float = 8.0, browser: str = "auto",
                      log=print, check=None, proxy: str | None = None) -> tuple[str, list[str]]:
    proxy = proxy or _system_proxy()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise JSRenderError(
            "Playwright is not installed. Run  pip install playwright "
            "(Windows comes with Edge, usually no need to download another browser; otherwise run  python -m playwright install chromium)."
        ) from None

    found: dict[str, bool] = {}  # Address -> Is manifest file; dict maintains discovery order
    title = ""
    with sync_playwright() as p:
        br = _launch_browser(p, browser, log)
        try:
            ctx_kwargs = {"user_agent": UA, "viewport": {"width": 1280, "height": 720}, "ignore_https_errors": True}
            pw_proxy = _playwright_proxy(proxy)
            if pw_proxy:
                ctx_kwargs["proxy"] = pw_proxy
            ctx = br.new_context(**ctx_kwargs)
            page = ctx.new_page()

            def on_response(resp):
                try:
                    if resp.status not in (200, 206):
                        return
                    ok, manifest = classify_media(resp.url, resp.headers.get("content-type", ""))
                except Exception:  # noqa: BLE001
                    return
                if ok and resp.url not in found:
                    found[resp.url] = manifest
                    log(f"[Render] Captured: {resp.url}")

            page.on("response", on_response)
            try:
                page.goto(page_url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as e:  # noqa: BLE001
                raise JSRenderError(f"Page load failed: {str(e).strip().splitlines()[0]}") from None
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:  # noqa: BLE001
                pass
            try:
                title = re.sub(r"\s+", " ", page.title()).strip()
            except Exception:  # noqa: BLE001
                pass

            t0, rounds = time.time(), 0
            deadline = t0 + max(2.0, wait)
            while time.time() < deadline:
                if check:
                    check()
                if time.time() - t0 >= rounds * 2.5:  # Attempt to trigger play every 2.5 seconds
                    rounds += 1
                    for fr in page.frames:
                        try:
                            for u in fr.evaluate(_PLAY_JS) or []:
                                if isinstance(u, str) and u not in found:
                                    found[u] = classify_media(u)[1]
                        except Exception:  # noqa: BLE001
                            pass
                page.wait_for_timeout(500)
                elapsed = time.time() - t0
                if any(found.values()) and elapsed > 1.5:
                    break  # Getting the manifest file is enough
                if found and elapsed > min(4.0, wait):
                    break  # Only direct links found, wait a bit longer and finish
            page.wait_for_timeout(300)
        finally:
            br.close()
    return title, sorted(found, key=lambda u: 0 if found[u] else 1)


# ───────────────────────── Discover and Download ─────────────────────────
def discover_and_download(url: str, args, download_one, log=print, on_title=None, check=None) -> bool:
    """First try yt-dlp; if unrecognized, scan page source; if still failing and --js-render is enabled, use headless browser.

    download_one(url, referer=None, name=None) -> bool is provided by the caller (CLI and WebUI have different progress outputs).
    """
    if download_one(url):
        return True
    if args.list_formats or args.no_sniff or has_specific_extractor(url):
        return False

    tried: set[str] = set()

    def try_all(cands: list[str], title: str, label: str) -> bool:
        ok_any = False
        for n, cand in enumerate(cands, 1):
            if check:
                check()
            tried.add(cand)
            log(f"[{label}] Attempting {n}/{len(cands)}: {cand}")
            name = (title or "video") + (f"-{n}" if args.all_sniffed and len(cands) > 1 else "")
            if download_one(cand, referer=url, name=name):
                ok_any = True
                if not args.all_sniffed:
                    break
        return ok_any

    log("[Scan] yt-dlp could not directly recognize the page, looking for media addresses in page source code...")
    title, cands = sniff_media_urls(url, log, proxy=args.proxy)
    if cands:
        log(f"[Scan] Found {len(cands)} candidate addresses")
        if title and on_title:
            on_title(title)
        if try_all(cands, title, "Scan"):
            return True
    else:
        log("[Scan] No media addresses found.")

    if not getattr(args, "js_render", False):
        log("[Hint] If the video is loaded dynamically by JavaScript, you can enable headless browser rendering (--js-render, requires pip install playwright), "
            "or copy the m3u8 / mp4 address from your browser's F12 → Network tab.")
        return False

    log("[Render] Loading page with headless browser to capture media streams from network requests...")
    try:
        rtitle, rcands = render_media_urls(url, args.js_wait, args.js_browser, log, check, proxy=args.proxy)
    except JSRenderError as e:
        log(f"[Render] {e}")
        return False
    rcands = [c for c in rcands if c not in tried]
    if not rcands:
        log("[Render] Browser did not capture any new media requests. The video may require login, clicking a specific button, or it might use DRM.")
        return False
    log(f"[Render] Captured {len(rcands)} media addresses")
    title = rtitle or title
    if title and on_title:
        on_title(title)
    return try_all(rcands, title, "Render")


def process(url: str, args) -> bool:
    return discover_and_download(url, args, lambda u, referer=None, name=None: attempt(u, args, referer, name))


# ───────────────────────── JavaScript runtime and diagnostics ─────────────────────────
def find_deno() -> str | None:
    """Locate Deno: on PATH first, then next to this Python.

    `pip install "yt-dlp[deno]"` puts it in the Scripts / bin folder, which is often not on PATH on Windows.
    """
    found = shutil.which("deno")
    if found:
        return found
    exe = "deno.exe" if os.name == "nt" else "deno"
    here = Path(sys.executable).resolve().parent
    dirs = [here, here / "Scripts"]
    for scheme in (None, "nt_user" if os.name == "nt" else "posix_user"):
        try:
            dirs.append(Path(sysconfig.get_path("scripts", scheme) if scheme else sysconfig.get_path("scripts")))
        except (KeyError, ValueError):
            pass
    dirs.append(Path.home() / ".deno" / "bin")
    for d in dirs:
        candidate = d / exe
        if candidate.is_file():
            return str(candidate)
    return None


def js_runtime_opts() -> dict:
    """Tell yt-dlp where Deno is, so it works even when Deno is not on PATH (yt-dlp >= 2025.11.12)."""
    path = find_deno()
    return {"js_runtimes": {"deno": {"path": path}}} if path else {}


def check_item(cid: str, label: str, status: str, detail: str, fix: str = "", action: str = "") -> dict:
    """status: ok / info / warn / error. action: an id the web UI can offer as a one-click fix."""
    return {"id": cid, "label": label, "status": status, "detail": detail, "fix": fix, "action": action}


def _first_line_of(cmd: list[str], timeout: float = 6.0) -> str:
    kw = {"creationflags": 0x08000000} if os.name == "nt" else {}  # no console window flashing on Windows
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace", **kw)
    except (OSError, subprocess.SubprocessError):
        return ""
    return ((r.stdout or r.stderr or "").strip().splitlines() or [""])[0]


def _dist_version(name: str) -> str:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return ""


def _browser_candidates() -> dict[str, list[str]]:
    env = os.environ
    if sys.platform == "win32":
        pf, pf86, local = env.get("ProgramFiles", ""), env.get("ProgramFiles(x86)", ""), env.get("LOCALAPPDATA", "")
        return {
            "Edge": [rf"{pf86}\Microsoft\Edge\Application\msedge.exe", rf"{pf}\Microsoft\Edge\Application\msedge.exe"],
            "Chrome": [rf"{pf}\Google\Chrome\Application\chrome.exe", rf"{pf86}\Google\Chrome\Application\chrome.exe",
                       rf"{local}\Google\Chrome\Application\chrome.exe"],
        }
    if sys.platform == "darwin":
        return {"Edge": ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"],
                "Chrome": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]}
    return {"Edge": [shutil.which("microsoft-edge") or ""],
            "Chrome": [shutil.which("google-chrome") or shutil.which("google-chrome-stable") or ""]}


def _probe_site(name: str, url: str, timeout: float = 6.0) -> dict:
    cid, label = f"net_{name.lower()}", f"Network: {name}"
    t0 = time.time()
    ms = lambda: int((time.time() - t0) * 1000)  # noqa: E731
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
            r.read(1)
            return check_item(cid, label, "ok", f"Reachable (HTTP {r.status}, {ms()} ms)")
    except urllib.error.HTTPError as e:  # something answered, but not with a success code
        return check_item(cid, label, "warn",
                          f"Answered HTTP {e.code} after {ms()} ms. This can be the site itself, or a proxy / firewall block page.",
                          fix="If the site opens normally in your browser, check your proxy settings.")
    except Exception as e:  # noqa: BLE001
        reason = getattr(e, "reason", None) or e
        return check_item(cid, label, "error", f"Not reachable: {reason}",
                          fix="Check your proxy or VPN. If you use one, set it in Advanced Settings, or start with --proxy.")


def run_diagnostics(output_dir: str | Path | None = None, net: bool = False) -> list[dict]:
    """Collect setup checks. Fast and offline unless net=True."""
    checks: list[dict] = []

    # Python and yt-dlp
    req = ""
    try:
        req = importlib_metadata.metadata("yt-dlp").get("Requires-Python", "") or ""
    except importlib_metadata.PackageNotFoundError:
        pass
    m = re.search(r">=\s*(\d+)\.(\d+)", req)
    py_ok = sys.version_info >= (int(m.group(1)), int(m.group(2))) if m else True
    checks.append(check_item(
        "python", "Python", "ok" if py_ok else "error",
        f"Python {platform.python_version()} on {platform.system()} {platform.release()}"
        + (f" (this yt-dlp needs {req})" if req else ""),
        fix="" if py_ok else "Install a newer Python from python.org."))
    checks.append(check_item("ytdlp", "yt-dlp", "ok", f"Version {yt_dlp.version.__version__}"))

    # ffmpeg / ffprobe
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        checks.append(check_item("ffmpeg", "ffmpeg", "ok", f"{_first_line_of([ffmpeg, '-version'])[:90]}"))
    else:
        checks.append(check_item("ffmpeg", "ffmpeg", "error",
                                 "Not found. Merging audio/video and MP3 conversion will fail.",
                                 fix="winget install Gyan.FFmpeg   (Windows, then reopen the terminal)"))
    if shutil.which("ffprobe"):
        checks.append(check_item("ffprobe", "ffprobe", "ok", "Found"))
    else:
        checks.append(check_item("ffprobe", "ffprobe", "warn", "Not found. It normally ships with ffmpeg; some post-processing needs it."))

    # JavaScript runtime and yt-dlp-ejs (needed for full YouTube support)
    deno = find_deno()
    if deno:
        checks.append(check_item("js_runtime", "JavaScript runtime (Deno)", "ok",
                                 f"{_first_line_of([deno, '--version'])[:60] or 'Deno'}  at {deno}"))
    else:
        others = [n for n in ("node", "bun", "qjs") if shutil.which(n)]
        detail = ("No JavaScript runtime found. YouTube extraction still partly works, but some formats will be missing. "
                  + (f"{', '.join(others)} is installed, but yt-dlp only enables Deno by default. " if others else "")
                  + "You can also install Deno yourself: winget install DenoLand.Deno (Windows) or brew install deno (macOS).")
        checks.append(check_item("js_runtime", "JavaScript runtime (Deno)", "warn", detail,
                                 fix='pip install -U "yt-dlp[default,deno]"', action="install_components"))
    if importlib.util.find_spec("yt_dlp_ejs"):
        checks.append(check_item("ejs", "yt-dlp-ejs component", "ok", f"Version {_dist_version('yt-dlp-ejs') or 'installed'}"))
    else:
        checks.append(check_item("ejs", "yt-dlp-ejs component", "warn",
                                 "Not installed. yt-dlp uses it to solve YouTube's challenges together with the JavaScript runtime. "
                                 "It is included when you install yt-dlp with the default extra.",
                                 fix='pip install -U "yt-dlp[default]"',
                                 action="install_components" if not deno else "install_default"))

    # Playwright (optional)
    if importlib.util.find_spec("playwright"):
        found = [name for name, paths in _browser_candidates().items() if any(p and Path(p).is_file() for p in paths)]
        detail = f"Version {_dist_version('playwright') or 'installed'}. "
        if found:
            checks.append(check_item("playwright", "Playwright (page rendering)", "ok",
                                     detail + f"Browsers it can use: {', '.join(found)}."))
        else:
            checks.append(check_item("playwright", "Playwright (page rendering)", "warn",
                                     detail + "No Edge or Chrome found. It will fall back to Playwright's own Chromium if installed.",
                                     fix="python -m playwright install chromium"))
    else:
        checks.append(check_item("playwright", "Playwright (page rendering)", "info",
                                 "Not installed. Optional: only needed for pages that load their video with JavaScript.",
                                 fix="pip install playwright"))

    # Proxy settings as Python sees them
    proxies = {k: v for k, v in urllib.request.getproxies().items() if v}
    checks.append(check_item("proxy", "Proxy settings", "info",
                             ", ".join(f"{k}={v}" for k, v in proxies.items()) if proxies
                             else "No system or environment proxy detected."))

    # Output folder
    if output_dir is not None:
        out = Path(output_dir).expanduser()
        try:
            out.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=out, prefix=".write-test-", delete=True):
                pass
            free = shutil.disk_usage(out).free / 1024 ** 3
            checks.append(check_item("output_dir", "Download folder", "ok" if free >= 2 else "warn",
                                     f"{out.resolve()}  ({free:.1f} GB free)"
                                     + ("" if free >= 2 else ". Low disk space.")))
        except OSError as e:
            checks.append(check_item("output_dir", "Download folder", "error", f"{out}: {e}",
                                     fix="Choose a folder you can write to with --dir / -o."))

    if sys.platform == "win32":
        checks.append(check_item(
            "browser_cookies", "Browser cookies (Windows)", "info",
            "Reading cookies straight from Chrome or Edge can fail while the browser is open. "
            "Close the browser completely, or export a cookies.txt and use that instead."))

    if net:
        sites = [("YouTube", "https://www.youtube.com/generate_204"), ("Bilibili", "https://www.bilibili.com/"),
                 ("PyPI", "https://pypi.org/simple/yt-dlp/")]
        with ThreadPoolExecutor(max_workers=len(sites)) as pool:
            checks += list(pool.map(lambda a: _probe_site(*a), sites))
    return checks


def _mask(text: str) -> str:
    """Hide the home directory and proxy credentials before a report is shared."""
    text = re.sub(r"(://)[^/@\s]+:[^/@\s]+@", r"\1***:***@", text)
    home = str(Path.home())
    return text.replace(home, "~") if home and home != "/" else text


def format_report(checks: list[dict], sections: list[tuple[str, list[str]]] | None = None) -> str:
    tag = {"ok": "OK", "info": "INFO", "warn": "WARN", "error": "ERROR"}
    lines = ["Video Grabber diagnostics", "Generated " + datetime.datetime.now().astimezone().isoformat(timespec="seconds"), ""]
    for c in checks:
        lines.append(f"[{tag.get(c['status'], c['status'].upper())}] {c['label']}: {c['detail']}")
        if c.get("fix"):
            lines.append(f"      Fix: {c['fix']}")
    for title, body in sections or []:
        lines += ["", f"{title}:"] + [f"  {ln}" for ln in body]
    return _mask("\n".join(lines))


def doctor_cli(args) -> int:
    checks = run_diagnostics(args.output, net=args.net)
    print(format_report(checks))
    if not args.net:
        print("\n(Add --net to also test whether YouTube, Bilibili and PyPI are reachable.)")
    return 1 if any(c["status"] == "error" for c in checks) else 0


def _safe_console() -> None:
    """A Windows console cannot show every character (an emoji in a video title, say). Replace, don't crash."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main() -> None:
    _safe_console()
    args = parse_args()
    if args.doctor:
        sys.exit(doctor_cli(args))
    if not shutil.which("ffmpeg") and not args.list_formats:
        sys.exit(FFMPEG_HELP)

    urls = collect_urls(args)
    if not urls:
        sys.exit("No URLs provided. See usage:  python grab.py -h")

    failed: list[str] = []
    try:
        for i, url in enumerate(urls, 1):
            print(f"\n=== [{i}/{len(urls)}] {url}")
            if not process(url, args):
                failed.append(url)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)

    if args.list_formats:
        return
    print(f"\nFinished: Success {len(urls) - len(failed)} / {len(urls)}, saved to: {Path(args.output).resolve()}")
    if failed:
        fail_file = Path(args.output) / "failed_urls.txt"
        fail_file.write_text("\n".join(failed) + "\n", encoding="utf-8")
        print(f"There were {len(failed)} failures, recorded in {fail_file}, you can retry with  -i {fail_file}")
        print('Hint: Sites change often. On failure run  pip install -U "yt-dlp[default]"  and retry, or run  python grab.py --doctor')
        sys.exit(1)


if __name__ == "__main__":
    main()