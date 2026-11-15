"""Local automation API: an opt-in, token-protected way for other programs on this computer to queue
downloads and read their status (for example n8n, AutoHotkey, Raycast or a shell script).

Only a SHA-256 hash of the token is stored; the token itself is shown once when created. The API
token works only on /api/v1/ routes, and the app's own page token does not work there.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets

MAX_URLS = 50
MODES = ("mp4", "mp3", "original", "cover", "image")
ABR = (96, 128, 192, 256, 320)
TOKEN_PREFIX = "vg_"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    """(token to show once, hash to store)."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, hash_token(token)


def settings(raw) -> dict:
    """Saved API settings; anything unexpected means the API stays off."""
    if not isinstance(raw, dict):
        return {"enabled": False, "token_sha256": ""}
    digest = raw.get("token_sha256")
    digest = digest if isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest) \
        else ""
    return {"enabled": raw.get("enabled") is True and bool(digest), "token_sha256": digest}


def token_matches(header: str | None, saved: dict) -> bool:
    if not saved["enabled"] or not saved["token_sha256"] or not isinstance(header, str):
        return False
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return False
    return hmac.compare_digest(hash_token(token.strip()), saved["token_sha256"])


def download_request(body) -> tuple[list[str], dict]:
    """Validate POST /api/v1/downloads. Returns (urls, options) or raises ValueError.

    Only output choices are accepted. Cookies, proxies, referers, folders and page rendering stay
    under the app's control, so a caller cannot make the app send your cookies anywhere.
    """
    if not isinstance(body, dict):
        raise ValueError("Send a JSON object.")
    unknown = set(body) - {"urls", "mode", "quality", "abr", "no_playlist", "subtitles"}
    if unknown:
        raise ValueError(f"Unsupported fields: {', '.join(sorted(unknown))}.")
    urls = body.get("urls")
    if isinstance(urls, str):
        urls = [urls]
    if (not isinstance(urls, list) or not 1 <= len(urls) <= MAX_URLS
            or not all(isinstance(url, str) and url.strip().lower().startswith(("http://", "https://"))
                       and len(url) <= 4096 for url in urls)):
        raise ValueError(f"urls must be 1 to {MAX_URLS} http(s) links.")
    options: dict = {}
    mode = body.get("mode", "mp4")
    if mode not in MODES:
        raise ValueError(f"mode must be one of: {', '.join(MODES)}.")
    options["mode"] = mode
    quality = str(body.get("quality", "best")).lower().rstrip("p")
    if quality != "best" and not (quality.isdigit() and 100 <= int(quality) <= 4320):
        raise ValueError("quality must be best or a height such as 1080.")
    options["quality"] = quality
    abr = body.get("abr", 192)
    if isinstance(abr, bool) or abr not in ABR:
        raise ValueError(f"abr must be one of: {', '.join(map(str, ABR))}.")
    options["abr"] = abr
    for field, option in (("no_playlist", "no_playlist"), ("subtitles", "subs")):
        value = body.get(field, False)
        if not isinstance(value, bool):
            raise ValueError(f"{field} must be true or false.")
        options[option] = value
    return list(dict.fromkeys(url.strip() for url in urls)), options


def job_view(job, root) -> dict:
    """Status of one task without local paths beyond file names."""
    view = job.view(root)
    return {"id": job.id, "url": job.url, "title": job.title, "status": job.status, "stage": job.stage,
            "percent": round(job.percent, 1), "error": job.error if job.status == "error" else "",
            "files": [item["name"] for item in view.get("files", []) if isinstance(item, dict) and "name" in item]}
