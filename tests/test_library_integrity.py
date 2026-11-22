"""Library data check and repair: a damaged database or mirror is reported, never hides data, and is
repaired only on request, keeping the damaged file."""
import json
import os
import threading
import time

import pytest

from grab_library import MediaLibrary
import webui
from test_webui import call, isolated  # noqa: F401 - fresh folders and settings for every test


def make_library(root):
    (root / "clip.mp4").write_bytes(b"video")
    library = MediaLibrary(lambda: root, {".mp4"})
    library.remember({"clip.mp4": {"title": "Clip", "complete": True}})
    library.describe("clip.mp4", ["keep"], "important note")
    return library


def damage_database(root):
    time.sleep(0.02)
    (root / ".grab-library.db").write_bytes(b"this is not a database" * 100)


def test_a_healthy_library_passes(tmp_path):
    library = make_library(tmp_path)
    assert library.store.check() == {"database": "ok", "mirror": "ok", "in_sync": True, "records": 1,
                                     "action": "", "detail": ""}


def test_an_empty_folder_is_not_a_problem(tmp_path):
    report = MediaLibrary(lambda: tmp_path, {".mp4"}).store.check()
    assert report["database"] == "missing" and report["mirror"] == "missing" and report["action"] == ""


def test_a_damaged_database_falls_back_to_the_mirror_instead_of_hiding_annotations(tmp_path):
    make_library(tmp_path)
    damage_database(tmp_path)
    library = MediaLibrary(lambda: tmp_path, {".mp4"})
    assert library.load()["files"]["clip.mp4"]["note"] == "important note"
    assert library.store.state["problem"] == "database_unreadable"
    # Writes keep failing, so the mirror (now the only good copy) is never overwritten.
    with pytest.raises(OSError):
        library.describe("clip.mp4", ["new"], "new note")
    assert json.loads((tmp_path / ".grab-library.json").read_text(encoding="utf-8"))["files"]["clip.mp4"]["note"] == \
        "important note"


def test_a_newer_mirror_over_a_damaged_database_still_loads(tmp_path):
    make_library(tmp_path)
    damage_database(tmp_path)
    mirror = tmp_path / ".grab-library.json"
    future = time.time() + 10
    os.utime(mirror, (future, future))  # as after a backup restore
    library = MediaLibrary(lambda: tmp_path, {".mp4"})
    assert library.load()["files"]["clip.mp4"]["note"] == "important note"
    assert library.store.state["problem"] == "database_unreadable"


def test_rebuild_the_database_from_the_mirror_and_keep_the_damaged_file(tmp_path):
    make_library(tmp_path)
    damage_database(tmp_path)
    library = MediaLibrary(lambda: tmp_path, {".mp4"})
    report = library.store.check()
    assert report["database"] == "damaged" and report["mirror"] == "ok" and report["action"] == "rebuild_database"
    assert report["records"] == 1 and report["detail"]
    with pytest.raises(ValueError, match="does not apply"):
        library.store.repair("rewrite_mirror")
    report = library.store.repair("rebuild_database")
    assert report["database"] == "ok" and report["in_sync"] is True and report["action"] == ""
    kept = list(tmp_path.glob(".grab-library.db.damaged-*"))
    assert len(kept) == 1 and kept[0].read_bytes().startswith(b"this is not a database")
    assert "problem" not in library.store.state
    library.describe("clip.mp4", ["new"], "new note")  # writes work again
    assert MediaLibrary(lambda: tmp_path, {".mp4"}).load()["files"]["clip.mp4"]["note"] == "new note"


@pytest.mark.parametrize("mirror", ["damaged", "missing", "stale"])
def test_rewrite_a_damaged_missing_or_stale_mirror_from_the_database(tmp_path, mirror):
    library = make_library(tmp_path)
    path = tmp_path / ".grab-library.json"
    if mirror == "damaged":
        path.write_text("{not json", encoding="utf-8")
    elif mirror == "missing":
        path.unlink()
    else:
        stale = json.loads(path.read_text(encoding="utf-8"))
        stale["files"]["clip.mp4"]["note"] = "older note"
        path.write_text(json.dumps(stale), encoding="utf-8")
        past = time.time() - 60
        os.utime(path, (past, past))  # older than the database, like after a forced shutdown
    report = library.store.check()
    assert report["database"] == "ok" and report["action"] == "rewrite_mirror"
    assert report["in_sync"] is (False if mirror == "stale" else None)
    report = library.store.repair("rewrite_mirror")
    assert report["mirror"] == "ok" and report["in_sync"] is True and report["action"] == ""
    assert json.loads(path.read_text(encoding="utf-8"))["files"]["clip.mp4"]["note"] == "important note"


def test_a_just_restored_mirror_is_imported_not_reported_as_drift(tmp_path):
    library = make_library(tmp_path)
    path = tmp_path / ".grab-library.json"
    restored = json.loads(path.read_text(encoding="utf-8"))
    restored["files"]["clip.mp4"]["note"] = "restored note"
    path.write_text(json.dumps(restored), encoding="utf-8")
    future = time.time() + 10
    os.utime(path, (future, future))
    report = library.store.check()
    assert report["in_sync"] is True and report["action"] == ""
    assert library.load()["files"]["clip.mp4"]["note"] == "restored note"


def test_when_both_copies_are_damaged_nothing_is_offered_and_nothing_is_touched(tmp_path):
    make_library(tmp_path)
    damage_database(tmp_path)
    (tmp_path / ".grab-library.json").write_text("{broken", encoding="utf-8")
    store = MediaLibrary(lambda: tmp_path, {".mp4"}).store
    report = store.check()
    assert report["database"] == "damaged" and report["mirror"] == "damaged" and report["action"] == ""
    with pytest.raises(ValueError):
        store.repair("rebuild_database")
    assert (tmp_path / ".grab-library.json").read_text(encoding="utf-8") == "{broken"


# ── HTTP routes ──
def test_the_check_and_repair_routes_need_the_app_page(tmp_path):
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        assert call(base, "/api/library/integrity", token=False)[0] == 401
        assert call(base, "/api/library/integrity", {"action": "rebuild_database"}, token=False)[0] == 401
        make_library(webui.ROOT)
        status, report = call(base, "/api/library/integrity")
        assert status == 200 and report["database"] == "ok" and report["action"] == ""
        assert call(base, "/api/library/integrity", {"action": "rebuild_database"})[0] == 409
        damage_database(webui.ROOT)
        webui.LIBRARY.load()
        doctor = webui.collect_doctor(force=True)
        assert any(check["id"] == "library_data" and check["status"] == "warn" for check in doctor["checks"])
        status, report = call(base, "/api/library/integrity")
        assert report["action"] == "rebuild_database"
        status, report = call(base, "/api/library/integrity", {"action": "rebuild_database"})
        assert status == 200 and report["database"] == "ok"
        assert webui.LIBRARY.load()["files"]["clip.mp4"]["note"] == "important note"
    finally:
        srv.shutdown()
        srv.server_close()
        webui.LIBRARY.store.state.clear()
