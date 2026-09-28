"""Secure first-run component bootstrap for the Windows Portable ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import site
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = APP_ROOT / "runtime"
COMPONENTS_DIR = RUNTIME_DIR / "components"
STATE_FILE = RUNTIME_DIR / "components.json"
MANIFEST_FILE = APP_ROOT / "portable_manifest.json"
USER_AGENT = "Video-Grabber-Portable/1.0"
MAX_ARCHIVE_BYTES = 750 * 1024 * 1024
MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024


class BootstrapError(RuntimeError):
    pass


def load_manifest(path: Path = MANIFEST_FILE) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BootstrapError(f"Cannot read portable manifest: {exc}") from exc
    if data.get("schema") != 1 or data.get("platform") != "windows-x64":
        raise BootstrapError("Unsupported portable manifest")
    return data


def _load_state() -> dict:
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": 1, "components": {}}
    return data if isinstance(data, dict) and isinstance(data.get("components"), dict) else {
        "schema": 1, "components": {}
    }


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_FILE.with_name(f".{STATE_FILE.name}.{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, STATE_FILE)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _request_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.geturl().split(":", 1)[0].lower() != "https":
            raise BootstrapError("Release metadata was redirected away from HTTPS")
        return json.load(response)


def github_release_asset(repository: str, asset_name: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise BootstrapError("Invalid GitHub repository in portable manifest")
    release = _request_json(f"https://api.github.com/repos/{repository}/releases/latest")
    matches = [asset for asset in release.get("assets", []) if asset.get("name") == asset_name]
    if len(matches) != 1:
        raise BootstrapError(f"Release asset not found: {repository}/{asset_name}")
    asset = matches[0]
    digest = str(asset.get("digest") or "")
    url = str(asset.get("browser_download_url") or "")
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise BootstrapError(f"GitHub did not provide a SHA-256 digest for {asset_name}")
    if not url.startswith(f"https://github.com/{repository}/releases/download/"):
        raise BootstrapError(f"Unexpected release URL for {asset_name}")
    return {"url": url, "sha256": digest.split(":", 1)[1].lower(), "tag": str(release.get("tag_name") or "latest")}


def _download(url: str, destination: Path, expected_sha256: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=45) as response, destination.open("wb") as output:
                final_url = response.geturl()
                if not final_url.startswith("https://"):
                    raise BootstrapError("Component download was redirected away from HTTPS")
                length = int(response.headers.get("Content-Length") or 0)
                if length > MAX_ARCHIVE_BYTES:
                    raise BootstrapError("Component archive is unexpectedly large")
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ARCHIVE_BYTES:
                        raise BootstrapError("Component archive exceeded the size limit")
                    output.write(chunk)
            actual = _sha256(destination)
            if actual != expected_sha256.lower():
                raise BootstrapError(f"SHA-256 mismatch (expected {expected_sha256}, got {actual})")
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            destination.unlink(missing_ok=True)
            if attempt < 3:
                time.sleep(attempt)
    raise BootstrapError(f"Download failed after 3 attempts: {last_error}") from last_error


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    total = 0
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            path = Path(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise BootstrapError(f"Unsafe path in component archive: {member.filename}")
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise BootstrapError(f"Symbolic links are not allowed in component archives: {member.filename}")
            total += member.file_size
            if total > MAX_UNPACKED_BYTES:
                raise BootstrapError("Unpacked component exceeded the size limit")
        source.extractall(destination)


def _component_executable(record: dict) -> Path | None:
    relative = record.get("executable") if isinstance(record, dict) else None
    if not isinstance(relative, str):
        return None
    path = (APP_ROOT / relative).resolve()
    try:
        path.relative_to(COMPONENTS_DIR.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def _install_component(name: str, config: dict, update: bool = False) -> Path:
    state = _load_state()
    current = _component_executable(state["components"].get(name, {}))
    if current and not update:
        return current

    asset = github_release_asset(str(config["repository"]), str(config["asset"]))
    if current and state["components"][name].get("sha256") == asset["sha256"]:
        return current

    COMPONENTS_DIR.mkdir(parents=True, exist_ok=True)
    archive_fd, archive_name = tempfile.mkstemp(prefix=f"{name}-", suffix=".zip", dir=RUNTIME_DIR)
    os.close(archive_fd)  # Windows will not let urllib replace or remove a still-open mkstemp file.
    archive = Path(archive_name)
    staging = COMPONENTS_DIR / f".{name}-{uuid.uuid4().hex}.staging"
    try:
        print(f"Downloading {name} from {config['repository']} ({asset['tag']})...")
        _download(asset["url"], archive, asset["sha256"])
        _safe_extract(archive, staging)
        executables = list(staging.rglob(str(config["executable"])))
        if len(executables) != 1:
            raise BootstrapError(f"Expected one {config['executable']} in {config['asset']}, found {len(executables)}")
        version_dir = COMPONENTS_DIR / f"{name}-{asset['sha256'][:12]}"
        if version_dir.exists():
            shutil.rmtree(staging)
        else:
            os.replace(staging, version_dir)
        executable = next(version_dir.rglob(str(config["executable"])))
        state["components"][name] = {
            "version": asset["tag"],
            "sha256": asset["sha256"],
            "source": asset["url"],
            "executable": executable.relative_to(APP_ROOT).as_posix(),
        }
        _save_state(state)
        return executable
    finally:
        archive.unlink(missing_ok=True)
        if staging.exists():
            shutil.rmtree(staging)


def _imports_available(import_names: tuple[str, ...]) -> bool:
    """Probe a fresh isolated process so build-machine imports cannot leak into the portable check."""
    code = "; ".join(f"import {name}" for name in import_names)
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _ensure_python_package(import_names: tuple[str, ...], package: str, update: bool = False) -> None:
    if _imports_available(import_names) and not update:
        return
    print(f"Installing {package} into the portable Python runtime...")
    package_dir = Path(sys.executable).resolve().parent / "Lib" / "site-packages"
    package_dir.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade",
        "--ignore-installed", "--target", str(package_dir), package,
    ]
    result = subprocess.run(command, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise BootstrapError(f"pip could not install {package} (exit code {result.returncode})")
    site.addsitedir(str(Path(sys.executable).resolve().parent / "Lib" / "site-packages"))
    if not _imports_available(import_names):
        raise BootstrapError(f"{package} was installed but cannot be imported by the portable Python runtime")


def configure_portable() -> None:
    os.environ.setdefault("VIDEO_GRABBER_PORTABLE_ROOT", str(APP_ROOT))
    os.environ.setdefault("GRAB_CONFIG_DIR", str(APP_ROOT / "data" / "config"))
    os.environ["PYTHONNOUSERSITE"] = "1"
    paths = [str(Path(sys.executable).resolve().parent), str(Path(sys.executable).resolve().parent / "Scripts")]
    state = _load_state()
    for record in state["components"].values():
        executable = _component_executable(record)
        if executable:
            paths.append(str(executable.parent))
    existing = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([*dict.fromkeys(paths), existing])


def ensure_runtime(with_playwright: bool = False, update: bool = False) -> None:
    if os.name != "nt" or sys.maxsize <= 2**32:
        raise BootstrapError("This Portable ZIP supports 64-bit Windows only")
    manifest = load_manifest()
    for name in ("ffmpeg", "deno"):
        _install_component(name, manifest["components"][name], update)
    _ensure_python_package(("yt_dlp", "curl_cffi", "yt_dlp_ejs"), manifest["python_packages"]["yt_dlp"], update)
    _ensure_python_package(("webview",), manifest["python_packages"]["desktop"], update)
    if with_playwright:
        _ensure_python_package(("playwright",), manifest["python_packages"]["playwright"], update)
    configure_portable()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install or update Video Grabber portable components")
    parser.add_argument("--with-playwright", action="store_true", help="also install optional Playwright page rendering")
    parser.add_argument("--update", action="store_true", help="check for and install newer components")
    args = parser.parse_args(argv)
    try:
        configure_portable()
        ensure_runtime(args.with_playwright, args.update)
    except BootstrapError as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print("Portable components are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
