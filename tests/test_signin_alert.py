"""YouTube sign-in reminder: raised when YouTube rejects the cookies a task used, cleared when fixed."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from grab_hooks import HookRunner
from grab_models import Job
import webui
from test_webui import isolated  # noqa: F401

YOUTUBE = "https://www.youtube.com/watch?v=abc"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(webui, "SIGNIN_ALERT", None)
    sent = []
    runner = HookRunner(lambda: webui.CONFIG_DIR / "hooks.json")
    runner.send_alert = lambda event, title, body: sent.append((event, title, body)) or True
    monkeypatch.setattr(webui, "HOOKS", runner)
    return sent


def finished(url=YOUTUBE, status="error", error_kind="", notes=(), **options):
    job = Job(url, {"mode": "mp4", **options})
    job.status, job.error_kind = status, error_kind
    job._note_keys = set(notes)
    return job


def test_rotated_cookies_raise_the_alert_once_and_notify_once(fresh):
    webui.update_signin_alert(finished(error_kind="cookies_expired", use_cookies_file=True))
    first = webui.SIGNIN_ALERT
    assert first and first["browser"] is False
    webui.update_signin_alert(finished(error_kind="cookies_expired", use_cookies_file=True))
    assert webui.SIGNIN_ALERT is first and len(fresh) == 1 and fresh[0][0] == "signin_expired"


def test_a_rotation_note_counts_even_when_the_download_finished():
    webui.update_signin_alert(finished(status="done", notes={"rotated"}, cookies_from_browser="firefox"))
    assert webui.SIGNIN_ALERT["browser"] is True


@pytest.mark.parametrize("job", [
    finished(error_kind="cookies_expired"),                                         # no cookies used
    finished(url="https://vimeo.com/1", error_kind="cookies_expired", use_cookies_file=True),
    finished(error_kind="network", use_cookies_file=True),                          # another failure
])
def test_unrelated_failures_do_not_raise_it(job):
    webui.update_signin_alert(job)
    assert webui.SIGNIN_ALERT is None


def test_it_clears_after_a_working_download_new_cookies_or_dismissal():
    raise_it = finished(error_kind="cookies_expired", use_cookies_file=True)
    webui.update_signin_alert(raise_it)
    webui.update_signin_alert(finished(url="https://youtu.be/abc", status="done", use_cookies_file=True))
    assert webui.SIGNIN_ALERT is None
    webui.update_signin_alert(raise_it)
    webui.save_cookies("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tPREF\tx\n")
    assert webui.SIGNIN_ALERT is None
    webui.update_signin_alert(raise_it)
    webui.delete_cookies()
    assert webui.SIGNIN_ALERT is None


def test_channels_receive_the_alert_only_if_they_take_failures(tmp_path):
    config = tmp_path / "hooks.json"
    config.write_text(json.dumps({"enabled": True, "language": "zh-CN", "notifications": [
        {"type": "webhook", "url": "https://example.com/all"},
        {"type": "webhook", "url": "https://example.com/done", "events": ["download_completed"]}]}),
        encoding="utf-8")
    sent = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    runner = HookRunner(lambda: config, opener=lambda request, timeout: sent.append(request) or Response())
    import grab_push

    assert runner.send_alert("signin_expired", *grab_push.signin_message("zh-CN")) is True
    assert runner.status()["pending"] == 1
    runner.start()
    try:
        import time
        deadline = time.monotonic() + 10
        while not runner.status()["recent"] and time.monotonic() < deadline:
            time.sleep(0.02)
    finally:
        runner.stop()
    body = json.loads(sent[0].data)
    assert sent[0].full_url == "https://example.com/all" and body["event"] == "signin_expired"
    assert body["message"]["title"] == "YouTube 登录已失效"


@pytest.fixture
def server():
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None):
    request = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-Token": webui.TOKEN})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_state_shows_the_alert_and_dismissing_clears_it(server):
    webui.update_signin_alert(finished(error_kind="cookies_expired", use_cookies_file=True))
    assert call(server, "/api/state")["signin_alert"]["browser"] is False
    assert call(server, "/api/signin-alert/dismiss", {}) == {"signin_alert": None}
    assert call(server, "/api/state")["signin_alert"] is None
