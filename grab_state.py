"""Thread-safe in-memory registries for jobs and subscriptions."""

from __future__ import annotations

import queue
import copy
import threading
import time

from grab_models import Job, Subscription


class DownloadQueue(queue.Queue):
    """Pause and reorder only pending work; claiming a job is atomic with controls."""

    def __init__(self):
        super().__init__()
        self.paused = False
        self.stopping = False

    def get(self, block=True, timeout=None):
        with self.not_empty:
            deadline = None if timeout is None else time.monotonic() + timeout
            while self.paused or not self._qsize():
                if self.stopping:
                    raise queue.Empty
                if not block:
                    raise queue.Empty
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise queue.Empty
                self.not_empty.wait(remaining)
            if self.stopping:
                raise queue.Empty
            job = self._get()
            if job.status == "queued" and not job.cancel.is_set():
                job.status, job.stage = "running", "Preparing"
            self.not_full.notify()
            return job

    def set_paused(self, paused: bool) -> None:
        with self.not_empty:
            self.paused = paused
            self.not_empty.notify_all()

    def stop(self) -> None:
        with self.not_empty:
            self.stopping = True
            self.not_empty.notify_all()

    def pending_ids(self) -> list[str]:
        with self.mutex:
            return [job.id for job in self.queue if job.status == "queued" and not job.cancel.is_set()]

    def move(self, job_id: str, direction: int) -> bool:
        with self.mutex:
            positions = [i for i, job in enumerate(self.queue) if job.status == "queued" and not job.cancel.is_set()]
            current = next((i for i, pos in enumerate(positions) if self.queue[pos].id == job_id), None)
            if current is None:
                return False
            target = current + direction
            if 0 <= target < len(positions):
                a, b = positions[current], positions[target]
                self.queue[a], self.queue[b] = self.queue[b], self.queue[a]
            return True


class JobManager:
    def __init__(self, history_max: int = 500):
        self.history_max = history_max
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.queue = DownloadQueue()

    def batch(self, ids: list[str], action: str) -> tuple[list[str], list[str]]:
        processed, skipped, retry = [], [], []
        # Workers claim under the queue mutex, so a queued cancel cannot race a claim.
        with self.queue.mutex, self.lock:
            for job_id in ids:
                job = self.jobs.get(job_id)
                if not job:
                    skipped.append(job_id)
                    continue
                if action == "cancel" and job.status in ("queued", "running"):
                    job.cancel.set()
                    if job.status == "queued":
                        job.status, job.stage, job.finished = "canceled", "Canceled", time.time()
                    else:
                        job.stage = "Canceling…"
                elif action == "retry" and job.status in ("error", "canceled"):
                    retry.append(job)
                elif action == "remove" and job.status in ("done", "error", "canceled"):
                    self.jobs.pop(job_id)
                else:
                    skipped.append(job_id)
                    continue
                if action != "retry":
                    processed.append(job_id)
        for job in retry:
            (processed if self.retry(job) else skipped).append(job.id)
        return processed, skipped

    def retry(self, job: Job) -> list[str]:
        """Keep playlist indices and output names when only some entries failed."""
        options = dict(job.options)
        failed = job.failed_items if job.status == "error" else []
        if failed and all(item.get("index") for item in failed):
            options["items"] = ",".join(str(i) for i in sorted({item["index"] for item in failed}))
            urls = [job.url]
        elif failed and all(item["url"] != job.url for item in failed):
            options.update(items="", no_playlist=True)
            urls = list(dict.fromkeys(item["url"] for item in failed))
        else:
            urls = [job.url]
        return self.enqueue(urls, options, job.source, work_key=job.work_key)

    def enqueue(self, urls: list[str], options: dict, source: str = "", *, work_key: str | None = None) -> list[str]:
        created = []
        # Keep duplicate checks, registry insertion and queue publication atomic.
        # All operations taking both locks use this order (queue, then registry).
        with self.queue.not_empty, self.lock:
            for url in urls:
                if any(job.url == url and job.options == options and job.status in ("queued", "running")
                       and not job.cancel.is_set() for job in self.jobs.values()):
                    continue
                job = Job(url, copy.deepcopy(options))
                job.source = source
                job.work_key = work_key or job.id
                self.jobs[job.id] = job
                self.queue._put(job)
                self.queue.unfinished_tasks += 1
                created.append(job.id)
            self.queue.not_empty.notify_all()
        self.prune()
        return created

    def add_restored(self, job: Job) -> None:
        with self.lock:
            self.jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def snapshot(self, *, newest_first: bool = False) -> list[Job]:
        with self.lock:
            return sorted(self.jobs.values(), key=lambda job: job.created, reverse=newest_first)

    def prune(self) -> None:
        with self.lock:
            finished = sorted(
                (job for job in self.jobs.values() if job.status in ("done", "error", "canceled")),
                key=lambda job: job.created,
            )
            for job in finished[:max(0, len(self.jobs) - self.history_max)]:
                self.jobs.pop(job.id, None)

    def remove_finished(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.status not in ("done", "error", "canceled"):
                return False
            self.jobs.pop(job_id, None)
            return True

    def clear_finished(self) -> None:
        with self.lock:
            for job_id in [
                job.id for job in self.jobs.values() if job.status in ("done", "error", "canceled")
            ]:
                self.jobs.pop(job_id, None)

    def active_count(self) -> int:
        with self.lock:
            return sum(1 for job in self.jobs.values() if job.status in ("queued", "running"))

    def reset(self) -> None:
        """Clear registry and pending queue entries; intended for a fresh runtime or tests."""
        with self.lock:
            self.jobs.clear()
        self.queue.set_paused(False)
        with self.queue.mutex:
            self.queue.stopping = False
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break
            else:
                self.queue.task_done()


class SubscriptionManager:
    def __init__(self):
        self.subscriptions: dict[str, Subscription] = {}
        self.lock = threading.Lock()
        self.checking: set[str] = set()
        self.checking_lock = threading.Lock()

    def add(self, subscription: Subscription) -> None:
        subscription.removed = False
        with self.lock:
            self.subscriptions[subscription.id] = subscription

    def get(self, subscription_id: str) -> Subscription | None:
        with self.lock:
            return self.subscriptions.get(subscription_id)

    def remove(self, subscription_id: str) -> bool:
        with self.lock:
            subscription = self.subscriptions.pop(subscription_id, None)
            if subscription is None:
                return False
            subscription.removed = True
            return True

    def snapshot(self, *, newest_first: bool = False) -> list[Subscription]:
        with self.lock:
            return sorted(
                self.subscriptions.values(),
                key=lambda subscription: subscription.created,
                reverse=newest_first,
            )

    def due(self, interval_seconds: int, now: float | None = None) -> list[Subscription]:
        current_time = time.time() if now is None else now
        with self.lock:
            return [
                subscription for subscription in self.subscriptions.values()
                if subscription.enabled and current_time - subscription.last_checked >= interval_seconds
            ]

    def begin_check(self, subscription_id: str) -> bool:
        with self.checking_lock:
            if subscription_id in self.checking:
                return False
            self.checking.add(subscription_id)
            return True

    def end_check(self, subscription_id: str) -> None:
        with self.checking_lock:
            self.checking.discard(subscription_id)

    def is_checking(self, subscription_id: str) -> bool:
        with self.checking_lock:
            return subscription_id in self.checking

    def reset(self) -> None:
        with self.lock:
            self.subscriptions.clear()
        with self.checking_lock:
            self.checking.clear()
