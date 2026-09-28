from grab_models import Subscription
from grab_state import JobManager, SubscriptionManager


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
