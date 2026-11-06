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

# Chrome extension protocol and manifest checks (no npm dependencies)
node --test ../browser-extension/tests/connection.test.js
```

The frontend build writes to `webui_dist/`. Commit the updated hashed assets and remove the old
ones so the prebuilt interface remains usable without Node.js.

## Design boundaries

- `frontend/src/lib/audioPlayer.ts` owns the bounded, library-scoped playback queue, shuffle and
  repeat transitions, persistence and one audio element's lifecycle. Only the bottom player's
  UI subscribes to frequent time updates; app navigation and Library use stable controller actions.
  Native hiding preserves the main WebView; the quick-download window does not own audio.
  Playback progress writes include an optional root binding to reject stale-library saves.

- `grab.py` owns download discovery and yt-dlp options.
- `grab_download.py` records structured yt-dlp item failures for selective retries.
- `grab_images.py` uses yt-dlp's request client for bounded original-format image downloads and
  cover-only extraction. Temporary files are hidden and published atomically after completion.
- `grab_library.py` owns local media metadata and reversible group operations for companion files.
- `grab_organizer.py` owns bounded, cancellable library inventory, byte-verified duplicate checks
  and reviewed duplicate recycling. Its read-only worker never holds the library lock while
  hashing; destructive file operations remain delegated to `MediaLibrary.trash_many`.
- `grab_backup.py` owns versioned, allowlisted preference/annotation backups and reviewed merges.
  Restore requires a fresh preview token, preserves existing conflicting scalar values and never
  copies media, credentials, source URLs, subscriptions, job history or download-folder settings.
- `grab_sites.py` contains narrow site adapters; keep them independent and fixture-tested.
- `grab_models.py` contains persisted state models and API views.
- `grab_state.py` owns thread-safe in-memory registries.
- `grab_storage.py` owns atomic JSON persistence.
- `webui.py` coordinates services, HTTP routes and the desktop/browser lifecycle.
  `POST /api/jobs` preserves its legacy behavior by default. Clients opt into existing-file
  review with `check_existing: true`, then submit `existing_action: "skip"` or `"download"`.
  A review response contains an empty `ids` array and `existing` items; no task has been created.
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
