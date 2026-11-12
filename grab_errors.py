"""Pure helpers that turn downloader output into text a person can act on."""

from __future__ import annotations

import importlib.util
import re

from grab_download import transient_network_error

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


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


def error_details(msg: str) -> dict[str, str]:
    """Classify a downloader failure without discarding its actionable cause."""
    m = re.sub(r"^ERROR:\s*", "", strip_ansi(msg or "").strip())
    # yt-dlp appends "; please report this issue ... Confirm you are on the latest version" to unexpected errors.
    # That boilerplate must not be mistaken for the real cause ("confirm you" once triggered the login message).
    m = re.split(r";\s*please report this issue", m, maxsplit=1)[0].strip()
    low = m.lower()
    if "winerror 4551" in low:
        return {"kind": "app_control", "message": "Windows blocked a media component.",
                "hint": "View technical details to identify the blocked file. Automatic setup cannot override Windows security."}
    if "unsupported url" in low:
        return {"kind": "unsupported", "message": "Cannot recognize this page or find a media URL.",
                "hint": "Enable page rendering in Advanced Settings. If that still fails, paste the m3u8 or mp4 URL from the browser Network panel."}
    if any(k in low for k in ("javascript runtime", "challenge solving failed", "signature solving failed")):
        return {"kind": "javascript", "message": "The site challenge could not be solved.",
                "hint": "Open Diagnostics and install Deno plus the recommended yt-dlp components."}
    if "cookie" in low and any(k in low for k in ("could not copy", "cookie database", "decrypt", "locked")):
        return {"kind": "cookies_locked", "message": "Could not read the browser's cookies.",
                "hint": "Close the browser completely and retry, or upload a cookies.txt file in Advanced Settings."}
    if "cookies are no longer valid" in low or "likely been rotated" in low:
        return {"kind": "cookies_expired", "message": "The saved cookies were rotated or expired.",
                "hint": "Export a fresh cookies.txt from a private window and upload it in Advanced Settings."}
    if any(k in low for k in ("sign in", "log in", "login", "not a bot", "use --cookies", "cookies-from-browser")):
        return {"kind": "login", "message": "This content requires login or verification.",
                "hint": "Upload a cookies.txt file or select a browser in Advanced Settings, then retry."}
    if re.search(r"winerror 32\b", low) or "used by another process" in low or "sharing violation" in low:
        return {"kind": "file_locked", "message": "A player or another app is using this file.",
                "hint": "Close the player, then retry. Open the download folder to find the file."}
    if "permission denied" in low or re.search(r"winerror 5\b", low) or "access is denied" in low:
        return {"kind": "file_permission", "message": "The app cannot save to this folder.",
                "hint": "Check the download folder is writable and close any player using the file, then retry."}
    if any(k in low for k in ("no space left", "disk full", "errno 28")):
        return {"kind": "disk_full", "message": "The download drive is out of free space.",
                "hint": "Free some space or choose another download folder, then retry."}
    if "ffmpeg" in low or "ffprobe" in low:
        return {"kind": "ffmpeg", "message": "ffmpeg is missing or could not process the media.",
                "hint": "Open Diagnostics and verify the selected ffmpeg can run; check its path and application control policy, then restart the app."}
    if any(k in low for k in ("getaddrinfo failed", "name or service not known", "nodename nor servname",
                              "temporary failure in name resolution", "no address associated")):
        return {"kind": "dns", "message": "Cannot find that site's address.",
                "hint": "Check the link and DNS settings, then open Diagnostics > Test network."}
    if "certificate" in low and "verify" in low:
        return {"kind": "certificate", "message": "The site's SSL certificate could not be verified.",
                "hint": "Check the system clock and any antivirus, VPN, or proxy that inspects HTTPS."}
    if transient_network_error(m) or any(k in low for k in ("timed out", "connection refused", "failed to establish a new connection", "connection reset",
                              "network is unreachable", "proxyerror", "unable to connect to proxy")):
        return {"kind": "network", "message": "Cannot reach the site.",
                "hint": "Check the network, VPN, DNS, or proxy, then open Diagnostics > Test network."}
    if "http error 403" in low or "http error 401" in low:
        if importlib.util.find_spec("curl_cffi") is None:
            return {"kind": "impersonation_missing", "message": "The server denied access and browser impersonation is unavailable.",
                    "hint": "Open Diagnostics, install the recommended components, then retry."}
        return {"kind": "forbidden", "message": "The server denied access.",
                "hint": "Add the source page as Referer or provide cookies in Advanced Settings, then retry."}
    if "http error 404" in low:
        return {"kind": "not_found", "message": "The link was not found or has expired (404).",
                "hint": "Open the original page and copy a fresh link."}
    return {"kind": "unknown", "message": m[:300] or "Download failed.",
            "hint": "Expand the log for the technical details, update yt-dlp, then retry."}


def friendly_error(msg: str) -> str:
    details = error_details(msg)
    return f"{details['message']} {details['hint']}".strip()
