"""Small, dependency-free storage persistence primitives used by the local app."""

from __future__ import annotations

import contextlib
import datetime
import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Callable

LOG = logging.getLogger(__name__)


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
    """SQLite-backed persistence with transparent JSON synchronization and recovery support.

    Every save commits to SQLite first and then atomically replaces the JSON mirror, which backup
    restore and older versions also read and write. When the database cannot be read but the mirror
    can, loads fall back to the mirror and ``state["problem"]`` says so, so annotations never seem to
    vanish; writes keep failing until ``repair`` rebuilds the database. Nothing is repaired silently,
    because the mirror can be one save behind the database after a forced shutdown.
    """

    root: Callable[[], Path]
    write_lock: Lock
    state: dict = field(default_factory=dict, compare=False)

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
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error:
            # A damaged file fails here, before any caller can close the connection; an open
            # handle would stop Windows from renaming the damaged database during repair.
            conn.close()
            raise
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

    def _read_json(self) -> Any:
        """The mirror's content, or None when it is missing or unreadable."""
        try:
            raw = json.loads(self._json_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return raw if isinstance(raw, dict) else None

    def _degraded(self, error: Exception) -> None:
        if self.state.get("problem") != "database_unreadable":
            LOG.warning("The library database cannot be read (%s); using the JSON copy until it is repaired.", error)
        self.state["problem"] = "database_unreadable"

    def load(self, default: Any = None) -> Any:
        db_file = self._db_path()
        json_file = self._json_path()

        need_sync = False
        if json_file.is_file():
            if not db_file.is_file():
                need_sync = True
            else:
                try:
                    # The JSON document is written last (and alone by backup restore); equal times
                    # within one clock tick must still count as newer, or a restore looks lost.
                    if json_file.stat().st_mtime_ns >= db_file.stat().st_mtime_ns:
                        need_sync = True
                except OSError:
                    pass

        if need_sync:
            raw = self._read_json()
            if raw is not None:
                try:
                    with self.write_lock:
                        with contextlib.closing(self._connect()) as conn:
                            self._ensure_schema(conn)
                            with conn:
                                self._save_to_conn(conn, raw)
                    self.state.pop("problem", None)
                except sqlite3.Error as error:
                    self._degraded(error)
                except OSError:
                    pass
                return raw

        if not db_file.is_file():
            raw = self._read_json() if json_file.is_file() else None
            return default if raw is None else raw

        try:
            with contextlib.closing(self._connect()) as conn:
                self._ensure_schema(conn)
                result = self._read_conn(conn)
            self.state.pop("problem", None)
            return result
        except (sqlite3.Error, OSError) as error:
            raw = self._read_json()
            if raw is None:
                return default
            self._degraded(error)
            return raw

    def _read_conn(self, conn: sqlite3.Connection) -> dict:
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

        # Auto rules live in the key-value meta table, so no schema change is needed and
        # older versions, which never delete meta rows, keep them intact.
        cur.execute("SELECT value FROM meta WHERE key = 'auto_rules'")
        row = cur.fetchone()

        result = {
            "version": version,
            "files": files,
            "trash": trash,
            "collections": collections,
            "smart_collections": smart_collections,
        }
        # Only when saved, so this path returns exactly what the JSON mirror path returns.
        if row:
            try:
                auto_rules = json.loads(row[0]) if row[0] else {}
            except ValueError:
                auto_rules = {}
            result["auto_rules"] = auto_rules if isinstance(auto_rules, dict) else {}
        return result

    def _save_to_conn(self, conn: sqlite3.Connection, value: dict) -> None:
        version = value.get("version", 1)
        conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('version', ?)", (str(version),))
        if isinstance(value.get("auto_rules"), dict):
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('auto_rules', ?)",
                         (json.dumps(value["auto_rules"], ensure_ascii=False),))

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

    def _write_json(self, encoded: str) -> None:
        json_file = self._json_path()
        temp_json = json_file.with_name(json_file.name + ".tmp")
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

    def _save_locked(self, value: dict) -> None:
        self._db_path().parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(value, ensure_ascii=False)
        try:
            with contextlib.closing(self._connect()) as conn:
                self._ensure_schema(conn)
                with conn:
                    self._save_to_conn(conn, value)
        except sqlite3.Error as e:
            raise OSError(f"SQLite database write failed: {e}") from e
        self._write_json(encoded)

    def save(self, value: Any) -> None:
        if not isinstance(value, dict):
            return
        with self.write_lock:
            self._save_locked(value)

    # ── Integrity check and repair (Diagnostics) ──
    def _canonical(self, value: dict) -> dict:
        """What the database would hold for this document, so the two copies compare like for like."""
        with contextlib.closing(sqlite3.connect(":memory:")) as conn:
            self._ensure_schema(conn)
            self._save_to_conn(conn, value)
            result = self._read_conn(conn)
        result.setdefault("auto_rules", {})
        return result

    def _check_locked(self) -> dict:
        database, mirror, records, in_sync, detail = "missing", "missing", 0, None, ""
        db_data = None
        if self._db_path().is_file():
            try:
                with contextlib.closing(self._connect()) as conn:
                    rows = conn.execute("PRAGMA quick_check").fetchall()
                    if [tuple(row) for row in rows] != [("ok",)]:
                        raise sqlite3.DatabaseError("; ".join(str(row[0]) for row in rows[:3]))
                    self._ensure_schema(conn)
                    db_data = self._read_conn(conn)
                db_data.setdefault("auto_rules", {})
                database, records = "ok", len(db_data["files"])
            except (sqlite3.Error, OSError) as error:
                database, detail = "damaged", str(error)[:200]
        json_data = None
        if self._json_path().is_file():
            json_data = self._read_json()
            mirror = "ok" if json_data is not None else "damaged"
            if json_data is not None and database != "ok":
                records = len(json_data.get("files") or {}) if isinstance(json_data.get("files"), dict) else 0
        if database == "ok" and mirror == "ok":
            in_sync = self._canonical(json_data) == db_data
        if database == "ok" and (mirror != "ok" or not in_sync):
            action = "rewrite_mirror"
        elif database != "ok" and mirror == "ok":
            action = "rebuild_database"
        else:
            action = ""
        return {"database": database, "mirror": mirror, "in_sync": in_sync, "records": records,
                "action": action, "detail": detail}

    def check(self) -> dict:
        """Run SQLite's quick check and compare the database with its JSON mirror.

        A mirror that is newer than the database is imported first, as a normal load would, so a
        just-restored backup is never reported as drift.
        """
        self.load({})
        with self.write_lock:
            return self._check_locked()

    def repair(self, action: str) -> dict:
        """rewrite_mirror (database is fine) or rebuild_database (mirror is fine). Returns check()."""
        with self.write_lock:
            report = self._check_locked()
            if action != report["action"] or action not in ("rewrite_mirror", "rebuild_database"):
                raise ValueError("Run the check again; this repair does not apply to the library data now.")
            if action == "rewrite_mirror":
                with contextlib.closing(self._connect()) as conn:
                    data = self._read_conn(conn)
                self._write_json(json.dumps(data, ensure_ascii=False))
            else:
                data = self._read_json()
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                db_file = self._db_path()
                # Keep the damaged database next to the library rather than deleting it.
                for suffix in ("", "-journal"):
                    damaged = db_file.with_name(db_file.name + suffix)
                    if damaged.exists():
                        os.replace(damaged, db_file.with_name(f"{db_file.name}{suffix}.damaged-{stamp}"))
                self._save_locked(data)
                self.state.pop("problem", None)
            LOG.info("Library data repaired: %s.", action)
            return self._check_locked()
