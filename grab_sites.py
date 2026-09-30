"""Small, isolated adapters for sites that yt-dlp's generic extractor cannot reliably parse."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit


_HANIME1_HOSTS = {"hanime1.me", "www.hanime1.me"}
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_HEIGHT = re.compile(r"(?<!\d)(\d{3,4})p(?!\d)", re.IGNORECASE)


@dataclass(frozen=True)
class SiteMedia:
    url: str
    title: str = ""
    height: int | None = None


def hanime1_download_page(page_url: str) -> str | None:
    """Return the public download page for a valid hanime1 watch URL."""
    parts = urlsplit(page_url)
    if parts.scheme not in {"http", "https"} or (parts.hostname or "").lower() not in _HANIME1_HOSTS:
        return None
    if parts.path.rstrip("/") != "/watch":
        return None
    video_ids = parse_qs(parts.query, keep_blank_values=True).get("v", [])
    if len(video_ids) != 1 or not _VIDEO_ID.fullmatch(video_ids[0]):
        return None
    return urlunsplit((parts.scheme, parts.netloc, "/download", urlencode({"v": video_ids[0]}), ""))


class _DownloadTableParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.table_depth = 0
        self.current: dict[str, str] | None = None
        self.text: list[str] = []
        self.items: list[SiteMedia] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "table":
            classes = values.get("class", "").split()
            if self.table_depth or "download-table" in classes:
                self.table_depth += 1
        elif self.table_depth and tag.lower() in {"a", "button"} and any(
            values.get(name) for name in ("href", "data-url", "data-src")
        ):
            self.current = values
            self.text = []

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        low = tag.lower()
        if low in {"a", "button"} and self.current is not None:
            media_url = next(
                (self.current.get(name, "") for name in ("href", "data-url", "data-src") if self.current.get(name)),
                "",
            )
            href = urljoin(self.base_url, media_url)
            if href.startswith(("http://", "https://")):
                label = " ".join("".join(self.text).split())
                title = re.sub(
                    r"\.(?:mp4|webm|mov|m4v|mp3|m4a|aac|flac|ogg)\Z", "",
                    self.current.get("download", "").strip(), flags=re.IGNORECASE,
                )
                match = _HEIGHT.search(" ".join((label, title, href)))
                self.items.append(SiteMedia(href, title, int(match.group(1)) if match else None))
            self.current = None
            self.text = []
        elif low == "table" and self.table_depth:
            self.table_depth -= 1


def parse_hanime1_downloads(document: str, download_page: str, quality: str = "best") -> list[SiteMedia]:
    parser = _DownloadTableParser(download_page)
    parser.feed(document)
    unique = list({item.url: item for item in parser.items}.values())
    if quality == "best":
        return sorted(unique, key=lambda item: item.height if item.height is not None else 10_000, reverse=True)

    limit = int(quality)
    within_limit = [item for item in unique if item.height is not None and item.height <= limit]
    unknown = [item for item in unique if item.height is None]
    above_limit = [item for item in unique if item.height is not None and item.height > limit]
    return (
        sorted(within_limit, key=lambda item: item.height or -1, reverse=True)
        + unknown
        + sorted(above_limit, key=lambda item: item.height or 10_000)
    )
