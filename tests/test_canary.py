"""Canary yt-dlp updates (ADR 0010): stage, compare old and new on the same links, install only
without a regression. Fake yt_dlp packages stand in for real releases, so no network is used."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import time
import types

import pytest

import grab_canary
import webui
from test_webui import call, isolated, server  # noqa: F401 - fresh folders and a live server

FAKE_YTDLP = '''
class YoutubeDL:
    def __init__(self, options):
        if any(key in options for key in ("cookiefile", "cookiesfrombrowser", "username", "password")):
            raise RuntimeError("a probe received sign-in data")
        self.options = options
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False
    def extract_info(self, url, download=True):
        assert download is False and self.options.get("skip_download") is True
        if "{broken}" in url:
            raise RuntimeError("Unable to extract video data")
        if "playlist" in url:
            return {{"_type": "playlist", "entries": [{{"formats": [{{"url": "https://cdn.example/1.mp4"}}]}}]}}
        return {{"formats": [{{"url": "https://cdn.example/v.mp4"}}]}}
'''


def fake_release(root: Path, version: str, broken: str = "never-matches") -> Path:
    package = root / version / "yt_dlp"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(FAKE_YTDLP.format(broken=broken), encoding="utf-8")
    (package / "version.py").write_text(f"__version__ = {version!r}\n", encoding="utf-8")
    return package.parent


# ── Pure logic ──
@pytest.mark.parametrize("current, new, expected", [
    (True, True, "fine"), (False, True, "fixed"), (False, False, "inconclusive"), (True, False, "regression")])
def test_each_link_is_judged_by_comparing_both_versions(current, new, expected):
    assert grab_canary.verdict(current, new) == expected


@pytest.mark.parametrize("verdicts, expected", [
    (["fine", "fixed", "inconclusive"], "pass"),
    (["fine", "regression", "fine"], "regression"),
    (["inconclusive", "inconclusive"], "untestable"),
    ([], "untestable"),
])
def test_a_run_passes_only_without_regressions_and_with_something_conclusive(verdicts, expected):
    assert grab_canary.overall([{"verdict": item} for item in verdicts]) == expected


def test_probe_options_never_carry_sign_in_data():
    options = grab_canary.probe_options({"cookiefile": "c.txt", "cookiesfrombrowser": ("chrome",),
                                         "username": "u", "password": "p", "js_runtimes": {"deno": {}}})
    assert not {"cookiefile", "cookiesfrombrowser", "username", "password"} & set(options)
    assert options["skip_download"] is True and options["noplaylist"] is True and "js_runtimes" in options


def test_recent_sites_pick_one_successful_link_per_site():
    jobs = [types.SimpleNamespace(url=url, status=status) for url, status in [
        ("https://www.bilibili.com/video/BV1", "done"),
        ("https://www.bilibili.com/video/BV2", "done"),
        ("https://soundcloud.com/a/b", "error"),
        ("https://www.youtube.com/watch?v=x", "done"),  # already a built-in probe site
        ("https://vimeo.com/1", "done"),
        ("ftp://example.com/x", "done"),
        ("https://example.org/1", "done"),
        ("https://example.net/1", "done"),
    ]]
    probes = grab_canary.recent_probes(jobs)
    assert [item["url"] for item in probes] == ["https://www.bilibili.com/video/BV1", "https://vimeo.com/1",
                                                "https://example.org/1"]
    assert probes[0]["site"] == "bilibili.com"


# ── Child-process probes with fake releases ──
def test_a_probe_runs_the_given_release_in_a_child_process(tmp_path):
    release = fake_release(tmp_path, "2099.01.01")
    options = grab_canary.probe_options()
    assert grab_canary.run_probe("https://example.com/v", [str(release)], options) == \
        {"ok": True, "version": "2099.01.01", "error": ""}
    assert grab_canary.run_probe("https://example.com/playlist", [str(release)], options)["ok"] is True
    broken = fake_release(tmp_path, "2099.02.02", broken="example.com")
    result = grab_canary.run_probe("https://example.com/v", [str(broken)], options)
    assert result["ok"] is False and "Unable to extract" in result["error"]


def test_a_probe_that_hangs_or_cannot_start_is_a_failure_not_a_crash(tmp_path):
    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    def missing(*args, **kwargs):
        raise FileNotFoundError("python")

    assert "No answer within" in grab_canary.run_probe("https://x", [], {}, runner=hang)["error"]
    assert grab_canary.run_probe("https://x", [], {}, runner=missing)["ok"] is False


def test_compare_flags_only_links_the_new_release_breaks(tmp_path):
    current = fake_release(tmp_path, "2026.10.01", broken="dead.example")
    new = fake_release(tmp_path, "2026.11.10", broken="video.example")
    probes = [{"site": "Video", "url": "https://video.example/1"},
              {"site": "Dead", "url": "https://dead.example/1"},
              {"site": "Fine", "url": "https://fine.example/1"}]
    # Production probes the current release from the normal sys.path; here a fake stands in for it.
    def probe(url, paths, options):
        return grab_canary.run_probe(url, paths or [str(current)], options)

    seen = []
    results = grab_canary.compare(probes, new, grab_canary.probe_options(), probe=probe,
                                  progress=lambda done, total: seen.append((done, total)))
    assert [(item["site"], item["verdict"]) for item in results] == [
        ("Video", "regression"), ("Dead", "fixed"), ("Fine", "fine")]
    assert "Unable to extract" in results[0]["error"] and results[1]["error"] == ""
    assert seen[-1] == (6, 6)
    assert grab_canary.overall(results) == "regression"


# ── Update pipeline ──
@pytest.fixture
def newer_release(monkeypatch):
    monkeypatch.setattr(webui, "check_ytdlp", lambda force=False: {"latest": "2026.11.10", "newer": True})
    monkeypatch.setattr(webui, "installed_version", lambda: "2026.10.01")
    staged = []

    def pip(cmd):
        target = Path(cmd[cmd.index("--target") + 1])
        target.mkdir(parents=True)
        staged.append((target, cmd[-1]))
        return 0

    monkeypatch.setattr(webui, "_run_pip", pip)
    installed = []
    monkeypatch.setattr(webui, "_do_update", lambda extras="default", **kw: installed.append(kw.get("version")))
    return staged, installed


def results_with(*verdicts):
    return lambda probes, staging, options, **kw: [
        {"site": item["site"], "url": item["url"], "current": True, "new": verdict != "regression",
         "verdict": verdict, "error": "boom" if verdict == "regression" else ""}
        for item, verdict in zip(probes, list(verdicts) + ["fine"] * len(probes))]


def test_a_passing_release_is_installed_exactly_and_staging_is_removed(monkeypatch, newer_release):
    staged, installed = newer_release
    monkeypatch.setattr(grab_canary, "compare", results_with("fine", "fixed", "inconclusive"))
    webui._do_tested_update("default")
    assert staged[0][1] == "yt-dlp[curl-cffi,default]==2026.11.10"
    assert installed == ["2026.11.10"] and webui.UPDATE["verdict"] == "pass"
    assert not staged[0][0].exists()


def test_a_regression_keeps_the_current_version_and_quiets_that_release(monkeypatch, newer_release):
    staged, installed = newer_release
    monkeypatch.setattr(grab_canary, "compare", results_with("regression"))
    webui._do_tested_update("default")
    assert installed == [] and webui.UPDATE["status"] == "tested" and webui.UPDATE["verdict"] == "regression"
    assert webui.UPDATE["probes"][0] == {"site": "YouTube", "current": True, "new": False,
                                         "verdict": "regression", "error": "boom"}
    assert webui.skipped_ytdlp() == "2026.11.10" and not staged[0][0].exists()


def test_an_untestable_run_asks_instead_of_installing(monkeypatch, newer_release):
    _, installed = newer_release
    monkeypatch.setattr(grab_canary, "compare", results_with("inconclusive", "inconclusive", "inconclusive"))
    webui._do_tested_update("default")
    assert installed == [] and webui.UPDATE["status"] == "tested" and webui.UPDATE["verdict"] == "untestable"
    assert webui.skipped_ytdlp() == ""


def test_a_failed_download_for_testing_reports_an_error(monkeypatch, newer_release):
    _, installed = newer_release
    monkeypatch.setattr(webui, "_run_pip", lambda cmd: 1)
    webui._do_tested_update("default")
    assert installed == [] and webui.UPDATE["status"] == "error" and "for testing" in webui.UPDATE["error"]


def test_recent_sites_are_probed_only_after_opting_in(monkeypatch, newer_release):
    seen = []
    monkeypatch.setattr(grab_canary, "compare", lambda probes, *a, **kw: seen.append([p["site"] for p in probes]) or [])
    job = webui.Job("https://www.bilibili.com/video/BV1", {})
    job.status = "done"
    webui.JOBS[job.id] = job
    webui._do_tested_update("default")
    webui.set_test_recent_sites(True)
    webui._do_tested_update("default")
    assert "bilibili.com" not in seen[0] and "bilibili.com" in seen[1]


def test_nothing_newer_means_a_plain_component_install(monkeypatch):
    monkeypatch.setattr(webui, "check_ytdlp", lambda force=False: {"latest": "2026.10.01", "newer": False})
    installed = []
    monkeypatch.setattr(webui, "_do_update", lambda extras="default", **kw: installed.append((extras, kw)))
    webui._do_tested_update("default,deno")
    assert installed == [("default,deno", {})]


def test_a_skipped_release_is_no_longer_suggested(monkeypatch):
    monkeypatch.setattr(webui, "installed_version", lambda: "2026.10.01")
    monkeypatch.setattr(webui, "PYPI_CACHE", {"ts": 9e12, "latest": "2026.11.10"})
    assert webui.check_ytdlp()["newer"] is True
    webui._change_ytdlp_history(skipped="2026.11.10")
    check = webui.check_ytdlp()
    assert check["newer"] is False and check["skipped"] == "2026.11.10"
    monkeypatch.setattr(webui, "PYPI_CACHE", {"ts": 9e12, "latest": "2026.12.01"})
    assert webui.check_ytdlp()["newer"] is True


def test_routes_validate_test_settings_and_versions(server, monkeypatch):  # noqa: F811
    assert call(server, "/api/ytdlp/settings", {"test_recent_sites": "yes"})[0] == 400
    status, body = call(server, "/api/ytdlp/settings", {"test_recent_sites": True})
    assert status == 200 and body == {"test_recent_sites": True} and webui.test_recent_sites()
    assert call(server, "/api/ytdlp/settings", {"test_recent_sites": True}, token=False)[0] == 401
    status, body = call(server, "/api/ytdlp/update", {"version": "2026.11.10 --index-url=http://evil"})
    assert status == 409 and "valid yt-dlp version" in body["error"]
    assert call(server, "/api/ytdlp/update", {"version": 5})[0] == 400
    started = []
    monkeypatch.setattr(webui, "_do_tested_update", lambda extras: started.append(("tested", extras)))
    monkeypatch.setattr(webui, "_do_update", lambda extras, **kw: started.append(("install", extras, kw)))
    assert call(server, "/api/ytdlp/update", {"extras": "default", "test": True})[0] == 200
    webui.UPDATE["status"] = "idle"
    assert call(server, "/api/ytdlp/update", {"extras": "default", "version": "2026.11.10"})[0] == 200
    for _ in range(50):
        if len(started) == 2:
            break
        time.sleep(0.05)
    assert started == [("tested", "default"), ("install", "default", {"version": "2026.11.10"})]
    assert json.loads(json.dumps(webui.UPDATE))  # the status stays JSON for the Updates window


def test_a_probe_that_loaded_another_version_is_inconclusive_not_a_pass(tmp_path):
    """If the staged copy were not importable, the "new" side would quietly run the current one."""
    current = fake_release(tmp_path, "2026.10.01")
    not_staged = tmp_path / "empty-staging"
    not_staged.mkdir()

    def probe(url, paths, options):
        return grab_canary.run_probe(url, [str(current)], options)  # both sides load the current release

    results = grab_canary.compare([{"site": "Fine", "url": "https://fine.example/1"}], not_staged,
                                  grab_canary.probe_options(), expected_version="2026.11.10", probe=probe)
    assert results[0]["verdict"] == "inconclusive" and "instead of 2026.11.10" in results[0]["error"]
    assert results[0]["new_version"] == "2026.10.01"
    assert grab_canary.overall(results) == "untestable"
    same = grab_canary.compare([{"site": "Fine", "url": "https://fine.example/1"}], not_staged,
                               grab_canary.probe_options(), expected_version="2026.10.1", probe=probe)
    assert same[0]["verdict"] == "fine"  # 2026.10.01 and 2026.10.1 are the same release
