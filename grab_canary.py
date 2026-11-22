"""Try a new yt-dlp on a few sites before switching to it (docs/adr/0010-canary-yt-dlp-updates.md).

A newer yt-dlp is installed into a separate staging folder. The current and the staged versions then
read metadata for the same links in child processes, at the same time and on the same network, and
only a link that works with the current version but fails with the new one counts as a regression.
That turns flaky single requests (dead links, rate limits, sign-in walls) into a usable signal
without any project server. Probes never download media and never receive cookies.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

PROBE_TIMEOUT_SECONDS = 45
PARALLEL_PROBES = 2
RECENT_SITES_MAX = 3

# Stable, public, permissively licensed videos. Each licence was read from the site's own metadata
# (yt-dlp's "license" field) when it was added. All three are Blender Foundation's Big Buck Bunny.
BUILT_IN_PROBES = (
    {"site": "YouTube", "url": "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
     "why": "Blender's official upload; Creative Commons Attribution"},
    {"site": "Internet Archive", "url": "https://archive.org/details/BigBuckBunny_124",
     "why": "CC BY 3.0"},
    {"site": "Wikimedia Commons", "url": "https://commons.wikimedia.org/wiki/File:Big_Buck_Bunny_4K.webm",
     "why": "Creative Commons Attribution 3.0"},
)

# Runs inside a child process: argv = [url, options JSON, extra sys.path entries JSON].
PROBE_SCRIPT = r"""
import json, sys
url, options, paths = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
sys.path[:0] = paths
try:
    import yt_dlp
    from yt_dlp.version import __version__
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    info = (info.get("entries") or [info])[0] if info and info.get("_type") == "playlist" else info
    formats = [f for f in (info or {}).get("formats") or [] if f.get("url")] or ([info] if info and info.get("url") else [])
    result = {"ok": bool(formats), "version": __version__,
              "error": "" if formats else "No playable format was found."}
except BaseException as error:  # report every failure as data, never as a crash
    result = {"ok": False, "version": "", "error": (str(error) or type(error).__name__)[:300]}
print("CANARY-RESULT " + json.dumps(result))
"""


def probe_options(extra: dict | None = None) -> dict:
    """yt-dlp options for a probe: metadata only, no playlists, no cookies, no files written."""
    options = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
               "socket_timeout": 20, "retries": 1, "extractor_retries": 1, "cachedir": False,
               "noprogress": True}
    options.update(extra or {})
    for key in ("cookiefile", "cookiesfrombrowser", "username", "password", "usenetrc", "netrc_cmd"):
        options.pop(key, None)  # probes never use sign-in data
    return options


def run_probe(url: str, paths: list[str], options: dict, *, python: str = sys.executable,
              timeout: float = PROBE_TIMEOUT_SECONDS, runner=subprocess.run) -> dict:
    """One link with one yt-dlp: {"ok", "version", "error"}. Never raises for a failed probe."""
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
    with tempfile.TemporaryDirectory(prefix="vg-canary-") as empty:  # -c puts the working folder on sys.path
        try:
            done = runner([python, "-c", PROBE_SCRIPT, url, json.dumps(options), json.dumps(paths)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=empty, env=env, creationflags=flags)
        except subprocess.TimeoutExpired:
            return {"ok": False, "version": "", "error": f"No answer within {int(timeout)} seconds."}
        except OSError as error:
            return {"ok": False, "version": "", "error": f"Could not start the check: {error}"[:300]}
    for line in reversed((done.stdout or "").splitlines()):
        if line.startswith("CANARY-RESULT "):
            try:
                result = json.loads(line[len("CANARY-RESULT "):])
            except ValueError:
                break
            if isinstance(result, dict):
                return {"ok": result.get("ok") is True, "version": str(result.get("version") or ""),
                        "error": str(result.get("error") or "")[:300]}
    return {"ok": False, "version": "", "error": ((done.stderr or "").strip().splitlines() or ["The check stopped."])[-1][:300]}


def verdict(current_ok: bool, new_ok: bool) -> str:
    """fine, fixed, inconclusive or regression, per the table in ADR 0010."""
    if current_ok:
        return "fine" if new_ok else "regression"
    return "fixed" if new_ok else "inconclusive"


def overall(results: list[dict]) -> str:
    """pass, regression or untestable for a whole run."""
    if any(item["verdict"] == "regression" for item in results):
        return "regression"
    if not any(item["verdict"] != "inconclusive" for item in results):
        return "untestable"
    return "pass"


def recent_probes(jobs, limit: int = RECENT_SITES_MAX) -> list[dict]:
    """One recent successful link per site, newest first, for users who opt in."""
    built_in = {urlsplit(item["url"]).hostname for item in BUILT_IN_PROBES}
    seen, result = set(), []
    for job in jobs:
        url = getattr(job, "url", "")
        host = (urlsplit(url).hostname or "").lower()
        if getattr(job, "status", "") != "done" or not url.startswith(("http://", "https://")) or not host:
            continue
        if host in seen or host in built_in:
            continue
        seen.add(host)
        result.append({"site": host.removeprefix("www."), "url": url, "why": "recently downloaded"})
        if len(result) == limit:
            break
    return result


def compare(probes: list[dict], staged: Path, options: dict, *, progress=None, probe=run_probe) -> list[dict]:
    """Probe each link with the current and the staged yt-dlp and return one result per link."""
    tasks = [(item, side) for item in probes for side in ("current", "new")]
    outcomes: dict[tuple[str, str], dict] = {}

    def one(task):
        item, side = task
        outcome = probe(item["url"], [str(staged)] if side == "new" else [], options)
        outcomes[(item["url"], side)] = outcome
        if progress:
            progress(len(outcomes), len(tasks))
        return outcome

    with ThreadPoolExecutor(max_workers=PARALLEL_PROBES) as pool:
        list(pool.map(one, tasks))
    results = []
    for item in probes:
        current, new = outcomes[(item["url"], "current")], outcomes[(item["url"], "new")]
        results.append({"site": item["site"], "url": item["url"], "current": current["ok"], "new": new["ok"],
                        "verdict": verdict(current["ok"], new["ok"]),
                        "error": new["error"] if not new["ok"] else ""})
    return results


def remove_staging(path: Path) -> None:
    """Delete a staging folder; it only ever holds a pip --target install."""
    if path.exists() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
