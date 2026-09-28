# Contributing

Thanks for helping improve Video Grabber. Keep changes focused, preserve local-first behavior, and
never include cookies, access tokens, private URLs or downloaded media in an issue or commit.

## Development setup

```sh
python -m venv .venv
# Activate .venv for your platform
python -m pip install -e ".[dev]"

cd frontend
npm ci
```

ffmpeg is optional for most tests, but the local media download tests use it when it is available.

## Checks

Run the checks relevant to your change. Before submitting a broad change, run all of them:

```sh
python -m ruff check .
python -m pytest -q

cd frontend
npm test
npm run typecheck
npm run format:check
npm run build
```

The frontend build writes to `webui_dist/`. Commit the updated hashed assets and remove the old
ones so the prebuilt interface remains usable without Node.js.

## Design boundaries

- `grab.py` owns download discovery and yt-dlp options.
- `grab_sites.py` contains narrow site adapters; keep them independent and fixture-tested.
- `grab_models.py` contains persisted state models and API views.
- `grab_state.py` owns thread-safe in-memory registries.
- `grab_storage.py` owns atomic JSON persistence.
- `webui.py` coordinates services, HTTP routes and the desktop/browser lifecycle.
- `portable_bootstrap.py` owns verified native-component installation; it must remain standard-library-only.
- `frontend/` contains the React interface; `webui_dist/` is generated from it.

Tests must not contact production accounts or require private cookies. Prefer local HTTP fixtures and
mocked extractor responses. When reporting a site failure, include a redacted Diagnostics report and
the public URL only when it is safe to share.

## Portable build

On Windows, `scripts\build_portable.ps1` downloads the pinned official CPython embeddable archive,
verifies its SHA-256, bundles pip and the application, then writes a ZIP plus checksum under
`artifacts/`. Do not weaken digest checks or add unverified download mirrors. The generated ZIP is a
release artifact and is intentionally ignored by Git.
