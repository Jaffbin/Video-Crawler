"""Cancellable, read-only library checks and reviewed duplicate recycling."""
from __future__ import annotations

import copy
import contextlib
import hashlib
import logging
import os
from pathlib import Path, PurePosixPath
import stat
import threading
import time
import uuid

from grab_images import IMAGE_SUFFIXES
from grab_library import MediaLibrary, SUBTITLE_SUFFIXES

LOG = logging.getLogger(__name__)
CHUNK_SIZE = 1024 * 1024


class CheckCancelled(Exception):
    pass


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def checked_file(root: Path, relative: str):
    """Check each path component before opening; never traverse links or junctions."""
    if (not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative
            or PurePosixPath(relative).is_absolute()
            or any(part in ("", ".", "..") or part.startswith(".") for part in relative.split("/"))):
        raise ValueError("Choose a file inside the current library.")
    path = root
    for part in relative.split("/"):
        path /= part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked files are not checked.")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Choose a regular media file.")
    return path, info


def recovery_only_paths(library):
    """Job history may still mention files intentionally moved into Recovery."""
    raw = library.store.load(None)
    # Missing and unreadable metadata have different meanings for missing-file inference.
    if ((raw is None and library.store.path().exists())
            or (raw is not None and (not isinstance(raw, dict)
                or not isinstance(raw.get("files", {}), dict) or not isinstance(raw.get("trash", {}), dict)))):
        raise ValueError("Could not read Library records. Restore access or use a valid backup before organizing.")
    data = raw or {}
    paths = set()
    for item in data.get("trash", {}).values():
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("path"), str):
            paths.add(item["path"])
        attachments = item.get("attachments", [])
        if isinstance(attachments, list):
            paths.update(item["path"] for item in attachments if isinstance(item, dict) and isinstance(item.get("path"), str))
    return paths - data.get("files", {}).keys()


class LibraryOrganizer:
    def __init__(self, library, records, active=lambda: False):
        self.library = library
        self.records = records
        self.active = active
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.thread = None
        self.state = {"status": "idle", "id": "", "root": "", "phase": "inventory",
                      "checked": 0, "total": 0, "bytes_read": 0, "error": "", "result": None}
        self.review = None

    def snapshot(self):
        with self.lock:
            if self.state["root"] and self.state["root"] != str(self.library.root().resolve()):
                self.cancel_event.set()
                return {**self.state, "status": "idle", "id": "", "result": None, "error": ""}
            return copy.deepcopy(self.state)

    def start(self, *, entry_limit=20000, max_depth=3):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError("A library check is already running.")
            if self.active():
                raise ValueError("Wait for running downloads to finish before checking Library.")
            root = self.library.root().resolve()
            self.cancel_event = threading.Event()
            self.review = None
            self.state = {"status": "running", "id": uuid.uuid4().hex, "root": str(root), "phase": "inventory",
                          "checked": 0, "total": 0, "bytes_read": 0, "error": "", "result": None}
            self.thread = threading.Thread(target=self._run, args=(root, entry_limit, max_depth),
                                           name="library-organizer", daemon=True)
            self.thread.start()
            return copy.deepcopy(self.state)

    def cancel(self):
        with self.lock:
            if self.state["status"] in ("running", "cancelling"):
                self.state["status"] = "cancelling"
                self.cancel_event.set()
            return self.snapshot()

    def stop(self):
        self.cancel_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

    def _check(self, root):
        if self.cancel_event.is_set():
            raise CheckCancelled()
        if self.library.root().resolve() != root:
            raise CheckCancelled("The library changed. Start a new check.")
        if self.active():
            raise CheckCancelled("Downloads started. Check Library again after they finish.")

    def _progress(self, **values):
        with self.lock:
            self.state.update(values)

    def _run(self, root, entry_limit, max_depth):
        try:
            result, review = self._scan(root, entry_limit, max_depth)
            self._check(root)
            with self.lock:
                self.review = review
                self.state.update(status="done", result=result)
        except CheckCancelled as error:
            self._progress(status="cancelled", result=None, error=str(error))
        except ValueError as error:
            self._progress(status="error", result=None, error=str(error))
        except Exception:
            LOG.exception("Library check failed")
            self._progress(status="error", result=None,
                           error="Could not check Library. Check folder access and try again.")

    def _scan(self, root, entry_limit, max_depth):
        library = MediaLibrary(lambda: root, self.library.suffixes)
        records = self.records()
        entries, recovery, unknown, reasons = {}, {}, {}, set()
        checked = 0

        def walk(directory, depth=0, trash=False):
            nonlocal checked
            self._check(root)
            try:
                iterator = os.scandir(directory)
                with iterator:
                    for entry in iterator:
                        self._check(root)
                        if checked >= entry_limit:
                            reasons.add("entry_limit")
                            return
                        checked += 1
                        if checked % 100 == 0:
                            self._progress(checked=checked)
                        relative = Path(entry.path).relative_to(root).as_posix()
                        try:
                            info = entry.stat(follow_symlinks=False)
                            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                                unknown[relative] = "linked"
                                reasons.add("linked")
                                continue
                            if stat.S_ISDIR(info.st_mode):
                                if not trash and entry.name == ".grab-trash" and depth == 0:
                                    walk(entry.path, depth, trash=True)
                                elif not entry.name.startswith("."):
                                    if not trash and depth < max_depth:
                                        walk(entry.path, depth + 1)
                                    else:
                                        reasons.add("depth_limit")
                            elif stat.S_ISREG(info.st_mode):
                                if trash:
                                    recovery[relative] = info
                                elif not entry.name.startswith(".") and Path(entry.name).suffix.lower() in library.suffixes | SUBTITLE_SUFFIXES:
                                    # Windows DirEntry.stat reports zero device/inode values. Use lstat
                                    # for the durable identity also checked against open file handles.
                                    _, info = checked_file(root, relative)
                                    entries[relative] = info
                        except (OSError, ValueError):
                            reasons.add("unreadable")
                            unknown[relative] = "unreadable"
            except OSError:
                reasons.add("unreadable")
                unknown[Path(directory).relative_to(root).as_posix()] = "unreadable"

        walk(root)
        self._check(root)
        media_paths = {root / key for key in entries if Path(key).suffix.lower() in library.suffixes}
        main, attachments = {}, {}
        for relative, info in entries.items():
            self._check(root)
            path = root / relative
            record = records.get(relative, {})
            record = record if isinstance(record, dict) else {}
            if path.suffix.lower() in SUBTITLE_SUFFIXES or (path.suffix.lower() in IMAGE_SUFFIXES
                    and library.is_attachment(path, records, media_paths=media_paths if not reasons else None)):
                attachments[relative] = info
            else:
                main[relative] = info

        # Missing findings require both a complete inventory and a current metadata record.
        missing = []
        current = self.records()
        recovered = recovery_only_paths(library)
        for relative, record in current.items():
            self._check(root)
            if relative in main or relative in attachments or relative in recovered:
                continue
            try:
                checked_file(root, relative)
            except FileNotFoundError:
                if reasons:
                    unknown[relative] = "incomplete"
                elif Path(relative).suffix.lower() in library.suffixes and isinstance(record, dict) and record.get("role") != "attachment":
                    missing.append({"path": relative, "title": str(record.get("title") or Path(relative).name)[:300]})
            except (OSError, ValueError):
                unknown[relative] = "unreadable"
            else:
                unknown[relative] = "changed"

        sizes, signatures, physical = {}, {}, set()
        for relative, info in main.items():
            if relative in recovered:
                unknown[relative] = "recovery_record"
                continue
            record = records.get(relative, {})
            if isinstance(record, dict) and record.get("complete") is False:
                unknown[relative] = "incomplete_file"
                continue
            if info.st_size <= 0:
                continue
            inode = (info.st_dev, info.st_ino)
            if info.st_ino and inode in physical:
                unknown[relative] = "shared"
                continue
            physical.add(inode)
            sizes.setdefault(info.st_size, []).append(relative)
            signatures[relative] = identity(info)
        candidates = [path for group in sizes.values() if len(group) > 1 for path in group]
        self._progress(phase="hashing", checked=0, total=len(candidates), bytes_read=0)
        digests = {}
        handle_versions = {}
        read_bytes, last_update = 0, time.monotonic()

        def valid(relative):
            path, info = checked_file(root, relative)
            if identity(info) != signatures[relative]:
                raise ValueError("File changed during the check.")
            return path

        @contextlib.contextmanager
        def opened(relative):
            path = valid(relative)
            with path.open("rb") as stream:
                handle_before = identity(os.fstat(stream.fileno()))
                # On Windows, path and handle APIs can disagree about ctime's meaning.
                # Compare common identity fields across APIs and each API's own full version over time.
                if handle_before[:4] != signatures[relative][:4]:
                    raise ValueError("File changed during the check.")
                yield stream
                if identity(os.fstat(stream.fileno())) != handle_before:
                    raise ValueError("File changed during the check.")
                valid(relative)
                handle_versions[relative] = handle_before

        for index, relative in enumerate(candidates):
            self._check(root)
            try:
                digest = hashlib.sha256()
                with opened(relative) as stream:
                    remaining = main[relative].st_size
                    while remaining:
                        self._check(root)
                        chunk = stream.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            raise ValueError("File changed during the check.")
                        digest.update(chunk)
                        remaining -= len(chunk)
                        read_bytes += len(chunk)
                        if time.monotonic() - last_update > .15:
                            self._progress(bytes_read=read_bytes)
                            last_update = time.monotonic()
                valid(relative)
                digests.setdefault((main[relative].st_size, digest.digest()), []).append(relative)
            except (OSError, ValueError):
                unknown[relative] = "changed"
            self._progress(checked=index + 1, bytes_read=read_bytes)

        # Hashes shortlist candidates; byte comparison establishes equality even on a hash collision.
        groups = []
        self._progress(phase="verifying", checked=0, total=sum(len(group) for group in digests.values() if len(group) > 1))
        verified = 0
        for group in digests.values():
            if len(group) < 2:
                continue
            buckets = []
            for relative in group:
                self._check(root)
                try:
                    valid(relative)
                    for bucket in buckets:
                        equal = True
                        with opened(bucket[0]) as left, opened(relative) as right:
                            remaining = main[relative].st_size
                            while remaining:
                                self._check(root)
                                amount = min(CHUNK_SIZE, remaining)
                                a, b = left.read(amount), right.read(amount)
                                if len(a) != amount or len(b) != amount:
                                    raise ValueError("File changed during the check.")
                                if a != b:
                                    equal = False
                                    break
                                remaining -= amount
                        valid(bucket[0])
                        valid(relative)
                        if equal:
                            bucket.append(relative)
                            break
                    else:
                        buckets.append([relative])
                except (OSError, ValueError):
                    unknown[relative] = "changed"
                verified += 1
                self._progress(checked=verified)
            for bucket in buckets:
                stable = []
                for relative in bucket:
                    try:
                        valid(relative)
                        stable.append(relative)
                    except (OSError, ValueError):
                        unknown[relative] = "changed"
                if len(stable) > 1:
                    groups.append({"id": uuid.uuid4().hex, "size": main[stable[0]].st_size,
                                   "files": [{"path": path, "name": Path(path).name,
                                              "favorite": isinstance(records.get(path), dict) and records[path].get("favorite") is True}
                                             for path in sorted(stable)]})
        # A large hash pass may outlive an external rename/write of an earlier file.
        # Recheck the whole visible inventory before publishing snapshot findings.
        for relative, before in entries.items():
            self._check(root)
            try:
                _, after = checked_file(root, relative)
                if identity(before) != identity(after):
                    unknown[relative] = "changed"
            except (OSError, ValueError):
                unknown[relative] = "changed"
        stable_groups = []
        for group in groups:
            group["files"] = [item for item in group["files"] if item["path"] not in unknown]
            if len(group["files"]) > 1:
                stable_groups.append(group)
        groups = stable_groups
        current = self.records()
        recovered = recovery_only_paths(library)
        confirmed_missing = []
        for item in missing:
            self._check(root)
            if item["path"] not in current or item["path"] in recovered:
                continue
            try:
                checked_file(root, item["path"])
            except FileNotFoundError:
                confirmed_missing.append(item)
            except (OSError, ValueError):
                unknown[item["path"]] = "unreadable"
            else:
                unknown[item["path"]] = "changed"
        missing = confirmed_missing

        def total(values):
            return {"count": len(values), "bytes": sum(info.st_size for info in values.values())}
        result = {"media": total(main), "attachments": total(attachments), "recovery": total(recovery),
                  "missing": sorted(missing, key=lambda item: item["path"]),
                  "unknown": [{"path": key, "reason": reason} for key, reason in sorted(unknown.items())],
                  "duplicates": groups, "duplicate_bytes": sum(group["size"] * (len(group["files"]) - 1) for group in groups),
                  "incomplete": bool(reasons or unknown), "reasons": sorted(reasons), "finished": time.time()}
        return result, {"root": root, "signatures": signatures, "handles": handle_versions, "groups": groups}

    def recycle(self, scan_id, items):
        if (not isinstance(items, list) or not 1 <= len(items) <= 200
                or any(not isinstance(item, str) for item in items)):
            raise ValueError("Choose between 1 and 200 duplicate files.")
        with self.lock, self.library.lock:
            review = self.review
            if (not isinstance(scan_id, str) or scan_id != self.state["id"] or self.state["status"] != "done"
                    or review is None or review["root"] != self.library.root().resolve()):
                raise ValueError("These check results are out of date. Run a new check.")
            if self.active():
                raise ValueError("Wait for running downloads to finish before editing files")
            recovery_only_paths(self.library)
            selected = set(items)
            found, reviewed_paths = set(), set()
            for group in review["groups"]:
                paths = {item["path"] for item in group["files"]}
                if not paths & selected:
                    continue
                if paths <= selected:
                    raise ValueError("Keep at least one file in each duplicate group.")
                for path in paths:
                    absolute, info = checked_file(review["root"], path)
                    if identity(info) != review["signatures"][path]:
                        raise ValueError("These files changed. Run a new check before recycling.")
                    with absolute.open("rb") as stream:
                        if identity(os.fstat(stream.fileno())) != review["handles"][path]:
                            raise ValueError("These files changed. Run a new check before recycling.")
                found.update(paths & selected)
                reviewed_paths.update(paths)
            if found != selected:
                raise ValueError("Choose only duplicate files from these check results.")
            records = self.records()
            if any(isinstance(records.get(path), dict) and records[path].get("complete") is False for path in reviewed_paths):
                raise ValueError("These files changed. Run a new check before recycling.")
            result = self.library.trash_many(items, completions={path: record.get("complete") for path, record in records.items() if isinstance(record, dict)})
            if result["processed"]:
                self.review = None
                self.state.update(status="idle", result=None, id="")
            return result
