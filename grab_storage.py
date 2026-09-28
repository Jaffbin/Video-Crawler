"""Small, dependency-free JSON persistence primitives used by the local app."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Callable


@dataclass(frozen=True)
class JsonStore:
    """Read and atomically replace one JSON document.

    ``path`` is a callback because the download directory is selected at
    startup and replaced by tests.
    """

    path: Callable[[], Path]
    write_lock: Lock

    def load(self, default: Any = None) -> Any:
        try:
            return json.loads(self.path().read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return default

    def save(self, value: Any) -> None:
        target = self.path()
        temp = target.with_name(target.name + ".tmp")
        encoded = json.dumps(value, ensure_ascii=False)
        with self.write_lock:
            try:
                with temp.open("w", encoding="utf-8", newline="\n") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, target)
            except OSError:
                try:
                    temp.unlink()
                except OSError:
                    pass
                raise
