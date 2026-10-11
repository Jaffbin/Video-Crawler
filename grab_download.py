"""Track structured extractor failures without parsing site-specific log messages."""

from __future__ import annotations

import contextlib
import copy
import re

from yt_dlp.utils import DownloadCancelled, DownloadError

from grab_models import http_url

RETRY_DELAYS = (2, 5)


def transient_network_error(message: str) -> bool:
    text = str(message).lower()
    if re.search(r"winerror\s+(?:5|32|4551)\b", text) or any(
        word in text for word in ("certificate", "permission", "ffmpeg", "cookies", "sign in", "login")
    ):
        return False
    return bool(re.search(r"http(?: error)?[ :]+(?:408|429|500|502|503|504)\b|\d+ bytes read, \d+ more expected", text)) or any(
        word in text for word in ("timed out", "timeout", "connection reset", "connection aborted",
                                 "connection closed", "remote end closed", "network is unreachable",
                                 "temporary failure in name resolution", "incompleteread", "incomplete read"))


def tracking_downloader(base, job):
    class TrackingDownloader(base):
        context = None
        testing_formats = False

        def _check_formats(self, *args, **kwargs):
            iterator = super()._check_formats(*args, **kwargs)
            try:
                while True:
                    previous = self.testing_formats
                    self.testing_formats = True
                    try:
                        value = next(iterator)
                    except StopIteration:
                        return
                    finally:
                        self.testing_formats = previous
                    # A lazy consumer can download while this generator is suspended.
                    yield value
            finally:
                iterator.close()

        @contextlib.contextmanager
        def item_context(self, info):
            previous = self.context
            self.context = {**(previous or {}), **info}
            try:
                yield
            finally:
                self.context = previous

        def extract_info(self, url, *args, **kwargs):
            extra = kwargs.get("extra_info") or {}
            with self.item_context({**extra, "webpage_url": url}):
                return self.extract_with_retry(url, *args, **kwargs)

        def extract_with_retry(self, url, *args, **kwargs):
            # Retry the leaf entry, preserving playlist context and completed sibling entries.
            exhausted = getattr(self, "retry_exhausted", set())
            self.retry_exhausted = exhausted
            for attempt in range(len(RETRY_DELAYS) + 1):
                previous = copy.deepcopy(job.failed_items)
                previous_error = job.error
                previous_code = getattr(self, "_download_retcode", 0)
                caught = None
                try:
                    result = super().extract_info(url, *args, **kwargs)
                except DownloadError as error:
                    caught, result = error, None
                changed = [item for item in job.failed_items if item not in previous]
                keys = {(item.get("index"), item["url"]) for item in changed}
                messages = [item["error"] for item in changed] or ([str(caught)] if caught else [])
                playlist = isinstance(result, dict) and result.get("_type") in ("playlist", "multi_video")
                can_retry = not playlist and messages and all(transient_network_error(message) for message in messages)
                if not can_retry or keys & exhausted or attempt == len(RETRY_DELAYS):
                    if can_retry:
                        exhausted.update(keys)
                    if caught:
                        raise caught
                    return result
                job.failed_items = previous
                job.error = previous_error
                self._download_retcode = previous_code
                job.stage, job.speed, job.eta = f"Reconnecting ({attempt + 1}/{len(RETRY_DELAYS)})", "", ""
                job.log.append(f"[Retry] Temporary network error; retry {attempt + 1}/{len(RETRY_DELAYS)}")
                if job.cancel.wait(RETRY_DELAYS[attempt]):
                    raise DownloadCancelled("Canceled")

        def process_ie_result(self, ie_result, download=True, extra_info=None):
            with self.item_context({**(extra_info or {}), **ie_result}):
                return super().process_ie_result(ie_result, download, extra_info)

        def report_error(self, message, *args, **kwargs):
            if self.testing_formats:
                return super().report_error(message, *args, **kwargs)
            info = self.context or {}
            index = info.get("playlist_index")
            index = index if type(index) is int and index > 0 else None
            url = http_url(info.get("webpage_url")) or job.url
            record = {"index": index, "url": url,
                      "title": str(info.get("title") or "")[:300], "error": str(message)[:600]}
            # Several format/fragment failures can belong to the same playlist item.
            for item in job.failed_items:
                if (item["index"], item["url"]) == (index, url):
                    item.update(record)
                    break
            else:
                job.failed_items.append(record)
            return super().report_error(message, *args, **kwargs)

    return TrackingDownloader
