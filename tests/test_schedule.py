"""Download schedule: time windows, busy-hour speed limits, and the queue holding pending work."""
import datetime
import json
import queue
import threading
import time
import urllib.error
import urllib.request

import pytest

import grab_schedule as schedule
from grab_models import Job
from grab_state import DownloadQueue
import webui


def at(hour, minute=0):
    return datetime.datetime(2026, 11, 15, hour, minute)


NIGHT = {"enabled": True, "window": {"start": "23:00", "end": "07:00"}, "limit": None}
BUSY = {"enabled": True, "window": None, "limit": {"start": "09:00", "end": "18:00", "rate": "2m"}}


# ── Time logic ──
@pytest.mark.parametrize("now, expected", [(at(22, 59), False), (at(23), True), (at(3), True), (at(6, 59), True),
                                           (at(7), False), (at(12), False)])
def test_a_window_can_cross_midnight(now, expected):
    assert schedule.may_start(schedule.checked(NIGHT), now) is expected


def test_a_daytime_window_and_turning_the_schedule_off():
    day = schedule.checked({"enabled": True, "window": {"start": "09:30", "end": "17:00"}})
    assert schedule.may_start(day, at(9, 30)) and not schedule.may_start(day, at(17))
    assert schedule.may_start({**day, "enabled": False}, at(20))


def test_busy_hours_limit_only_inside_their_range():
    busy = schedule.checked(BUSY)
    assert busy["limit"]["rate"] == "2M"
    assert schedule.rate_limit(busy, at(10)) == "2M" and schedule.rate_limit(busy, at(18)) is None
    assert schedule.may_start(busy, at(10))  # a limit alone never holds downloads
    assert schedule.rate_limit({**busy, "enabled": False}, at(10)) is None


def test_next_start_is_today_or_tomorrow():
    night = schedule.checked(NIGHT)
    assert schedule.next_start(night, at(12)) == at(23)
    assert schedule.next_start(night, at(3)) is None
    early = schedule.checked({"enabled": True, "window": {"start": "01:00", "end": "05:00"}})
    assert schedule.next_start(early, at(12)) == at(1) + datetime.timedelta(days=1)
    view = schedule.view(night, at(12))
    assert view["holding"] is True and view["next_start"] == at(23).timestamp() and view["limit_active"] is None


@pytest.mark.parametrize("value, message", [
    ([], "Invalid download schedule"),
    ({"enabled": "yes"}, "Invalid download schedule"),
    ({"enabled": True}, "window, a speed limit, or both"),
    ({"enabled": True, "window": {"start": "7:00", "end": "08:00"}}, "HH:MM"),
    ({"enabled": True, "window": {"start": "24:00", "end": "08:00"}}, "HH:MM"),
    ({"enabled": True, "window": {"start": "08:00", "end": "08:00"}}, "must differ"),
    ({"enabled": True, "limit": {"start": "08:00", "end": "09:00", "rate": "fast"}}, "2M or 500K"),
    ({"enabled": True, "limit": {"start": "08:00", "end": "09:00", "rate": "0"}}, "2M or 500K"),
    ({"enabled": True, "window": None, "extra": 1}, "Invalid download schedule"),
])
def test_invalid_schedules_are_rejected(value, message):
    with pytest.raises(ValueError, match=message):
        schedule.checked(value)


def test_a_broken_saved_file_falls_back_to_no_schedule():
    assert schedule.load({"enabled": True, "window": {"start": "x"}}) == schedule.DEFAULT
    assert schedule.load(None) == schedule.DEFAULT
    assert schedule.load({"enabled": False, "window": None, "limit": None}) == schedule.DEFAULT


# ── Queue hold ──
def test_held_queue_keeps_jobs_waiting_and_releases_them_when_the_hold_ends():
    q = DownloadQueue()
    holding = [True]
    q.hold = lambda: holding[0]
    job = Job("https://example.com/v", {})
    q.put(job)
    with pytest.raises(queue.Empty):
        q.get(timeout=0.2)
    assert job.status == "queued"
    got = []
    worker = threading.Thread(target=lambda: got.append(q.get(timeout=10)))
    worker.start()
    time.sleep(0.1)
    holding[0] = False
    q.wake()
    worker.join(5)
    assert got == [job] and job.status == "running"


def test_a_hold_is_rechecked_without_a_wake(monkeypatch):
    monkeypatch.setattr(DownloadQueue, "HOLD_RECHECK_SECONDS", 0.05)
    q = DownloadQueue()
    deadline = time.monotonic() + 0.3
    q.hold = lambda: time.monotonic() < deadline  # the clock reaches the window by itself
    job = Job("https://example.com/v", {})
    q.put(job)
    assert q.get(timeout=5) is job


def test_manual_pause_still_wins_over_an_open_window():
    q = DownloadQueue()
    q.put(Job("https://example.com/v", {}))
    q.set_paused(True)
    with pytest.raises(queue.Empty):
        q.get(timeout=0.1)


# ── App integration ──
@pytest.fixture
def app(tmp_path, monkeypatch):
    root = (tmp_path / "dl").resolve()
    root.mkdir()
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(webui, "SCHEDULE", dict(schedule.DEFAULT))
    yield webui


def test_busy_hours_set_a_limit_only_when_the_task_has_none(app, monkeypatch):
    app.SCHEDULE.update(schedule.checked(BUSY))
    seen = []

    class Stop(Exception):
        pass

    def fake_check(name):
        raise Stop

    monkeypatch.setattr(app.grab, "media_tool_check", fake_check)
    monkeypatch.setattr(app, "downloaded_matches", lambda urls, options: [])

    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return at(10)

    monkeypatch.setattr(app.datetime, "datetime", Clock)
    original = app.make_args

    def spy(options):
        args = original(options)
        seen.append(args)
        return args

    monkeypatch.setattr(app, "make_args", spy)
    for options in ({"mode": "mp4"}, {"mode": "mp4", "limit_rate": "500K"}):
        job = Job("https://example.com/v", options)
        with pytest.raises(Stop):
            app.run_job(job)
        seen[-1].job_log = list(job.log)
    assert seen[0].limit_rate == "2M" and any("busy hours" in line for line in seen[0].job_log)
    assert seen[1].limit_rate == "500K" and not seen[1].job_log


def test_schedule_is_saved_reloaded_and_holds_the_app_queue(app, monkeypatch):
    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return at(12)

    monkeypatch.setattr(app.datetime, "datetime", Clock)
    view = app.save_schedule(NIGHT)
    assert view["holding"] is True and app.QUEUE.hold() is True
    app.SCHEDULE.clear()
    app.load_schedule()
    assert app.SCHEDULE == schedule.checked(NIGHT)
    app.save_schedule({"enabled": False, "window": NIGHT["window"], "limit": None})
    assert app.QUEUE.hold() is False and app.schedule_view()["window"] == NIGHT["window"]


@pytest.fixture
def server(app):
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


def test_routes_read_save_and_reject_a_schedule(server):
    status, body = call(server, "/api/schedule")
    assert status == 200 and body["enabled"] is False and body["holding"] is False
    status, body = call(server, "/api/schedule", {"schedule": BUSY})
    assert status == 200 and body["limit"]["rate"] == "2M"
    assert call(server, "/api/state")[1]["schedule"]["limit"]["rate"] == "2M"
    status, body = call(server, "/api/schedule", {"schedule": {"enabled": True}})
    assert status == 400 and "window" in body["error"]
