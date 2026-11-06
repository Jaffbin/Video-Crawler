import types
from unittest.mock import Mock

import pytest

from grab_notifications import CompletionBatch, WindowsNotifier, completion_content


def job(key="one", status="done", finished=11, files=None, mode="mp4"):
    return {"id": key, "status": status, "finished": finished, "title": "Example", "mode": mode,
            "files": files if files is not None else [{"path": "example.mp4", "complete": True}]}


def test_fast_jobs_are_detected_but_previous_history_is_not_replayed():
    batch = CompletionBatch(started=10)
    assert batch.update([job(finished=9)]) is None
    result = batch.update([job(), job("two", finished=12)])
    assert result["ok"] == 2 and result["latest"]["id"] == "two"
    assert batch.update([job(), job("two", finished=12)]) is None
    assert batch.update([job("retry", finished=13)])["ok"] == 1


def test_batch_waits_for_paused_queued_work_and_all_workers_to_finish():
    batch = CompletionBatch(started=10)
    assert batch.update([job(), job("two", "running", 0), job("three", "queued", 0)]) is None
    assert batch.update([job(), job("two", "done", 12), job("three", "queued", 0)]) is None
    result = batch.update([job(), job("two", "done", 12), job("three", "error", 13)])
    assert (result["ok"], result["bad"]) == (2, 1)


def test_terminal_status_is_not_counted_before_worker_records_finished_time():
    batch = CompletionBatch(started=10)
    assert batch.update([job(finished=0)]) is None
    assert batch.update([job()])["ok"] == 1
    assert batch.update([job("canceled", "canceled", 12)]) is None


@pytest.mark.parametrize("locale", ["en", "zh-CN", "zh-TW", "ja"])
def test_success_has_fixed_actions_and_a_safe_media_target(locale):
    latest = job(files=[{"path": "cover.jpg"}, {"path": "fragment.mp4", "complete": False}, {"path": "final.mp4"}])
    _, _, detail, path, actions = completion_content({"ok": 1, "bad": 0, "latest": latest}, locale)
    assert detail == path == "final.mp4"
    assert [action for _, action in actions] == ["play", "folder", "queue"]


def test_multi_file_label_is_explicit_and_all_failed_only_offers_queue():
    content = completion_content({"ok": 2, "bad": 1, "latest": job()}, "en")
    assert content[1] == "Completed 2, failed 1"
    assert content[4][0] == ("Play latest file", "play")
    content = completion_content({"ok": 0, "bad": 2, "latest": None}, "en")
    assert content[3] == "" and content[4] == [("View queue", "queue")]
    content = completion_content({"ok": 1, "bad": 0, "latest": job(mode="cover", files=[{"path": "image.jpg"}])}, "en")
    assert content[4][0][0] == "Open image"
    content = completion_content({"ok": 1, "bad": 0, "latest": job(files=[{"path": "first.mp4"}, {"path": "last.mp4"}])}, "en")
    assert content[3] == "last.mp4" and content[4][0][0] == "Play latest file"


def test_native_toast_callbacks_are_bound_to_original_target_and_whitelisted():
    class Toast:
        def __init__(self, text, **kwargs):
            self.text_fields, self.actions = text, []

        def AddAction(self, action):
            self.actions.append(action)

    notifier = WindowsNotifier.__new__(WindowsNotifier)
    notifier.Toast, notifier.Button = Toast, lambda label, action: (label, action)
    notifier.toaster = Mock()
    activate, failed = Mock(), Mock()
    notifier.show({"ok": 1, "bad": 0, "latest": job()}, "en", activate, failed)
    first = notifier.toast
    notifier.show({"ok": 1, "bad": 0, "latest": job(files=[{"path": "later.mp4"}])}, "en", activate, failed)
    first.on_activated(types.SimpleNamespace(arguments="play"))
    activate.assert_called_with("play", "example.mp4")
    first.on_activated(types.SimpleNamespace(arguments="https://untrusted.invalid"))
    activate.assert_called_with("queue", "example.mp4")
    first.on_failed(None)
    failed.assert_called_once()
    assert first.tag == "completion" and len(first.actions) == 3


def test_winrt_objects_are_released_before_the_apartment_is_closed():
    import weakref
    class Toaster:
        def clear_toasts(self):
            pass

    notifier = WindowsNotifier.__new__(WindowsNotifier)
    # Mock's parent/child call tracking introduces cycles that real WinRT handles do not have.
    notifier.toaster = Toaster()
    reference = weakref.ref(notifier.toaster)
    notifier.toast = Mock()
    observed = []
    notifier._uninit = lambda: observed.append(reference() is None)
    notifier.close()
    notifier.close()
    assert observed == [True] and notifier.toast is None
