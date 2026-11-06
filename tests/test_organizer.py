import os
import threading
from pathlib import Path

import pytest

import grab_organizer
from grab_library import MediaLibrary
from grab_organizer import LibraryOrganizer
from grab_images import IMAGE_SUFFIXES


@pytest.fixture
def organizer(tmp_path):
    library = MediaLibrary(lambda: tmp_path, {".mp4", ".mp3"} | IMAGE_SUFFIXES)
    service = LibraryOrganizer(library, lambda: library.load()["files"])
    yield service
    service.stop()


def put(service, name, data=b"same content"):
    path = service.library.root() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def scan(service, **kwargs):
    service.start(**kwargs)
    service.thread.join(timeout=10)
    assert not service.thread.is_alive()
    state = service.snapshot()
    assert state["status"] == "done", state
    return state


def test_inventory_duplicates_missing_and_space_preserve_all_data(organizer):
    for name in ("one.mp4", "folder/two.mp3"):
        put(organizer, name)
    put(organizer, "one.jpg", b"cover")
    put(organizer, "one.en.srt", b"subtitle")
    put(organizer, "independent.jpg", b"picture")
    put(organizer, ".grab-trash/stored.mp4", b"recycled")
    put(organizer, ".hidden.mp4", b"hidden")
    put(organizer, "unrelated.txt", b"ignored")
    organizer.library.store.save({"files": {"gone.mp4": {"favorite": True, "note": "keep"}}})
    before = organizer.library.store.path().read_bytes()
    state = scan(organizer)
    result = state["result"]
    assert result["media"] == {"count": 3, "bytes": 31}
    assert result["attachments"] == {"count": 2, "bytes": 13}
    assert result["recovery"] == {"count": 1, "bytes": 8}
    assert result["missing"] == [{"path": "gone.mp4", "title": "gone.mp4"}]
    assert result["unknown"] == [] and not result["incomplete"]
    assert result["duplicate_bytes"] == 12
    assert [item["path"] for item in result["duplicates"][0]["files"]] == ["folder/two.mp3", "one.mp4"]
    assert organizer.library.store.path().read_bytes() == before


def test_unique_sizes_are_not_read_and_hash_collisions_are_byte_verified(organizer, monkeypatch):
    for name, data in [("a.mp4", b"abc"), ("b.mp4", b"abc"), ("c.mp4", b"xyz"), ("only.mp4", b"longer")]:
        put(organizer, name, data)
    opened = []
    original = Path.open

    def tracked(path, *args, **kwargs):
        opened.append(path.name)
        return original(path, *args, **kwargs)

    class Collision:
        def update(self, value):
            pass

        def digest(self):
            return b"constant digest"

    monkeypatch.setattr(Path, "open", tracked)
    monkeypatch.setattr(grab_organizer.hashlib, "sha256", Collision)
    groups = scan(organizer)["result"]["duplicates"]
    assert len(groups) == 1 and [item["path"] for item in groups[0]["files"]] == ["a.mp4", "b.mp4"]
    assert "only.mp4" not in opened


def test_path_and_handle_change_times_can_differ_without_false_changes(organizer, monkeypatch):
    from types import SimpleNamespace
    put(organizer, "a.mp4")
    put(organizer, "b.mp4")
    original = os.fstat

    def handle_info(fd):
        info = original(fd)
        return SimpleNamespace(st_dev=info.st_dev, st_ino=info.st_ino, st_size=info.st_size,
                               st_mtime_ns=info.st_mtime_ns, st_ctime_ns=info.st_ctime_ns + 100)

    monkeypatch.setattr(grab_organizer.os, "fstat", handle_info)
    result = scan(organizer)["result"]
    assert len(result["duplicates"]) == 1 and result["unknown"] == []


@pytest.mark.parametrize("partial", ["limit", "depth", "unreadable"])
def test_incomplete_inventory_never_invents_missing_files(organizer, monkeypatch, partial):
    put(organizer, "nested/deeper/clip.mp4")
    organizer.library.store.save({"files": {"gone.mp4": {"favorite": True}, "nested/gone.mp4": {}}})
    kwargs = {}
    if partial == "limit":
        kwargs["entry_limit"] = 0
    elif partial == "depth":
        kwargs["max_depth"] = 0
    else:
        original = os.scandir

        def denied(path):
            if Path(path).name == "nested":
                raise PermissionError("fixture")
            return original(path)
        monkeypatch.setattr(grab_organizer.os, "scandir", denied)
    result = scan(organizer, **kwargs)["result"]
    assert result["missing"] == [] and result["incomplete"]
    assert {item["path"] for item in result["unknown"]} >= {"gone.mp4", "nested/gone.mp4"}


def test_incomplete_downloads_and_hardlinks_are_not_duplicate_candidates(organizer):
    first = put(organizer, "one.mp4")
    put(organizer, "incomplete.mp4")
    os.link(first, first.with_name("linked.mp4"))
    organizer.library.store.save({"files": {"incomplete.mp4": {"complete": False}}})
    result = scan(organizer)["result"]
    assert result["duplicates"] == [] and result["media"]["count"] == 3
    assert {item["reason"] for item in result["unknown"]} == {"incomplete_file", "shared"}


def test_links_and_linked_parents_are_not_followed(organizer, tmp_path):
    external = tmp_path.parent / (tmp_path.name + "-external")
    external.mkdir()
    (external / "outside.mp4").write_bytes(b"private")
    try:
        (tmp_path / "linked").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory links is unavailable")
    organizer.library.store.save({"files": {"linked/outside.mp4": {"favorite": True}}})
    result = scan(organizer)["result"]
    assert result["media"]["count"] == 0 and not result["missing"]
    assert result["unknown"] and (external / "outside.mp4").read_bytes() == b"private"


def test_reparse_attribute_is_rejected_before_reading(organizer, monkeypatch):
    from types import SimpleNamespace
    from grab_organizer import checked_file
    path = put(organizer, "linked.mp4")
    before = Path.lstat

    def reparse(item, *args, **kwargs):
        if item == path:
            return SimpleNamespace(st_mode=0o100644, st_file_attributes=0x400)
        return before(item, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", reparse)
    with pytest.raises(ValueError, match="Linked"):
        checked_file(organizer.library.root(), path.name)


@pytest.mark.parametrize("phase", ["hashing", "verifying"])
def test_cancel_at_phase_boundary_publishes_no_partial_findings(organizer, monkeypatch, phase):
    put(organizer, "a.mp4")
    put(organizer, "b.mp4")
    original = organizer._progress

    def cancel(**values):
        original(**values)
        if values.get("phase") == phase:
            organizer.cancel_event.set()

    monkeypatch.setattr(organizer, "_progress", cancel)
    organizer.start()
    organizer.thread.join(timeout=10)
    assert organizer.snapshot()["status"] == "cancelled" and organizer.snapshot()["result"] is None


def test_only_one_worker_runs_and_cancellation_can_be_restarted(organizer, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = organizer.records

    def blocked():
        entered.set()
        assert release.wait(timeout=5)
        return original()

    monkeypatch.setattr(organizer, "records", blocked)
    organizer.start()
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(ValueError, match="already running"):
            organizer.start()
        assert organizer.cancel()["status"] == "cancelling"
    finally:
        release.set()
    organizer.thread.join(timeout=10)
    monkeypatch.setattr(organizer, "records", original)
    assert scan(organizer)["status"] == "done"


def test_download_start_and_root_change_stop_checks(organizer, monkeypatch, tmp_path):
    monkeypatch.setattr(organizer, "active", lambda: True)
    with pytest.raises(ValueError, match="running downloads"):
        organizer.start()
    monkeypatch.setattr(organizer, "active", lambda: False)
    put(organizer, "a.mp4")
    put(organizer, "b.mp4")
    original = organizer._progress

    def download_started(**values):
        original(**values)
        if values.get("phase") == "hashing":
            monkeypatch.setattr(organizer, "active", lambda: True)

    monkeypatch.setattr(organizer, "_progress", download_started)
    organizer.start()
    organizer.thread.join(timeout=10)
    assert organizer.snapshot()["status"] == "cancelled"
    assert "Downloads started" in organizer.snapshot()["error"]
    changed = tmp_path / "new-library"
    changed.mkdir()
    monkeypatch.setattr(organizer.library, "root", lambda: changed)
    assert organizer.snapshot()["status"] == "idle" and organizer.snapshot()["result"] is None


def test_changed_files_are_excluded_even_after_their_hash_was_read(organizer, monkeypatch):
    first = put(organizer, "a.mp4")
    put(organizer, "b.mp4")
    original = organizer._progress

    def modify(**values):
        original(**values)
        if values.get("phase") == "verifying":
            first.write_bytes(b"different content")

    monkeypatch.setattr(organizer, "_progress", modify)
    result = scan(organizer)["result"]
    assert not result["duplicates"] and any(item["path"] == "a.mp4" for item in result["unknown"])


def test_unique_file_changes_and_returned_missing_files_are_rechecked_at_finish(organizer, monkeypatch):
    unique = put(organizer, "unique.mp4", b"unique length content")
    put(organizer, "a.mp4")
    put(organizer, "b.mp4")
    organizer.library.store.save({"files": {"gone.mp4": {"favorite": True}}})
    original = organizer._progress

    def mutate(**values):
        original(**values)
        if values.get("phase") == "verifying":
            unique.write_bytes(b"edited")
            put(organizer, "gone.mp4")

    monkeypatch.setattr(organizer, "_progress", mutate)
    result = scan(organizer)["result"]
    assert result["missing"] == []
    assert {item["path"] for item in result["unknown"]} >= {"unique.mp4", "gone.mp4"}


def test_reviewed_recycling_keeps_one_and_restores_companions_and_annotations(organizer):
    for name in ("a.mp4", "b.mp4"):
        put(organizer, name)
    put(organizer, "a.jpg", b"cover")
    put(organizer, "a.en.srt", b"subtitle")
    organizer.library.store.save({"files": {"a.mp4": {"favorite": True, "tags": ["keep"], "note": "My note"}}})
    state = scan(organizer)
    with pytest.raises(ValueError, match="at least one"):
        organizer.recycle(state["id"], ["a.mp4", "b.mp4"])
    with pytest.raises(ValueError, match="only duplicate"):
        organizer.recycle(state["id"], ["../outside.mp4"])
    with pytest.raises(ValueError, match="out of date"):
        organizer.recycle("old", ["a.mp4"])
    result = organizer.recycle(state["id"], ["a.mp4", "a.mp4"])
    assert result["processed"] == ["a.mp4"] and not result["failed"]
    assert not (organizer.library.root() / "a.jpg").exists()
    assert (organizer.library.root() / "b.mp4").read_bytes() == b"same content"
    organizer.library.restore(result["recovery_ids"][0])
    assert (organizer.library.root() / "a.jpg").read_bytes() == b"cover"
    assert (organizer.library.root() / "a.en.srt").read_bytes() == b"subtitle"
    assert organizer.library.load()["files"]["a.mp4"]["note"] == "My note"
    with pytest.raises(ValueError, match="out of date"):
        organizer.recycle(state["id"], ["a.mp4"])


@pytest.mark.parametrize("changed", ["replaced", "missing", "incomplete", "keeper_incomplete", "preserved_mtime"])
def test_recycle_rechecks_every_group_member(organizer, changed):
    first = put(organizer, "a.mp4")
    keep = put(organizer, "b.mp4")
    state = scan(organizer)
    if changed == "replaced":
        keep.write_bytes(b"new content")
    elif changed == "missing":
        keep.unlink()
    elif changed == "preserved_mtime":
        info = keep.stat()
        keep.write_bytes(b"diff content")
        os.utime(keep, ns=(info.st_atime_ns, info.st_mtime_ns))
    elif changed == "keeper_incomplete":
        organizer.library.store.save({"files": {"b.mp4": {"complete": False}}})
    else:
        organizer.library.store.save({"files": {"a.mp4": {"complete": False}}})
    with pytest.raises((ValueError, OSError)):
        organizer.recycle(state["id"], ["a.mp4"])
    assert first.read_bytes() == b"same content" and not organizer.library.load()["trash"]


def test_initial_save_failure_does_not_report_success_or_move_files(organizer, monkeypatch):
    first = put(organizer, "a.mp4")
    put(organizer, "b.mp4")
    state = scan(organizer)
    assert len(state["result"]["duplicates"]) == 1, state
    monkeypatch.setattr(type(organizer.library.store), "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    result = organizer.recycle(state["id"], ["a.mp4"])
    assert result["processed"] == result["recovery_ids"] == [] and len(result["failed"]) == 1
    assert first.exists() and organizer.snapshot()["status"] == "done"


def test_history_references_to_recycled_media_and_companions_are_not_missing(organizer, monkeypatch):
    for name in ("a.mp4", "a.jpg", "a.en.srt"):
        put(organizer, name)
    organizer.library.trash("a.mp4")
    history = {"a.mp4": {}, "a.jpg": {}}
    monkeypatch.setattr(organizer, "records", lambda: {**history, **organizer.library.load()["files"]})
    result = scan(organizer)["result"]
    assert result["missing"] == [] and result["unknown"] == []
    # A genuinely new tracked download at the same path must still be checked for disappearance.
    put(organizer, "a.mp4", b"new version")
    organizer.library.remember({"a.mp4": {"complete": True}})
    (organizer.library.root() / "a.mp4").unlink()
    result = scan(organizer)["result"]
    assert result["missing"] == [{"path": "a.mp4", "title": "a"}]


def test_original_left_by_interrupted_recycling_is_unconfirmed_not_a_new_duplicate(organizer, monkeypatch):
    put(organizer, "a.mp4")
    put(organizer, "b.mp4")
    with monkeypatch.context() as context:
        context.setattr(organizer.library, "move_without_overwrite", lambda *args: (_ for _ in ()).throw(SystemExit()))
        with pytest.raises(SystemExit):
            organizer.library.trash("a.mp4")
    result = scan(organizer)["result"]
    assert result["duplicates"] == []
    assert {"path": "a.mp4", "reason": "recovery_record"} in result["unknown"]


def test_unreadable_metadata_never_becomes_an_empty_recovery_history(organizer, monkeypatch):
    put(organizer, "a.mp4")
    put(organizer, "b.mp4")
    state = scan(organizer)
    organizer.library.store.path().write_text("damaged metadata", encoding="utf-8")
    with pytest.raises(ValueError, match="read Library records"):
        organizer.recycle(state["id"], ["a.mp4"])
    assert (organizer.library.root() / "a.mp4").exists()
    organizer.start()
    organizer.thread.join(timeout=10)
    assert organizer.snapshot()["status"] == "error" and organizer.snapshot()["result"] is None
    assert "read Library records" in organizer.snapshot()["error"]
    assert organizer.library.store.path().read_text(encoding="utf-8") == "damaged metadata"
