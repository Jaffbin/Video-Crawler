"""Local media metadata and reversible file management, independent of job history."""

from __future__ import annotations

import contextlib
import hashlib
import math
import os
import re
import threading
import time
import tempfile
import uuid
from pathlib import Path

from grab_models import http_url
from grab_storage import SqliteLibraryStore
from grab_images import IMAGE_SUFFIXES

SUBTITLE_SUFFIXES = {".srt", ".vtt", ".ass", ".ssa", ".lrc", ".ttml", ".srv1", ".srv2", ".srv3", ".json3"}
COVER_SUFFIXES = IMAGE_SUFFIXES
IMPORT_MAX_BYTES = 8 * 1024**3
SMART_COLLECTION_LIMIT = 100


def checked_smart_collection(value: dict) -> dict:
    """Validate saved rules without silently dropping an unsupported condition."""
    if not isinstance(value, dict):
        raise ValueError("Invalid smart collection.")
    name, rules = value.get("name"), value.get("rules")
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 80
            or re.search(r"[\x00-\x1f]", name)):
        raise ValueError("Use a collection name of 1–80 characters.")
    if (not isinstance(rules, dict) or not rules
            or set(rules) - {"kind", "source", "format", "tag", "favorite", "recent_days", "playback"}):
        raise ValueError("Choose at least one supported smart collection rule.")
    checked = {}
    for key, item in rules.items():
        valid = False
        if key in {"source", "tag"}:
            valid = (isinstance(item, str) and 1 <= len(item.strip()) <= (40 if key == "tag" else 200)
                     and not re.search(r"[\x00-\x1f]", item))
            if valid:
                item = item.strip()
        elif key == "kind":
            valid = isinstance(item, str) and item in ("video", "audio", "image")
        elif key == "format":
            valid = isinstance(item, str) and bool(re.fullmatch(r"\.[a-z0-9]{1,10}", item))
        elif key == "favorite":
            valid = isinstance(item, bool)
        elif key == "recent_days":
            valid = type(item) is int and 1 <= item <= 3650
        elif key == "playback":
            valid = isinstance(item, str) and item in ("unplayed", "in_progress", "finished")
        if not valid:
            raise ValueError("Invalid smart collection rule.")
        checked[key] = item
    return {"name": name.strip(), "rules": checked}


def smart_collection_records(value, *, strict=False) -> dict:
    if not isinstance(value, dict) or len(value) > SMART_COLLECTION_LIMIT:
        if strict:
            raise ValueError("Use up to 100 smart collections.")
        return {}
    result, names = {}, set()
    for key, item in value.items():
        try:
            if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{32}", key):
                raise ValueError("Invalid smart collection identifier.")
            record = checked_smart_collection(item)
            if record["name"].casefold() in names:
                raise ValueError("A smart collection with that name already exists.")
            result[key] = record
            names.add(record["name"].casefold())
        except ValueError:
            if strict:
                raise
    return result


class MediaLibrary:
    def __init__(self, root, suffixes: set[str], store=None):
        self.root = root
        self.suffixes = suffixes
        self.lock = threading.RLock()
        self.store = store or SqliteLibraryStore(self.root, threading.Lock())

    def load(self) -> dict:
        data = self.store.load({})
        return {
            "version": 1,
            "files": data.get("files", {}) if isinstance(data, dict) and isinstance(data.get("files"), dict) else {},
            "trash": data.get("trash", {}) if isinstance(data, dict) and isinstance(data.get("trash"), dict) else {},
            "collections": {
                key: value for key, value in (data.get("collections", {}) if isinstance(data, dict)
                                             and isinstance(data.get("collections"), dict) else {}).items()
                if re.fullmatch(r"[0-9a-f]{32}", key) and isinstance(value, str) and 0 < len(value) <= 80
            },
            "smart_collections": smart_collection_records(data.get("smart_collections", {}))
                                 if isinstance(data, dict) else {},
        }

    def collections(self) -> list[dict]:
        with self.lock:
            return [{"id": key, "name": name} for key, name in self.load()["collections"].items()]

    def smart_collections(self) -> list[dict]:
        with self.lock:
            return [{"id": key, **item} for key, item in self.load()["smart_collections"].items()]

    def change_smart_collection(self, action, name=None, collection_id=None, rules=None) -> str:
        with self.lock:
            data = self.load()
            collections = data["smart_collections"]
            if action not in ("create", "update", "delete"):
                raise ValueError("Choose a valid smart collection action.")
            if action == "create":
                collection_id = None
            if action != "create" and (not isinstance(collection_id, str) or collection_id not in collections):
                raise ValueError("Smart collection no longer exists. Refresh Library.")
            if action == "delete":
                del collections[collection_id]
            else:
                record = checked_smart_collection({"name": name, "rules": rules})
                if any(item["name"].casefold() == record["name"].casefold() and key != collection_id
                       for key, item in collections.items()):
                    raise ValueError("A smart collection with that name already exists.")
                if action == "create":
                    if len(collections) >= SMART_COLLECTION_LIMIT:
                        raise ValueError("Use up to 100 smart collections.")
                    collection_id = uuid.uuid4().hex
                collections[collection_id] = record
            self.store.save(data)
            return collection_id

    @staticmethod
    def details_view(record: dict) -> dict:
        playback = record.get("playback")
        valid = (isinstance(playback, dict)
                 and type(playback.get("position")) in (int, float)
                 and type(playback.get("duration")) in (int, float)
                 and 0 < playback["duration"] <= 7 * 86400 and 0 <= playback["position"] <= playback["duration"]
                 and math.isfinite(playback["position"]) and math.isfinite(playback["duration"]))
        return {"tags": [tag for tag in record.get("tags", [])[:20] if isinstance(tag, str) and len(tag) <= 40]
                        if isinstance(record.get("tags"), list) else [],
                "note": str(record.get("note") or "")[:2000],
                "playback": {"position": playback["position"], "duration": playback["duration"],
                             "finished": playback.get("finished") is True,
                             "updated": playback.get("updated") if type(playback.get("updated")) in (int, float)
                             and 0 <= playback["updated"] <= 10**12
                             and math.isfinite(playback["updated"]) else 0} if valid else None}

    def describe(self, relative, tags, note) -> None:
        if (not isinstance(tags, list) or len(tags) > 20
                or any(not isinstance(tag, str) or not 1 <= len(tag.strip()) <= 40
                       or re.search(r"[\x00-\x1f]", tag) for tag in tags)
                or not isinstance(note, str) or len(note) > 2000
                or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", note)):
            raise ValueError("Use up to 20 tags of 40 characters and a note of up to 2000 characters.")
        unique = {}
        for tag in tags:
            unique.setdefault(tag.strip().casefold(), tag.strip())
        with self.lock:
            path = self.media_path(relative)
            key = path.relative_to(self.root().resolve()).as_posix()
            data = self.load()
            record = data["files"].get(key)
            record = record if isinstance(record, dict) else {}
            data["files"][key] = record
            record.update(tags=list(unique.values()), note=note)
            self.store.save(data)

    def save_playback(self, relative, position, duration) -> None:
        if (type(position) not in (int, float) or type(duration) not in (int, float)
                or not 0 < duration <= 7 * 86400 or not 0 <= position <= duration
                or not math.isfinite(position) or not math.isfinite(duration)):
            raise ValueError("Choose a valid playback position and duration.")
        with self.lock:
            path = self.media_path(relative)
            if path.suffix.lower() in IMAGE_SUFFIXES:
                raise ValueError("Images do not have playback progress.")
            key = path.relative_to(self.root().resolve()).as_posix()
            data = self.load()
            record = data["files"].get(key)
            record = record if isinstance(record, dict) else {}
            data["files"][key] = record
            if record.get("complete") is False:
                raise ValueError("Finish processing before saving playback progress.")
            record["playback"] = {"position": position, "duration": duration,
                                  "finished": position >= duration * 0.98, "updated": time.time()}
            self.store.save(data)

    def import_file(self, name, stream, size) -> dict:
        """Stream into a hidden temporary file, then publish content and metadata together."""
        if (not isinstance(name, str) or not name or name.startswith(".") or len(name) > 180
                or name.endswith((".", " ")) or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
                or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", name, re.I)
                or Path(name).suffix.lower() not in self.suffixes):
            raise ValueError("Choose a video, audio or image file with a valid filename.")
        if type(size) is not int or not 0 < size <= IMPORT_MAX_BYTES:
            raise ValueError("Choose a non-empty media file up to 8 GiB.")
        root = self.root().resolve()
        stage = root / ".library-imports"
        destination = root / "imports"
        for directory in (stage, destination):
            directory.resolve().relative_to(root)
            if directory.is_symlink():
                raise ValueError("The import folder must not be a symbolic link.")
            directory.mkdir(exist_ok=True)
        digest = hashlib.sha256()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=stage, suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                remaining = size
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("The import was interrupted. Your original file is unchanged.")
                    output.write(chunk)
                    digest.update(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            with self.lock:
                if self.root().resolve() != root:
                    raise ValueError("The save folder changed. Import this file again.")
                data = self.load()
                for key, record in data["files"].items():
                    if isinstance(record, dict) and record.get("import_hash") == digest.hexdigest():
                        try:
                            existing = self.media_path(key)
                            stat = existing.stat()
                            if (existing.suffix.lower() == Path(name).suffix.lower() and stat.st_size == size
                                    and stat.st_mtime_ns == record.get("import_mtime_ns")):
                                return {"path": key, "duplicate": True}
                        except (OSError, ValueError):
                            continue
                target = self.media_path("imports/" + name, existing=False, allow_attachment=True)
                relative = target.relative_to(root).as_posix()
                with self.move_group([(temporary, target)]):
                    data["files"][relative] = {"title": Path(name).stem, "source": "local", "source_url": "",
                                               "role": "image" if target.suffix.lower() in IMAGE_SUFFIXES else "media",
                                               "downloaded": time.time(), "complete": True,
                                               "import_hash": digest.hexdigest(), "import_mtime_ns": target.stat().st_mtime_ns}
                    self.store.save(data)
                return {"path": relative, "duplicate": False}
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def cover_path(self, path: Path, records: dict, *, media_paths: set[Path] | None = None) -> str:
        for suffix in (".jpg", ".jpeg", ".png", ".webp", ".avif"):
            cover = path.with_suffix(suffix)
            regular = cover in media_paths if media_paths is not None else cover.is_file() and not cover.is_symlink()
            if regular and self.is_attachment(cover, records, media_paths=media_paths):
                return cover.relative_to(self.root() if media_paths is not None else self.root().resolve()).as_posix()
        return ""

    def change_collection(self, action: str, name=None, collection_id=None) -> str:
        with self.lock:
            data = self.load()
            if action not in ("create", "rename", "delete"):
                raise ValueError("Choose a valid collection action")
            if action != "create" and (not isinstance(collection_id, str) or collection_id not in data["collections"]):
                raise ValueError("Collection no longer exists. Refresh Library.")
            if action != "delete":
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or re.search(r"[\x00-\x1f]", name):
                    raise ValueError("Use a collection name between 1 and 80 characters")
                name = name.strip()
                if any(value.casefold() == name.casefold() and key != collection_id
                       for key, value in data["collections"].items()):
                    raise ValueError("A collection with this name already exists")
            if action == "create":
                if len(data["collections"]) >= 200:
                    raise ValueError("You can create up to 200 collections")
                collection_id = uuid.uuid4().hex
            if action == "delete":
                del data["collections"][collection_id]
                records = list(data["files"].values()) + [item.get("metadata") for item in data["trash"].values()
                                                        if isinstance(item, dict)]
                for record in records:
                    if isinstance(record, dict) and isinstance(record.get("collections"), list):
                        record["collections"] = [key for key in record["collections"] if key != collection_id]
            else:
                data["collections"][collection_id] = name
            self.store.save(data)
            return collection_id

    def organize(self, items: list[str], *, favorite=None, collection_id=None, remove=False) -> dict:
        """Update virtual classification only; validate paths and preserve other metadata."""
        if (not isinstance(items, list) or not 1 <= len(items) <= 200
                or any(not isinstance(item, str) for item in items)
                or (favorite is None and collection_id is None)
                or (favorite is not None and not isinstance(favorite, bool))
                or not isinstance(remove, bool)):
            raise ValueError("Choose between 1 and 200 files and a valid organization action")
        with self.lock:
            data = self.load()
            if collection_id is not None and (not isinstance(collection_id, str) or collection_id not in data["collections"]):
                raise ValueError("Collection no longer exists. Refresh Library.")
            processed, failed = [], []
            for item in dict.fromkeys(items):
                try:
                    path = self.media_path(item)
                    relative = path.relative_to(self.root()).as_posix()
                    record = data["files"].get(relative)
                    record = record if isinstance(record, dict) else {}
                    if favorite is not None:
                        record["favorite"] = favorite
                    if collection_id is not None:
                        ids = record.get("collections", [])
                        ids = [key for key in ids if isinstance(key, str) and key in data["collections"]] if isinstance(ids, list) else []
                        record["collections"] = ([key for key in ids if key != collection_id] if remove
                                                 else list(dict.fromkeys([*ids, collection_id])))
                    data["files"][relative] = record
                    processed.append(item)
                except (ValueError, OSError) as error:
                    failed.append({"item": item, "error": str(error)})
            if processed:
                self.store.save(data)
            return {"processed": processed, "failed": failed}

    def media_path(self, relative: str, *, existing=True, allow_attachment=False, records=None) -> Path:
        root = self.root().resolve()
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            raise ValueError("Choose a file inside the download folder")
        raw = root / relative
        path = raw.resolve()
        try:
            path.relative_to(root)
        except ValueError:
            raise ValueError("Choose a file inside the download folder") from None
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            raise ValueError("Hidden files cannot be managed as media")
        if raw.is_symlink() or path.suffix.lower() not in self.suffixes:
            raise ValueError("Choose a regular media file")
        if existing and not path.is_file():
            raise FileNotFoundError("The file no longer exists")
        if (not allow_attachment and path.suffix.lower() in IMAGE_SUFFIXES
                and self.is_attachment(path, self.load()["files"] if records is None else records)):
            raise ValueError("Manage this cover together with its video or audio file.")
        return path

    def is_attachment(self, path: Path, records: dict, *, media_paths: set[Path] | None = None) -> bool:
        record = records.get(path.relative_to(self.root()).as_posix(), {})
        if isinstance(record, dict) and record.get("role") == "image":
            return False
        if isinstance(record, dict) and record.get("role") == "attachment":
            return True
        return path.suffix.lower() in IMAGE_SUFFIXES and any(
            path.with_suffix(suffix) in media_paths if media_paths is not None else path.with_suffix(suffix).is_file()
            for suffix in self.suffixes - IMAGE_SUFFIXES
        )

    def remember(self, records: dict[str, dict]) -> None:
        with self.lock:
            data = self.load()
            for relative, info in records.items():
                try:
                    path = self.media_path(relative, allow_attachment=info.get("role") == "image")
                except (ValueError, OSError):
                    continue
                url = http_url(info.get("source_url")) or ""
                relative = path.relative_to(self.root()).as_posix()
                previous = data["files"].get(relative)
                data["files"][relative] = {
                    **(previous if isinstance(previous, dict) else {}),
                    "source_url": url,
                    "source": (url.split("/")[2].lower() if url else ""),
                    "title": str(info.get("title") or path.stem)[:300],
                    "downloaded": time.time(),
                    "role": "image" if info.get("role") == "image" else "media",
                }
                if isinstance(info.get("complete"), bool):
                    data["files"][path.relative_to(self.root()).as_posix()]["complete"] = info["complete"]
                if isinstance(info.get("download_profile"), dict):
                    data["files"][relative]["download_profile"] = {
                        key: value for key, value in info["download_profile"].items()
                        if key in {"mode", "quality", "abr", "subs", "sub_langs", "auto_subs", "embed_subs", "cover", "keep_cover"}
                        and isinstance(value, (str, int, bool))
                    }
                if isinstance(info.get("repair_options"), dict):
                    data["files"][path.relative_to(self.root()).as_posix()]["repair_options"] = {
                        key: info["repair_options"][key] for key in ("mode", "abr", "cover", "keep_cover", "embed_subs")
                        if key in info["repair_options"]
                    }
            self.store.save(data)

    def companions(self, source: Path, *, records=None) -> list[Path]:
        """Only same-stem covers and same-stem/language-suffixed subtitles belong to media."""
        if source.suffix.lower() in IMAGE_SUFFIXES:
            return []
        records = self.load()["files"] if records is None else records
        result = []
        for path in source.parent.iterdir():
            if path.is_symlink() or not path.is_file():
                continue
            suffix = path.suffix.lower()
            subtitle = suffix in SUBTITLE_SUFFIXES and (
                path.stem == source.stem or
                (path.stem.startswith(source.stem + ".") and
                 re.fullmatch(r"[\w-]+(?:\.[\w-]+)*", path.stem[len(source.stem) + 1:])))
            if subtitle or (suffix in COVER_SUFFIXES and path.stem == source.stem and self.is_attachment(path, records)):
                result.append(path)
        if result and any(path != source and path.stem == source.stem and path.suffix.lower() in self.suffixes - IMAGE_SUFFIXES
                          for path in source.parent.iterdir()):
            raise ValueError("Companion files are shared by multiple media files. Give the media unique names first.")
        return sorted(result)

    @staticmethod
    def move_without_overwrite(source: Path, target: Path) -> None:
        if os.name == "nt":
            source.rename(target)
        else:
            os.link(source, target)
            try:
                source.unlink()
            except OSError:
                target.unlink()
                raise

    @contextlib.contextmanager
    def move_group(self, moves: list[tuple[Path, Path]]):
        """Preflight the whole group and roll back on move or metadata-save failure."""
        for source, target in moves:
            if source.is_symlink() or not source.is_file():
                raise FileNotFoundError("The file no longer exists")
            if target.exists() or target.is_symlink():
                raise FileExistsError("A file with that name already exists")
        moved = []
        try:
            for source, target in moves:
                target.parent.mkdir(parents=True, exist_ok=True)
                self.move_without_overwrite(source, target)
                moved.append((source, target))
            yield
        except (OSError, ValueError):
            for source, target in reversed(moved):
                self.move_without_overwrite(target, source)
            raise

    def rename(self, relative: str, name: str, *, complete=None) -> str:
        with self.lock:
            source = self.media_path(relative)
            if (not isinstance(name, str) or not name or name.startswith(".") or len(name) > 200 or name.endswith((".", " "))
                    or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
                    or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", name, re.I)
                    or Path(name).suffix.lower() != source.suffix.lower()):
                raise ValueError("Use a valid filename and keep the original extension")
            target = source.with_name(name)
            if target == source:
                return relative
            moves = [(source, target)] + [
                (path, path.with_name(target.stem + path.name[len(source.stem):]))
                for path in self.companions(source)
            ]
            data = self.load()
            new_relative = target.relative_to(self.root()).as_posix()
            record = data["files"].pop(source.relative_to(self.root()).as_posix(), None)
            if isinstance(complete, bool):
                record = record if isinstance(record, dict) else {}
                record["complete"] = complete
            if record:
                data["files"][new_relative] = record
            with self.move_group(moves):
                self.store.save(data)
            return new_relative

    def trash_directory(self) -> Path:
        directory = self.root() / ".grab-trash"
        if directory.is_symlink() or directory.resolve().parent != self.root().resolve():
            raise ValueError("The recovery folder is not inside the download folder")
        return directory

    def trash(self, relative: str, *, complete=None, include_companions=True) -> str:
        processed, failed = self._trash_many([(relative, complete)], include_companions=include_companions)
        if failed:
            raise failed[0][1]
        return processed[0][1]

    def trash_many(self, items: list[str], *, completions=None) -> dict:
        """Persist one batch's recovery intent before moving any files."""
        completions = completions or {}
        order = {item: index for index, item in enumerate(dict.fromkeys(items))}
        processed, failed = self._trash_many([(item, completions.get(item)) for item in order])
        failed.sort(key=lambda failure: order[failure[0]])
        return {"processed": [item for item, _ in processed],
                "failed": [{"item": item, "error": str(error)} for item, error in failed],
                "recovery_ids": [recovery_id for _, recovery_id in processed]}

    @staticmethod
    def file_identity(path: Path) -> list[int]:
        info = path.stat()
        return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]

    def _trash_many(self, items, *, include_companions=True):
        with self.lock:
            data = self.load()
            plans, failed, claimed = [], [], set()
            for item, complete in items:
                try:
                    source = self.media_path(item, records=data["files"])
                    if source in claimed:
                        raise FileNotFoundError("The file no longer exists")
                    directory = self.trash_directory()
                    directory.mkdir(exist_ok=True)
                    recovery_id = uuid.uuid4().hex
                    target = directory / (recovery_id + source.suffix.lower())
                    companions = self.companions(source, records=data["files"]) if include_companions else []
                    companions = [path for path in companions if path not in claimed]
                    attachments = [{"path": path.relative_to(self.root()).as_posix(),
                                    "stored": recovery_id + f"-attachment-{i}" + path.suffix.lower()}
                                   for i, path in enumerate(companions)]
                    moves = [(source, target)] + [(path, directory / attachment["stored"])
                                                 for path, attachment in zip(companions, attachments)]
                    relative = source.relative_to(self.root()).as_posix()
                    metadata = data["files"].get(relative, {})
                    if isinstance(complete, bool):
                        metadata = dict(metadata) if isinstance(metadata, dict) else {}
                        metadata["complete"] = complete
                    record = {"path": relative, "stored": target.name, "removed": time.time(),
                              "metadata": metadata, "attachments": attachments,
                              "originals": [self.file_identity(path) for path, _ in moves]}
                    plans.append((item, recovery_id, record, moves))
                    claimed.update(path for path, _ in moves)
                except (ValueError, OSError) as error:
                    failed.append((item, error))
            if not plans:
                return [], failed
            previous = {record["path"]: data["files"][record["path"]] for _, _, record, _ in plans
                        if record["path"] in data["files"]}
            for _, recovery_id, record, _ in plans:
                data["files"].pop(record["path"], None)
                data["trash"][recovery_id] = record
            try:
                # Never move a group until its original paths and metadata are durable.
                self.store.save(data)
            except OSError as error:
                return [], failed + [(item, error) for item, _, _, _ in plans]
            processed, changed = [], False
            for item, recovery_id, record, moves in plans:
                try:
                    with self.move_group(moves):
                        pass
                    processed.append((item, recovery_id))
                except (ValueError, OSError) as error:
                    failed.append((item, error))
                    # A failed rollback must retain the intent for every remaining recovery file.
                    try:
                        rolled_back = all(not target.exists() and not target.is_symlink()
                                          and not source.is_symlink() and source.is_file()
                                          and self.file_identity(source) == identity
                                          for (source, target), identity in zip(moves, record["originals"]))
                    except OSError:
                        rolled_back = False
                    if rolled_back:
                        data["trash"].pop(recovery_id)
                        if record["path"] in previous:
                            data["files"][record["path"]] = previous[record["path"]]
                        changed = True
            if changed:
                try:
                    self.store.save(data)
                except OSError as error:
                    # The first save still describes all groups, including originals not moved.
                    failed = [(item, OSError(f"{failure}. Recovery records were retained: {error}"))
                              for item, failure in failed]
            return processed, failed

    def trash_items(self) -> list[dict]:
        with self.lock:
            directory = self.trash_directory()
            return [
                {"id": key, "path": item["path"], "removed": item.get("removed", 0),
                 "size": sum(path.stat().st_size for path in directory.glob(key + "*")
                             if path.is_file() and not path.is_symlink())}
                for key, item in self.load()["trash"].items()
                if isinstance(item, dict) and re.fullmatch(r"[0-9a-f]{32}", key)
                and isinstance(item.get("path"), str)
                and isinstance(item.get("stored"), str)
                and item["stored"].startswith(key + ".")
                and Path(item["stored"]).name == item["stored"]
                and (not (directory / item["stored"]).exists() or (directory / item["stored"]).is_file())
                and not (directory / item["stored"]).is_symlink()
            ]

    def purge(self, recovery_id: str) -> None:
        """Delete only validated recovery files, retaining the record on partial failure."""
        with self.lock:
            data = self.load()
            item = data["trash"].get(recovery_id)
            if not re.fullmatch(r"[0-9a-f]{32}", recovery_id) or not isinstance(item, dict):
                raise FileNotFoundError("Recovery file not found")
            directory = self.trash_directory().resolve()
            stored = item.get("stored")
            if (not isinstance(stored, str) or Path(stored).name != stored or
                    stored != recovery_id + Path(str(item.get("path") or "")).suffix.lower()):
                raise ValueError("Invalid recovery record")
            attachments = item.get("attachments", [])
            if not isinstance(attachments, list):
                raise ValueError("Invalid recovery record")
            names = []
            for i, attachment in enumerate(attachments):
                if not isinstance(attachment, dict) or not isinstance(attachment.get("path"), str):
                    raise ValueError("Invalid recovery record")
                suffix = Path(attachment["path"]).suffix.lower()
                name = recovery_id + f"-attachment-{i}" + suffix
                if suffix not in SUBTITLE_SUFFIXES | COVER_SUFFIXES or attachment.get("stored") != name:
                    raise ValueError("Invalid recovery record")
                names.append(name)
            # Validate the entire group before deleting; remove the main file last so failures stay visible.
            paths = [directory / name for name in [*names, stored]]
            for path in paths:
                if path.is_symlink() or path.resolve().parent != directory or (path.exists() and not path.is_file()):
                    raise ValueError("Invalid recovery record")
            for path in paths:
                path.unlink(missing_ok=True)
            data["trash"].pop(recovery_id)
            self.store.save(data)

    def restore(self, recovery_id: str) -> str:
        with self.lock:
            data = self.load()
            item = data["trash"].get(recovery_id)
            if not isinstance(item, dict) or not re.fullmatch(r"[0-9a-f]{32}", recovery_id):
                raise FileNotFoundError("Recovery file not found")
            stored = item.get("stored")
            if not isinstance(stored, str) or Path(stored).name != stored:
                raise ValueError("Invalid recovery record")
            if stored != recovery_id + Path(str(item.get("path") or "")).suffix.lower():
                raise ValueError("Invalid recovery record")
            source = self.trash_directory() / stored
            target = self.media_path(item.get("path"), existing=False,
                                     allow_attachment=isinstance(item.get("metadata"), dict) and item["metadata"].get("role") == "image")
            moves = [(source, target)]
            attachments = item.get("attachments", [])
            if not isinstance(attachments, list):
                raise ValueError("Invalid recovery record")
            for i, attachment in enumerate(attachments):
                if not isinstance(attachment, dict) or not isinstance(attachment.get("path"), str):
                    raise ValueError("Invalid recovery record")
                raw = self.root() / attachment["path"]
                path = raw.resolve()
                suffix = path.suffix.lower()
                stored = recovery_id + f"-attachment-{i}" + suffix
                if (raw.is_symlink() or path.parent != target.parent or
                        any(part.startswith(".") for part in Path(attachment["path"]).parts) or
                        suffix not in SUBTITLE_SUFFIXES | COVER_SUFFIXES or attachment.get("stored") != stored):
                    raise ValueError("Invalid recovery record")
                moves.append((self.trash_directory() / stored, path))
            remaining = []
            originals = item.get("originals")
            for i, (source, target) in enumerate(moves):
                if source.is_symlink() or (source.exists() and not source.is_file()):
                    raise ValueError("Invalid recovery record")
                if target.exists() or target.is_symlink():
                    # An interrupted batch may not have moved this file yet. Never accept a replacement.
                    if (not source.exists() and not target.is_symlink() and target.is_file()
                            and isinstance(originals, list) and len(originals) == len(moves)
                            and self.file_identity(target) == originals[i]):
                        continue
                    raise FileExistsError("A file already exists at the original location")
                remaining.append((source, target))
            data["files"][item["path"]] = item.get("metadata", {})
            data["trash"].pop(recovery_id)
            with self.move_group(remaining):
                self.store.save(data)
            return item["path"]
