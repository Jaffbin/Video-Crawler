"""yt-dlp plugin reporting in Diagnostics. Real plugins are never loaded: that would change
yt-dlp's global extractor table for every later test."""
import sys
import types
from pathlib import Path

import pytest
import yt_dlp.globals as registry
import yt_dlp.plugins

import grab
import grab_plugins

FOLDER = Path("C:/Users/me/AppData/Roaming/yt-dlp/plugins")


def summary(**values):
    return {"disabled": False, "modules": [], "extractors": [], "postprocessors": [], "folders": [], **values}


def test_no_plugins_is_information_with_where_to_put_one():
    row = grab_plugins.describe(summary(), FOLDER)
    assert row["id"] == "plugins" and row["status"] == "info"
    assert "works without them" in row["detail"] and str(FOLDER) in row["fix"]


def test_loaded_plugins_are_listed_with_their_folders():
    row = grab_plugins.describe(summary(modules=["extractor.getpot_bgutil_http"],
                                        folders=["C:/py/site-packages/yt_dlp_plugins"]), FOLDER)
    assert row["status"] == "ok"
    assert "Loaded 1 plugin module(s): extractor.getpot_bgutil_http." in row["detail"]
    assert "Found in: C:/py/site-packages/yt_dlp_plugins." in row["detail"]
    assert "after a restart" in row["fix"]
    assert "Post-processors" not in row["detail"]


def test_post_processor_plugins_are_named_honestly_and_long_lists_are_shortened():
    modules = [f"extractor.site{i}" for i in range(15)]
    row = grab_plugins.describe(summary(modules=modules, extractors=["SiteIE"], postprocessors=["TagPP"]), FOLDER)
    assert "and 3 more" in row["detail"] and "Site extractors: SiteIE." in row["detail"]
    assert "Video Grabber does not run post-processor plugins." in row["detail"]


def test_disabled_plugins_are_reported_without_demanding_attention():
    row = grab_plugins.describe(summary(disabled=True), FOLDER)
    assert row["status"] == "info" and "YTDLP_NO_PLUGINS" in row["detail"]


def test_collect_reads_what_yt_dlp_registered(monkeypatch):
    monkeypatch.delenv("YTDLP_NO_PLUGINS", raising=False)
    monkeypatch.setattr(registry.all_plugins_loaded, "value", True)
    monkeypatch.setattr(registry.plugin_ies, "value", {"SiteIE": object})
    monkeypatch.setattr(registry.plugin_pps, "value", {"TagPP": object})
    monkeypatch.setattr(yt_dlp.plugins, "directories", lambda: ["C:/plugins/yt_dlp_plugins"])
    monkeypatch.setattr(yt_dlp.plugins, "load_all_plugins", lambda: pytest.fail("already loaded"))
    for name in ("yt_dlp_plugins.extractor.getpot", "yt_dlp_plugins.extractor._private", "yt_dlp_plugins.extractor"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    assert grab_plugins.collect() == {
        "disabled": False, "modules": ["extractor.getpot"], "extractors": ["SiteIE"],
        "postprocessors": ["TagPP"], "folders": ["C:/plugins/yt_dlp_plugins"],
    }


def test_collect_loads_plugins_first_like_a_download_would(monkeypatch):
    monkeypatch.delenv("YTDLP_NO_PLUGINS", raising=False)
    calls = []
    monkeypatch.setattr(registry.all_plugins_loaded, "value", False)
    monkeypatch.setattr(registry.plugin_ies, "value", {})
    monkeypatch.setattr(registry.plugin_pps, "value", {})
    monkeypatch.setattr(yt_dlp.plugins, "directories", lambda: [])
    monkeypatch.setattr(yt_dlp.plugins, "load_all_plugins", lambda: calls.append(1))
    grab_plugins.collect()
    assert calls == [1]


def test_collect_respects_the_off_switch(monkeypatch):
    monkeypatch.setenv("YTDLP_NO_PLUGINS", "1")
    monkeypatch.setattr(yt_dlp.plugins, "load_all_plugins", lambda: pytest.fail("must not load"))
    assert grab_plugins.collect()["disabled"] is True


def test_a_broken_plugin_does_not_hide_the_rest_of_diagnostics(monkeypatch, tmp_path):
    def broken():
        raise ImportError("bad plugin")

    monkeypatch.setattr(grab_plugins, "collect", broken)
    checks = grab.run_diagnostics(tmp_path)
    row = next(check for check in checks if check["id"] == "plugins")
    assert row["status"] == "warn" and "bad plugin" in row["detail"]
    assert any(check["id"] == "ytdlp" for check in checks)


def test_user_folder_follows_the_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:/Users/me/AppData/Roaming")
    assert grab_plugins.user_plugin_folder() == Path("C:/Users/me/AppData/Roaming/yt-dlp/plugins")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/home/me/.config")
    assert grab_plugins.user_plugin_folder() == Path("/home/me/.config/yt-dlp/plugins")
