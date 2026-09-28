"""Thread-safe in-memory registries for jobs and subscriptions."""

from __future__ import annotations

import queue
import threading
import time

from grab_models import Job, Subscription


class JobManager:
    def __init__(self, history_max: int = 500):
        self.history_max = history_max
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.queue: queue.Queue[Job] = queue.Queue()

    def enqueue(self, urls: list[str], options: dict, source: str = "") -> list[str]:
        created = []
        for url in urls:
            job = Job(url, options)
            job.source = source
            with self.lock:
                self.jobs[job.id] = job
            self.queue.put(job)
            created.append(job.id)
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
