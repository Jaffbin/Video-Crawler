"""MCP server: a thin, loopback-only client of /api/v1 that exposes three tools."""
import urllib.error

import pytest

import grab_mcp
import webui
from test_api import enable, server  # noqa: F401 - reuse the live API fixture
from test_webui import isolated  # noqa: F401 - fresh folders and job list for every test


# ── Configuration ──
@pytest.mark.parametrize("url", ["http://127.0.0.1:8765/api/v1", "http://localhost:9000/api/v1/",
                                 "http://[::1]:8765/api/v1", "http://127.0.0.2:8765/api/v1"])
def test_loopback_addresses_are_accepted(url):
    assert grab_mcp.check_base_url(url) == url.rstrip("/")


@pytest.mark.parametrize("url", ["https://127.0.0.1:8765/api/v1", "http://example.com/api/v1",
                                 "http://192.168.1.5:8765/api/v1", "http://user:pw@127.0.0.1/api/v1",
                                 "http://127.0.0.1.evil.example/api/v1", "http://127.0.0.1:8765/api/v1?x=1",
                                 "ftp://127.0.0.1/api/v1", ""])
def test_the_token_is_never_sent_off_this_computer(url):
    with pytest.raises(ValueError):
        grab_mcp.ApiClient(url, "vg_token")


def test_a_token_is_required():
    with pytest.raises(ValueError, match="VG_API_TOKEN"):
        grab_mcp.ApiClient(grab_mcp.DEFAULT_URL, "  ")


def test_main_explains_missing_configuration(monkeypatch, capsys):
    monkeypatch.delenv("VG_API_TOKEN", raising=False)
    assert grab_mcp.main() == 2
    assert "VG_API_TOKEN" in capsys.readouterr().err


# ── Client ──
@pytest.mark.parametrize("job_id", ["../status", "DEADBEEF", "abc", "deadbeef/x", "deadbeef0", 12345678])
def test_job_ids_are_checked_before_they_reach_a_url(job_id):
    opened = []
    client = grab_mcp.ApiClient(grab_mcp.DEFAULT_URL, "vg_token", opener=lambda *a, **k: opened.append(a))
    with pytest.raises(grab_mcp.ApiError, match="8-character"):
        client.job(job_id)
    assert opened == []


def test_an_unreachable_app_gives_an_actionable_message():
    def refuse(*args, **kwargs):
        raise urllib.error.URLError(ConnectionRefusedError())

    client = grab_mcp.ApiClient(grab_mcp.DEFAULT_URL, "vg_secret", opener=refuse)
    with pytest.raises(grab_mcp.ApiError, match="running") as error:
        client.status()
    assert "vg_secret" not in str(error.value)


def test_the_api_works_end_to_end_and_reports_its_own_errors(server):  # noqa: F811
    token = enable(server)
    client = grab_mcp.ApiClient(server + "/api/v1", token)
    queued = client.queue({"urls": ["https://example.com/a"], "mode": "mp3", "abr": 320})
    assert len(queued["ids"]) == 1 and queued["duplicates"] == 0
    assert webui.JOB_MANAGER.get(queued["ids"][0]).options["mode"] == "mp3"
    assert client.job(queued["ids"][0])["status"] == "queued"
    assert client.status()["jobs"]["queued"] == 1
    with pytest.raises(grab_mcp.ApiError, match="mode must be"):
        client.queue({"urls": ["https://example.com/a"], "mode": "exe"})
    with pytest.raises(grab_mcp.ApiError, match="No task"):
        client.job("deadbeef")
    with pytest.raises(grab_mcp.ApiError, match="valid API token"):
        grab_mcp.ApiClient(server + "/api/v1", "vg_wrong").status()
