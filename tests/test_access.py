"""The start page carries the API token, so it is only given to clients the app itself launched."""
import json
import threading
import urllib.error
import urllib.request

import pytest

import webui


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    root = (tmp_path / "dl").resolve()
    root.mkdir()
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(webui, "FILES_CACHE", {"rev": None, "ts": 0.0, "data": []})


@pytest.fixture
def server():
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def get(base, path, headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, headers=headers or {}), timeout=10) as r:
            return r.status, r.read(), r.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def post(base, path, body, headers=None):
    request = urllib.request.Request(
        base + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_start_page_without_launch_proof_never_contains_the_token(server):
    status, body, headers = get(server, "/")
    assert status == 403
    assert webui.TOKEN.encode() not in body
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers.get("Set-Cookie") is None
    assert get(server, "/?n=wrong")[0] == 403


def test_launch_link_gives_the_page_and_a_session_cookie(server):
    status, body, headers = get(server, f"/?n={webui.LAUNCH_SECRET}")
    assert status == 200 and webui.TOKEN.encode() in body
    cookie = headers["Set-Cookie"]
    assert cookie.startswith(f"{webui.SESSION_COOKIE}=") and "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert webui.LAUNCH_SECRET not in cookie
    # Reloading after the address bar dropped ?n=... keeps working through the cookie alone.
    status, body, headers = get(server, "/", {"Cookie": f"{webui.SESSION_COOKIE}={webui.SESSION_SECRET}"})
    assert status == 200 and webui.TOKEN.encode() in body
    assert get(server, "/", {"Cookie": f"{webui.SESSION_COOKIE}=stale"})[0] == 403
    assert get(server, "/", {"Cookie": "broken; ;;="})[0] == 403


def test_launch_url_points_at_the_app_and_carries_the_launch_secret():
    assert webui.launch_url(8765) == f"http://127.0.0.1:8765/?n={webui.LAUNCH_SECRET}"
    assert webui.LAUNCH_SECRET != webui.TOKEN != webui.SESSION_SECRET


def test_extension_gets_the_page_only_after_the_user_allows_it(server):
    extension = {"X-Grab-Client": "extension"}
    status, body, _ = get(server, "/", extension)
    assert status == 403 and json.loads(body) == {"error": "extension_access_off"}
    # A header alone is not enough without the setting, and the setting alone is not enough without the header.
    assert post(server, "/api/access", {"extension": True}, {"X-Token": webui.TOKEN}) == (200, {"extension": True})
    status, body, headers = get(server, "/", extension)
    assert status == 200 and webui.TOKEN.encode() in body and headers.get("Set-Cookie") is None
    assert get(server, "/")[0] == 403
    assert post(server, "/api/access", {"extension": False}, {"X-Token": webui.TOKEN})[1] == {"extension": False}
    assert get(server, "/", extension)[0] == 403


def test_access_setting_requires_the_token_and_a_boolean(server):
    assert post(server, "/api/access", {"extension": True})[0] == 401
    assert post(server, "/api/access", {"extension": "yes"}, {"X-Token": webui.TOKEN})[0] == 400
    assert get(server, "/api/access")[0] == 401
    status, body, _ = get(server, "/api/access", {"X-Token": webui.TOKEN})
    assert status == 200 and json.loads(body) == {"extension": False}
    assert not webui.extension_access_enabled()
    webui.set_extension_access(True)
    assert webui.extension_access_enabled()


def test_media_is_served_with_the_session_cookie_but_not_anonymously(server):
    (webui.ROOT / "a.mp4").write_bytes(b"0123456789")
    assert get(server, "/files/a.mp4")[0] == 401
    status, body, _ = get(server, "/files/a.mp4", {"Cookie": f"{webui.SESSION_COOKIE}={webui.SESSION_SECRET}"})
    assert status == 200 and body == b"0123456789"
    assert get(server, "/files/a.mp4", {"Cookie": f"{webui.SESSION_COOKIE}=stale"})[0] == 401
    # The cookie never opens anything outside the media library.
    (webui.ROOT / "secret.txt").write_text("x")
    assert get(server, "/files/secret.txt", {"Cookie": f"{webui.SESSION_COOKIE}={webui.SESSION_SECRET}"})[0] == 404


def test_cookie_does_not_authorize_api_calls_and_token_in_the_url_is_read_only(server):
    cookie = {"Cookie": f"{webui.SESSION_COOKIE}={webui.SESSION_SECRET}"}
    assert get(server, "/api/cookies", cookie)[0] == 401
    assert post(server, "/api/queue", {"paused": True}, cookie)[0] == 401
    assert post(server, f"/api/queue?t={webui.TOKEN}", {"paused": True})[0] == 401
    assert get(server, f"/api/cookies?t={webui.TOKEN}")[0] == 200
