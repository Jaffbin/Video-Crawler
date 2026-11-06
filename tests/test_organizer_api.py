import threading

import pytest

import webui
from grab_organizer import LibraryOrganizer
from test_webui import isolated, call  # noqa: F401


@pytest.fixture
def server(monkeypatch):
    service = LibraryOrganizer(webui.LIBRARY, webui.library_records,
                               lambda: any(job.status == "running" for job in webui.JOB_MANAGER.snapshot()))
    monkeypatch.setattr(webui, "ORGANIZER", service)
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    worker = threading.Thread(target=srv.serve_forever)
    worker.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    service.stop()
    srv.shutdown()
    srv.server_close()
    worker.join()


def test_scan_api_requires_auth_and_recycles_only_reviewed_items_with_undo(server):
    for name in ("a.mp4", "b.mp4", "a.jpg", "a.en.srt"):
        (webui.ROOT / name).write_bytes(b"identical" if name.endswith("mp4") else name.encode())
    webui.LIBRARY.remember({"a.mp4": {"complete": True, "source_url": "https://example.com/a"}})
    webui.LIBRARY.describe("a.mp4", ["keep"], "Keep my note")
    assert call(server, "/api/library/organizer", token=False)[0] == 401
    assert call(server, "/api/library/organizer", {"action": "start"}, token=False)[0] == 401
    assert call(server, "/api/library/organizer", {"action": "invalid"})[0] == 400
    assert call(server, "/api/library/organizer", {"action": "start"})[0] == 200
    webui.ORGANIZER.thread.join(timeout=10)
    status, state = call(server, "/api/library/organizer")
    assert status == 200 and state["status"] == "done" and len(state["result"]["duplicates"]) == 1
    body = {"scan_id": state["id"], "items": ["a.mp4", "b.mp4"]}
    assert call(server, "/api/library/organizer/recycle", body)[0] == 400
    body["items"] = ["a.mp4"]
    assert call(server, "/api/library/organizer/recycle", body, token=False)[0] == 401
    status, result = call(server, "/api/library/organizer/recycle", body)
    assert status == 200 and result["processed"] == ["a.mp4"] and not result["failed"]
    assert len(result["recovery_ids"]) == 1
    assert not (webui.ROOT / "a.jpg").exists() and (webui.ROOT / "b.mp4").exists()
    assert call(server, "/api/library/organizer/recycle", body)[0] == 400
    _, restored = call(server, "/api/library/batch", {"action": "restore", "items": result["recovery_ids"]})
    assert restored["processed"] == result["recovery_ids"] and not restored["failed"]
    assert webui.LIBRARY.load()["files"]["a.mp4"]["note"] == "Keep my note"
    assert (webui.ROOT / "a.en.srt").read_bytes() == b"a.en.srt"


def test_active_jobs_block_scanning_and_recycling_and_changed_keeper_is_protected(server):
    for name in ("a.mp4", "b.mp4"):
        (webui.ROOT / name).write_bytes(b"same")
    job = webui.Job("https://example.invalid", {})
    job.status = "running"
    webui.JOB_MANAGER.add_restored(job)
    assert call(server, "/api/library/organizer", {"action": "start"})[0] == 400
    job.status = "done"
    call(server, "/api/library/organizer", {"action": "start"})
    webui.ORGANIZER.thread.join(timeout=10)
    state = call(server, "/api/library/organizer")[1]
    body = {"scan_id": state["id"], "items": ["a.mp4"]}
    job.status = "running"
    assert call(server, "/api/library/organizer/recycle", body)[0] == 400
    job.status = "done"
    (webui.ROOT / "b.mp4").write_bytes(b"replacement")
    assert call(server, "/api/library/organizer/recycle", body)[0] == 400
    assert (webui.ROOT / "a.mp4").read_bytes() == b"same"


def test_cancel_route_can_stop_worker_without_blocking_http(server, monkeypatch):
    entered, released = threading.Event(), threading.Event()
    original = webui.ORGANIZER.records

    def blocked():
        entered.set()
        assert released.wait(timeout=5)
        return original()

    monkeypatch.setattr(webui.ORGANIZER, "records", blocked)
    call(server, "/api/library/organizer", {"action": "start"})
    assert entered.wait(timeout=5)
    try:
        assert call(server, "/api/library/organizer", {"action": "cancel"})[1]["status"] == "cancelling"
        assert call(server, "/api/library/organizer")[0] == 200
    finally:
        released.set()
    webui.ORGANIZER.thread.join(timeout=10)
    assert call(server, "/api/library/organizer")[1]["status"] == "cancelled"
