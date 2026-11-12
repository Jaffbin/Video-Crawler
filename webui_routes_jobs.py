"""Queue, job and live-state routes.

Every function takes ``app`` (the webui module) and ``h`` (the request handler).
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import re


def jobs_get(app, h, path: str, q: dict) -> bool:
    if path == "/api/state":
        views = [job.view(app.ROOT) for job in app.JOB_MANAGER.snapshot(newest_first=True)]
        try:
            client_rev = int((q.get("rev") or ["-1"])[0])
        except ValueError:
            client_rev = -1
        data = {"version": app.yt_dlp.version.__version__, "ffmpeg": app.grab.ffmpeg_available(),
                "playwright": importlib.util.find_spec("playwright") is not None,
                "root": str(app.ROOT), "rev": app.FILES_REV, "jobs": views,
                "queue_paused": app.QUEUE.paused, "queue_order": app.QUEUE.pending_ids(),
                "window": app.WINDOW_MODE, "desktop_notifications": app.desktop_notifications_supported()}
        if app.WINDOW_MODE and app.NATIVE_DESKTOP is not None:
            data["native_notifications"] = {"enabled": app.NATIVE_DESKTOP.notifications_enabled,
                                             "available": app.NATIVE_DESKTOP.notifications_available}
        if client_rev != app.FILES_REV:
            data["files"] = app.list_files(force=client_rev < 0)
            data["library_scan"] = app.FILES_CACHE.get("scan")
            data["collections"] = app.LIBRARY.collections()
            data["smart_collections"] = app.LIBRARY.smart_collections()
        h._json(data)
        return True
    m = re.fullmatch(r"/api/jobs/([0-9a-f]{8})/log", path)
    if m:
        job = app.JOB_MANAGER.get(m.group(1))
        h._json({"lines": list(job.log)[-200:] if job else []})
        return True
    return False


def jobs_post(app, h, path: str, body: dict) -> bool:
    if path == "/api/jobs":
        if app.UPDATE["status"] == "running":
            h._json({"error": "Currently updating yt-dlp, please add tasks later"}, 409)
            return True
        raw = body.get("urls") or []
        urls = list(dict.fromkeys(x.strip() for x in raw if isinstance(x, str) and app.http_url(x)))[:200]
        if not urls:
            h._json({"error": "No valid URLs found (requires http:// or https://)"}, 400)
            return True
        options = body.get("options") or {}
        if not isinstance(options, dict):
            h._json({"error": "options must be an object"}, 400)
            return True
        action = body.get("existing_action")
        if action not in (None, "skip", "download"):
            h._json({"error": "Choose a valid existing download action"}, 400)
            return True
        matches = app.downloaded_matches(urls, options) if body.get("check_existing") is True else []
        if matches and action is None:
            exact_urls = {item["url"] for item in matches if item["settings_match"]}
            preferred = [item for item in matches if item["url"] not in exact_urls or item["settings_match"]]
            h._json({"ids": [], "duplicates": 0, "existing": preferred})
            return True
        skipped = set(item["url"] for item in matches) if action == "skip" else set()
        if action == "download":
            options = {**options, "_download_copy": True, "archive": False}
        pending = [url for url in urls if url not in skipped]
        ids = app.create_jobs(pending, options) if pending else []
        if body.get("check_existing") is True:
            h._json({"ids": ids, "duplicates": len(pending) - len(ids), "skipped_existing": len(skipped)})
            return True
        h._json({"ids": ids, "duplicates": len(urls) - len(ids)})
        return True

    if path == "/api/queue":
        if not isinstance(body.get("paused"), bool):
            h._json({"error": "paused must be true or false"}, 400)
            return True
        app.QUEUE.set_paused(body["paused"])
        app.save_history()
        h._json({"paused": app.QUEUE.paused})
        return True

    m = re.fullmatch(r"/api/jobs/([0-9a-f]{8})/retry-browser", path)
    if m:
        job = app.JOB_MANAGER.get(m[1])
        browser = body.get("browser")
        if not job:
            h._json({"error": "Task not found"}, 404)
            return True
        if not isinstance(browser, str) or browser not in app.BROWSERS:
            h._json({"error": "Choose a browser to use its sign-in session"}, 400)
            return True
        if job.status not in ("error", "canceled") or app.UPDATE["status"] == "running":
            h._json({"error": "This task cannot be retried right now"}, 409)
            return True
        retry = app.Job(job.url, {**job.options, "cookies_from_browser": browser, "use_cookies_file": False})
        retry.status, retry.source, retry.work_key = job.status, job.source, job.work_key
        retry.failed_items = [dict(item) for item in job.failed_items]
        ids = app.JOB_MANAGER.retry(retry)
        app.save_history()
        app.bump_rev()
        h._json({"ids": ids, "duplicates": not bool(ids)})
        return True

    if path == "/api/jobs/batch":
        action, ids = body.get("action"), body.get("ids")
        if action not in ("cancel", "retry", "remove") or not isinstance(ids, list) or not ids:
            h._json({"error": "Choose an action and job IDs"}, 400)
            return True
        if len(ids) > app.HISTORY_MAX or any(not isinstance(i, str) or not re.fullmatch(r"[0-9a-f]{8}", i) for i in ids):
            h._json({"error": "Invalid job IDs"}, 400)
            return True
        if action == "retry" and app.UPDATE["status"] == "running":
            h._json({"error": "Currently updating yt-dlp, please retry later"}, 409)
            return True
        processed, skipped = app.JOB_MANAGER.batch(list(dict.fromkeys(ids)), action)
        app.save_history()
        h._json({"processed": processed, "skipped": skipped})
        return True

    m = re.fullmatch(r"/api/jobs/([0-9a-f]{8})/(cancel|retry|remove|move-up|move-down)", path)
    if m:
        job, action = app.JOB_MANAGER.get(m.group(1)), m.group(2)
        if not job:
            h._json({"error": "Job not found"}, 404)
            return True
        if action.startswith("move-"):
            if not app.QUEUE.move(job.id, -1 if action == "move-up" else 1):
                h._json({"error": "Only waiting jobs can be reordered"}, 409)
                return True
            app.save_history()
        elif action == "cancel":
            processed, _ = app.JOB_MANAGER.batch([job.id], "cancel")
            if not processed:
                h._json({"error": "Only queued or running jobs can be canceled"}, 409)
                return True
            app.save_history()
        elif action == "retry":
            if job.status not in ("error", "canceled"):
                h._json({"error": "Only failed or canceled jobs can be retried"}, 409)
                return True
            if app.UPDATE["status"] == "running":
                h._json({"error": "Currently updating yt-dlp, please retry later"}, 409)
                return True
            ids = app.JOB_MANAGER.retry(job)
            app.save_history()
            h._json({"ids": ids, "duplicates": not ids})
            return True
        elif action == "remove":
            if job.status not in ("done", "error", "canceled"):
                h._json({"error": "Running jobs must be canceled before removal"}, 409)
                return True
            app.JOB_MANAGER.remove_finished(job.id)
            app.save_history()
        h._json({"ok": True})
        return True

    if path == "/api/clear":
        app.JOB_MANAGER.clear_finished()
        app.save_history()
        h._json({"ok": True})
        return True

    return False
