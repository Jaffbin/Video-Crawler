"""Run user-configured programs after downloads finish.

Commands come only from a settings file the user edits by hand. No HTTP route can change them,
because the Chrome extension shares the API token once it is allowed to connect. Commands run
without a shell; event details reach the program through standard input (JSON) and ``VG_*``
environment variables, never through the command line, so titles and URLs cannot inject arguments.
"""
from __future__ import annotations

import collections
import json
import logging
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable

import grab_push

LOG = logging.getLogger(__name__)

EVENTS = ("download_completed", "download_failed")
DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 600
MAX_COMMAND_PARTS = 32
MAX_COMMAND_PART_LENGTH = 4096
MAX_CONFIG_BYTES = 64 * 1024
MAX_PENDING = 100
RECENT_RESULTS = 20
STDERR_TAIL_BYTES = 2048
ENV_VALUE_MAX = 2000
COMPANION_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".srt", ".vtt", ".ass"}


class HookConfigError(ValueError):
    pass
# grab_push.ChannelConfigError is also a ValueError, so load_config reports both the same way.


def _validate_hook(event: str, value) -> dict:
    if not isinstance(value, dict):
        raise HookConfigError(f"hooks.{event} must be an object.")
    unknown = set(value) - {"command", "timeout_seconds"}
    if unknown:
        raise HookConfigError(f"hooks.{event} has unknown keys: {', '.join(sorted(unknown))}.")
    command = value.get("command")
    if (not isinstance(command, list) or not 1 <= len(command) <= MAX_COMMAND_PARTS
            or not all(isinstance(part, str) and part and len(part) <= MAX_COMMAND_PART_LENGTH
                       and "\0" not in part for part in command)):
        raise HookConfigError(f"hooks.{event}.command must be a list of 1 to {MAX_COMMAND_PARTS} non-empty strings: "
                              "the program first, then its arguments.")
    timeout = value.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= MAX_TIMEOUT_SECONDS:
        raise HookConfigError(f"hooks.{event}.timeout_seconds must be a whole number from 1 to {MAX_TIMEOUT_SECONDS}.")
    return {"command": list(command), "timeout_seconds": timeout}


def parse_config(raw) -> dict:
    """Validate a decoded settings document. Keys starting with ``_`` are comments and ignored."""
    if not isinstance(raw, dict):
        raise HookConfigError("The settings file must contain a JSON object.")
    unknown = {key for key in raw if not key.startswith("_")} - {"enabled", "hooks", "notifications", "language"}
    if unknown:
        raise HookConfigError(f"Unknown settings: {', '.join(sorted(unknown))}.")
    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise HookConfigError("enabled must be true or false.")
    hooks = raw.get("hooks", {})
    if not isinstance(hooks, dict):
        raise HookConfigError("hooks must be an object.")
    unknown = set(hooks) - set(EVENTS)
    if unknown:
        raise HookConfigError(f"Unknown events: {', '.join(sorted(unknown))}. Supported: {', '.join(EVENTS)}.")
    return {"enabled": enabled,
            "hooks": {event: _validate_hook(event, hooks[event]) for event in EVENTS if event in hooks},
            "notifications": grab_push.parse_channels(raw.get("notifications"), EVENTS),
            "language": grab_push.parse_language(raw.get("language"))}


def load_config(path: Path) -> dict:
    """Return the validated settings plus ``exists`` and ``error``. A broken file runs nothing."""
    empty = {"enabled": False, "hooks": {}, "notifications": [], "language": "en"}
    try:
        if path.stat().st_size > MAX_CONFIG_BYTES:
            return {**empty, "exists": True, "error": "The settings file is larger than 64 KB."}
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {**empty, "exists": False, "error": None}
    except (OSError, UnicodeDecodeError) as error:
        return {**empty, "exists": True, "error": f"Could not read the settings file: {error}"}
    try:
        return {**parse_config(json.loads(text)), "exists": True, "error": None}
    except ValueError as error:  # json.JSONDecodeError and HookConfigError are both ValueErrors.
        return {**empty, "exists": True, "error": str(error)}


def template_text() -> str:
    script = r"C:\Scripts\after-download.bat" if sys.platform.startswith("win") else "/path/to/after-download.sh"
    return json.dumps({
        "_help": ("Set enabled to true and list the program, then its arguments, in command. Event details arrive "
                  "as JSON on standard input and in VG_* environment variables. To send notifications, rename "
                  "_notifications_example to notifications and fill in your own addresses. "
                  "See docs/USER_GUIDE.md."),
        "enabled": False,
        "hooks": {"download_completed": {"command": [script], "timeout_seconds": DEFAULT_TIMEOUT_SECONDS}},
        # Keys starting with "_" are ignored; rename this one to "notifications" to use it.
        "_notifications_example": [
            {"type": "discord", "url": "https://discord.com/api/webhooks/…"},
            {"type": "telegram", "bot_token": "123456:ABC…", "chat_id": "123456789"},
            {"type": "ntfy", "url": "https://ntfy.sh/your-topic", "events": ["download_failed"]},
            {"type": "webhook", "url": "https://example.com/hook", "headers": {"Authorization": "Bearer …"}},
        ],
        "language": "en",
    }, indent=2, ensure_ascii=False) + "\n"


def ensure_config_file(path: Path) -> bool:
    """Create a disabled template when no settings file exists. Never overwrites. True if created."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(template_text())
    except FileExistsError:
        return False
    return True


def _env_value(value) -> str:
    return str(value or "").replace("\0", "")[:ENV_VALUE_MAX]


def event_for(status: str) -> str | None:
    return {"done": "download_completed", "error": "download_failed"}.get(status)


def build_payload(event: str, job, root: Path) -> dict:
    """Describe a finished job. Download options are left out: they can hold proxy credentials."""
    files = []
    for filename in job.files:
        path = Path(filename)
        try:
            relative = path.resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            relative = ""
        files.append({"path": str(path), "relative": relative})
    payload = {
        "version": 1,
        "event": event,
        "job": {
            "id": job.id, "url": job.url, "title": job.title, "status": job.status,
            "mode": job.options.get("mode", "mp4"), "subscription_id": job.source or "",
            "finished": job.finished, "repair": "_repair_path" in job.options,
        },
        "files": files,
        "library_root": str(root),
    }
    if event == "download_failed":
        payload["job"]["error"] = job.error
        payload["job"]["error_kind"] = job.error_kind
    return payload


def primary_file(payload: dict) -> str:
    """The file a simple script most likely wants: media rather than a cover or subtitle."""
    paths = [item["path"] for item in payload["files"]]
    if payload["job"]["mode"] not in {"cover", "image"}:
        media = [path for path in paths if Path(path).suffix.lower() not in COMPANION_SUFFIXES]
        paths = media or paths
    return paths[-1] if paths else ""


def program_name(command: list[str]) -> str:
    """The program's own file name; the settings panel and run results show this, not the full path."""
    return command[0].replace("\\", "/").rsplit("/", 1)[-1] or command[0]


def build_env(payload: dict, base: dict | None = None) -> dict:
    job = payload["job"]
    env = dict(os.environ if base is None else base)
    env.update({
        "VG_EVENT": payload["event"],
        "VG_JOB_ID": _env_value(job["id"]),
        "VG_STATUS": _env_value(job["status"]),
        "VG_TITLE": _env_value(job["title"]),
        "VG_URL": _env_value(job["url"]),
        "VG_MODE": _env_value(job["mode"]),
        "VG_FILE": _env_value(primary_file(payload)),
        "VG_FILE_COUNT": str(len(payload["files"])),
        "VG_LIBRARY_ROOT": _env_value(payload["library_root"]),
    })
    if payload["event"] == "download_failed":
        env["VG_ERROR"] = _env_value(job.get("error"))
    return env


class HookRunner:
    """Run hooks one at a time on a background thread so downloads never wait for them."""

    def __init__(self, config_path: Callable[[], Path], run=subprocess.run, max_pending: int = MAX_PENDING,
                 opener=None):
        self._config_path = config_path
        self._run = run
        self._opener = opener
        self._pending: queue.Queue = queue.Queue(maxsize=max_pending)
        self._recent: collections.deque = collections.deque(maxlen=RECENT_RESULTS)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def config_path(self) -> Path:
        return self._config_path()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="download-hooks", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stop taking work. A hook still running keeps its own timeout; pending ones are dropped."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def dispatch(self, job, root: Path) -> bool:
        """Queue the configured program and notifications for a finished job. True when any was queued."""
        event = event_for(job.status)
        if event is None or self._stop.is_set():
            return False
        config = load_config(self.config_path())
        if config["error"]:
            LOG.warning("Download hooks skipped: %s", config["error"])
        if not config["enabled"]:
            return False
        # Commands and channels are captured now, so editing the file later never changes queued work.
        payload = build_payload(event, job, root)
        work = []
        if event in config["hooks"]:
            hook = config["hooks"][event]
            work.append(("program", (event, job.id, hook, payload), program_name(hook["command"])))
        for channel in config["notifications"]:
            if event in channel["events"]:
                work.append(("notification", (event, job.id, channel, payload, config["language"]),
                             grab_push.target_label(channel)))
        queued = False
        for kind, args, target in work:
            try:
                self._pending.put_nowait((kind, args))
                queued = True
            except queue.Full:
                self._record(event, job.id, "skipped", None, 0.0, "Too many were waiting; this one was skipped.",
                             kind=kind, target=target)
        return queued

    def send_test(self) -> list[dict]:
        """Send a test message to every configured channel now, even while hooks are turned off.

        Programs are never run from here: only a finished download may start one.
        """
        config = load_config(self.config_path())
        if config["error"]:
            raise HookConfigError(config["error"])
        title, body = grab_push.test_message(config["language"])
        results = []
        for channel in config["notifications"]:
            started = time.monotonic()
            reason = self._send(channel, title, body, None)
            target = grab_push.target_label(channel)
            self._record("test", "", "failed" if reason else "ok", None, time.monotonic() - started, reason,
                         kind="notification", target=target)
            results.append({"target": target, "ok": not reason, "detail": reason})
        return results

    def status(self) -> dict:
        with self._lock:
            recent = list(self._recent)
        return {"pending": self._pending.qsize(), "recent": recent[::-1]}

    def _record(self, event, job_id, outcome, exit_code, duration, detail, *, kind="program", target="") -> None:
        if outcome != "ok":
            LOG.warning("Download %s %s for job %s (%s): %s %s", kind, event, job_id, target, outcome, detail)
        with self._lock:
            self._recent.append({"event": event, "job_id": job_id, "kind": kind, "target": target,
                                 "outcome": outcome, "exit_code": exit_code, "duration": round(duration, 2),
                                 "detail": detail, "finished": time.time()})

    def _send(self, channel, title, body, payload) -> str:
        if self._opener is None:
            return grab_push.send(channel, title, body, payload)
        return grab_push.send(channel, title, body, payload, opener=self._opener)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                item = self._pending.get(timeout=0.5)
            except queue.Empty:
                continue
            kind, args = item
            try:
                (self.run_now if kind == "program" else self.notify_now)(*args)
            except Exception as error:  # noqa: BLE001
                # One broken item must not stop this thread, or every later hook would silently never run.
                LOG.exception("Download %s failed unexpectedly", kind)
                self._record(args[0], args[1], "failed", None, 0.0, f"Unexpected error: {error}", kind=kind)
            finally:
                self._pending.task_done()

    def notify_now(self, event: str, job_id: str, channel: dict, payload: dict, language: str) -> None:
        title, body = grab_push.message(event, payload, language)
        started = time.monotonic()
        reason = self._send(channel, title, body, payload)
        self._record(event, job_id, "failed" if reason else "ok", None, time.monotonic() - started, reason,
                     kind="notification", target=grab_push.target_label(channel))

    def run_now(self, event: str, job_id: str, hook: dict, payload: dict) -> None:
        target = program_name(hook["command"])
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform.startswith("win") else 0
        started = time.monotonic()
        # stderr goes to a temporary file so a noisy program cannot grow memory without bound.
        with tempfile.TemporaryFile() as stderr:
            try:
                result = self._run(hook["command"], input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                   stdout=subprocess.DEVNULL, stderr=stderr, env=build_env(payload),
                                   timeout=hook["timeout_seconds"], creationflags=flags, check=False)
            except subprocess.TimeoutExpired:
                self._record(event, job_id, "timeout", None, time.monotonic() - started,
                             f"Stopped after {hook['timeout_seconds']} seconds.", target=target)
                return
            except (OSError, ValueError) as error:
                self._record(event, job_id, "not_started", None, time.monotonic() - started,
                             f"Could not start {hook['command'][0]}: {error}", target=target)
                return
            duration = time.monotonic() - started
            detail = ""
            if result.returncode:
                stderr.seek(max(0, stderr.seek(0, os.SEEK_END) - STDERR_TAIL_BYTES))
                detail = stderr.read().decode("utf-8", "replace").strip()
            self._record(event, job_id, "ok" if result.returncode == 0 else "failed", result.returncode,
                         duration, detail, target=target)
