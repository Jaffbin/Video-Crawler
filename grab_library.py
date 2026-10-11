"""Local media metadata and reversible file management, independent of job history."""

from __future__ import annotations

import contextlib
import os
import re
import threading
import time
import uuid
from pathlib import Path

from grab_models import http_url
from grab_storage import JsonStore
from grab_images import IMAGE_SUFFIXES

SUBTITLE_SUFFIXES = {".srt", ".vtt", ".ass", ".ssa", ".lrc", ".ttml", ".srv1", ".srv2", ".srv3", ".json3"}
COVER_SUFFIXES = IMAGE_SUFFIXES


class MediaLibrary:
    def __init__(self, root, suffixes: set[str]):
        self.root = root
        self.suffixes = suffixes
        self.lock = threading.RLock()
        self.store = JsonStore(lambda: self.root() / ".grab-library.json", threading.Lock())

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
        }

    def collections(self) -> list[dict]:
        with self.lock:
            return [{"id": key, "name": name} for key, name in self.load()["collections"].items()]

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

    def media_path(self, relative: str, *, existing=True, allow_attachment=False) -> Path:
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
        if not allow_attachment and path.suffix.lower() in IMAGE_SUFFIXES and self.is_attachment(path, self.load()["files"]):
            raise ValueError("Manage this cover together with its video or audio file.")
        return path

    def is_attachment(self, path: Path, records: dict) -> bool:
        record = records.get(path.relative_to(self.root()).as_posix(), {})
        if isinstance(record, dict) and record.get("role") == "image":
            return False
        if isinstance(record, dict) and record.get("role") == "attachment":
            return True
        return path.suffix.lower() in IMAGE_SUFFIXES and any(
            path.with_suffix(suffix).is_file() for suffix in self.suffixes - IMAGE_SUFFIXES
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
                if isinstance(info.get("repair_options"), dict):
                    data["files"][path.relative_to(self.root()).as_posix()]["repair_options"] = {
                        key: info["repair_options"][key] for key in ("mode", "abr", "cover", "keep_cover", "embed_subs")
                        if key in info["repair_options"]
                    }
            self.store.save(data)

    def companions(self, source: Path) -> list[Path]:
        """Only same-stem covers and same-stem/language-suffixed subtitles belong to media."""
        if source.suffix.lower() in IMAGE_SUFFIXES:
            return []
        records = self.load()["files"]
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
        with self.lock:
            source = self.media_path(relative)
            relative = source.relative_to(self.root()).as_posix()
            directory = self.trash_directory()
            directory.mkdir(exist_ok=True)
            recovery_id = uuid.uuid4().hex
            target = directory / (recovery_id + source.suffix.lower())
            companions = self.companions(source) if include_companions else []
            attachments = [{"path": path.relative_to(self.root()).as_posix(),
                            "stored": recovery_id + f"-attachment-{i}" + path.suffix.lower()}
                           for i, path in enumerate(companions)]
            moves = [(source, target)] + [(path, directory / item["stored"])
                                         for path, item in zip(companions, attachments)]
            data = self.load()
            before = self.load()
            data["trash"][recovery_id] = {
                "path": relative, "stored": target.name, "removed": time.time(),
                "metadata": data["files"].pop(relative, {}),
                "attachments": attachments,
            }
            if isinstance(complete, bool):
                metadata = data["trash"][recovery_id]["metadata"]
                metadata = metadata if isinstance(metadata, dict) else {}
                metadata["complete"] = complete
                data["trash"][recovery_id]["metadata"] = metadata
            # Record the destination before moving so a crash cannot orphan the recovery file.
            self.store.save(data)
            try:
                with self.move_group(moves):
                    pass
            except OSError:
                self.store.save(before)
                raise
            return recovery_id

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
            if source.is_symlink() or not source.is_file():
                raise FileNotFoundError("Recovery file not found")
            target = self.media_path(item.get("path"), existing=False,
                                     allow_attachment=isinstance(item.get("metadata"), dict) and item["metadata"].get("role") == "image")
            if target.exists():
                raise FileExistsError("A file already exists at the original location")
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
            data["files"][item["path"]] = item.get("metadata", {})
            data["trash"].pop(recovery_id)
            with self.move_group(moves):
                self.store.save(data)
            return item["path"]
