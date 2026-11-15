"""Public automation API (/api/v1/) and its settings routes.

/api/v1/ requires the separate API token. The settings routes require the app's own session cookie,
so the Chrome extension, which shares the page token, cannot turn the API on or read a token.
"""

from __future__ import annotations

import re

import grab_api


def _authorized(app, h) -> bool:
    saved = app.api_settings()
    if not saved["enabled"]:
        h._json({"error": "The automation API is turned off. Turn it on in Video Grabber settings."}, 403)
        return False
    if not grab_api.token_matches(h.headers.get("Authorization"), saved):
        h._json({"error": "Send a valid API token as: Authorization: Bearer <token>."}, 401)
        return False
    return True


def v1_get(app, h, path: str) -> None:
    if not _authorized(app, h):
        return
    if path == "/api/v1/status":
        counts = {status: 0 for status in ("queued", "running", "done", "error", "canceled")}
        for job in app.JOB_MANAGER.snapshot():
            counts[job.status] = counts.get(job.status, 0) + 1
        schedule = app.schedule_view()
        h._json({"version": 1, "jobs": counts, "paused": app.QUEUE.paused,
                 "waiting_for_schedule": schedule["holding"], "next_start": schedule["next_start"]})
        return
    m = re.fullmatch(r"/api/v1/jobs/([0-9a-f]{8})", path)
    if m:
        job = app.JOB_MANAGER.get(m[1])
        if job is None:
            h._json({"error": "No task with that id. Finished tasks may have been cleared."}, 404)
            return
        h._json(grab_api.job_view(job, app.ROOT))
        return
    h._json({"error": "not found"}, 404)


def v1_post(app, h, path: str, body: dict) -> None:
    if not _authorized(app, h):
        return
    if path != "/api/v1/downloads":
        h._json({"error": "not found"}, 404)
        return
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


def settings_get(app, h, path: str) -> bool:
    if path != "/api/automation-api":
        return False
    if not h._session_cookie_ok():
        h._json({"error": "Open Video Grabber to manage the automation API."}, 403)
        return True
    h._json(app.api_settings_view())
    return True


def settings_post(app, h, path: str, body: dict) -> bool:
    if path != "/api/automation-api":
        return False
    if not h._session_cookie_ok():
        h._json({"error": "Open Video Grabber to manage the automation API."}, 403)
        return True
    action = body.get("action")
    if action not in ("enable", "disable", "new_token"):
        h._json({"error": "Choose enable, disable or new_token."}, 400)
        return True
    try:
        h._json(app.change_api_settings(action))
    except OSError:
        h._json({"error": "Could not save the automation API settings."}, 500)
    return True
