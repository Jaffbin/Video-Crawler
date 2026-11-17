"""Remote access: a separate opt-in listener, paired devices, narrow routes and strict request checks."""
import http.client
import json
import threading

import pytest

import grab_remote
import webui
from test_webui import isolated  # noqa: F401 - fresh folders and job list for every test

SESSION = {"Cookie": f"{webui.SESSION_COOKIE}={webui.SESSION_SECRET}"}
PAGE = {"X-Token": webui.TOKEN}
JSON = {"Content-Type": "application/json", "X-VG-Remote": "1"}


# ── Pure logic ──
def test_settings_fall_back_to_off_and_drop_invalid_values():
    assert grab_remote.settings(None) == {"enabled": False, "bind": "loopback", "port": 8766,
                                          "trusted_hosts": [], "devices": []}
    saved = grab_remote.settings({"enabled": "yes", "bind": "0.0.0.0", "port": 80,
                                  "trusted_hosts": ["ok.example.ts.net", "bad host", 5],
                                  "devices": [{"id": "xyz", "token_sha256": "0" * 64}, "junk"]})
    assert saved == {"enabled": False, "bind": "loopback", "port": 8766,
                     "trusted_hosts": ["ok.example.ts.net"], "devices": []}
    assert grab_remote.settings({"bind": "8.8.8.8"})["bind"] == "loopback"
    assert grab_remote.settings({"bind": "192.168.1.20"})["bind"] == "192.168.1.20"


@pytest.mark.parametrize("body, message", [
    ({"bind": "0.0.0.0"}, "network addresses"),
    ({"bind": "192.168.9.9"}, "network addresses"),  # private, but not one of this computer's
    ({"bind": "8.8.8.8"}, "network addresses"),
    ({"port": 80}, "1024 to 65535"),
    ({"port": "8766"}, "1024 to 65535"),
    ({"trusted_hosts": ["192.168.1.5"]}, "not a host name"),
    ({"trusted_hosts": ["*.ts.net"]}, "not a host name"),
    ({"trusted_hosts": ["a.example"] * 11}, "at most"),
    ({"folder": "C:/"}, "Unsupported fields"),
])
def test_configuration_is_validated(body, message):
    with pytest.raises(ValueError, match=message):
        grab_remote.configure(grab_remote.settings({}), body, ["192.168.1.20"])


def test_configuration_normalizes_host_names():
    saved = grab_remote.configure(grab_remote.settings({}), {"bind": "192.168.1.20", "port": 9000,
                                  "trusted_hosts": [" Box.Tailnet.ts.net. ", "", "box.tailnet.ts.net"]},
                                  ["192.168.1.20"])
    assert saved["bind"] == "192.168.1.20" and saved["port"] == 9000
    assert saved["trusted_hosts"] == ["box.tailnet.ts.net"]


@pytest.mark.parametrize("bind, host, allowed", [
    ("loopback", "127.0.0.1:8766", True),
    ("loopback", "localhost", True),
    ("loopback", "box.tailnet.ts.net", True),
    ("loopback", "evil.example", False),
    ("loopback", "192.168.1.20:8766", False),
    ("192.168.1.20", "192.168.1.20:8766", True),
    ("192.168.1.20", "127.0.0.1:8766", False),
    ("192.168.1.20", "box.tailnet.ts.net", True),
    ("192.168.1.20", "box.tailnet.ts.net.evil.example", False),
    ("192.168.1.20", "", False),
    ("192.168.1.20", "192.168.1.20 evil", False),
])
def test_host_names_must_be_the_bound_address_or_trusted(bind, host, allowed):
    saved = {"bind": bind, "trusted_hosts": ["box.tailnet.ts.net"]}
    assert grab_remote.host_allowed(host, saved) is allowed


@pytest.mark.parametrize("bind, client, allowed", [
    ("loopback", "127.0.0.1", True),
    ("loopback", "192.168.1.5", False),
    ("192.168.1.20", "192.168.1.5", True),
    ("192.168.1.20", "10.0.0.8", True),
    ("192.168.1.20", "100.101.102.103", True),  # Tailscale
    ("192.168.1.20", "fe80::1", True),
    ("192.168.1.20", "8.8.8.8", False),  # e.g. through a router port forward
    ("192.168.1.20", "not-an-ip", False),
])
def test_lan_clients_must_come_from_a_private_network(bind, client, allowed):
    assert grab_remote.client_allowed(client, {"bind": bind}) is allowed


def test_pairing_codes_are_single_use_short_lived_and_limited():
    now = [1000.0]
    pairing = grab_remote.Pairing(clock=lambda: now[0])
    assert pairing.redeem("ABCD-EFGH") is False  # no code yet
    code = pairing.new_code()["code"]
    assert len(code) == 9 and code[4] == "-" and all(c in grab_remote.CODE_ALPHABET for c in code.replace("-", ""))
    assert pairing.redeem(code.lower().replace("-", " ")) is True  # forgiving about case and separators
    assert pairing.redeem(code) is False  # single use
    code = pairing.new_code()["code"]
    now[0] += grab_remote.CODE_TTL_SECONDS
    assert pairing.active() is None and pairing.redeem(code) is False  # expired
    code = pairing.new_code()["code"]
    for _ in range(grab_remote.CODE_MAX_FAILURES):
        assert pairing.redeem("WRONG-CODE") is False
    assert pairing.redeem(code) is False and pairing.active() is None  # discarded after too many tries


def test_device_tokens_are_stored_only_as_hashes():
    token, device = grab_remote.new_device("  My\x00 phone  ", [], 5.0)
    assert token.startswith("vgd_") and token not in json.dumps(device)
    assert device["name"] == "My phone" and device["token_sha256"] == grab_remote.hash_token(token)
    assert grab_remote.find_device(token, [device]) is device
    assert grab_remote.find_device("vgd_other", [device]) is None
    assert grab_remote.find_device(webui.TOKEN, [device]) is None
    full = [grab_remote.new_device("x", [], 0)[1] for _ in range(grab_remote.MAX_DEVICES)]
    with pytest.raises(ValueError, match="At most"):
        grab_remote.new_device("one more", full, 0)


def test_library_pages_carry_only_safe_fields():
    files = [{"name": f"{i}.mp4", "path": f"a/{i}.mp4", "title": f"Clip {i}", "kind": "video", "size": i,
              "downloaded": i, "thumbnail": "", "source": "example.com", "source_url": "https://secret",
              "notes": "private", "tags": ["x"], "complete": True} for i in range(5)]
    files.append({**files[0], "name": "partial.mp4", "complete": False})
    page = grab_remote.library_page(files, "clip", "video", 1, 2)
    assert page["total"] == 5 and page["offset"] == 1 and [i["name"] for i in page["items"]] == ["1.mp4", "2.mp4"]
    assert set(page["items"][0]) == set(grab_remote.LIBRARY_FIELDS)
    assert grab_remote.library_page(files, kind="audio")["total"] == 0
    assert grab_remote.library_page(files, limit=1000)["items"].__len__() == 5


# ── Live listeners ──
@pytest.fixture
def main_server():
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_port
    srv.shutdown()
    srv.server_close()
    webui.REMOTE.stop()
    webui.REMOTE_PAIRING.clear()


def request(port, method, path, body=None, headers=None, host=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    data = json.dumps(body).encode() if body is not None else None
    connection.request(method, path, body=data, headers={"Host": host or f"127.0.0.1:{port}", **(headers or {})})
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    try:
        parsed = json.loads(raw) if raw else {}
    except ValueError:
        parsed = raw
    return response.status, parsed, response


def manage(port, body=None):
    if body is None:
        return request(port, "GET", "/api/remote-access", headers={**PAGE, **SESSION})
    return request(port, "POST", "/api/remote-access", body,
                   {**PAGE, **SESSION, "Content-Type": "application/json"})


def turn_on(main_port, monkeypatch):
    """Enable remote access on a free port and return it."""
    original = webui.RemoteListener.apply
    monkeypatch.setattr(webui.RemoteListener, "apply", lambda self, saved, port=None: original(self, saved, port=0))
    status, view, _ = manage(main_port, {"action": "enable"})
    assert status == 200 and view["enabled"] and view["running"], view
    return webui.REMOTE.port


def pair(main_port, remote_port, name="Test phone"):
    code = manage(main_port, {"action": "new_code"})[1]["pairing"]["code"]
    status, body, response = request(remote_port, "POST", "/pair", {"code": code, "name": name}, JSON)
    assert status == 200 and body == {"device": name}
    cookie = response.getheader("Set-Cookie")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    return {"Cookie": cookie.split(";")[0]}


def test_remote_access_is_off_and_only_the_app_window_can_manage_it(main_server):
    status, view, _ = manage(main_server)
    assert status == 200 and view["enabled"] is False and view["running"] is False and view["devices"] == []
    extension = {**PAGE, "X-Grab-Client": "extension"}
    assert request(main_server, "GET", "/api/remote-access", headers=extension)[0] == 403
    assert request(main_server, "POST", "/api/remote-access", {"action": "enable"},
                   {**extension, "Content-Type": "application/json"})[0] == 403
    assert request(main_server, "GET", "/api/remote-access", headers=SESSION)[0] == 401  # no page token
    assert manage(main_server, {"action": "new_code"})[0] == 400  # not on yet
    assert not (webui.CONFIG_DIR / "remote.json").exists()


def test_pair_a_phone_then_use_only_the_narrow_routes(main_server, monkeypatch):
    remote = turn_on(main_server, monkeypatch)
    status, page, response = request(remote, "GET", "/")
    assert status == 200 and "default-src 'self'" in response.getheader("Content-Security-Policy")
    assert request(remote, "GET", "/api/jobs")[0] == 401
    phone = pair(main_server, remote)
    stored = (webui.CONFIG_DIR / "remote.json").read_text(encoding="utf-8")
    assert phone["Cookie"].split("=", 1)[1] not in stored

    assert request(remote, "GET", "/api/me", headers=phone)[1] == {"device": "Test phone"}
    status, body, _ = request(remote, "POST", "/api/downloads", {"urls": ["https://example.com/a"], "mode": "mp3"},
                              {**JSON, **phone})
    assert status == 202 and len(body["ids"]) == 1
    job_id = body["ids"][0]
    jobs = request(remote, "GET", "/api/jobs", headers=phone)[1]
    assert jobs["jobs"][0]["id"] == job_id and jobs["jobs"][0]["status"] == "queued"
    assert request(remote, "POST", f"/api/jobs/{job_id}/cancel", {}, {**JSON, **phone})[0] == 200
    assert webui.JOB_MANAGER.get(job_id).status == "canceled"
    assert request(remote, "POST", f"/api/jobs/{job_id}/retry", {}, {**JSON, **phone})[0] == 200

    (webui.ROOT / "clip.mp4").write_bytes(b"video-bytes")
    library = request(remote, "GET", "/api/library?q=clip", headers=phone)[1]
    assert library["total"] == 1 and library["items"][0]["path"] == "clip.mp4"
    status, data, _ = request(remote, "GET", "/files/clip.mp4", headers=phone)
    assert status == 200 and data == b"video-bytes"
    assert request(remote, "GET", "/files/clip.mp4")[0] == 401

    # Main-server routes, page token and settings do not exist on the remote listener.
    both = {**PAGE, "Cookie": phone["Cookie"] + "; " + SESSION["Cookie"]}
    for path in ("/api/state", "/api/remote-access", "/api/automation-api", "/api/v1/status", "/api/hooks"):
        assert request(remote, "GET", path, headers=both)[0] == 404
    for path in ("/api/library/trash", "/api/jobs", "/api/remote-access", "/api/settings"):
        assert request(remote, "POST", path, {"action": "enable"}, {**JSON, **both})[0] == 404


def test_cross_site_and_malformed_posts_are_refused(main_server, monkeypatch):
    remote = turn_on(main_server, monkeypatch)
    phone = pair(main_server, remote)
    body = {"urls": ["https://example.com/a"]}
    assert request(remote, "POST", "/api/downloads", body, {"Content-Type": "application/json", **phone})[0] == 403
    assert request(remote, "POST", "/api/downloads", body, {"X-VG-Remote": "1", "Content-Type": "text/plain",
                                                             **phone})[0] == 403
    assert request(remote, "POST", "/api/downloads", body, {**JSON, **phone, "Origin": "http://evil.example"})[0] == 403
    assert request(remote, "POST", "/api/downloads", body,
                   {**JSON, **phone, "Origin": f"http://127.0.0.1:{remote}"})[0] == 202
    assert request(remote, "GET", "/api/jobs", headers=phone, host="evil.example")[0] == 403  # DNS rebinding
    assert webui.JOB_MANAGER.snapshot().__len__() == 1


def test_wrong_codes_discard_the_code_and_full_device_lists_are_refused(main_server, monkeypatch):
    remote = turn_on(main_server, monkeypatch)
    code = manage(main_server, {"action": "new_code"})[1]["pairing"]["code"]
    for _ in range(grab_remote.CODE_MAX_FAILURES):
        assert request(remote, "POST", "/pair", {"code": "AAAA-AAAA"}, JSON)[0] == 403
    assert request(remote, "POST", "/pair", {"code": code}, JSON)[0] == 403
    saved = webui.remote_settings()
    saved["devices"] = [grab_remote.new_device("x", [], 0)[1] for _ in range(grab_remote.MAX_DEVICES)]
    webui.save_remote_settings(saved)
    code = manage(main_server, {"action": "new_code"})[1]["pairing"]["code"]
    assert request(remote, "POST", "/pair", {"code": code}, JSON)[0] == 409


def test_revoking_or_forgetting_a_device_ends_its_access(main_server, monkeypatch):
    remote = turn_on(main_server, monkeypatch)
    first, second = pair(main_server, remote, "First"), pair(main_server, remote, "Second")
    view = manage(main_server)[1]
    assert [d["name"] for d in view["devices"]] == ["First", "Second"]
    assert all("token_sha256" not in d for d in view["devices"])
    manage(main_server, {"action": "revoke", "device": view["devices"][0]["id"]})
    assert request(remote, "GET", "/api/me", headers=first)[0] == 401
    status, _, response = request(remote, "POST", "/api/forget", {}, {**JSON, **second})
    assert status == 200 and "Max-Age=0" in response.getheader("Set-Cookie")
    assert request(remote, "GET", "/api/me", headers=second)[0] == 401
    assert manage(main_server)[1]["devices"] == []


def test_turning_off_stops_the_listener_and_configure_restarts_it(main_server, monkeypatch):
    remote = turn_on(main_server, monkeypatch)
    status, view, _ = manage(main_server, {"action": "configure", "trusted_hosts": ["box.tailnet.ts.net"]})
    assert status == 200 and view["running"] and view["urls"] == ["https://box.tailnet.ts.net/"]
    remote = webui.REMOTE.port
    assert request(remote, "GET", "/", host="box.tailnet.ts.net")[0] == 200
    assert manage(main_server, {"action": "configure", "bind": "0.0.0.0"})[0] == 400
    manage(main_server, {"action": "disable"})
    assert webui.REMOTE.running is False
    with pytest.raises(OSError):
        request(remote, "GET", "/")


def test_a_lan_bind_checks_the_host_against_that_address(monkeypatch):
    """Bound to a LAN address, the listener accepts that address as Host and nothing else."""
    saved = grab_remote.settings({"enabled": True, "bind": "192.168.1.20"})
    monkeypatch.setattr(webui, "remote_settings", lambda: saved)
    srv = webui.Server(("127.0.0.1", 0), webui.RemoteHandler)  # loopback socket, LAN settings
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        port = srv.server_port
        assert request(port, "GET", "/", host="192.168.1.20:8766")[0] == 200
        assert request(port, "GET", "/", host=f"127.0.0.1:{port}")[0] == 403
    finally:
        srv.shutdown()
        srv.server_close()


def test_a_missing_address_or_busy_port_is_reported_not_raised(main_server):
    webui.REMOTE.apply(grab_remote.settings({"enabled": True, "bind": "192.168.250.250"}))
    assert webui.REMOTE.running is False and webui.REMOTE.error == "address_missing"
    blocker = webui.Server(("127.0.0.1", 0), webui.Handler)
    try:
        webui.REMOTE.apply(grab_remote.settings({"enabled": True, "port": blocker.server_port}))
        assert webui.REMOTE.running is False and webui.REMOTE.error == "port_busy"
    finally:
        blocker.server_close()


def test_the_phone_page_never_inserts_site_text_as_html():
    """Titles and errors come from websites; the page must only use textContent."""
    import webui_remote_page

    script = webui_remote_page.JS
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "setAttribute('style'"):
        assert unsafe not in script
    assert "'style'" not in script  # the CSP blocks style attributes
    assert "<script>" not in webui_remote_page.HTML.replace('<script src="/remote.js"></script>', "")
