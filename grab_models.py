"""State models shared by the Web UI services and persistence layer."""

from __future__ import annotations

import collections
import re
import threading
import time
import uuid
from pathlib import Path


BACKFILL_MAX = 50
FILTER_DURATION_MAX = 7 * 24 * 60 * 60


def normalize_subscription_filters(value) -> dict:
    """Return a bounded, JSON-safe subscription filter object.

    Older subscription files have no ``filters`` field, so an empty object must
    continue to mean "download everything".
    """
    value = value if isinstance(value, dict) else {}

    def keywords(name: str) -> list[str]:
        raw = value.get(name, [])
        if isinstance(raw, str):
            raw = re.split(r"[,\n]", raw)
        if not isinstance(raw, list):
            return []
        result = []
        for item in raw:
            word = str(item).strip()[:80]
            if word and word.casefold() not in {entry.casefold() for entry in result}:
                result.append(word)
            if len(result) == 20:
                break
        return result

    def duration(name: str) -> int:
        try:
            return max(0, min(int(value.get(name) or 0), FILTER_DURATION_MAX))
        except (TypeError, ValueError):
            return 0

    minimum, maximum = duration("min_duration"), duration("max_duration")
    if minimum and maximum and minimum > maximum:
        minimum, maximum = maximum, minimum
    return {
        "include_keywords": keywords("include_keywords"),
        "exclude_keywords": keywords("exclude_keywords"),
        "exclude_live": value.get("exclude_live") is True,
        "exclude_shorts": value.get("exclude_shorts") is True,
        "min_duration": minimum,
        "max_duration": maximum,
    }


def http_url(value, schemes=("http", "https")) -> str | None:
    value = str(value or "").strip()
    return value if re.match(rf"^({'|'.join(schemes)})://\S+$", value, re.I) else None


class Job:
    def __init__(self, url: str, options: dict):
        self.id = uuid.uuid4().hex[:8]
        self.url = url
        self.options = dict(options)
        self.status = "queued"
        self.stage = "Queued"
        self.title = ""
        self.percent = 0.0
        self.speed = ""
        self.eta = ""
        self.item = ""
        self.error = ""
        self.error_kind = ""
        self.error_hint = ""
        self.files: list[str] = []
        self.seen_paths: list[str] = []
        self.log: collections.deque[str] = collections.deque(maxlen=400)
        self.cancel = threading.Event()
        self.created = time.time()
        self._parts_done = 0
        self._cur_id = None
        self.title_locked = False
        self.finished = 0.0
        self.notes: list[str] = []
        self._note_keys: set[str] = set()
        self.source: str = ""

    def to_dict(self, root: Path) -> dict:
        files = []
        for filename in self.files:
            try:
                files.append(Path(filename).resolve().relative_to(root).as_posix())
            except (ValueError, OSError):
                pass
        keep_log = list(self.log)[-30:] if self.status in ("error", "canceled") else []
        return {
            "id": self.id, "url": self.url, "options": self.options, "status": self.status,
            "stage": self.stage, "title": self.title, "percent": self.percent, "item": self.item,
            "error": self.error, "error_kind": self.error_kind, "error_hint": self.error_hint,
            "files": files, "created": self.created, "finished": self.finished,
            "log": [line[:300] for line in keep_log], "notes": self.notes[:3], "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict, root: Path) -> "Job | None":
        url, job_id = http_url(data.get("url")), str(data.get("id") or "")
        if not url or not re.fullmatch(r"[0-9a-f]{8}", job_id):
            return None
        options = data.get("options") if isinstance(data.get("options"), dict) else {}
        job = cls(url, options)
        job.id = job_id
        status = data.get("status")
        interrupted = status in ("queued", "running")
        job.status = status if status in ("done", "error", "canceled") else "canceled"
        job.stage = "Last incomplete" if interrupted else {
            "done": "Done", "error": "Failed", "canceled": "Canceled",
        }[job.status]
        job.title = str(data.get("title") or "")[:300]
        job.item = str(data.get("item") or "")[:20]
        job.error = (
            "This task was incomplete when the program exited, you can click 'Retry'."
            if interrupted else str(data.get("error") or "")[:600]
        )
        job.error_kind = str(data.get("error_kind") or "")[:40]
        job.error_hint = str(data.get("error_hint") or "")[:400]
        try:
            job.percent = 100.0 if job.status == "done" else float(data.get("percent") or 0)
            job.created = float(data.get("created") or time.time())
            job.finished = float(data.get("finished") or 0)
        except (TypeError, ValueError):
            job.created = time.time()
        if interrupted and not job.finished:
            job.finished = time.time()
        stored_files = data.get("files")
        for relative in stored_files if isinstance(stored_files, list) else []:
            try:
                path = (root / str(relative)).resolve()
                path.relative_to(root)
                if path.is_file():
                    job.files.append(str(path))
            except (ValueError, OSError):
                continue
        stored_log = data.get("log")
        if isinstance(stored_log, list):
            job.log.extend(str(line)[:300] for line in stored_log[-30:])
        stored_notes = data.get("notes")
        job.notes = [str(note)[:300] for note in stored_notes[:3]] if isinstance(stored_notes, list) else []
        job.source = str(data.get("source") or "")[:8]
        return job

    def view(self, root: Path) -> dict:
        files = []
        for filename in self.files:
            try:
                path = Path(filename).resolve()
                files.append({"name": path.name, "path": path.relative_to(root).as_posix()})
            except (ValueError, OSError):
                pass
        return {
            "id": self.id, "url": self.url, "status": self.status, "stage": self.stage,
            "title": self.title, "percent": round(self.percent, 1), "speed": self.speed,
            "eta": self.eta, "item": self.item, "error": self.error,
            "error_kind": self.error_kind, "error_hint": self.error_hint, "files": files,
            "mode": self.options.get("mode", "mp4"), "created": self.created,
            "finished": self.finished, "notes": list(self.notes), "source": self.source,
        }


class Subscription:
    def __init__(self, url: str, options: dict, backfill: str = "none", backfill_count: int = 5, filters=None):
        self.id = uuid.uuid4().hex[:8]
        self.url = url
        self.title = ""
        self.options = dict(options)
        self.enabled = True
        self.backfill = backfill if backfill in ("none", "recent") else "none"
        try:
            count = 5 if backfill_count is None else int(backfill_count)
        except (TypeError, ValueError):
            count = 5
        self.backfill_count = max(1, min(count, BACKFILL_MAX))
        self.filters = normalize_subscription_filters(filters)
        self.seen_ids: set[str] = set()
        self.initialized = False
        self.created = time.time()
        self.last_checked = 0.0
        self.last_error = ""
        self.last_error_kind = ""
        self.total_queued = 0
        self.total_filtered = 0
        self.last_found = 0
        self.last_queued = 0
        self.last_filtered = 0
        self.removed = False

    def to_dict(self) -> dict:
        return {
            "id": self.id, "url": self.url, "title": self.title, "options": self.options,
            "enabled": self.enabled, "backfill": self.backfill, "backfill_count": self.backfill_count,
            "filters": self.filters,
            "seen_ids": sorted(self.seen_ids), "initialized": self.initialized, "created": self.created,
            "last_checked": self.last_checked, "last_error": self.last_error,
            "last_error_kind": self.last_error_kind, "total_queued": self.total_queued,
            "total_filtered": self.total_filtered,
            "last_found": self.last_found, "last_queued": self.last_queued,
            "last_filtered": self.last_filtered,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Subscription | None":
        url, subscription_id = http_url(data.get("url")), str(data.get("id") or "")
        if not url or not re.fullmatch(r"[0-9a-f]{8}", subscription_id):
            return None
        options = data.get("options") if isinstance(data.get("options"), dict) else {}
        subscription = cls(
            url, options, str(data.get("backfill") or "none"), data.get("backfill_count"), data.get("filters")
        )
        subscription.id = subscription_id
        subscription.title = str(data.get("title") or "")[:300]
        subscription.enabled = bool(data.get("enabled", True))
        seen_ids = data.get("seen_ids")
        subscription.seen_ids = {str(item) for item in seen_ids if item} if isinstance(seen_ids, list) else set()
        subscription.initialized = bool(data.get("initialized"))
        subscription.last_error = str(data.get("last_error") or "")[:600]
        subscription.last_error_kind = str(data.get("last_error_kind") or "")[:40]
        try:
            subscription.created = float(data.get("created") or time.time())
            subscription.last_checked = float(data.get("last_checked") or 0)
            subscription.total_queued = int(data.get("total_queued") or 0)
            subscription.total_filtered = int(data.get("total_filtered") or 0)
            subscription.last_found = int(data.get("last_found") or 0)
            subscription.last_queued = int(data.get("last_queued") or 0)
            subscription.last_filtered = int(data.get("last_filtered") or 0)
        except (TypeError, ValueError):
            pass
        return subscription

    def view(self, interval_seconds: int, checking: bool) -> dict:
        return {
            "id": self.id, "url": self.url, "title": self.title, "enabled": self.enabled,
            "backfill": self.backfill, "backfill_count": self.backfill_count, "filters": self.filters,
            "mode": self.options.get("mode", "mp4"), "options": self.options,
            "created": self.created, "last_checked": self.last_checked, "last_error": self.last_error,
            "last_error_kind": self.last_error_kind,
            "total_queued": self.total_queued, "total_filtered": self.total_filtered,
            "last_found": self.last_found, "last_queued": self.last_queued,
            "last_filtered": self.last_filtered,
            "next_check": (self.last_checked + interval_seconds) if self.enabled else None,
            "checking": checking,
        }
