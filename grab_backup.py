"""Allowlisted portable annotations and preferences; media and credentials never enter backups."""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import logging
import math
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import uuid

from grab_storage import JsonStore
from grab_library import SMART_COLLECTION_LIMIT, smart_collection_records

BACKUP_MAX_BYTES = 16 * 1024**2
LOG = logging.getLogger(__name__)
OUTPUT_DEFAULTS = {"mode": "mp4", "quality": "best", "abr": 192, "subs": False,
                   "sub_langs": "zh-Hans,zh-Hant,zh,en", "auto_subs": False, "embed_subs": False,
                   "cover": False, "keep_cover": False}


def checked_text(value, limit, empty=True):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()) or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value):
        raise ValueError("The backup contains invalid text.")
    return value


def output_options(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid download preferences.")
    result = {}
    for key, item in value.items():
        if key not in OUTPUT_DEFAULTS:
            continue
        if key == "mode":
            valid = item in ("mp4", "mp3", "original", "cover", "image")
        elif key == "quality":
            valid = isinstance(item, str) and (item == "best" or bool(re.fullmatch(r"[1-9][0-9]{0,4}", item)))
        elif key == "abr":
            valid = type(item) is int and item in (96, 128, 192, 256, 320)
        elif key == "sub_langs":
            checked_text(item, 200)
            valid = True
        else:
            valid = isinstance(item, bool)
        if not valid:
            raise ValueError("Invalid download preferences.")
        result[key] = item
    return result


def preferences(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid backup preferences.")
    result = {}
    if "download" in value:
        result["download"] = output_options(value["download"])
    for key, choices in {"theme": ("light", "dark"), "locale": ("en", "zh-CN", "zh-TW", "ja")}.items():
        if key in value:
            if value[key] not in choices:
                raise ValueError("Invalid appearance preferences.")
            result[key] = value[key]
    if "presets" in value:
        items = value["presets"]
        if not isinstance(items, list) or len(items) > 50:
            raise ValueError("A backup can contain up to 50 custom presets.")
        result["presets"], names, ids = [], set(), set()
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not re.fullmatch(r"[0-9a-f]{32}", item["id"]):
                raise ValueError("Invalid preset identifier.")
            name = checked_text(item.get("name"), 60, empty=False).strip()
            if name.lower() in names or item["id"] in ids:
                raise ValueError("Duplicate presets in backup.")
            names.add(name.lower())
            ids.add(item["id"])
            result["presets"].append({"id": item["id"], "name": name,
                                      "options": {**OUTPUT_DEFAULTS, **output_options(item.get("options"))}})
    return result


def desktop_preferences(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid desktop preferences.")
    result = {}
    if "close_behavior" in value:
        if value["close_behavior"] not in ("ask", "background", "exit"):
            raise ValueError("Invalid close behavior.")
        result["close_behavior"] = value["close_behavior"]
    if "notifications_enabled" in value:
        if not isinstance(value["notifications_enabled"], bool):
            raise ValueError("Invalid notification preference.")
        result["notifications_enabled"] = value["notifications_enabled"]
    return result


def relative_path(value):
    checked_text(value, 1000, empty=False)
    path = PurePosixPath(value)
    if path.is_absolute() or "\\" in value or ":" in value or any(part in ("", ".", "..") or part.startswith(".") for part in value.split("/")):
        raise ValueError("The backup contains an unsafe media path.")
    return value


def annotations(value):
    if not isinstance(value, dict):
        raise ValueError("Invalid media annotations.")
    result = {}
    if "favorite" in value:
        if not isinstance(value["favorite"], bool):
            raise ValueError("Invalid favorite value.")
        result["favorite"] = value["favorite"]
    if "note" in value:
        result["note"] = checked_text(value["note"], 2000)
    for key, limit in (("tags", 20), ("collections", 200)):
        if key in value:
            if not isinstance(value[key], list) or len(value[key]) > limit:
                raise ValueError("Too many tags or collections.")
            result[key] = list(dict.fromkeys(checked_text(item, 40 if key == "tags" else 32, empty=False) for item in value[key]))
            if key == "collections" and any(not re.fullmatch(r"[0-9a-f]{32}", item) for item in result[key]):
                raise ValueError("Invalid collection reference.")
    if "playback" in value and value["playback"] is not None:
        item = value["playback"]
        if not isinstance(item, dict) or any(type(item.get(key)) not in (int, float) or not math.isfinite(item[key]) for key in ("position", "duration")):
            raise ValueError("Invalid playback progress.")
        if not 0 < item["duration"] <= 7 * 86400 or not 0 <= item["position"] <= item["duration"]:
            raise ValueError("Invalid playback progress.")
        result["playback"] = {"position": item["position"], "duration": item["duration"], "finished": item["position"] >= item["duration"] * .98}
    return result


def document(value):
    if len(encoded(value)) > BACKUP_MAX_BYTES:
        raise ValueError("The backup exceeds the 16 MiB limit.")
    if not isinstance(value, dict) or value.get("format") != "video-grabber-backup" or type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("Choose a supported Video Grabber backup (version 1).")
    browser = preferences(value.get("preferences", {}))
    desktop = desktop_preferences(value.get("desktop", {}))
    library = value.get("library")
    if not isinstance(library, dict) or not isinstance(library.get("files"), list) or len(library["files"]) > 20000 or not isinstance(library.get("collections"), dict) or len(library["collections"]) > 200:
        raise ValueError("Invalid or oversized library backup.")
    collections = {}
    for key, name in library["collections"].items():
        if not re.fullmatch(r"[0-9a-f]{32}", key):
            raise ValueError("Invalid collection identifier.")
        collections[key] = checked_text(name, 80, empty=False).strip()
    smart = smart_collection_records(library.get("smart_collections", {}), strict=True)
    files, paths = [], set()
    for item in library["files"]:
        if not isinstance(item, dict):
            raise ValueError("Invalid media entry.")
        path = relative_path(item.get("path"))
        if path in paths or type(item.get("size")) is not int or item["size"] <= 0:
            raise ValueError("Duplicate media path or invalid file size.")
        paths.add(path)
        info = annotations(item.get("annotations"))
        if any(key not in collections for key in info.get("collections", [])):
            raise ValueError("A media entry refers to an unknown collection.")
        files.append({"path": path, "size": item["size"], "annotations": info})
    return {"format": "video-grabber-backup", "version": 1, "preferences": browser, "desktop": desktop,
            "library": {"files": files, "collections": collections, "smart_collections": smart}}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")


def replace_documents(writes):
    """Stage both documents and recovery copies before publishing either one."""
    staged, replaced = [], []
    try:
        for target, value in writes:
            target.parent.mkdir(parents=True, exist_ok=True)
            original = target.read_bytes() if target.exists() else None
            paths = []
            for content in (encoded(value), original):
                if content is None:
                    paths.append(None)
                    continue
                fd, name = tempfile.mkstemp(prefix=".backup-restore-", suffix=".tmp", dir=target.parent)
                path = Path(name)
                paths.append(path)
                # Register immediately so a failed write also cleans its temporary file.
                staged.append(path)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
            replaced.append((target, *paths, False))
        for index, (target, new, old, _) in enumerate(replaced):
            os.replace(new, target)
            replaced[index] = (target, new, old, True)
    except OSError:
        failures = []
        for target, new, old, published in reversed(replaced):
            if published:
                try:
                    if old is None:
                        target.unlink(missing_ok=True)
                    else:
                        os.replace(old, target)
                except OSError as error:
                    # Keep the original recovery copy if the OS also prevents rollback.
                    if old in staged:
                        staged.remove(old)
                    LOG.error("Restore rollback failed. Original recovery copy retained at %s", old)
                    failures.append(error)
        if failures:
            raise OSError("Restore rollback failed; original recovery copies were retained. See the local log.") from failures[0]
        raise
    finally:
        for path in staged:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                LOG.warning("Could not remove restore temporary file: %s", path)


class BackupService:
    def __init__(self, library, desktop_path, preference_lock):
        self.library = library
        self.desktop_store = JsonStore(lambda: desktop_path, preference_lock)
        self.preference_lock = preference_lock

    def export(self, browser, desktop_defaults=None):
        with self.library.lock, self.preference_lock:
            data = self.library.load()
            files = []
            for relative, record in data["files"].items():
                try:
                    info = annotations(record)
                    if not info:
                        continue
                    path = self.library.media_path(relative)
                    size = path.stat().st_size
                    if size > 0:
                        files.append({"path": path.relative_to(self.library.root().resolve()).as_posix(), "size": size, "annotations": info})
                except (OSError, ValueError):
                    continue
            desktop = self.desktop_store.load({})
            result = document({"format": "video-grabber-backup", "version": 1, "preferences": browser,
                               "desktop": {**(desktop_defaults or {}), **desktop_preferences(desktop)},
                               "library": {"files": files, "collections": data["collections"],
                                           "smart_collections": data["smart_collections"]}})
            result["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if len(encoded(result)) > BACKUP_MAX_BYTES:
                raise ValueError("The backup exceeds the 16 MiB limit.")
            return result

    def plan(self, backup, current):
        source, current = document(backup), preferences(current)
        original = self.library.load()
        data, browser = copy.deepcopy(original), copy.deepcopy(current)
        saved_desktop = self.desktop_store.load({})
        if not isinstance(saved_desktop, dict):
            raise ValueError("Current desktop settings are unreadable.")
        desktop = {**source["desktop"], **saved_desktop}
        counts = {"files": 0, "collections": 0, "smart_collections": 0, "presets": 0, "settings": 0, "conflicts": 0}
        for key in ("download", "theme", "locale"):
            if key not in source["preferences"]:
                continue
            incoming = source["preferences"][key]
            if key == "download":
                before = browser.get(key, {})
                counts["settings"] += sum(field not in before for field in incoming)
                counts["conflicts"] += sum(field in before and before[field] != item for field, item in incoming.items())
                browser[key] = {**incoming, **before}
            elif key not in browser:
                browser[key] = incoming
                counts["settings"] += 1
            elif browser[key] != incoming:
                counts["conflicts"] += 1
        for key, value in source["desktop"].items():
            counts["settings"] += key not in saved_desktop
            counts["conflicts"] += key in saved_desktop and saved_desktop[key] != value
        presets = browser.setdefault("presets", [])
        for preset in source["preferences"].get("presets", []):
            match = next((item for item in presets if item["id"] == preset["id"] or item["name"].lower() == preset["name"].lower()), None)
            if match:
                counts["conflicts"] += match != preset
            else:
                presets.append(preset)
                counts["presets"] += 1
        if len(presets) > 50:
            raise ValueError("Merging would exceed the 50 preset limit.")
        mapping = {}
        for key, name in source["library"]["collections"].items():
            match = next((key for key, current_name in data["collections"].items() if current_name.lower() == name.lower()), None)
            if match:
                mapping[key] = match
            else:
                target = key if key not in data["collections"] else uuid.uuid5(uuid.NAMESPACE_URL, key + name).hex
                if target in data["collections"] and data["collections"][target] != name:
                    raise ValueError("Collection identifiers conflict.")
                mapping[key] = target
                data["collections"][target] = name
                counts["collections"] += 1
        if len(data["collections"]) > 200:
            raise ValueError("Merging would exceed the 200 collection limit.")
        for key, incoming in source["library"]["smart_collections"].items():
            match = data["smart_collections"].get(key)
            if match is None:
                match = next((item for item in data["smart_collections"].values()
                              if item["name"].casefold() == incoming["name"].casefold()), None)
            if match is not None:
                counts["conflicts"] += match != incoming
            else:
                data["smart_collections"][key] = incoming
                counts["smart_collections"] += 1
        if len(data["smart_collections"]) > SMART_COLLECTION_LIMIT:
            raise ValueError("Use up to 100 smart collections.")
        skipped = []
        for item in source["library"]["files"]:
            try:
                path = self.library.media_path(item["path"])
                if path.stat().st_size != item["size"]:
                    skipped.append({"path": item["path"], "reason": "size"})
                    continue
            except (OSError, ValueError):
                skipped.append({"path": item["path"], "reason": "missing"})
                continue
            relative = path.relative_to(self.library.root().resolve()).as_posix()
            record = data["files"].setdefault(relative, {})
            if not isinstance(record, dict):
                raise ValueError("An existing media record is unreadable.")
            before = copy.deepcopy(record)
            for key, value in item["annotations"].items():
                if key == "collections":
                    value = [mapping[entry] for entry in value]
                if key in ("collections", "tags"):
                    existing = record.get(key, [])
                    if not isinstance(existing, list):
                        counts["conflicts"] += 1
                        continue
                    merged = list(dict.fromkeys([*existing, *value]))
                    record[key] = merged[:20] if key == "tags" else merged
                    if key == "tags" and len(merged) > 20:
                        counts["conflicts"] += 1
                elif key not in record:
                    record[key] = value
                elif record[key] != value:
                    counts["conflicts"] += 1
            counts["files"] += record != before
        token = hashlib.sha256(encoded({"root": str(self.library.root().resolve()), "original": original,
                                       "saved_desktop": saved_desktop, "current": current, "source": source,
                                       "data": data, "desktop": desktop, "browser": browser, "skipped": skipped})).hexdigest()
        return {"counts": counts, "skipped": skipped, "review_token": token, "browser": browser}, data, desktop

    def preview(self, backup, current):
        with self.library.lock, self.preference_lock:
            return self.plan(backup, current)[0]

    def restore(self, backup, current, token):
        with self.library.lock, self.preference_lock:
            review, data, desktop = self.plan(backup, current)
            if not isinstance(token, str) or token != review["review_token"]:
                raise ValueError("Data changed since preview. Preview the backup again.")
            replace_documents([(self.library.store.path(), data), (self.desktop_store.path(), desktop)])
            return review
