"""Local speech-to-text for Library audio and video, and full-text search over the results.

Transcription is optional: it needs ``pip install -e ".[ai]"`` (faster-whisper) and downloads the
chosen model the first time. Nothing leaves the computer. Each transcript is saved next to its media
as ``<name>.transcript.srt``; the Library already moves such subtitle companions with their media,
so the search index is only a cache rebuilt from those files.
"""
from __future__ import annotations

import collections
import contextlib
import importlib.util
import logging
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Callable

LOG = logging.getLogger(__name__)

SUFFIX = ".transcript.srt"
MODELS = ("tiny", "base", "small", "medium", "large-v3-turbo")
DEFAULT_MODEL = "small"
INSTALL_HINT = 'Install transcription support: pip install -e ".[ai]", then restart Video Grabber.'
MAX_QUEUE = 500
SEARCH_LIMIT = 200
PER_FILE_LIMIT = 5


class Cancelled(Exception):
    pass


def available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def sidecar(media: Path) -> Path:
    return media.with_name(media.stem + SUFFIX)


# ── SRT ──
def _stamp(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_srt(segments: list[tuple[float, float, str]]) -> str:
    blocks = []
    for index, (start, end, text) in enumerate((s for s in segments if s[2].strip()), 1):
        blocks.append(f"{index}\n{_stamp(start)} --> {_stamp(end)}\n{text.strip()}\n")
    return "\n".join(blocks)


_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    segments = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        lines = block.splitlines()
        for position, line in enumerate(lines):
            match = _TIME.search(line)
            if match:
                h1, m1, s1, ms1, h2, m2, s2, ms2 = match.groups()
                start = int(h1) * 3600 + int(m1) * 60 + int(s1) + int(ms1.ljust(3, "0")) / 1000
                end = int(h2) * 3600 + int(m2) * 60 + int(s2) + int(ms2.ljust(3, "0")) / 1000
                body = " ".join(part.strip() for part in lines[position + 1:] if part.strip())
                if body:
                    segments.append((start, end, body))
                break
    return segments


def write_sidecar(media: Path, segments: list[tuple[float, float, str]]) -> Path:
    """Replace this app's transcript atomically, so a crash never leaves half a file."""
    target = sidecar(media)
    temp = target.with_name(target.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(to_srt(segments))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, target)
    return target


# ── Search index ──
class TranscriptIndex:
    """SQLite cache of transcript text. ``LIKE`` finds Chinese and other text without word breaks."""

    def __init__(self, path: Callable[[], Path]):
        self.path = path
        self.lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path(), timeout=10)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS docs (path TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS segments (path TEXT NOT NULL, start REAL NOT NULL, text TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_segments_path ON segments(path);
        """)
        return conn

    def sync(self, media: dict[str, Path]) -> None:
        """Match the index to ``media`` (library path -> transcript file); re-read only changed files."""
        with self.lock, contextlib.closing(self._connect()) as conn, conn:
            known = dict(conn.execute("SELECT path, mtime_ns FROM docs"))
            for path in set(known) - set(media):
                conn.execute("DELETE FROM docs WHERE path = ?", (path,))
                conn.execute("DELETE FROM segments WHERE path = ?", (path,))
            for path, file in media.items():
                try:
                    mtime = file.stat().st_mtime_ns
                    if known.get(path) == mtime:
                        continue
                    segments = parse_srt(file.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    continue
                conn.execute("DELETE FROM segments WHERE path = ?", (path,))
                conn.executemany("INSERT INTO segments (path, start, text) VALUES (?, ?, ?)",
                                 [(path, start, text) for start, _end, text in segments])
                conn.execute("INSERT OR REPLACE INTO docs (path, mtime_ns) VALUES (?, ?)", (path, mtime))

    def search(self, query: str) -> list[dict]:
        terms = query.strip()
        if not terms:
            return []
        pattern = "%" + re.sub(r"([\\%_])", r"\\\1", terms) + "%"
        with self.lock, contextlib.closing(self._connect()) as conn:
            rows = conn.execute("SELECT path, start, text FROM segments WHERE text LIKE ? ESCAPE '\\' "
                                "ORDER BY path, start LIMIT ?", (pattern, SEARCH_LIMIT * 4)).fetchall()
        grouped: dict[str, list[dict]] = collections.OrderedDict()
        for path, start, text in rows:
            hits = grouped.setdefault(path, [])
            if len(hits) < PER_FILE_LIMIT:
                hits.append({"start": round(start, 2), "text": text})
        results, total = [], 0
        for path, hits in grouped.items():
            if total >= SEARCH_LIMIT:
                break
            results.append({"path": path, "hits": hits})
            total += len(hits)
        return results


# ── Background work ──
def whisper_transcriber(model_name: str):
    """Load faster-whisper once per model; returns transcribe(path, progress, cancelled)."""
    from faster_whisper import WhisperModel  # Optional dependency, imported only when used.

    model = WhisperModel(model_name, device="auto", compute_type="int8")

    def transcribe(path: Path, progress: Callable[[float], None], cancelled: Callable[[], bool]):
        segments, info = model.transcribe(str(path), vad_filter=True)
        result = []
        for segment in segments:  # A generator: decoding happens while we iterate.
            if cancelled():
                raise Cancelled
            result.append((segment.start, segment.end, segment.text))
            if info.duration:
                progress(min(99.0, segment.end / info.duration * 100))
        return result, info.language
    return transcribe


class TranscriptionManager:
    """One worker at a time: transcription is CPU/GPU heavy and must not compete with downloads."""

    def __init__(self, resolve: Callable[[str], Path], on_done: Callable[[], None] = lambda: None,
                 loader: Callable[[str], Callable] = whisper_transcriber, is_available: Callable[[], bool] = available):
        self.resolve = resolve        # library path -> absolute media path (raises ValueError/OSError)
        self.on_done = on_done
        self.loader = loader
        self.is_available = is_available
        self.model = DEFAULT_MODEL
        self.lock = threading.Lock()
        self.wake = threading.Condition(self.lock)
        self.pending: collections.deque[str] = collections.deque()
        self.items: dict[str, dict] = {}
        self.current: str | None = None
        self.cancel_current = threading.Event()
        self.stopping = False
        self.thread: threading.Thread | None = None
        self._loaded: tuple[str, Callable] | None = None

    def start(self) -> None:
        with self.lock:
            if self.thread is None:
                self.stopping = False
                self.thread = threading.Thread(target=self._loop, name="transcription", daemon=True)
                self.thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        with self.lock:
            self.stopping = True
            self.pending.clear()
            self.cancel_current.set()
            self.wake.notify_all()
            thread, self.thread = self.thread, None
        if thread:
            thread.join(timeout)

    def set_model(self, model) -> None:
        if model not in MODELS:
            raise ValueError(f"Choose one of: {', '.join(MODELS)}.")
        with self.lock:
            self.model = model

    def enqueue(self, paths) -> dict:
        if not self.is_available():
            raise ValueError(INSTALL_HINT)
        if not isinstance(paths, list) or not 1 <= len(paths) <= 200 or not all(isinstance(p, str) for p in paths):
            raise ValueError("Choose between 1 and 200 files.")
        added, skipped = [], []
        with self.lock:
            for path in dict.fromkeys(paths):
                state = self.items.get(path, {}).get("status")
                if state in ("queued", "running") or len(self.pending) >= MAX_QUEUE:
                    skipped.append(path)
                    continue
                try:
                    self.resolve(path)
                except (ValueError, OSError) as error:
                    skipped.append(path)
                    self.items[path] = {"status": "error", "percent": 0, "error": str(error), "language": ""}
                    continue
                self.pending.append(path)
                self.items[path] = {"status": "queued", "percent": 0, "error": "", "language": ""}
                added.append(path)
            self.wake.notify_all()
        return {"added": added, "skipped": skipped}

    def cancel(self) -> None:
        """Stop the current transcription and drop everything waiting."""
        with self.lock:
            for path in self.pending:
                self.items[path] = {**self.items[path], "status": "canceled"}
            self.pending.clear()
            if self.current:
                self.cancel_current.set()

    def status(self) -> dict:
        with self.lock:
            return {"available": self.is_available(), "install_hint": INSTALL_HINT, "model": self.model,
                    "models": list(MODELS), "items": {path: dict(state) for path, state in self.items.items()},
                    "pending": len(self.pending), "current": self.current}

    def _transcriber(self, model: str) -> Callable:
        if self._loaded is None or self._loaded[0] != model:
            self._loaded = (model, self.loader(model))
        return self._loaded[1]

    def _loop(self) -> None:
        while True:
            with self.lock:
                while not self.pending and not self.stopping:
                    self.wake.wait(1.0)
                if self.stopping:
                    return
                path = self.pending.popleft()
                self.current, model = path, self.model
                self.cancel_current.clear()
                self.items[path] = {**self.items[path], "status": "running", "percent": 0}
            self._run(path, model)
            with self.lock:
                self.current = None
            self.on_done()

    def _run(self, path: str, model: str) -> None:
        def progress(percent: float) -> None:
            with self.lock:
                self.items[path]["percent"] = round(percent, 1)

        started = time.monotonic()
        try:
            media = self.resolve(path)
            transcribe = self._transcriber(model)
            segments, language = transcribe(media, progress, self.cancel_current.is_set)
            write_sidecar(media, segments)
            state = {"status": "done", "percent": 100, "error": "", "language": language or "",
                     "seconds": round(time.monotonic() - started, 1)}
        except Cancelled:
            state = {"status": "canceled", "percent": 0, "error": "", "language": ""}
        except Exception as error:  # noqa: BLE001
            # Decoder, model download and disk errors all end this one file, never the worker.
            LOG.warning("Transcription failed for %s: %s", path, error)
            state = {"status": "error", "percent": 0, "error": str(error)[:300], "language": ""}
        with self.lock:
            self.items[path] = state
