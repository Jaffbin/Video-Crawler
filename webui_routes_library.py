"""Library, backup and import routes.

Every function takes ``app`` (the webui module) and ``h`` (the request handler).
"""

from __future__ import annotations

import logging
from pathlib import Path


def library_get(app, h, path: str) -> bool:
    if path == "/api/library/organizer":
        h._json(app.ORGANIZER.snapshot())
        return True
    if path == "/api/library/trash":
        h._json({"items": app.LIBRARY.trash_items()})
        return True
    if path == "/api/library/auto-rules":
        h._json({"auto_rules": app.LIBRARY.auto_rules()})
        return True
    if path == "/api/media-export":
        if not h._session_cookie_ok():
            h._json({"error": "Open Video Grabber to manage the media server folder."}, 403)
            return True
        h._json(app.media_export_status())
        return True
    return False


def media_export_post(app, h, body: dict) -> None:
    """The export folder decides where files are written, so only the app window may use this."""
    if not h._session_cookie_ok():
        h._json({"error": "Open Video Grabber to manage the media server folder."}, 403)
        return
    action = body.get("action")
    try:
        if action == "folder":
            h._json(app.save_media_export_folder(body.get("folder")))
        elif action == "export":
            paths = body.get("paths")
            if not isinstance(paths, list) or not 1 <= len(paths) <= 500 or \
                    not all(isinstance(item, str) for item in paths):
                raise ValueError("Choose between 1 and 500 files.")
            # No queue lock: copying to another disk can take a while.
            h._json(app.export_to_media_server(paths))
        else:
            raise ValueError("Choose folder or export.")
    except (ValueError, app.grab_mediaexport.ExportError) as error:
        h._json({"error": str(error)}, 400)
    except OSError:
        h._json({"error": "Could not save the media server folder."}, 500)


def library_post(app, h, path: str, body: dict) -> bool:
    if path == "/api/media-export":
        media_export_post(app, h, body)
        return True
    if path == "/api/library/repair":
        try:
            p = app.LIBRARY.media_path(body.get("path"))
            relative = p.relative_to(app.ROOT).as_posix()
            record = app.library_records().get(relative, {})
            if record.get("complete") is not False or not isinstance(record.get("repair_options"), dict):
                raise ValueError("This item cannot be repaired locally. Download it again.")
            url = app.http_url(record.get("source_url"))
            if not url:
                raise ValueError("The original settings are missing. Download this item again.")
            options = {"_repair_path": relative, "mode": record["repair_options"].get("mode", "mp4")}
            ids = app.create_jobs([url], options)
            app.bump_rev()
            h._json({"ids": ids, "duplicates": not bool(ids)})
            return True
        except FileNotFoundError as e:
            h._json({"error": str(e)}, 404)
            return True
        except (ValueError, OSError) as e:
            h._json({"error": str(e)}, 400)
            return True

    if path in ("/api/library/details", "/api/library/playback"):
        try:
            if "root" in body and body["root"] != str(app.ROOT):
                raise ValueError("The library changed. Refresh before saving playback progress.")
            if path.endswith("/details"):
                app.LIBRARY.describe(body.get("path"), body.get("tags"), body.get("note"))
            else:
                app.LIBRARY.save_playback(body.get("path"), body.get("position"), body.get("duration"))
            app.bump_rev()
            h._json({"ok": True})
            return True
        except ValueError as error:
            h._json({"error": str(error)}, 400)
            return True
        except OSError:
            h._json({"error": "Could not save file details. Refresh Library and check folder permissions."}, 409)
            return True

    if path in ("/api/library/organize", "/api/library/collections", "/api/library/smart-collections",
                "/api/library/auto-rules"):
        export_now = []
        try:
            with app.QUEUE.mutex:
                if path.endswith("/auto-rules") and body.get("action") in ("preview_existing", "apply_existing"):
                    files = [(item["path"], item["kind"]) for item in app.list_files(force=True) if item["complete"]]
                    dry_run = body["action"] == "preview_existing"
                    result = app.LIBRARY.apply_auto_rule_to_existing(body.get("id"), files, dry_run=dry_run)
                    paths = result.pop("paths")
                    if result.pop("export"):
                        export_now = [p for p in paths if app.media_kind(Path(p).suffix.lower()) == "video"]
                        result["export"] = len(export_now)
                elif path.endswith("/auto-rules"):
                    rule_id = app.LIBRARY.change_auto_rule(body.get("action"), body.get("id"), body.get("rule"))
                    result = {"id": rule_id, "auto_rules": app.LIBRARY.auto_rules()}
                elif path.endswith("/organize"):
                    result = app.LIBRARY.organize(body.get("items"), favorite=body.get("favorite"),
                                              collection_id=body.get("collection_id"), remove=body.get("remove", False))
                elif path.endswith("/smart-collections"):
                    collection_id = app.LIBRARY.change_smart_collection(body.get("action"), body.get("name"),
                                                                    body.get("id"), body.get("rules"))
                    result = {"id": collection_id, "smart_collections": app.LIBRARY.smart_collections()}
                else:
                    collection_id = app.LIBRARY.change_collection(body.get("action"), body.get("name"), body.get("id"))
                    result = {"id": collection_id, "collections": app.LIBRARY.collections()}
            if export_now and body.get("action") == "apply_existing":
                # Outside the queue lock: copying to another disk can take a while.
                try:
                    exported = app.export_to_media_server(export_now)
                    result.update(exported=exported["exported"], export_failed=len(exported["failed"]))
                except app.grab_mediaexport.ExportError as error:
                    result["export_error"] = str(error)
            app.bump_rev()
            h._json(result)
            return True
        except ValueError as error:
            h._json({"error": str(error)}, 400)
            return True
        except OSError:
            h._json({"error": "Could not save Library organization. Check folder permissions and disk space."}, 409)
            return True

    if path in ("/api/library/organizer", "/api/library/organizer/recycle"):
        try:
            with app.QUEUE.mutex:
                if path.endswith("/recycle"):
                    result = app.ORGANIZER.recycle(body.get("scan_id"), body.get("items"))
                elif body.get("action") == "start":
                    result = app.ORGANIZER.start(entry_limit=app.FILE_SCAN_MAX_ENTRIES, max_depth=app.FILE_SCAN_MAX_DEPTH)
                elif body.get("action") == "cancel":
                    result = app.ORGANIZER.cancel()
                else:
                    raise ValueError("Choose a valid library check action.")
            if path.endswith("/recycle") and result["processed"]:
                app.save_history()
                app.bump_rev()
            h._json(result)
            return True
        except ValueError as error:
            h._json({"error": str(error)}, 400)
            return True
        except OSError:
            h._json({"error": "Files are unavailable or changed. Run a new check."}, 409)
            return True

    if path == "/api/library/batch":
        action, items = body.get("action"), body.get("items")
        if action not in ("trash", "restore", "purge") or not isinstance(items, list) or not 1 <= len(items) <= 200 or any(not isinstance(item, str) for item in items):
            h._json({"error": "Choose between 1 and 200 files and a valid action"}, 400)
            return True
        processed, failed, recovery_ids = [], [], []
        with app.QUEUE.mutex:
            if any(job.status == "running" for job in app.JOB_MANAGER.snapshot()):
                h._json({"error": "Wait for running downloads to finish before editing files"}, 409)
                return True
            if action == "trash":
                completions = {p: record.get("complete") for p, record in app.library_records().items()
                               if isinstance(record, dict)}
                result = app.LIBRARY.trash_many(items, completions=completions)
                processed, failed, recovery_ids = result["processed"], result["failed"], result["recovery_ids"]
            else:
                for item in dict.fromkeys(items):
                    try:
                        if action == "restore":
                            app.LIBRARY.restore(item)
                        else:
                            app.LIBRARY.purge(item)
                        processed.append(item)
                    except (ValueError, OSError) as error:
                        failed.append({"item": item, "error": str(error)})
        app.save_history()
        app.bump_rev()
        h._json({"processed": processed, "failed": failed, "recovery_ids": recovery_ids})
        return True

    if path in ("/api/library/rename", "/api/library/trash", "/api/library/restore", "/api/library/purge"):
        try:
            with app.QUEUE.mutex:
                if any(job.status == "running" for job in app.JOB_MANAGER.snapshot()):
                    h._json({"error": "Wait for running downloads to finish before editing files"}, 409)
                    return True
                completion = None
                if path.endswith(("/rename", "/trash")):
                    old = app.LIBRARY.media_path(body.get("path"))
                    for job in reversed(app.JOB_MANAGER.snapshot()):
                        linked = next((p for p in job.files if Path(p).resolve() == old), None)
                        if linked:
                            completion = app.output_complete(old, job.status, job.media_metadata.get(linked, {}).get("complete"))
                            break
                if path.endswith("/rename"):
                    relative = app.LIBRARY.rename(body.get("path"), body.get("name"), complete=completion)
                    new = str(app.ROOT / relative)
                    with app.JOB_MANAGER.lock:
                        for job in app.JOBS.values():
                            linked = any(Path(p).resolve() == old for p in job.files)
                            job.files = [new if Path(p).resolve() == old else p for p in job.files]
                            job.seen_paths = [new if Path(p).resolve() == old else p for p in job.seen_paths]
                            job.media_metadata = {new if Path(p).resolve() == old else p: info
                                                  for p, info in job.media_metadata.items()}
                            if linked and isinstance(completion, bool):
                                job.media_metadata.setdefault(new, {})["complete"] = completion
                    result = {"path": relative}
                elif path.endswith("/trash"):
                    result = {"id": app.LIBRARY.trash(body.get("path"), complete=completion)}
                elif path.endswith("/purge"):
                    app.LIBRARY.purge(str(body.get("id") or ""))
                    result = {"ok": True}
                else:
                    result = {"path": app.LIBRARY.restore(str(body.get("id") or ""))}
            app.save_history()
            app.bump_rev()
            h._json(result)
            return True
        except FileNotFoundError as e:
            h._json({"error": str(e)}, 404)
            return True
        except FileExistsError as e:
            h._json({"error": str(e)}, 409)
            return True
        except ValueError as e:
            h._json({"error": str(e)}, 400)
            return True
        except OSError:
            h._json({"error": "Could not update the file. Check permissions and close any player using it."}, 409)
            return True

    return False


def library_import(app, h, q: dict):
    if (h.headers.get("Content-Type") or "").split(";")[0] != "application/octet-stream":
        return h._json({"error": "bad content type"}, 415)
    try:
        size = int(h.headers.get("Content-Length") or 0)
    except ValueError:
        size = 0
    if not 0 < size <= app.IMPORT_MAX_BYTES:
        return h._json({"error": "Choose a non-empty media file up to 8 GiB."}, 413)
    if not app.FOLDER_PICK_LOCK.acquire(blocking=False):
        return h._json({"error": "A file import or folder chooser is already running."}, 409)
    previous_timeout = h.connection.gettimeout()
    try:
        h.connection.settimeout(30)
        result = app.LIBRARY.import_file((q.get("name") or [""])[0], h.rfile, size)
        app.bump_rev()
        return h._json(result)
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        return
    except ValueError as error:
        return h._json({"error": str(error)}, 400)
    except FileExistsError:
        return h._json({"error": "A file with that name already exists. Rename it before importing."}, 409)
    except OSError:
        return h._json({"error": "Could not import this file. Check permissions, available space and filename conflicts."}, 409)
    finally:
        h.connection.settimeout(previous_timeout)
        app.FOLDER_PICK_LOCK.release()


def backup_post(app, h, path: str, body: dict) -> bool:
    if path not in {"/api/backup/export", "/api/backup/preview", "/api/backup/restore"}:
        return False
    desktop = app.NATIVE_DESKTOP if app.WINDOW_MODE else None
    service = app.BackupService(app.LIBRARY, app.CONFIG_DIR / "desktop.json", desktop.preferences_lock if desktop else app.SETTINGS_LOCK)
    try:
        if path.endswith("/export"):
            defaults = {"close_behavior": desktop.close_behavior, "notifications_enabled": desktop.notifications_enabled} if desktop else None
            h._json(service.export(body.get("preferences", {}), defaults))
            return True
        if path.endswith("/preview"):
            h._json(service.preview(body.get("backup"), body.get("current", {})))
            return True
        result = service.restore(body.get("backup"), body.get("current", {}), body.get("review_token"))
        if desktop:
            desktop.reload_preferences()
        app.bump_rev()
        h._json(result)
        return True
    except ValueError as error:
        h._json({"error": str(error)}, 400)
        return True
    except OSError:
        logging.getLogger(__name__).exception("Backup operation failed. Check for retained restore recovery copies before retrying.")
        h._json({"error": "Could not save restored data. Check permissions and available space, then preview again."}, 409)
        return True
