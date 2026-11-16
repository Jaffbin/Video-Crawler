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
    assert json.loads((webui.CONFIG_DIR / "transcription.json").read_text(encoding="utf-8")) == {
        "model": "base", "auto": False, "reuse_subtitles": True}
    assert call(server, "/api/transcripts", {"action": "model", "model": "huge"})[0] == 400
    assert call(server, "/api/transcripts", {"action": "dance"})[0] == 400


def webui_routes_kind(relative):
    import webui_routes_transcripts
    return webui_routes_transcripts.kind_check(webui, relative)


# ── Real audio decoding and device fallback (regressions found with the real model) ──
def test_audio_is_decoded_with_ffmpeg_not_pyav(tmp_path):
    from conftest import FFMPEG_EXE, HAVE_FFMPEG
    import subprocess

    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg is not installed")
    clip = tmp_path / "tone.mp4"
    subprocess.run([str(FFMPEG_EXE), "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:a", "aac", str(clip)], check=True)
    samples = tr.decode_audio(clip, str(FFMPEG_EXE))
    assert abs(len(samples) - tr.SAMPLE_RATE) < tr.SAMPLE_RATE * 0.1  # about one second, mono 16 kHz
    assert samples.dtype.name == "float32" and 0.05 < float(abs(samples).max()) <= 1.0
    silent_video = tmp_path / "picture.mp4"
    subprocess.run([str(FFMPEG_EXE), "-loglevel", "error", "-f", "lavfi", "-i", "color=size=64x64:duration=1",
                    "-pix_fmt", "yuv420p", str(silent_video)], check=True)
    with pytest.raises(RuntimeError, match="no audio"):
        tr.decode_audio(silent_video, str(FFMPEG_EXE))
    with pytest.raises(RuntimeError, match="Could not read the audio"):
        tr.decode_audio(tmp_path / "missing.mp4", str(FFMPEG_EXE))


class FakeSegment:
    def __init__(self, start, end, text):
        self.start, self.end, self.text = start, end, text


class FakeInfo:
    duration = 4.0
    language = "en"


def test_a_missing_cuda_runtime_falls_back_to_the_cpu_once(monkeypatch):
    import numpy

    monkeypatch.setattr(tr, "ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(tr, "decode_audio", lambda path, ffmpeg: numpy.zeros(10, numpy.float32))
    built = []

    class GpuModel:
        def transcribe(self, audio, vad_filter):
            def segments():
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
                yield
            return segments(), FakeInfo()

    class CpuModel:
        def transcribe(self, audio, vad_filter):
            return iter([FakeSegment(0, 2, "hello")]), FakeInfo()

    def factory(device):
        built.append(device)
        return GpuModel() if device == "auto" else CpuModel()

    transcribe = tr.whisper_transcriber("tiny", model_factory=factory)
    progress = []
    assert transcribe("a.wav", progress.append, lambda: False) == ([(0, 2, "hello")], "en")
    assert transcribe("b.wav", progress.append, lambda: False) == ([(0, 2, "hello")], "en")
    assert built == ["auto", "cpu"] and progress[0] == 0


def test_other_model_errors_are_not_hidden_by_the_fallback(monkeypatch):
    import numpy

    monkeypatch.setattr(tr, "ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(tr, "decode_audio", lambda path, ffmpeg: numpy.zeros(10, numpy.float32))

    class Broken:
        def transcribe(self, audio, vad_filter):
            raise ValueError("bad input")

    built = []
    transcribe = tr.whisper_transcriber("tiny", model_factory=lambda device: built.append(device) or Broken())
    with pytest.raises(ValueError, match="bad input"):
        transcribe("a.wav", lambda p: None, lambda: False)
    assert built == ["auto"]
    assert tr.is_gpu_runtime_error(OSError("cudnn_ops64_9.dll missing"))
    assert not tr.is_gpu_runtime_error(RuntimeError("out of memory"))


# ── Automatic transcription of new downloads ──
def test_site_subtitles_follow_the_preferred_languages(tmp_path):
    media = tmp_path / "Talk [x].mp4"
    media.write_bytes(b"x")
    for name in ("Talk [x].en.srt", "Talk [x].zh-Hans.srt", "Talk [x].transcript.srt", "Talk [x].en.vtt",
                 "Other.en.srt"):
        (tmp_path / name).write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    assert tr.site_subtitles(media, ["zh-Hans", "en"]) == (tmp_path / "Talk [x].zh-Hans.srt", "zh-Hans")
    assert tr.site_subtitles(media, ["ja"]) == (tmp_path / "Talk [x].en.srt", "en")
    lonely = tmp_path / "Lonely.mp4"
    lonely.write_bytes(b"x")
    assert tr.site_subtitles(lonely, ["en"]) is None


def test_automation_settings_are_validated(media_dir):
    m, _, _ = manager(media_dir, lambda *a: ([], "en"))
    assert m.status()["auto"] is False and m.status()["reuse_subtitles"] is True
    m.set_automation(True, False)
    assert m.status()["auto"] is True and m.status()["reuse_subtitles"] is False
    with pytest.raises(ValueError):
        m.set_automation("yes", True)


@pytest.fixture
def auto_app(monkeypatch):
    root = webui.ROOT  # the shared isolated fixture already points ROOT and CONFIG_DIR at temp folders
    loader, loaded = fake_loader(lambda path, progress, cancelled: ([(0, 1, "recognized")], "en"))
    worker = tr.TranscriptionManager(lambda relative: root / relative, loader=loader, is_available=lambda: True)
    monkeypatch.setattr(webui, "TRANSCRIBER", worker)
    return root, worker


def test_new_downloads_use_site_subtitles_or_queue_recognition(auto_app):
    root, worker = auto_app
    for name in ("with subs.mp4", "no subs.mp3", "photo.jpg"):
        (root / name).write_bytes(b"x")
    (root / "with subs.zh-Hans.srt").write_text("1\n00:00:02,000 --> 00:00:03,500\n站点字幕\n", encoding="utf-8")
    (root / "Talk chapters").mkdir()
    (root / "Talk chapters" / "01. Intro.mp4").write_bytes(b"x")
    lines = []
    worker.set_automation(False, True)
    webui.auto_transcribe(["with subs.mp4"], {"sub_langs": "zh-Hans,en"}, lines.append)
    assert lines == [] and not (root / "with subs.transcript.srt").exists()  # off: nothing happens
    worker.set_automation(True, True)
    webui.auto_transcribe(["with subs.mp4", "no subs.mp3", "photo.jpg", "Talk chapters/01. Intro.mp4"],
                          {"sub_langs": "zh-Hans,en"}, lines.append)
    assert tr.parse_srt((root / "with subs.transcript.srt").read_text(encoding="utf-8")) == [(2.0, 3.5, "站点字幕")]
    items = worker.status()["items"]
    assert items["with subs.mp4"]["source"] == "subtitles" and items["with subs.mp4"]["language"] == "zh-Hans"
    assert items["no subs.mp3"]["status"] == "queued" and set(items) == {"with subs.mp4", "no subs.mp3"}
    assert any("site's zh-Hans subtitles" in line for line in lines)
    assert any("Queued 1 file" in line for line in lines)


def test_without_reuse_every_new_download_is_recognized(auto_app):
    root, worker = auto_app
    (root / "with subs.mp4").write_bytes(b"x")
    (root / "with subs.en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nsite\n", encoding="utf-8")
    worker.set_automation(True, False)
    webui.auto_transcribe(["with subs.mp4"], {}, lambda line: None)
    assert worker.status()["items"]["with subs.mp4"]["status"] == "queued"


def test_without_the_optional_package_only_subtitles_are_imported(auto_app, monkeypatch):
    root, worker = auto_app
    worker.is_available = lambda: False
    (root / "a.mp4").write_bytes(b"x")
    (root / "a.en.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nsite\n", encoding="utf-8")
    (root / "b.mp4").write_bytes(b"x")
    worker.set_automation(True, True)
    webui.auto_transcribe(["a.mp4", "b.mp4"], {}, lambda line: None)
    assert (root / "a.transcript.srt").is_file() and "b.mp4" not in worker.status()["items"]


def test_automation_settings_persist_with_the_model(auto_app):
    root, worker = auto_app
    webui.save_transcription_model("base")
    webui.save_transcription_automation(True, False)
    saved = json.loads((webui.CONFIG_DIR / "transcription.json").read_text(encoding="utf-8"))
    assert saved == {"model": "base", "auto": True, "reuse_subtitles": False}
    worker.set_automation(False, True)
    webui.load_transcription_model()
    assert worker.status()["auto"] is True and worker.status()["reuse_subtitles"] is False
