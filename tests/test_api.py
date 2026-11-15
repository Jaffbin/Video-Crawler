"""Automation API: opt-in, its own token, a narrow set of actions, and no reach from the extension."""
import json
import threading
import urllib.error
import urllib.request

import pytest

import grab_api
import webui
from test_webui import isolated  # noqa: F401 - fresh folders and job list for every test

SESSION = {"Cookie": f"{webui.SESSION_COOKIE}={webui.SESSION_SECRET}"}
PAGE = {"X-Token": webui.TOKEN}


@pytest.fixture
def server():
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def send(base, path, body=None, headers=None, ctype="application/json"):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=data,
                                     headers={**({"Content-Type": ctype} if data is not None else {}), **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def enable(base):
    status, body = send(base, "/api/automation-api", {"action": "enable"}, {**PAGE, **SESSION})
    assert status == 200 and body["enabled"] is True
    return body["token"]


# ── Settings ──
def test_the_api_is_off_until_the_app_window_turns_it_on(server):
    assert send(server, "/api/v1/status", headers=bearer("vg_anything"))[0] == 403
    status, body = send(server, "/api/automation-api", headers={**PAGE, **SESSION})
    assert status == 200 and body == {"enabled": False, "has_token": False, "base_url": body["base_url"]}
    token = enable(server)
    assert token.startswith("vg_") and len(token) > 40
    stored = (webui.CONFIG_DIR / "api.json").read_text(encoding="utf-8")
    assert token not in stored and grab_api.hash_token(token) in stored
    status, body = send(server, "/api/automation-api", headers={**PAGE, **SESSION})
    assert body["enabled"] is True and body["has_token"] is True and "token" not in body


def test_the_extension_cannot_turn_the_api_on_or_see_its_settings(server):
    extension = {**PAGE, "X-Grab-Client": "extension"}
    assert send(server, "/api/automation-api", headers=extension)[0] == 403
    assert send(server, "/api/automation-api", {"action": "enable"}, extension)[0] == 403
    assert not (webui.CONFIG_DIR / "api.json").exists()


def test_a_new_token_replaces_the_old_one_and_disabling_blocks_everything(server):
    first = enable(server)
    status, body = send(server, "/api/automation-api", {"action": "new_token"}, {**PAGE, **SESSION})
    second = body["token"]
    assert status == 200 and second != first
    assert send(server, "/api/v1/status", headers=bearer(first))[0] == 401
    assert send(server, "/api/v1/status", headers=bearer(second))[0] == 200
    send(server, "/api/automation-api", {"action": "disable"}, {**PAGE, **SESSION})
    assert send(server, "/api/v1/status", headers=bearer(second))[0] == 403
    status, body = send(server, "/api/automation-api", {"action": "enable"}, {**PAGE, **SESSION})
    assert "token" not in body  # turning it back on keeps the existing token
    assert send(server, "/api/v1/status", headers=bearer(second))[0] == 200
    assert send(server, "/api/automation-api", {"action": "reveal"}, {**PAGE, **SESSION})[0] == 400


# ── Authentication ──
def test_only_the_api_token_authorizes_api_routes(server):
    token = enable(server)
    for headers in ({}, bearer("vg_wrong"), bearer(webui.TOKEN), PAGE, {"Authorization": token},
                    {"Authorization": f"Basic {token}"}):
        assert send(server, "/api/v1/status", headers=headers)[0] == 401
    # ...and the API token opens nothing outside /api/v1/.
    assert send(server, "/api/state", headers=bearer(token))[0] == 401
    assert send(server, "/api/v1/status", headers={**bearer(token), "Host": "evil.example"})[0] == 403


# ── Actions ──
def test_queue_downloads_with_output_choices_only(server):
    token = enable(server)
    status, body = send(server, "/api/v1/downloads", {"urls": ["https://example.com/a", "https://example.com/a",
                                                                "https://example.com/b"], "mode": "mp3", "abr": 320},
                        bearer(token))
    assert status == 202 and len(body["ids"]) == 2 and body["duplicates"] == 0
    job = webui.JOB_MANAGER.get(body["ids"][0])
    assert job.options == {"mode": "mp3", "quality": "best", "abr": 320, "no_playlist": False, "subs": False}
    status, body = send(server, "/api/v1/downloads", {"urls": "https://example.com/a", "mode": "mp3", "abr": 320},
                        bearer(token))
    assert status == 202 and body == {"ids": [], "duplicates": 1}  # already queued with the same settings


@pytest.mark.parametrize("body, message", [
    ({"urls": []}, "1 to 50"),
    ({"urls": ["ftp://example.com/a"]}, "1 to 50"),
    ({"urls": [f"https://example.com/{i}" for i in range(51)]}, "1 to 50"),
    ({"urls": ["https://example.com/a"], "cookies_from_browser": "chrome"}, "Unsupported fields"),
    ({"urls": ["https://example.com/a"], "proxy": "http://attacker:1"}, "Unsupported fields"),
    ({"urls": ["https://example.com/a"], "mode": "exe"}, "mode must be"),
    ({"urls": ["https://example.com/a"], "quality": "8k"}, "quality must be"),
    ({"urls": ["https://example.com/a"], "abr": 999}, "abr must be"),
    ({"urls": ["https://example.com/a"], "subtitles": "yes"}, "subtitles must be"),
])
def test_unsafe_or_invalid_download_requests_are_rejected(server, body, message):
    token = enable(server)
    status, response = send(server, "/api/v1/downloads", body, bearer(token))
    assert status == 400 and message in response["error"]
    assert webui.JOB_MANAGER.snapshot() == []


def test_non_json_requests_are_refused(server):
    token = enable(server)
    assert send(server, "/api/v1/downloads", {"urls": ["https://example.com/a"]}, bearer(token),
                ctype="text/plain")[0] == 415


def test_status_and_task_details(server):
    token = enable(server)
    ids = send(server, "/api/v1/downloads", {"urls": ["https://example.com/a"]}, bearer(token))[1]["ids"]
    status, body = send(server, "/api/v1/status", headers=bearer(token))
    assert status == 200 and body["jobs"]["queued"] == 1 and body["paused"] is False
    status, body = send(server, f"/api/v1/jobs/{ids[0]}", headers=bearer(token))
    assert status == 200 and body["id"] == ids[0] and body["status"] == "queued" and body["files"] == []
    assert send(server, "/api/v1/jobs/deadbeef", headers=bearer(token))[0] == 404
    assert send(server, "/api/v1/library", headers=bearer(token))[0] == 404


def test_a_corrupt_settings_file_keeps_the_api_off():
    assert grab_api.settings({"enabled": True, "token_sha256": "short"}) == {"enabled": False, "token_sha256": ""}
    assert grab_api.settings("garbage")["enabled"] is False
