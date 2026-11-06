"""Existing-file recognition uses local records and keeps original media on re-download."""
import json
import threading
from pathlib import Path

import pytest
import webui
from test_webui import isolated, call  # noqa: F401 - reuse the isolated local API setup
from conftest import HAVE_FFMPEG


@pytest.fixture
def server():
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    thread = threading.Thread(target=srv.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()
    thread.join()


def saved(name="video.mp4", url="https://www.youtube.com/watch?v=WCgcSFC1GsU", quality="720", complete=True):
    path = webui.ROOT / name
    path.write_bytes(b"original")
    record = {"source_url": url, "complete": complete, "title": "Saved video"}
    if quality is not None:
        record["download_profile"] = webui.download_profile(webui.make_args({"quality": quality}))
    webui.LIBRARY.remember({name: record})
    return path, url


def test_check_requires_auth_and_does_not_enqueue_before_a_choice(server):
    _, url = saved()
    body = {"urls": [url], "options": {"quality": "720"}, "check_existing": True}
    assert call(server, "/api/jobs", body, token=False)[0] == 401
    status, result = call(server, "/api/jobs", body)
    assert status == 200 and result["ids"] == []
    assert result["existing"][0]["settings_match"] is True
    assert not webui.JOBS


def test_skip_only_existing_links_and_keep_legacy_api_behavior(server):
    _, url = saved()
    body = {"urls": [url, "https://example.com/new"], "options": {}, "check_existing": True, "existing_action": "skip"}
    result = call(server, "/api/jobs", body)[1]
    assert result["skipped_existing"] == 1 and len(result["ids"]) == 1
    assert webui.JOBS[result["ids"][0]].url.endswith("/new")
    assert len(call(server, "/api/jobs", {"urls": [url]})[1]["ids"]) == 1


def test_matching_quality_is_preferred_and_equivalent_links_can_both_be_skipped(server):
    _, url = saved(quality="720")
    saved(name="higher.mp4", url=url, quality="1080")
    urls = [url, "https://youtu.be/WCgcSFC1GsU"]
    body = {"urls": urls, "options": {"quality": "1080"}, "check_existing": True}
    result = call(server, "/api/jobs", body)[1]
    assert len(result["existing"]) == 2
    assert all(item["path"] == "higher.mp4" and item["settings_match"] for item in result["existing"])
    result = call(server, "/api/jobs", {**body, "existing_action": "skip"})[1]
    assert result["ids"] == [] and result["skipped_existing"] == 2


def test_quality_difference_is_disclosed_and_other_formats_are_distinct():
    _, url = saved(quality="720")
    result = webui.downloaded_matches([url], {"quality": "1080"})
    assert not result[0]["settings_match"] and result[0]["profile"]["quality"] == "720"
    assert webui.downloaded_matches([url], {"mode": "mp3"}) == []
    assert webui.downloaded_matches(["https://youtu.be/WCgcSFC1GsU"], {})
    assert webui.downloaded_matches([url + "&list=PLtest"], {}) == []
    assert webui.downloaded_matches([url], {"items": "1,2"}) == []


@pytest.mark.parametrize("kind", ["missing", "incomplete", "recovery", "empty"])
def test_unusable_files_do_not_block_new_downloads(kind):
    path, url = saved(complete=kind != "incomplete")
    if kind == "missing":
        path.unlink()
    if kind == "recovery":
        webui.LIBRARY.trash(path.name)
    if kind == "empty":
        path.write_bytes(b"")
    assert webui.downloaded_matches([url], {}) == []


def test_unknown_legacy_quality_and_signed_urls_are_handled_conservatively():
    _, url = saved(url="https://cdn.example/video?variant=1", quality=None)
    result = webui.downloaded_matches([url], {})
    assert not result[0]["profile_known"]
    assert webui.downloaded_matches(["https://cdn.example/video?variant=2"], {}) == []
    assert webui.downloaded_matches(["http://["], {}) == []


def test_download_copy_is_explicit_and_disables_archive_skip(server):
    _, url = saved()
    result = call(server, "/api/jobs", {"urls": [url], "options": {"archive": True}, "check_existing": True, "existing_action": "download"})[1]
    options = webui.JOBS[result["ids"][0]].options
    assert options["_download_copy"] is True and options["archive"] is False


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg is not installed")
def test_real_re_download_creates_a_copy_without_touching_the_original(media_site):
    url = media_site["base"] + "/clip.mp4"
    original = webui.Job(url, {})
    webui.run_job(original)
    assert original.status == "done", list(original.log)
    path = Path(original.files[0])
    before, mtime = path.read_bytes(), path.stat().st_mtime_ns
    copy = webui.Job(url, {"_download_copy": True})
    webui.run_job(copy)
    assert copy.status == "done", list(copy.log)
    assert Path(copy.files[0]) != path and "copy-" + copy.id in copy.files[0]
    assert path.read_bytes() == before and path.stat().st_mtime_ns == mtime
    assert len(webui.downloaded_matches([url], {})) == 2
    assert "cookies" not in json.dumps(webui.downloaded_matches([url], {}))


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg is not installed")
def test_waiting_quality_variant_uses_a_new_file_after_another_task_finishes(media_site):
    url = media_site["base"] + "/clip.mp4"
    first = webui.Job(url, {"quality": "720"})
    later = webui.Job(url, {"quality": "1080"})
    webui.run_job(first)
    webui.run_job(later)
    assert first.status == later.status == "done"
    assert first.files[0] != later.files[0]
