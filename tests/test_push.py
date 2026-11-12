"""Download notifications: channel validation, request shape, secret handling and the test route."""
import http.server
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request

import pytest

import grab_push
from grab_hooks import EVENTS, HookRunner, load_config
from grab_models import Job
import webui

TOKEN = "123456789:" + "A" * 35
DISCORD = "https://discord.com/api/webhooks/42/secret-path-token"


def payload(event="download_completed", **job):
    return {"version": 1, "event": event, "files": [], "library_root": "D:\\Videos",
            "job": {"id": "j1", "url": "https://example.com/v", "title": "Clip", "status": "done", "mode": "mp4",
                    **job}}


def body(request):
    return json.loads(request.data.decode("utf-8"))


class FakeResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ── Validation ──
def test_each_channel_type_validates_and_defaults_to_every_event():
    channels = grab_push.parse_channels([
        {"type": "discord", "url": DISCORD},
        {"type": "telegram", "bot_token": TOKEN, "chat_id": 123},
        {"type": "ntfy", "url": "http://nas.local:8080/downloads", "token": "tk_abc", "events": ["download_failed"]},
        {"type": "webhook", "url": "https://example.com/hook", "headers": {"Authorization": "Bearer x"},
         "_note": "comment keys are ignored"},
    ], EVENTS)
    assert [c["type"] for c in channels] == ["discord", "telegram", "ntfy", "webhook"]
    assert channels[0]["events"] == list(EVENTS) and channels[2]["events"] == ["download_failed"]
    assert channels[3]["headers"] == {"Authorization": "Bearer x"} and "_note" not in channels[3]


@pytest.mark.parametrize("raw, message", [
    ("discord", "must be a list"),
    ([{"type": "discord", "url": DISCORD}] * 11, "up to 10"),
    ([{"type": "slack", "url": DISCORD}], "type must be one of"),
    ([{"type": "discord", "url": "http://discord.com/api/webhooks/1/x"}], "https://"),
    ([{"type": "discord", "url": "file:///etc/passwd"}], "https://"),
    ([{"type": "webhook", "url": "ftp://example.com/x"}], "http:// or https://"),
    ([{"type": "webhook", "url": "https://example.com/a b"}], "web address"),
    ([{"type": "discord", "url": DISCORD, "token": "x"}], "unknown keys for discord: token"),
    ([{"type": "telegram", "bot_token": "nope", "chat_id": 1}], "bot_token"),
    ([{"type": "telegram", "bot_token": TOKEN, "chat_id": True}], "chat_id"),
    ([{"type": "telegram", "bot_token": TOKEN}], "chat_id"),
    ([{"type": "ntfy", "url": "https://ntfy.sh/"}], "topic address"),
    ([{"type": "ntfy", "url": "https://ntfy.sh/t?x=1"}], "topic address"),
    ([{"type": "ntfy", "url": "https://ntfy.sh/t", "token": "a\nb"}], "token"),
    ([{"type": "webhook", "url": "https://e.com/h", "headers": {"Bad Name": "x"}}], "headers"),
    ([{"type": "webhook", "url": "https://e.com/h", "headers": {"X-A": "line\r\nInjected: 1"}}], "headers"),
    ([{"type": "discord", "url": DISCORD, "events": []}], "events"),
    ([{"type": "discord", "url": DISCORD, "events": ["download_started"]}], "events"),
    ([{"type": "discord", "url": DISCORD, "events": ["download_failed", "download_failed"]}], "events"),
])
def test_invalid_channels_are_rejected_with_a_specific_reason(raw, message):
    with pytest.raises(grab_push.ChannelConfigError, match=message):
        grab_push.parse_channels(raw, EVENTS)


def test_language_is_checked_and_a_broken_channel_disables_the_whole_file(tmp_path):
    with pytest.raises(grab_push.ChannelConfigError, match="language"):
        grab_push.parse_language("fr")
    path = tmp_path / "hooks.json"
    path.write_text(json.dumps({"enabled": True, "hooks": {"download_completed": {"command": ["x"]}},
                                "notifications": [{"type": "discord", "url": "http://insecure"}]}), encoding="utf-8")
    config = load_config(path)
    assert config["error"] and config["enabled"] is False and config["hooks"] == {} and config["notifications"] == []


def test_description_never_contains_a_secret():
    channels = grab_push.parse_channels([
        {"type": "discord", "url": DISCORD},
        {"type": "telegram", "bot_token": TOKEN, "chat_id": "@me"},
        {"type": "ntfy", "url": "https://ntfy.sh/private-topic", "token": "tk_secret"},
    ], EVENTS)
    described = [grab_push.describe(c) for c in channels]
    assert described[0] == {"type": "discord", "target": "discord.com", "events": list(EVENTS)}
    text = json.dumps(described)
    for secret in ("secret-path-token", TOKEN, "private-topic", "tk_secret"):
        assert secret not in text


# ── Messages and requests ──
def test_messages_follow_the_language_and_failures_include_the_error():
    assert grab_push.message("download_completed", payload(), "zh-CN") == ("下载完成", "Clip")
    title, text = grab_push.message("download_failed", payload("download_failed", error="HTTP 403"), "en")
    assert title == "Download failed" and text == "Clip\nHTTP 403"
    assert grab_push.message("download_completed", payload(title=""), "ja")[1] == "https://example.com/v"


def test_discord_never_parses_mentions_from_titles():
    channel = grab_push.parse_channels([{"type": "discord", "url": DISCORD}], EVENTS)[0]
    request = grab_push.build_request(channel, "Download complete", "@everyone " + "x" * 3000, None)
    data = body(request)
    assert request.full_url == DISCORD and request.get_method() == "POST"
    assert data["allowed_mentions"] == {"parse": []} and len(data["content"]) == 2000


def test_telegram_sends_plain_text_to_the_bot_api():
    channel = grab_push.parse_channels([{"type": "telegram", "bot_token": TOKEN, "chat_id": 99}], EVENTS)[0]
    request = grab_push.build_request(channel, "T", "B", None)
    assert request.full_url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert body(request) == {"chat_id": 99, "text": "T\nB", "disable_web_page_preview": True}


def test_ntfy_publishes_json_to_the_server_root_so_titles_stay_out_of_headers():
    channel = grab_push.parse_channels([{"type": "ntfy", "url": "https://host/ntfy/my-topic/", "token": "tk"}],
                                       EVENTS)[0]
    request = grab_push.build_request(channel, "下载完成", "片名", None)
    assert request.full_url == "https://host/ntfy/"
    assert body(request) == {"topic": "my-topic", "title": "下载完成", "message": "片名"}
    assert request.get_header("Authorization") == "Bearer tk" and request.get_header("Title") is None


def test_webhook_receives_the_full_payload_with_its_own_headers():
    channel = grab_push.parse_channels([{"type": "webhook", "url": "https://e.com/h", "headers": {"X-Key": "k"}}],
                                       EVENTS)[0]
    data = payload()
    request = grab_push.build_request(channel, "Download complete", "Clip", data)
    assert body(request) == {**data, "message": {"title": "Download complete", "body": "Clip"}}
    assert request.get_header("X-key") == "k"


# ── Sending ──
def test_send_reports_success_http_errors_and_unreachable_services_without_secrets():
    channel = grab_push.parse_channels([{"type": "telegram", "bot_token": TOKEN, "chat_id": 1}], EVENTS)[0]
    assert grab_push.send(channel, "T", "B", opener=lambda request, timeout: FakeResponse()) == ""

    def not_found(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    assert grab_push.send(channel, "T", "B", opener=not_found) == "The service answered HTTP 404."

    def leaky(request, timeout):
        raise urllib.error.URLError(f"cannot connect to {request.full_url}")

    reason = grab_push.send(channel, "T", "B", opener=leaky)
    assert reason.startswith("Could not reach the service") and TOKEN not in reason

    def slow(request, timeout):
        assert timeout == grab_push.SEND_TIMEOUT_SECONDS
        raise TimeoutError("timed out")

    assert "timed out" in grab_push.send(channel, "T", "B", opener=slow)


@pytest.fixture
def receiver():
    received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers["Content-Length"])
            received.append({"path": self.path, "headers": dict(self.headers),
                             "body": json.loads(self.rfile.read(length))})
            self.send_response(500 if self.path == "/broken" else 200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", received
    server.shutdown()
    server.server_close()


def test_a_real_webhook_request_arrives_and_a_server_error_is_reported(receiver, monkeypatch):
    # Keep any system proxy from intercepting the loopback request.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    base, received = receiver
    good, broken = grab_push.parse_channels([
        {"type": "webhook", "url": f"{base}/hook", "headers": {"Authorization": "Bearer k"}},
        {"type": "webhook", "url": f"{base}/broken"},
    ], EVENTS)
    assert grab_push.send(good, "Download complete", "Clip", payload()) == ""
    assert grab_push.send(broken, "Download complete", "Clip", payload()) == "The service answered HTTP 500."
    first = received[0]
    assert first["path"] == "/hook" and first["headers"]["Authorization"] == "Bearer k"
    assert first["body"]["job"]["title"] == "Clip" and first["body"]["message"]["title"] == "Download complete"


# ── Runner ──
def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def finished_job(tmp_path, status="done"):
    job = Job("https://example.com/v", {"mode": "mp4"})
    job.status, job.title, job.finished = status, "Clip", 1.0
    return job


def test_dispatch_queues_the_program_and_only_channels_that_want_the_event(tmp_path):
    sent, ran = [], []
    config = tmp_path / "hooks.json"
    write(config, {"enabled": True, "language": "ja",
                   "hooks": {"download_failed": {"command": ["notify.exe"]}},
                   "notifications": [{"type": "discord", "url": DISCORD},
                                     {"type": "ntfy", "url": "https://ntfy.sh/t", "events": ["download_completed"]}]})
    runner = HookRunner(lambda: config, run=lambda command, **k: ran.append(command) or
                        subprocess.CompletedProcess(command, 0),
                        opener=lambda request, timeout: sent.append(request) or FakeResponse())
    assert runner.dispatch(finished_job(tmp_path, "error"), tmp_path) is True
    assert runner.status()["pending"] == 2  # program + Discord; ntfy wants finished downloads only
    runner.start()
    try:
        deadline = time.monotonic() + 15
        while len(runner.status()["recent"]) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        runner.stop()
    recent = runner.status()["recent"]
    notification = next(item for item in recent if item["kind"] == "notification")
    assert notification == {**notification, "event": "download_failed", "target": "Discord (discord.com)",
                            "outcome": "ok", "detail": ""}
    assert body(sent[0])["content"].startswith("ダウンロード失敗")
    assert len(ran) == 1


def test_nothing_is_sent_while_turned_off(tmp_path):
    config = tmp_path / "hooks.json"
    write(config, {"enabled": False, "notifications": [{"type": "discord", "url": DISCORD}]})
    runner = HookRunner(lambda: config, opener=lambda *a, **k: pytest.fail("must not send"))
    assert runner.dispatch(finished_job(tmp_path), tmp_path) is False and runner.status()["pending"] == 0


def test_send_test_works_while_off_and_never_runs_a_program(tmp_path):
    config = tmp_path / "hooks.json"
    write(config, {"enabled": False, "language": "zh-TW",
                   "hooks": {"download_completed": {"command": ["must-not-run.exe"]}},
                   "notifications": [{"type": "discord", "url": DISCORD},
                                     {"type": "telegram", "bot_token": TOKEN, "chat_id": 1}]})
    sent = []

    def opener(request, timeout):
        sent.append(request)
        if "telegram" in request.full_url:
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)
        return FakeResponse()

    runner = HookRunner(lambda: config, run=lambda *a, **k: pytest.fail("must not run"), opener=opener)
    results = runner.send_test()
    assert results == [
        {"target": "Discord (discord.com)", "ok": True, "detail": ""},
        {"target": "Telegram (api.telegram.org)", "ok": False, "detail": "The service answered HTTP 401."},
    ]
    assert body(sent[0])["content"] == "測試通知\nVideo Grabber 的通知設定正常。"
    assert [item["event"] for item in runner.status()["recent"]] == ["test", "test"]


def test_send_test_refuses_a_broken_file(tmp_path):
    config = tmp_path / "hooks.json"
    config.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError):
        HookRunner(lambda: config).send_test()


# ── HTTP routes ──
SESSION = {"Cookie": f"{webui.SESSION_COOKIE}={webui.SESSION_SECRET}"}


@pytest.fixture
def server(tmp_path, monkeypatch):
    root = (tmp_path / "dl").resolve()
    root.mkdir()
    cfg = tmp_path / "cfg"
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", cfg)
    sent = []
    monkeypatch.setattr(webui, "HOOKS", HookRunner(lambda: cfg / "hooks.json",
                                                   opener=lambda request, timeout: sent.append(request)
                                                   or FakeResponse()))
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", cfg / "hooks.json", sent
    srv.shutdown()
    srv.server_close()


def call(base, path, headers, data=None):
    request = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json", "X-Token": webui.TOKEN, **headers})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def test_status_shows_channels_without_addresses_or_tokens(server):
    base, config, _ = server
    write(config, {"enabled": True, "language": "zh-CN", "notifications": [
        {"type": "discord", "url": DISCORD}, {"type": "telegram", "bot_token": TOKEN, "chat_id": 5}]})
    status, text = call(base, "/api/hooks", SESSION)
    assert status == 200
    data = json.loads(text)
    assert data["language"] == "zh-CN" and [c["type"] for c in data["notifications"]] == ["discord", "telegram"]
    assert "secret-path-token" not in text and TOKEN not in text


def test_test_route_needs_the_app_window_and_reports_each_channel(server):
    base, config, sent = server
    write(config, {"enabled": False, "notifications": [{"type": "discord", "url": DISCORD}]})
    assert call(base, "/api/hooks/test-notifications", {"X-Grab-Client": "extension"}, {})[0] == 403
    assert not sent
    status, text = call(base, "/api/hooks/test-notifications", SESSION, {})
    data = json.loads(text)
    assert status == 200 and data["results"] == [{"target": "Discord (discord.com)", "ok": True, "detail": ""}]
    assert data["status"]["recent"][0]["event"] == "test" and len(sent) == 1
    config.write_text("{", encoding="utf-8")
    assert call(base, "/api/hooks/test-notifications", SESSION, {})[0] == 409
