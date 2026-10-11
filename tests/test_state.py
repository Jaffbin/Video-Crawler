from grab_models import Subscription
from grab_state import JobManager, SubscriptionManager
import queue
import pytest
from concurrent.futures import ThreadPoolExecutor


def test_job_manager_enqueues_tracks_and_prunes_finished_jobs():
    manager = JobManager(history_max=2)
    ids = manager.enqueue(["https://example.com/1", "https://example.com/2"], {"mode": "mp4"})
    assert manager.active_count() == 2
    assert [job.id for job in manager.snapshot()] == ids

    for job in manager.snapshot():
        job.status = "done"
    third_id = manager.enqueue(["https://example.com/3"], {})[0]
    manager.get(third_id).status = "done"
    manager.prune()
    assert len(manager.snapshot()) == 2
    assert manager.get(ids[0]) is None


def test_enqueued_jobs_keep_an_options_snapshot():
    manager = JobManager()
    options = {"mode": "mp4", "quality": "1080"}
    job_id = manager.enqueue(["https://example.com/video"], options)[0]
    options["quality"] = "360"
    assert manager.get(job_id).options["quality"] == "1080"


def test_job_manager_only_removes_finished_jobs():
    manager = JobManager()
    job_id = manager.enqueue(["https://example.com/video"], {})[0]
    assert not manager.remove_finished(job_id)
    manager.get(job_id).status = "error"
    assert manager.remove_finished(job_id)
    assert manager.get(job_id) is None


def test_job_manager_reset_clears_registry_and_pending_queue():
    manager = JobManager()
    manager.enqueue(["https://example.com/video"], {})
    manager.reset()
    assert manager.snapshot() == []
    assert manager.queue.empty()


def test_subscription_manager_filters_due_items_and_guards_checks():
    manager = SubscriptionManager()
    due = Subscription("https://example.com/due", {})
    recent = Subscription("https://example.com/recent", {})
    paused = Subscription("https://example.com/paused", {})
    due.last_checked = 100
    recent.last_checked = 950
    paused.last_checked = 100
    paused.enabled = False
    for subscription in (due, recent, paused):
        manager.add(subscription)

    assert manager.due(100, now=1000) == [due]
    assert manager.begin_check(due.id)
    assert not manager.begin_check(due.id)
    assert manager.is_checking(due.id)
    manager.end_check(due.id)
    assert not manager.is_checking(due.id)


def test_paused_queue_can_reorder_and_cancel_without_claiming_jobs():
    manager = JobManager()
    ids = manager.enqueue(["https://example.com/1", "https://example.com/2", "https://example.com/3"], {})
    manager.queue.set_paused(True)
    with pytest.raises(queue.Empty):
        manager.queue.get(timeout=0.01)
    assert all(job.status == "queued" for job in manager.snapshot())
    assert manager.queue.move(ids[2], -1)
    assert manager.queue.pending_ids() == [ids[0], ids[2], ids[1]]
    assert manager.batch([ids[0]], "cancel") == ([ids[0]], [])
    assert manager.queue.pending_ids() == [ids[2], ids[1]]
    manager.queue.set_paused(False)
    canceled = manager.queue.get_nowait()
    assert canceled.status == "canceled"
    manager.queue.task_done()
    claimed = manager.queue.get_nowait()
    assert claimed.id == ids[2] and claimed.status == "running"
    manager.queue.task_done()
    assert not manager.queue.move(claimed.id, -1)


def test_batch_retry_preserves_settings_and_skips_ineligible_jobs():
    manager = JobManager()
    ids = manager.enqueue(["https://example.com/1", "https://example.com/2"], {"quality": "720"})
    manager.get(ids[0]).status = "error"
    processed, skipped = manager.batch(ids + ["deadbeef"], "retry")
    assert processed == [ids[0]] and skipped == [ids[1], "deadbeef"]
    retry = manager.snapshot()[-1]
    assert retry.url == "https://example.com/1" and retry.options == {"quality": "720"}
    manager.queue.set_paused(True)
    manager.reset()
    assert manager.queue.empty() and not manager.queue.paused


def test_concurrent_enqueue_rejects_only_matching_active_downloads():
    manager = JobManager()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: manager.enqueue(["https://example.com/video"], {"quality": "720"}), range(20)))
    assert sum(map(len, results)) == 1
    first = manager.snapshot()[0]
    assert manager.enqueue([first.url], {"quality": "1080"})
    first.status = "done"
    assert manager.enqueue([first.url], {"quality": "720"})


def test_batch_retry_deduplicates_and_preserves_source():
    manager = JobManager()
    job = manager.get(manager.enqueue(["https://example.com/list"], {}, "abcd1234")[0])
    job.status = "error"
    job.failed_items = [{"index": 8, "url": "https://example.com/8", "title": "", "error": "error"},
                        {"index": 2, "url": "https://example.com/2", "title": "", "error": "error"}]
    assert manager.batch([job.id], "retry") == ([job.id], [])
    retry = manager.snapshot()[-1]
    assert retry.options["items"] == "2,8" and retry.source == "abcd1234"
    assert retry.work_key == job.work_key
    assert manager.batch([job.id], "retry") == ([], [job.id])


def test_unindexed_child_failures_clear_parent_playlist_selection():
    manager = JobManager()
    job = manager.get(manager.enqueue(["https://example.com/page"], {"items": "2-3"})[0])
    job.status = "error"
    job.failed_items = [{"index": None, "url": "https://example.com/video", "title": "", "error": "error"}]
    retry = manager.get(manager.retry(job)[0])
    assert retry.url == "https://example.com/video"
    assert retry.options == {"items": "", "no_playlist": True}


def test_canceled_playlist_retry_keeps_unattempted_entries():
    manager = JobManager()
    job = manager.get(manager.enqueue(["https://example.com/list"], {"items": "1-10"})[0])
    job.status = "canceled"
    job.failed_items = [{"index": 2, "url": "https://example.com/2", "title": "", "error": "error"}]
    retry = manager.get(manager.retry(job)[0])
    assert retry.options["items"] == "1-10"


def test_stopping_queue_does_not_claim_or_reorder_waiting_jobs():
    manager = JobManager()
    ids = manager.enqueue(["https://example.com/1", "https://example.com/2"], {})
    manager.queue.move(ids[1], -1)
    manager.queue.stop()
    with pytest.raises(queue.Empty):
        manager.queue.get_nowait()
    assert manager.queue.pending_ids() == ids[::-1]
    manager.reset()
    assert not manager.queue.stopping
