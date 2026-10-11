"""Original-format image downloads with bounded requests and atomic publication."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import HTTPError, RequestError
from yt_dlp.utils import DownloadCancelled, sanitize_filename
from grab_download import transient_network_error

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
IMAGE_MAX_BYTES = 100 * 1024 * 1024


def image_extension(header: bytes) -> str:
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ".webp"
    if header[4:8] == b"ftyp" and any(
        header[i:i + 4] in (b"avif", b"avis") for i in [8, *range(16, min(len(header), 64), 4)]
    ):
        return ".avif"
    raise ValueError("The response is not a supported image (JPG, PNG, WebP, GIF or AVIF).")


def image_response(response) -> tuple[bytes, str, int | None]:
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if content_type and not content_type.startswith("image/") and content_type not in (
        "application/octet-stream", "binary/octet-stream",
    ):
        raise ValueError("The link returned a page instead of an image. Use a direct image URL.")
    length = response.headers.get("Content-Length", "")
    size = int(length) if length.isdigit() and not response.headers.get("Content-Encoding") else None
    if size is not None and size > IMAGE_MAX_BYTES:
        raise ValueError("Image exceeds the 100 MiB download limit.")
    header = response.read(64)
    return header, image_extension(header), size


def image_title(url: str) -> str:
    return sanitize_filename(Path(unquote(urlparse(url).path)).stem, restricted=False)[:100] or "image"


def wait(seconds, check):
    deadline = time.monotonic() + seconds
    while (remaining := deadline - time.monotonic()) > 0:
        check()
        time.sleep(min(remaining, 0.1))
    check()


def probe_image(client, url: str, headers=None) -> dict:
    with client.urlopen(Request(url, headers={**(headers or {}), "Accept-Encoding": "identity"})) as response:
        _, extension, size = image_response(response)
    return {"kind": "image", "title": image_title(url), "image_format": extension[1:].upper(),
            "size": {"bytes": size, "approximate": False}}


def download_image(client, url: str, root: Path, *, base: Path | None = None,
                   headers=None, check=lambda: None, progress=lambda _: None) -> Path:
    """Retry transient requests; incomplete files never become visible Library items."""
    root = root.resolve()
    if base is None:
        digest = hashlib.sha256(url.encode()).hexdigest()[:12]
        base = root / "images" / f"{image_title(url)} [{digest}]"
    base = base.resolve()
    base.relative_to(root)
    if any(part.startswith(".") for part in base.relative_to(root).parts):
        raise ValueError("Choose a file inside the download folder")
    wait(client.params.get("sleep_interval") or 0, check)
    for attempt in range(3):
        temporary = None
        try:
            check()
            with client.urlopen(Request(url, headers={**(headers or {}), "Accept-Encoding": "identity"})) as response:
                header, extension, size = image_response(response)
                destination = Path(str(base) + extension)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.resolve().relative_to(root)
                if destination.is_symlink():
                    raise ValueError("Choose a regular image file")
                downloaded = len(header)
                started = time.monotonic()
                with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".image-", suffix=".part", delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(header)
                    while True:
                        check()
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        downloaded += len(chunk)
                        if downloaded > IMAGE_MAX_BYTES:
                            raise ValueError("Image exceeds the 100 MiB download limit.")
                        stream.write(chunk)
                        rate = client.params.get("ratelimit")
                        if rate:
                            wait(max(0, downloaded / rate - (time.monotonic() - started)), check)
                        progress({"downloaded_bytes": downloaded, "total_bytes": size,
                                  "speed": downloaded / max(time.monotonic() - started, 0.001)})
                    if size is not None and downloaded != size:
                        raise ValueError("The image download is incomplete. Retry the link.")
                    stream.flush()
                    os.fsync(stream.fileno())
                check()
                os.replace(temporary, destination)
                return destination
        except DownloadCancelled:
            raise
        except RequestError as error:
            transient = error.status in (408, 429, 500, 502, 503, 504) if isinstance(error, HTTPError) else transient_network_error(str(error))
            if attempt == 2 or not transient:
                raise
            progress({"retry_attempt": attempt + 1})
            wait(2 ** attempt, check)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    raise RuntimeError("Image download did not finish")


def thumbnail_downloader(base_class, root: Path, check=lambda: None,
                         progress=lambda _: None, on_image=lambda path, info: None):
    class ThumbnailDownloader(base_class):
        def _write_thumbnails(self, label, info_dict, filename, thumb_filename_base=None):
            if label != "video":
                return []
            thumbnails = info_dict.get("thumbnails") or []
            for thumbnail in reversed(thumbnails):
                url = thumbnail.get("url") or ""
                if urlparse(url).scheme not in ("http", "https"):
                    continue
                try:
                    # The normal template has a video extension, removed before sniffing the image.
                    target = Path(thumb_filename_base or filename).with_suffix("")
                    path = download_image(self, url, root, base=target,
                                          headers=thumbnail.get("http_headers") or info_dict.get("http_headers"),
                                          check=check, progress=progress)
                    thumbnail["filepath"] = str(path)
                    on_image(str(path), info_dict)
                    return [(str(path), str(path))]
                except DownloadCancelled:
                    raise
                except (RequestError, OSError, ValueError) as error:
                    self.report_warning(f"Could not save this cover: {error}")
            self.report_error("No supported video cover could be downloaded from this source.")
            return None

    return ThumbnailDownloader
