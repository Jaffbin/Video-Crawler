"""Seed yt-dlp's download archive from files the Library already has.

yt-dlp only skips videos it recorded itself while the archive option was on, so a file downloaded earlier,
imported by another run, or recorded before the option was enabled would be downloaded again. Before a task
that asked to skip downloaded videos, the Library's complete files are written into the archive as well.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urlparse

from yt_dlp.extractor import gen_extractor_classes

VIDEO_SUFFIXES = {".mp4", ".webm", ".mkv", ".mov"}
_LOCK = threading.Lock()
_EXTRACTORS: list | None = None
_BY_URL: dict[str, str] = {}
_BY_HOST: dict[str, list] = {}
_NO_EXTRACTOR: set[str] = set()


def _extractors() -> list:
    global _EXTRACTORS
    if _EXTRACTORS is None:
        _EXTRACTORS = [ie for ie in gen_extractor_classes() if ie.ie_key() != "Generic"]
    return _EXTRACTORS


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def archive_id(url: str) -> str:
    """The line yt-dlp writes for this video (``youtube WCgcSFC1GsU``), or '' when no site extractor owns the URL.

    Matching all ~1700 extractors costs ~0.15 s, so a URL only pays that once per host: later URLs of the
    same host try the extractors that matched before. A wrong or missing id only means one video is
    downloaded again, never that one is skipped by mistake.
    """
    if url in _BY_URL:
        return _BY_URL[url]
    host = _host(url)
    result = ""
    if host and host not in _NO_EXTRACTOR:
        ies = _BY_HOST.get(host, [])
        found = next((ie for ie in ies if _suitable(ie, url)), None)
        if found is None:
            found = next((ie for ie in _extractors() if _suitable(ie, url)), None)
            if found is None:
                _NO_EXTRACTOR.add(host)
            else:
                _BY_HOST.setdefault(host, []).append(found)
        if found is not None:
            try:
                result = f"{found.ie_key().lower()} {found.get_temp_id(url)}"
            except Exception:  # noqa: BLE001 - an extractor that cannot name the video just means no skip
                result = ""
    _BY_URL[url] = result
    return result


def _suitable(ie, url: str) -> bool:
    try:
        return bool(ie.suitable(url))
    except Exception:  # noqa: BLE001 - one broken third-party extractor must not stop the others
        return False


def seed_archive(
    archive: Path,
    records: dict,
    *,
    kind: str,
    audio_suffixes: Iterable[str],
    is_complete_file: Callable[[str], bool],
) -> int:
    """Append archive lines for complete Library files of ``kind`` ('video' or 'audio'); returns how many.

    ``is_complete_file`` is asked about each record's relative path so a record whose file was deleted outside
    the app never blocks a fresh download.
    """
    audio = {suffix.lower() for suffix in audio_suffixes}
    wanted: list[str] = []
    for relative, record in records.items():
        if not isinstance(record, dict) or record.get("complete") is False or record.get("role") == "image":
            continue
        suffix = Path(relative).suffix.lower()
        if (kind == "audio" and suffix not in audio) or (kind == "video" and suffix not in VIDEO_SUFFIXES):
            continue
        url = record.get("source_url")
        line = archive_id(url) if isinstance(url, str) and url else ""
        if line and is_complete_file(relative):
            wanted.append(line)
    if not wanted:
        return 0
    with _LOCK:
        try:
            known = set(archive.read_text(encoding="utf-8").splitlines()) if archive.is_file() else set()
        except OSError:
            return 0
        missing = [line for line in dict.fromkeys(wanted) if line not in known]
        if not missing:
            return 0
        archive.parent.mkdir(parents=True, exist_ok=True)
        needs_break = archive.is_file() and archive.stat().st_size > 0 and not archive.read_bytes().endswith(b"\n")
        with archive.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(("\n" if needs_break else "") + "\n".join(missing) + "\n")
        return len(missing)
