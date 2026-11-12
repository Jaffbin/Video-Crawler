"""Validation and per-run copies of the uploaded cookies.txt (Netscape format).

These functions take the file locations as arguments; webui.py supplies the current settings folder.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import tempfile
import time
from pathlib import Path


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


def cookies_status(path: Path) -> dict:
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


def save_cookies(text: str, path: Path) -> dict:
    info = parse_cookies(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(info["text"])
    with contextlib.suppress(OSError):
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return cookies_status(path)


def delete_cookies(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


@contextlib.contextmanager
def cookie_copy(args, directory: Path):
    """Give every yt-dlp run its own copy of the cookies file.

    yt-dlp writes cookies back to the file when it closes; separate copies stop parallel jobs from
    clobbering each other and keep the uploaded file exactly as the user exported it.
    """
    if not getattr(args, "cookies", None):
        yield None
        return
    tmp = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="run-", suffix=".txt", dir=directory)
        os.close(fd)
        shutil.copyfile(args.cookies, tmp)
        yield tmp
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.remove(tmp)
