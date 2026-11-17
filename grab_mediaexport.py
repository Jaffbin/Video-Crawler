"""Export Library videos for media servers (Jellyfin, Emby, Kodi, Plex).

Layout, one show per channel and one season per year::

    <export>/<Channel>/tvshow.nfo, poster.jpg
    <export>/<Channel>/Season 2026/<Channel> - S2026E111501 - <Title> [<id>].mp4  (+ .nfo, -thumb.jpg, .srt)

The episode number is the upload date (MMDD) plus a two-digit counter, the common convention for
date-based channels. Files are hard-linked when the export folder is on the same disk (no extra space)
and copied otherwise. Nothing in the export folder is ever overwritten or deleted.
"""
from __future__ import annotations

import datetime
import glob
import hashlib
import os
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

SUBTITLE_SUFFIXES = {".srt", ".vtt", ".ass", ".ssa"}
THUMB_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class ExportError(Exception):
    pass


def safe_name(text: str, limit: int = 120) -> str:
    """Valid on Windows and media servers: no reserved characters, no trailing dots or spaces."""
    cleaned = UNSAFE.sub(" ", str(text or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)[:limit].rstrip(" .")
    return cleaned or "Untitled"


def episode_info(record: dict, relative: str, downloaded: float | None = None) -> dict:
    """What the export needs from a Library record, with fallbacks for downloads made before the
    app recorded channel and upload date."""
    info = record.get("media_info") if isinstance(record.get("media_info"), dict) else {}
    show = info.get("channel") or record.get("source") or "Other"
    upload = str(info.get("upload_date") or "")
    if re.fullmatch(r"\d{8}", upload):
        date = datetime.date(int(upload[:4]), int(upload[4:6]), int(upload[6:]))
    else:
        stamp = record.get("downloaded") if isinstance(record.get("downloaded"), (int, float)) else downloaded
        date = datetime.date.fromtimestamp(stamp) if stamp else datetime.date.today()
    key = str(info.get("id") or "") or hashlib.sha1(relative.encode("utf-8")).hexdigest()[:11]
    return {
        "show": safe_name(show, 80), "title": str(record.get("title") or Path(relative).stem)[:300],
        "date": date, "key": re.sub(r"[^\w-]", "", key)[:40] or "video",
        "plot": str(info.get("description") or "")[:5000],
        "source_url": str(record.get("source_url") or ""),
        "site": str(info.get("extractor") or record.get("source") or "").lower(),
        "duration": info.get("duration") if isinstance(info.get("duration"), (int, float)) else None,
    }


def _existing_episode(season: Path, key: str) -> Path | None:
    """A video already exported under this key, found by the [key] in its name."""
    if not season.is_dir():
        return None
    marker = f" [{key}]."
    for file in season.iterdir():
        if marker in file.name and file.suffix.lower() == ".nfo":
            return file.with_suffix("")
    return None


def _next_episode(season: Path, date: datetime.date) -> int:
    prefix = f"E{date:%m%d}"
    used = set()
    if season.is_dir():
        for file in season.iterdir():
            match = re.search(rf" - S\d{{4}}{prefix}(\d{{2}}) - ", file.name)
            if match:
                used.add(int(match.group(1)))
    number = next((n for n in range(1, 100) if n not in used), None)
    if number is None:
        raise ExportError(f"More than 99 videos on {date.isoformat()} for this channel.")
    return int(f"{date:%m%d}{number:02d}")


def link_or_copy(source: Path, target: Path) -> str:
    """Hard link when possible, otherwise copy. Returns "hardlink", "copy" or "exists"."""
    if target.exists():
        if target.stat().st_size == source.stat().st_size:
            return "exists"
        raise ExportError(f"A different file already exists: {target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        # Different disk, or a file system without hard links (FAT, some network shares).
        temp = target.with_name(target.name + ".part")
        shutil.copy2(source, temp)
        os.replace(temp, target)
        return "copy"


def _write_xml(root: ET.Element, target: Path) -> None:
    ET.indent(root)
    temp = target.with_name(target.name + ".tmp")
    ET.ElementTree(root).write(temp, encoding="utf-8", xml_declaration=True)
    os.replace(temp, target)


def episode_nfo(info: dict, season: int, episode: int) -> ET.Element:
    root = ET.Element("episodedetails")
    for tag, value in (("title", info["title"]), ("showtitle", info["show"]), ("season", season),
                       ("episode", episode), ("plot", info["plot"]), ("aired", info["date"].isoformat()),
                       ("premiered", info["date"].isoformat()), ("studio", info["show"])):
        ET.SubElement(root, tag).text = str(value)
    if info["duration"]:
        ET.SubElement(root, "runtime").text = str(max(1, round(info["duration"] / 60)))
    unique = ET.SubElement(root, "uniqueid", type=info["site"] or "web", default="true")
    unique.text = info["key"]
    if info["source_url"]:
        ET.SubElement(root, "trailer").text = info["source_url"]
    return root


def show_nfo(info: dict) -> ET.Element:
    root = ET.Element("tvshow")
    ET.SubElement(root, "title").text = info["show"]
    ET.SubElement(root, "studio").text = info["show"]
    return root


def companions(media: Path) -> tuple[list[tuple[Path, str]], Path | None]:
    """(subtitles with their name suffix after the stem, cover image) saved next to ``media``."""
    subtitles = []
    for file in media.parent.glob(glob.escape(media.stem) + ".*"):
        rest = file.name[len(media.stem):]
        if file.suffix.lower() in SUBTITLE_SUFFIXES and rest.count(".") <= 2:
            subtitles.append((file, rest))
    cover = next((media.with_suffix(s) for s in THUMB_SUFFIXES if media.with_suffix(s).is_file()), None)
    return sorted(subtitles), cover


def export_video(media: Path, record: dict, relative: str, export_root: Path) -> dict:
    """Place one video, its subtitles, cover and NFO files in ``export_root``. Never overwrites."""
    if not media.is_file():
        raise ExportError("The file no longer exists.")
    info = episode_info(record, relative, media.stat().st_mtime)
    show_dir = export_root / info["show"]
    season_dir = show_dir / f"Season {info['date'].year}"
    base = _existing_episode(season_dir, info["key"])
    if base is None:
        episode = _next_episode(season_dir, info["date"])
        name = safe_name(f"{info['show']} - S{info['date'].year}E{episode} - {info['title']}", 180)
        base = season_dir / f"{name} [{info['key']}]"
    else:
        episode = int(re.search(r"E(\d+) - ", base.name).group(1))
    method = link_or_copy(media, base.with_name(base.name + media.suffix.lower()))
    subtitles, cover = companions(media)
    for file, rest in subtitles:
        link_or_copy(file, base.with_name(base.name + rest))
    if cover:
        link_or_copy(cover, base.with_name(base.name + "-thumb" + cover.suffix.lower()))
        poster = show_dir / ("poster" + cover.suffix.lower())
        if not any((show_dir / f"poster{s}").exists() for s in THUMB_SUFFIXES):
            link_or_copy(cover, poster)
    nfo = base.with_name(base.name + ".nfo")
    _write_xml(episode_nfo(info, info["date"].year, episode), nfo)
    if not (show_dir / "tvshow.nfo").exists():
        _write_xml(show_nfo(info), show_dir / "tvshow.nfo")
    return {"status": "exists" if method == "exists" else "exported", "method": method,
            "target": str(base.with_name(base.name + media.suffix.lower()))}


def check_folder(folder, library_root: Path) -> Path:
    """An absolute export folder outside the download folder (the Library would list everything twice)."""
    if not isinstance(folder, str) or not folder.strip():
        raise ExportError("Choose a folder for the media server.")
    path = Path(folder.strip()).expanduser()
    if not path.is_absolute():
        raise ExportError("Enter the full path of the media server folder.")
    resolved, library = path.resolve(), library_root.resolve()
    if resolved == library or library in resolved.parents:
        raise ExportError("Choose a folder outside the download folder.")
    return resolved
