"""Transcription: SRT files, the search cache, the background worker and the routes.

A fake transcriber stands in for faster-whisper, so these tests need no model or network.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

import pytest

import grab_transcribe as tr
from grab_library import MediaLibrary
import webui
from test_webui import isolated  # noqa: F401


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("timed out")


# ── SRT ──
def test_srt_round_trip_skips_empty_text():
    segments = [(0.0, 1.5, " 你好，世界 "), (1.5, 2.0, "   "), (3661.25, 3662.0, "Hello")]
    text = tr.to_srt(segments)
    assert text.startswith("1\n00:00:00,000 --> 00:00:01,500\n你好，世界\n")
    assert "2\n01:01:01,250 --> 01:01:02,000\nHello" in text
    assert tr.parse_srt(text) == [(0.0, 1.5, "你好，世界"), (3661.25, 3662.0, "Hello")]


def test_parsing_tolerates_other_srt_styles():
    text = "1\r\n00:00:01.5 --> 00:00:02.000\r\nfirst\r\nline\r\n\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\n\r\n"
    assert tr.parse_srt(text) == [(1.5, 2.0, "first line")]


def test_sidecar_is_named_for_the_library_companion_rules_and_written_atomically(tmp_path):
    media = tmp_path / "Lecture 1.mp4"
    media.write_bytes(b"x")
    target = tr.write_sidecar(media, [(0, 1, "hi")])
    assert target.name == "Lecture 1.transcript.srt" and not list(tmp_path.glob("*.tmp"))
    assert tr.parse_srt(target.read_text(encoding="utf-8")) == [(0, 1, "hi")]


def test_transcripts_follow_their_media_when_renamed(tmp_path):
    library = MediaLibrary(lambda: tmp_path, {".mp4"})
    media = tmp_path / "talk.mp4"
    media.write_bytes(b"x")
    tr.write_sidecar(media, [(0, 1, "hi")])
    library.rename("talk.mp4", "keynote.mp4")
    assert (tmp_path / "keynote.transcript.srt").is_file() and not (tmp_path / "talk.transcript.srt").exists()


# ── Search cache ──
def test_index_finds_chinese_and_english_and_follows_file_changes(tmp_path):
    index = tr.TranscriptIndex(lambda: tmp_path / "index.db")
    a, b = tmp_path / "a.transcript.srt", tmp_path / "b.transcript.srt"
    a.write_text(tr.to_srt([(0, 1, "今天我们讲 Python 教程"), (5, 6, "100% sure_thing")]), encoding="utf-8")
    b.write_text(tr.to_srt([(2, 3, "nothing here")]), encoding="utf-8")
    index.sync({"a.mp4": a, "b.mp3": b})
    assert index.search("python") == [{"path": "a.mp4", "hits": [{"start": 0.0, "text": "今天我们讲 Python 教程"}]}]
    assert index.search("讲")[0]["path"] == "a.mp4"
    assert index.search("100%")[0]["hits"][0]["start"] == 5.0
    assert index.search("0% s") and index.search("e_t") and not index.search("e%t") and not index.search("e_x")
    assert index.search("  ") == []
    b.write_text(tr.to_srt([(2, 3, "now about python")]), encoding="utf-8")
    os.utime(b, ns=(b.stat().st_mtime_ns + 10_000_000,) * 2)
    index.sync({"a.mp4": a, "b.mp3": b})
    assert [item["path"] for item in index.search("python")] == ["a.mp4", "b.mp3"]
    index.sync({"b.mp3": b})  # a.mp4 was renamed or moved to Recovery
    assert [item["path"] for item in index.search("python")] == ["b.mp3"]


def test_results_are_capped_per_file(tmp_path):
    index = tr.TranscriptIndex(lambda: tmp_path / "index.db")
    srt = tmp_path / "a.transcript.srt"
    srt.write_text(tr.to_srt([(i, i + 1, f"word {i}") for i in range(20)]), encoding="utf-8")
    index.sync({"a.mp4": srt})
    assert len(index.search("word")[0]["hits"]) == tr.PER_FILE_LIMIT


# ── Worker ──
def fake_loader(script):
    """script(path, progress, cancelled) -> (segments, language); records which models loaded."""
    loaded = []

    def loader(model):
        loaded.append(model)
        return script
    return loader, loaded


@pytest.fixture
def media_dir(tmp_path):
    for name in ("one.mp4", "two.mp3", "three.mp4"):
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


def manager(media_dir, script, **kwargs):
    def resolve(relative):
        path = media_dir / relative
        if not path.is_file():
            raise ValueError("Missing file")
        return path

    loader, loaded = fake_loader(script)
    done = []
    m = tr.TranscriptionManager(resolve, on_done=lambda: done.append(1), loader=loader,
                                is_available=lambda: True, **kwargs)
    return m, loaded, done


def test_transcribes_in_order_writes_sidecars_and_reports_progress(media_dir):
    seen_progress = []

    def script(path, progress, cancelled):
        progress(50)
        seen_progress.append(path.name)
        return [(0, 1, f"text of {path.stem}")], "en"

    m, loaded, done = manager(media_dir, script)
    assert m.enqueue(["one.mp4", "two.mp3", "one.mp4", "missing.mp4"]) == {
        "added": ["one.mp4", "two.mp3"], "skipped": ["missing.mp4"]}
    assert m.status()["items"]["missing.mp4"]["status"] == "error"
    m.start()
    try:
        wait_for(lambda: len(done) == 2)
    finally:
        m.stop()
    assert seen_progress == ["one.mp4", "two.mp3"] and loaded == ["small"]
    state = m.status()["items"]["two.mp3"]
    assert state["status"] == "done" and state["language"] == "en" and state["percent"] == 100
    assert "text of two" in (media_dir / "two.transcript.srt").read_text(encoding="utf-8")


def test_cancel_stops_the_current_file_and_drops_the_rest(media_dir):
    started = threading.Event()

    def script(path, progress, cancelled):
        started.set()
        while not cancelled():
            time.sleep(0.01)
        raise tr.Cancelled

    m, _, done = manager(media_dir, script)
    m.enqueue(["one.mp4", "two.mp3"])
    m.start()
    try:
        assert started.wait(5)
        m.cancel()
        wait_for(lambda: done)
    finally:
        m.stop()
    items = m.status()["items"]
    assert items["one.mp4"]["status"] == "canceled" and items["two.mp3"]["status"] == "canceled"
    assert not (media_dir / "one.transcript.srt").exists()


def test_a_failure_ends_only_that_file(media_dir):
    def script(path, progress, cancelled):
        if path.name == "one.mp4":
            raise RuntimeError("cannot decode audio")
        return [(0, 1, "ok")], "zh"

    m, _, done = manager(media_dir, script)
    m.enqueue(["one.mp4", "three.mp4"])
    m.start()
    try:
        wait_for(lambda: len(done) == 2)
    finally:
        m.stop()
    items = m.status()["items"]
    assert items["one.mp4"]["status"] == "error" and "cannot decode" in items["one.mp4"]["error"]
    assert items["three.mp4"]["status"] == "done"


def test_the_model_loads_once_per_choice(media_dir):
    m, loaded, done = manager(media_dir, lambda p, progress, cancelled: ([(0, 1, "x")], "en"))
    m.start()
    try:
        m.enqueue(["one.mp4"])
        wait_for(lambda: len(done) == 1)
        m.enqueue(["two.mp3"])
        wait_for(lambda: len(done) == 2)
        m.set_model("tiny")
        m.enqueue(["three.mp4"])
        wait_for(lambda: len(done) == 3)
    finally:
        m.stop()
    assert loaded == ["small", "tiny"]
    with pytest.raises(ValueError, match="Choose one of"):
        m.set_model("gigantic")


def test_without_the_optional_package_the_app_explains_how_to_install_it(media_dir):
    m = tr.TranscriptionManager(lambda r: media_dir / r, is_available=lambda: False)
    with pytest.raises(ValueError, match=r'pip install -e "\.\[ai\]"'):
        m.enqueue(["one.mp4"])
    assert m.status()["available"] is False


# ── Routes ──
@pytest.fixture
def server(monkeypatch):
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None):
    request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Token": webui.TOKEN})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def test_routes_transcribe_search_and_save_the_model(server, monkeypatch):
    monkeypatch.setattr(webui, "LIBRARY", MediaLibrary(lambda: webui.ROOT, webui.MEDIA_SUFFIX))
    monkeypatch.setattr(webui, "TRANSCRIPT_INDEX", tr.TranscriptIndex(lambda: webui.ROOT / ".grab-transcripts.db"))
    (webui.ROOT / "lecture.mp4").write_bytes(b"x")
    (webui.ROOT / "photo.jpg").write_bytes(b"x")
    webui.LIBRARY.remember({"lecture.mp4": {"source_url": "https://example.com/v", "title": "Lecture one",
                                            "complete": True}})
    loader, _ = fake_loader(lambda path, progress, cancelled: ([(12.5, 14, "今天讲 Python")], "zh"))
    worker = tr.TranscriptionManager(lambda r: webui_routes_kind(r), loader=loader, is_available=lambda: True,
                                     on_done=webui.bump_rev)
    monkeypatch.setattr(webui, "TRANSCRIBER", worker)
    worker.start()
    try:
        status, body = call(server, "/api/transcripts", {"action": "start", "paths": ["lecture.mp4", "photo.jpg"]})
        assert status == 200 and body["added"] == ["lecture.mp4"] and body["skipped"] == ["photo.jpg"]
        assert "Only audio and video" in body["items"]["photo.jpg"]["error"]
        wait_for(lambda: worker.status()["items"]["lecture.mp4"]["status"] == "done")
    finally:
        worker.stop()
    webui.FILES_CACHE.update(rev=None)
    status, body = call(server, "/api/transcripts/search?q=python")
    assert status == 200 and body["results"] == [{"path": "lecture.mp4", "hits": [{"start": 12.5, "text": "今天讲 Python"}],
                                                  "name": "lecture.mp4", "title": "Lecture one", "kind": "video"}]
    assert call(server, "/api/transcripts", {"action": "model", "model": "base"})[1]["model"] == "base"
    assert json.loads((webui.CONFIG_DIR / "transcription.json").read_text(encoding="utf-8")) == {"model": "base"}
    assert call(server, "/api/transcripts", {"action": "model", "model": "huge"})[0] == 400
    assert call(server, "/api/transcripts", {"action": "dance"})[0] == 400


def webui_routes_kind(relative):
    import webui_routes_transcripts
    return webui_routes_transcripts.kind_check(webui, relative)
