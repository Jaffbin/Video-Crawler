"""Exercise failure tracking against the real yt-dlp playlist traversal, offline."""

import yt_dlp
import pytest
import grab_download
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import ExtractorError
from yt_dlp.utils import DownloadCancelled

from grab_download import tracking_downloader
from grab_models import Job
from grab_state import JobManager


class FixtureIE(InfoExtractor):
    _VALID_URL = r"https://fixture.invalid/(?P<id>playlist|[1-3])"

    def __init__(self, *, fail=True):
        super().__init__()
        self.fail = fail
        self.visited = []

    def _real_extract(self, url):
        item_id = self._match_id(url)
        if item_id == "playlist":
            return self.playlist_result([
                self.url_result(f"https://fixture.invalid/{i}", ie=FixtureIE, video_id=str(i))
                for i in range(1, 4)
            ], "playlist", "Fixture playlist")
        self.visited.append(item_id)
        if item_id == "2" and self.fail:
            raise ExtractorError("Fixture unavailable", expected=True)
        return {"id": item_id, "title": f"Item {item_id}", "url": "http://127.0.0.1/clip.mp4", "ext": "mp4"}


def download(job, extractor):
    with tracking_downloader(yt_dlp.YoutubeDL, job)({
        "simulate": True, "quiet": True, "ignoreerrors": "only_download",
        "playlist_items": job.options.get("items"),
    }, auto_init=False) as ydl:
        ydl.add_info_extractor(extractor)
        return ydl.download([job.url])


def test_extractor_failures_record_original_index_and_retry_only_that_entry(tmp_path):
    manager = JobManager()
    job = manager.get(manager.enqueue(["https://fixture.invalid/playlist"], {"quality": "720"})[0])
    extractor = FixtureIE()
    assert download(job, extractor) != 0
    assert extractor.visited == ["1", "2", "3"]
    assert len(job.failed_items) == 1
    assert job.failed_items[0]["index"] == 2
    assert job.failed_items[0]["url"] == "https://fixture.invalid/2"
    job.status = "error"
    restored = Job.from_dict(job.to_dict(tmp_path), tmp_path)
    retry = manager.get(manager.retry(restored)[0])
    assert retry.options["items"] == "2" and retry.options["quality"] == "720"
    successful = FixtureIE(fail=False)
    assert download(retry, successful) == 0
    assert successful.visited == ["2"] and retry.failed_items == []


def test_download_failure_inside_video_context_keeps_index(tmp_path):
    job = Job("https://fixture.invalid/playlist", {})

    class FailingVideo(yt_dlp.YoutubeDL):
        def process_video_result(self, info_dict, download=True):
            if info_dict["id"] == "3":
                self.report_error("Fixture postprocessing failed")
                return info_dict
            return super().process_video_result(info_dict, download)

    with tracking_downloader(FailingVideo, job)({
        "simulate": True, "quiet": True, "ignoreerrors": "only_download",
    }, auto_init=False) as ydl:
        ydl.add_info_extractor(FixtureIE(fail=False))
        assert ydl.download([job.url]) != 0
    assert job.failed_items[0]["index"] == 3
    assert job.failed_items[0]["url"] == "https://fixture.invalid/3"


def test_format_probe_errors_are_ignored_but_download_errors_after_yield_are_tracked():
    job = Job("https://fixture.invalid/1", {})

    class Probe:
        def _check_formats(self, formats):
            self.report_error("Probe failure")
            yield {"format_id": "working"}

        def report_error(self, message):
            pass

    ydl = tracking_downloader(Probe, job)()
    formats = ydl._check_formats([])
    assert next(formats)["format_id"] == "working"
    assert not job.failed_items
    ydl.report_error("Real download failure")
    assert job.failed_items[0]["error"] == "Real download failure"
    formats.close()


def test_missing_formats_error_keeps_item_context_after_exception_unwinds():
    job = Job("https://fixture.invalid/playlist", {})

    class MissingFormat(yt_dlp.YoutubeDL):
        def process_video_result(self, info_dict, download=True):
            if info_dict["id"] == "3":
                raise ExtractorError("Requested format unavailable", expected=True)
            return super().process_video_result(info_dict, download)

    with tracking_downloader(MissingFormat, job)({
        "simulate": True, "quiet": True, "ignoreerrors": "only_download",
    }, auto_init=False) as ydl:
        ydl.add_info_extractor(FixtureIE(fail=False))
        assert ydl.download([job.url]) != 0
    assert len(job.failed_items) == 1
    assert job.failed_items[0]["index"] == 3
    assert job.failed_items[0]["url"] == "https://fixture.invalid/3"


class TemporaryFixtureIE(FixtureIE):
    @classmethod
    def ie_key(cls):
        return FixtureIE.ie_key()

    def __init__(self, failures):
        super().__init__(fail=False)
        self.failures = failures
        self.calls = []

    def _real_extract(self, url):
        item_id = self._match_id(url)
        self.calls.append(item_id)
        if item_id == "2" and self.calls.count("2") <= self.failures:
            raise ExtractorError("Connection reset by peer", expected=True)
        return super()._real_extract(url)


@pytest.mark.parametrize("failures,expected_code,attempts", [(1, 0, 2), (10, 1, 3)])
def test_transient_playlist_failure_retries_only_leaf_entry(monkeypatch, failures, expected_code, attempts):
    monkeypatch.setattr(grab_download, "RETRY_DELAYS", (0, 0))
    job = Job("https://fixture.invalid/playlist", {})
    extractor = TemporaryFixtureIE(failures)
    assert bool(download(job, extractor)) == bool(expected_code)
    assert extractor.calls.count("1") == extractor.calls.count("3") == extractor.calls.count("playlist") == 1
    assert extractor.calls.count("2") == attempts
    assert len(job.failed_items) == expected_code
    if job.failed_items:
        assert job.failed_items[0]["index"] == 2
    assert any("[Retry]" in line for line in job.log)


def test_cancel_during_retry_does_not_issue_another_request(monkeypatch):
    monkeypatch.setattr(grab_download, "RETRY_DELAYS", (0, 0))
    job = Job("https://fixture.invalid/2", {})
    extractor = TemporaryFixtureIE(10)

    def canceled_wait(seconds):
        job.cancel.set()
        return True

    monkeypatch.setattr(job.cancel, "wait", canceled_wait)
    with pytest.raises(DownloadCancelled):
        download(job, extractor)
    assert extractor.calls == ["2"]


@pytest.mark.parametrize("message", ["HTTP Error 403", "HTTP Error 404", "Sign in required", "ffmpeg timed out", "certificate verify failed", "Permission denied", "Cookies expired"])
def test_permanent_failures_are_not_automatically_retried(message):
    assert not grab_download.transient_network_error(message)


def test_windows_connection_reset_is_retryable_but_application_control_is_not():
    assert grab_download.transient_network_error("Connection reset [WinError 10054]")
    assert not grab_download.transient_network_error("Windows blocked [WinError 4551]")


def test_retry_success_does_not_erase_an_earlier_non_network_playlist_failure(monkeypatch):
    monkeypatch.setattr(grab_download, "RETRY_DELAYS", (0, 0))

    class MixedFixtureIE(TemporaryFixtureIE):
        def _real_extract(self, url):
            if self._match_id(url) == "1":
                self.calls.append("1")
                raise ExtractorError("Sign in required", expected=True)
            return super()._real_extract(url)

    job = Job("https://fixture.invalid/playlist", {})
    extractor = MixedFixtureIE(1)
    assert download(job, extractor) != 0
    assert extractor.calls.count("1") == 1 and extractor.calls.count("2") == 2
    assert len(job.failed_items) == 1 and job.failed_items[0]["index"] == 1
