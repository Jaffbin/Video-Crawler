import os
import subprocess
import sys
from pathlib import Path

import webui


ROOT = Path(__file__).resolve().parent.parent


def run_help(script: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(ROOT / script), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=10,
        check=False,
    )


def test_cli_entry_points_show_help():
    for script in ("grab.py", "webui.py"):
        result = run_help(script)
        assert result.returncode == 0, result.stderr
        assert "usage:" in result.stdout.lower()


def test_committed_interface_build_is_complete():
    assert webui.check_dist() == (True, "")


def test_web_config_normalizes_operational_limits(tmp_path):
    config = webui.parse_web_config([
        "--dir", str(tmp_path),
        "--workers", "99",
        "--sub-interval", "1",
        "--ui", "none",
    ])
    assert config.download_dir == tmp_path.resolve()
    assert config.workers == 6
    assert config.subscription_interval_seconds == 300
    assert config.ui == "none"
