"""Routes for remote access: the phone-facing listener and its settings in the app window.

The phone side (remote_get / remote_post) runs on RemoteHandler. Apart from the page and pairing,
every route needs a paired device's cookie, and only these actions exist: add downloads, list and
cancel/retry tasks, browse the Library read-only, play media and forget this device.

The settings routes run on the main server and need the app's own session cookie, so the Chrome
extension, which shares the page token, cannot turn remote access on or pair devices.
"""

from __future__ import annotations

import json
import re
import time
from urllib.parse import unquote

import grab_api
import grab_remote
import webui_remote_page

JOB_ROUTE = re.compile(r"/api/jobs/([0-9a-f]{8})/(cancel|retry)")
JOBS_SHOWN = 50
PAGE_CSP = ("default-src 'self'; img-src 'self'; media-src 'self'; style-src 'self'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")


def _json_with_cookie(h, data: dict, status: int, cookie: str) -> None:
    h._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8",
            {"Set-Cookie": cookie})


def _int(q: dict, name: str, default: int) -> int:
    try:
        return int((q.get(name) or [str(default)])[0])
    except ValueError:
        return default


# ── Phone side ──
def remote_get(app, h, path: str, q: dict, saved: dict) -> None:
    if path in webui_remote_page.ASSETS:
        body, ctype = webui_remote_page.ASSETS[path]
        extra = {"Referrer-Policy": "no-referrer"}
        if ctype.startswith("text/html"):
            extra["Content-Security-Policy"] = PAGE_CSP
        h._send(200, body, ctype, extra)
        return
    device = h.remote_device(saved)
    if device is None:
        h._json({"error": "This phone is not paired. Enter a pairing code from Video Grabber."}, 401)
        return
    if path == "/api/me":
        h._json({"device": device["name"]})
        return
    if path == "/api/jobs":
        jobs = app.JOB_MANAGER.snapshot(newest_first=True)[:JOBS_SHOWN]
        h._json({"jobs": [grab_api.job_view(job, app.ROOT) for job in jobs], "paused": app.QUEUE.paused})
        return
    if path == "/api/library":
        kind = (q.get("kind") or [""])[0]
        kind = kind if kind in ("video", "audio", "image") else ""
        h._json(grab_remote.library_page(app.list_files(), (q.get("q") or [""])[0], kind,
                                         _int(q, "offset", 0), _int(q, "limit", 30)))
        return
    if path.startswith("/files/"):
        h._file(unquote(path[len("/files/"):]))
        return
    h._json({"error": "not found"}, 404)


def remote_post(app, h, path: str, body: dict, saved: dict) -> None:
    if path == "/pair":
        _pair(app, h, body)
        return
    device = h.remote_device(saved)
    if device is None:
        h._json({"error": "This phone is not paired. Enter a pairing code from Video Grabber."}, 401)
        return
    if path == "/api/downloads":
        if app.UPDATE["status"] == "running":
            h._json({"error": "yt-dlp is being updated. Try again in a minute."}, 409)
            return
        try:
            urls, options = grab_api.download_request(body)
        except ValueError as error:
            h._json({"error": str(error)}, 400)
            return
        urls = [url for url in urls if app.http_url(url)]
        if not urls:
            h._json({"error": "urls must be 1 to 50 http(s) links."}, 400)
            return
        ids = app.create_jobs(urls, options)
        h._json({"ids": ids, "duplicates": len(urls) - len(ids)}, 202)
        return
    m = JOB_ROUTE.fullmatch(path)
    if m:
        _job_action(app, h, m.group(1), m.group(2))
        return
    if path == "/api/forget":
        with app.REMOTE_LOCK:
            current = app.remote_settings()
            current["devices"] = [item for item in current["devices"] if item["id"] != device["id"]]
            app.save_remote_settings(current)
        _json_with_cookie(h, {"ok": True}, 200, grab_remote.clear_cookie_header())
        return
    h._json({"error": "not found"}, 404)


def _pair(app, h, body: dict) -> None:
    with app.REMOTE_LOCK:
        current = app.remote_settings()
        if len(current["devices"]) >= grab_remote.MAX_DEVICES:
            h._json({"error": f"At most {grab_remote.MAX_DEVICES} devices can be paired. "
                              "Remove one in Video Grabber first."}, 409)
            return
        if not app.REMOTE_PAIRING.redeem(body.get("code")):
            h._json({"error": "That code is wrong or has expired. Create a new one in Video Grabber."}, 403)
            return
        token, device = grab_remote.new_device(body.get("name"), current["devices"], time.time())
        current["devices"].append(device)
        try:
            app.save_remote_settings(current)
        except OSError:
            h._json({"error": "Video Grabber could not save the pairing. Try again."}, 500)
            return
    _json_with_cookie(h, {"device": device["name"]}, 200, grab_remote.cookie_header(token))


def _job_action(app, h, job_id: str, action: str) -> None:
    job = app.JOB_MANAGER.get(job_id)
    if job is None:
        h._json({"error": "No task with that id. Finished tasks may have been cleared."}, 404)
        return
    if action == "cancel":
        processed, _ = app.JOB_MANAGER.batch([job.id], "cancel")
        if not processed:
            h._json({"error": "Only waiting or running tasks can be canceled."}, 409)
            return
        app.save_history()
        h._json({"ok": True})
        return
    if job.status not in ("error", "canceled"):
        h._json({"error": "Only failed or canceled tasks can be retried."}, 409)
        return
    if app.UPDATE["status"] == "running":
        h._json({"error": "yt-dlp is being updated. Try again in a minute."}, 409)
        return
    ids = app.JOB_MANAGER.retry(job)
    app.save_history()
    h._json({"ids": ids, "duplicates": not ids})


# ── App window settings ──
def settings_get(app, h, path: str) -> bool:
    if path != "/api/remote-access":
        return False
    if not h._session_cookie_ok():
        h._json({"error": "Open Video Grabber to manage remote access."}, 403)
        return True
    h._json(app.remote_access_view())
    return True


def settings_post(app, h, path: str, body: dict) -> bool:
    if path != "/api/remote-access":
        return False
    if not h._session_cookie_ok():
        h._json({"error": "Open Video Grabber to manage remote access."}, 403)
        return True
    try:
        h._json(app.change_remote_access(body))
    except ValueError as error:
        h._json({"error": str(error)}, 400)
    except OSError:
        h._json({"error": "Could not save the remote access settings."}, 500)
    return True
