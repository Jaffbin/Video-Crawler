"""Report which yt-dlp plugins are loaded, so people can confirm a plugin (such as a PO Token provider) works.

yt-dlp loads plugins itself the first time a ``YoutubeDL`` is created, from its plugin folders and from
packages installed in the same Python. Video Grabber does not install, update or configure plugins.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

PACKAGE = "yt_dlp_plugins"
MAX_LISTED = 12


def user_plugin_folder() -> Path:
    """The folder yt-dlp searches that a person is most likely to use."""
    if sys.platform.startswith("win") and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "yt-dlp" / "plugins"
    config = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config) / "yt-dlp" / "plugins"


def collect() -> dict:
    """Load plugins the way a download would, then list what yt-dlp registered.

    This runs plugin code, exactly as the first download or link analysis already does.
    """
    if os.environ.get("YTDLP_NO_PLUGINS"):
        return {"disabled": True, "modules": [], "extractors": [], "postprocessors": [], "folders": []}
    import yt_dlp.globals as registry
    import yt_dlp.plugins as plugins

    if not registry.all_plugins_loaded.value:
        plugins.load_all_plugins()
    # Plugin modules that only register hooks (such as PO Token providers) define no extractor class,
    # so imported module names are the dependable list of what loaded.
    modules = sorted(name[len(PACKAGE) + 1:] for name in list(sys.modules)
                     if name.startswith(PACKAGE + ".") and name.count(".") >= 2
                     and not any(part.startswith("_") for part in name.split(".")[1:]))
    return {
        "disabled": False,
        "modules": modules,
        "extractors": sorted(registry.plugin_ies.value),
        "postprocessors": sorted(registry.plugin_pps.value),
        "folders": [str(folder) for folder in plugins.directories()],
    }


def _listed(names: list[str]) -> str:
    shown = ", ".join(names[:MAX_LISTED])
    return shown + (f" and {len(names) - MAX_LISTED} more" if len(names) > MAX_LISTED else "")


def describe(summary: dict, folder: Path) -> dict:
    """Turn a summary into a Diagnostics row (id, label, status, detail, fix, action)."""
    row = {"id": "plugins", "label": "yt-dlp plugins", "action": ""}
    if summary["disabled"]:
        # Someone set this on purpose, so it is information rather than a problem to fix.
        return {**row, "status": "info", "detail": "Plugins are turned off by the YTDLP_NO_PLUGINS environment "
                "variable.", "fix": "Remove YTDLP_NO_PLUGINS and restart Video Grabber to use plugins."}
    if not summary["modules"]:
        return {**row, "status": "info", "detail": "No plugins are installed. Video Grabber works without them.",
                "fix": f"To add one, put its folder or .zip file in {folder}, or install it with pip into the "
                       "same Python, then restart Video Grabber."}
    parts = [f"Loaded {len(summary['modules'])} plugin module(s): {_listed(summary['modules'])}."]
    if summary["extractors"]:
        parts.append(f"Site extractors: {_listed(summary['extractors'])}.")
    if summary["postprocessors"]:
        parts.append(f"Post-processors: {_listed(summary['postprocessors'])}. Video Grabber does not run "
                     "post-processor plugins.")
    if summary["folders"]:
        parts.append(f"Found in: {'; '.join(summary['folders'])}.")
    return {**row, "status": "ok", "detail": " ".join(parts),
            "fix": "Plugins added or removed while Video Grabber is running take effect after a restart."}


def diagnostics_row() -> dict:
    try:
        summary = collect()
    except Exception as error:  # noqa: BLE001
        # A broken plugin must not hide the rest of Diagnostics.
        return {"id": "plugins", "label": "yt-dlp plugins", "status": "warn", "action": "",
                "detail": f"Could not list plugins: {error}",
                "fix": "Remove the plugin you added most recently, then restart Video Grabber."}
    return describe(summary, user_plugin_folder())
