"""Settings, setup, update, cookies, diagnostics and desktop routes.

Every function takes ``app`` (the webui module) and ``h`` (the request handler).
"""

from __future__ import annotations

import subprocess
import threading
import webbrowser


def system_get(app, h, path: str, q: dict) -> bool:
    if path == "/api/doctor":
        flag = lambda k: bool((q.get(k) or [""])[0])  # noqa: E731
        h._json(app.collect_doctor(net=flag("net"), force=flag("force")))
        return True
    if path == "/api/cookies":
        h._json(app.cookies_status())
        return True
    if path == "/api/access":
        h._json({"extension": app.extension_access_enabled()})
        return True
    if path == "/api/setup":
        h._json(app.setup_status())
        return True
    if path == "/api/ytdlp/check":
        h._json(app.check_ytdlp(force=bool((q.get("force") or [""])[0])))
        return True
    if path == "/api/ytdlp/update-status":
        with app.UPDATE_LOCK:
            h._json({k: (list(v) if isinstance(v, list) else v) for k, v in app.UPDATE.items()})
        return True
    return False


def system_post(app, h, path: str, body: dict) -> bool:
    if path == "/api/probe":
        url = app.http_url(body.get("url"))
        if not url:
            h._json({"error": "Please enter an http(s) URL"}, 400)
            return True
        h._json(app.probe(url, body.get("options") or {}))
        return True

    if path == "/api/download-folder/select":
        try:
            h._json(app.select_download_folder())
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            h._json({"error": str(error)}, 409)
        return True

    if path == "/api/open-url":
        url = app.http_url(body.get("url"))
        if not url:
            h._json({"error": "Please enter an http(s) URL"}, 400)
            return True
        try:
            h._json({"ok": webbrowser.open(url)})
        except OSError:
            h._json({"error": "Could not open it"}, 409)
        return True

    if path == "/api/desktop/show":
        view = body.get("view", "queue")
        if view not in ("new", "queue", "library"):
            h._json({"error": "Unsupported app view"}, 400)
            return True
        desktop = app.NATIVE_DESKTOP
        if not app.WINDOW_MODE or desktop is None or desktop.exiting.is_set():
            h._json({"opened": False})
            return True
        try:
            desktop.show_main(view)
        except Exception as exc:  # noqa: BLE001
            print(f"Could not bring the desktop window forward: {exc}")
            h._json({"error": "Could not open the main window. Use the tray menu to try again."}, 503)
            return True
        h._json({"opened": True})
        return True

    if path == "/api/open-folder":
        target = app.ROOT
        rel = str(body.get("path") or "")
        if rel:
            cand = (app.ROOT / rel).resolve().parent
            try:
                cand.relative_to(app.ROOT)
                target = cand
            except ValueError:
                pass
        app.open_in_file_manager(target)
        h._json({"ok": True})
        return True

    if path == "/api/open-file":
        rel = str(body.get("path") or "")
        if not rel:
            h._json({"error": "No file given"}, 400)
            return True
        target = (app.ROOT / rel).resolve()
        try:
            target.relative_to(app.ROOT)
        except ValueError:
            h._json({"error": "forbidden"}, 403)
            return True
        if not target.is_file() or target.suffix.lower() not in app.MEDIA_SUFFIX:
            h._json({"error": "File not found"}, 404)
            return True
        app.open_file(target)
        h._json({"ok": True})
        return True

    if path == "/api/notify":
        if not app.desktop_notifications_supported():
            h._json({"ok": False})
            return True
        title = str(body.get("title") or "Video Grabber")[:120]
        message = str(body.get("body") or "")[:500]
        h._json({"ok": app.show_desktop_notification(title, message)})
        return True

    if path == "/api/desktop/notifications":
        if not app.WINDOW_MODE or app.NATIVE_DESKTOP is None or app.NATIVE_DESKTOP.exiting.is_set():
            h._json({"error": "Desktop notifications are unavailable."}, 409)
            return True
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            h._json({"error": "enabled must be a boolean"}, 400)
            return True
        try:
            app.NATIVE_DESKTOP.set_notifications(enabled)
        except OSError:
            h._json({"error": "Could not save notification preferences."}, 500)
            return True
        h._json({"ok": True})
        return True

    if path == "/api/cookies":
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            h._json({"error": "Empty file, or larger than 3 MB."}, 400)
            return True
        try:
            h._json(app.save_cookies(text))
        except ValueError as e:
            h._json({"error": str(e)}, 400)
        except OSError as e:
            h._json({"error": f"Could not save the file: {e}"}, 500)
        return True

    if path == "/api/access":
        enabled = body.get("extension")
        if not isinstance(enabled, bool):
            h._json({"error": "extension must be true or false"}, 400)
            return True
        try:
            app.set_extension_access(enabled)
        except OSError:
            h._json({"error": "Could not save this setting."}, 500)
            return True
        h._json({"extension": enabled})
        return True

    if path == "/api/cookies/delete":
        app.delete_cookies()
        h._json({"present": False})
        return True

    if path == "/api/setup":
        ok, error = app.start_setup()
        h._json({"ok": True} if ok else {"error": error}, 200 if ok else 409)
        return True

    if path == "/api/ytdlp/update":
        extras = body.get("extras") if body.get("extras") in ("default", "default,deno") else "default"
        ok, why = app.start_update(extras)
        h._json({"ok": True} if ok else {"error": why}, 200 if ok else 409)
        return True

    if path == "/api/restart":
        if app.active_jobs() or app.UPDATE["status"] == "running" or app.FOLDER_PICK_LOCK.locked():
            h._json({"error": "Tasks are still running, wait for them to finish before restarting."}, 409)
            return True
        h._json({"ok": True})
        threading.Timer(0.5, app.restart_self).start()
        return True

    return False
