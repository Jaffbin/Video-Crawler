"""Small, dependency-free storage persistence primitives used by the local app."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
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


@dataclass(frozen=True)
class SqliteLibraryStore:
    """SQLite-backed persistence with transparent JSON synchronization and recovery support."""

    root: Callable[[], Path]
    write_lock: Lock

    @property
    def path(self) -> Callable[[], Path]:
        return self._json_path

    def _db_path(self) -> Path:
        return self.root() / ".grab-library.db"

    def _json_path(self) -> Path:
        return self.root() / ".grab-library.json"

    def _connect(self) -> sqlite3.Connection:
        db_file = self._db_path()
        conn = sqlite3.connect(str(db_file), timeout=30.0)
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, complete INTEGER, favorite INTEGER, source TEXT, format TEXT, data TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_files_fav ON files(favorite);
            CREATE INDEX IF NOT EXISTS idx_files_comp ON files(complete);
            CREATE TABLE IF NOT EXISTS trash (id TEXT PRIMARY KEY, path TEXT, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS collections (id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS smart_collections (id TEXT PRIMARY KEY, name TEXT NOT NULL, rules TEXT NOT NULL);
        """)

    def load(self, default: Any = None) -> Any:
        db_file = self._db_path()
        json_file = self._json_path()

        need_sync = False
        if json_file.is_file():
            if not db_file.is_file():
                need_sync = True
            else:
                try:
                    if json_file.stat().st_mtime_ns > db_file.stat().st_mtime_ns:
                        need_sync = True
                except OSError:
                    pass

        if need_sync:
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    with self.write_lock:
                        with contextlib.closing(self._connect()) as conn:
                            self._ensure_schema(conn)
                            with conn:
                                self._save_to_conn(conn, raw)
                    return raw
            except (OSError, ValueError):
                pass

        if not db_file.is_file():
            if json_file.is_file():
                try:
                    return json.loads(json_file.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    return default
            return default

        try:
            with contextlib.closing(self._connect()) as conn:
                self._ensure_schema(conn)
                cur = conn.cursor()
                cur.execute("SELECT value FROM meta WHERE key = 'version'")
                row = cur.fetchone()
                version = int(row[0]) if row and row[0].isdigit() else 1

                cur.execute("SELECT path, data FROM files")
                files = {}
                for p, d in cur.fetchall():
                    try:
                        files[p] = json.loads(d)
                    except ValueError:
                        pass

                cur.execute("SELECT id, data FROM trash")
                trash = {}
                for i, d in cur.fetchall():
                    try:
                        trash[i] = json.loads(d)
                    except ValueError:
                        pass

                cur.execute("SELECT id, name FROM collections")
                collections = {i: n for i, n in cur.fetchall()}

                cur.execute("SELECT id, name, rules FROM smart_collections")
                smart_collections = {}
                for i, n, r in cur.fetchall():
                    try:
                        smart_collections[i] = {"name": n, "rules": json.loads(r)}
                    except ValueError:
                        pass

                return {
                    "version": version,
                    "files": files,
                    "trash": trash,
                    "collections": collections,
                    "smart_collections": smart_collections,
                }
        except (sqlite3.Error, OSError):
            return default

    def _save_to_conn(self, conn: sqlite3.Connection, value: dict) -> None:
        version = value.get("version", 1)
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('version', ?)", (str(version),))

        conn.execute("DELETE FROM files")
        files = value.get("files", {})
        if isinstance(files, dict):
            params = []
            for path, record in files.items():
                if not isinstance(record, dict):
                    continue
                complete = 1 if record.get("complete") is True else 0 if record.get("complete") is False else -1
                fav = 1 if record.get("favorite") is True else 0
                src = str(record.get("source") or "")
                fmt = str(record.get("format") or "")
                params.append((str(path), complete, fav, src, fmt, json.dumps(record, ensure_ascii=False)))
            conn.executemany(
                "INSERT INTO files (path, complete, favorite, source, format, data) VALUES (?, ?, ?, ?, ?, ?)",
                params,
            )

        conn.execute("DELETE FROM trash")
        trash = value.get("trash", {})
        if isinstance(trash, dict):
            params = [
                (str(i), str(d.get("path") or ""), json.dumps(d, ensure_ascii=False))
                for i, d in trash.items()
                if isinstance(d, dict)
            ]
            conn.executemany("INSERT INTO trash (id, path, data) VALUES (?, ?, ?)", params)

        conn.execute("DELETE FROM collections")
        collections = value.get("collections", {})
        if isinstance(collections, dict):
            params = [(str(i), str(n)) for i, n in collections.items() if isinstance(n, str)]
            conn.executemany("INSERT INTO collections (id, name) VALUES (?, ?)", params)

        conn.execute("DELETE FROM smart_collections")
        sc = value.get("smart_collections", {})
        if isinstance(sc, dict):
            params = []
            for i, item in sc.items():
                if isinstance(item, dict) and "name" in item and "rules" in item:
                    params.append((str(i), str(item["name"]), json.dumps(item["rules"], ensure_ascii=False)))
            conn.executemany("INSERT INTO smart_collections (id, name, rules) VALUES (?, ?, ?)", params)

    def save(self, value: Any) -> None:
        if not isinstance(value, dict):
            return
        db_file = self._db_path()
        json_file = self._json_path()
        db_file.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(value, ensure_ascii=False)
        temp_json = json_file.with_name(json_file.name + ".tmp")

        with self.write_lock:
            try:
                with contextlib.closing(self._connect()) as conn:
                    self._ensure_schema(conn)
                    with conn:
                        self._save_to_conn(conn, value)
            except sqlite3.Error as e:
                raise OSError(f"SQLite database write failed: {e}") from e

            try:
                with temp_json.open("w", encoding="utf-8", newline="\n") as stream:
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_json, json_file)
            except OSError:
                try:
                    temp_json.unlink()
                except OSError:
                    pass
                raise

