import hashlib
import json
import zipfile

import pytest

import portable_bootstrap


def test_manifest_pins_official_python_and_required_ytdlp_extras():
    manifest = portable_bootstrap.load_manifest()
    assert manifest["python"]["url"].startswith("https://www.python.org/")
    assert len(manifest["python"]["sha256"]) == 64
    package = manifest["python_packages"]["yt_dlp"]
    assert "curl-cffi" in package and "default" in package
    assert manifest["python_packages"]["desktop"].startswith("pywebview")


def test_github_asset_requires_exact_name_https_and_digest(monkeypatch):
    monkeypatch.setattr(portable_bootstrap, "_request_json", lambda url: {
        "tag_name": "v1.2.3",
        "assets": [{
            "name": "tool.zip",
            "digest": "sha256:" + "a" * 64,
            "browser_download_url": "https://github.com/example/tool/releases/download/v1.2.3/tool.zip",
        }],
    })
    asset = portable_bootstrap.github_release_asset("example/tool", "tool.zip")
    assert asset == {
        "url": "https://github.com/example/tool/releases/download/v1.2.3/tool.zip",
        "sha256": "a" * 64,
        "tag": "v1.2.3",
    }
    with pytest.raises(portable_bootstrap.BootstrapError):
        portable_bootstrap.github_release_asset("../example/tool", "tool.zip")


def test_download_rejects_wrong_hash(monkeypatch, tmp_path):
    class Response:
        headers = {"Content-Length": "4"}

        def __enter__(self): return self
        def __exit__(self, *args): pass
        def geturl(self): return "https://github.com/example/archive.zip"
        def read(self, _size):
            value, self.payload = getattr(self, "payload", b"data"), b""
            return value

    monkeypatch.setattr(portable_bootstrap.urllib.request, "urlopen", lambda *a, **k: Response())
    monkeypatch.setattr(portable_bootstrap.time, "sleep", lambda *_: None)
    target = tmp_path / "download.zip"
    with pytest.raises(portable_bootstrap.BootstrapError, match="SHA-256 mismatch"):
        portable_bootstrap._download("https://github.com/example/archive.zip", target, "0" * 64)
    assert not target.exists()


def test_download_accepts_matching_hash(monkeypatch, tmp_path):
    payload = b"portable component"

    class Response:
        headers = {"Content-Length": str(len(payload))}

        def __init__(self): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def geturl(self): return "https://github.com/example/archive.zip"
        def read(self, _size):
            value, self.payload = self.payload, b""
            return value

    monkeypatch.setattr(portable_bootstrap.urllib.request, "urlopen", lambda *a, **k: Response())
    target = tmp_path / "download.zip"
    portable_bootstrap._download(
        "https://github.com/example/archive.zip", target, hashlib.sha256(payload).hexdigest()
    )
    assert target.read_bytes() == payload


def test_safe_extract_rejects_parent_paths(tmp_path):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../escape.exe", b"bad")
    with pytest.raises(portable_bootstrap.BootstrapError, match="Unsafe path"):
        portable_bootstrap._safe_extract(archive, tmp_path / "out")
    assert not (tmp_path / "escape.exe").exists()


def test_component_record_cannot_escape_component_directory(monkeypatch, tmp_path):
    root = tmp_path / "app"
    component_dir = root / "runtime" / "components"
    component_dir.mkdir(parents=True)
    outside = root / "outside.exe"
    outside.write_bytes(b"x")
    monkeypatch.setattr(portable_bootstrap, "APP_ROOT", root)
    monkeypatch.setattr(portable_bootstrap, "COMPONENTS_DIR", component_dir)
    assert portable_bootstrap._component_executable({"executable": "outside.exe"}) is None


def test_state_write_is_valid_json(monkeypatch, tmp_path):
    state_file = tmp_path / "runtime" / "components.json"
    monkeypatch.setattr(portable_bootstrap, "STATE_FILE", state_file)
    portable_bootstrap._save_state({"schema": 1, "components": {"deno": {"version": "v1"}}})
    assert json.loads(state_file.read_text(encoding="utf-8"))["components"]["deno"]["version"] == "v1"


def test_component_installer_closes_mkstemp_handle(monkeypatch, tmp_path):
    root = tmp_path / "app"
    runtime = root / "runtime"
    components = runtime / "components"
    runtime.mkdir(parents=True)
    state_file = runtime / "components.json"
    monkeypatch.setattr(portable_bootstrap, "APP_ROOT", root)
    monkeypatch.setattr(portable_bootstrap, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(portable_bootstrap, "COMPONENTS_DIR", components)
    monkeypatch.setattr(portable_bootstrap, "STATE_FILE", state_file)
    monkeypatch.setattr(portable_bootstrap, "github_release_asset", lambda *a: {
        "url": "https://github.com/example/tool/releases/download/v1/tool.zip",
        "sha256": "a" * 64,
        "tag": "v1",
    })

    def fake_download(_url, destination, _digest):
        # Opening for write fails on Windows if the descriptor returned by mkstemp is still open.
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("bin/tool.exe", b"tool")

    monkeypatch.setattr(portable_bootstrap, "_download", fake_download)
    executable = portable_bootstrap._install_component("tool", {
        "repository": "example/tool", "asset": "tool.zip", "executable": "tool.exe",
    })
    assert executable.read_bytes() == b"tool"
    assert not list(runtime.glob("tool-*.zip"))


def test_import_probe_uses_a_fresh_isolated_python(monkeypatch):
    seen = {}

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        seen["command"] = command
        return Result()

    monkeypatch.setattr(portable_bootstrap.subprocess, "run", fake_run)
    assert portable_bootstrap._imports_available(("yt_dlp", "curl_cffi", "yt_dlp_ejs"))
    assert seen["command"][1:3] == ["-I", "-c"]
    assert "import curl_cffi" in seen["command"][-1]


def test_python_package_install_is_forced_into_portable_runtime(monkeypatch, tmp_path):
    python_dir = tmp_path / "python"
    python_dir.mkdir()
    executable = python_dir / "python.exe"
    executable.write_bytes(b"")
    checks = iter((False, True))
    seen = {}

    monkeypatch.setattr(portable_bootstrap.sys, "executable", str(executable))
    monkeypatch.setattr(portable_bootstrap, "_imports_available", lambda _names: next(checks))

    class Result:
        returncode = 0

    def fake_run(command, **kwargs):
        seen["command"] = command
        return Result()

    monkeypatch.setattr(portable_bootstrap.subprocess, "run", fake_run)
    portable_bootstrap._ensure_python_package(("yt_dlp",), "yt-dlp[curl-cffi,default]")
    command = seen["command"]
    assert "--ignore-installed" in command
    assert command[command.index("--target") + 1] == str(python_dir / "Lib" / "site-packages")


def test_portable_launcher_defaults_to_native_window():
    launcher = (portable_bootstrap.APP_ROOT / "portable_launcher.py").read_text(encoding="utf-8")
    assert 'default_args = ["--ui", "window"' in launcher
