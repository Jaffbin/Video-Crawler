# Video Grabber

A private, local-first video and audio downloader powered by yt-dlp and ffmpeg, with a desktop-style UI.

Paste a link, choose MP4 or MP3, and keep the result on your own computer. Video Grabber does not
require an account or a hosted service, and it does not send your links or cookies to a
project-owned cloud service. It connects directly to the sites you ask it to download from and to
PyPI when checking for yt-dlp updates.

## Highlights

- Download individual videos, playlists and channels supported by yt-dlp.
- Choose MP4 quality limits or MP3 bitrate.
- Download subtitles and cover art.
- Queue several downloads with live progress, cancellation and retry.
- Subscribe to a channel or playlist and automatically download new entries.
- Fall back to static page scanning or optional browser rendering for less common sites.
- Diagnose ffmpeg, yt-dlp, Deno, Playwright, cookies and network problems from the UI.
- Run in a native pywebview window, a normal browser tab, or directly from the CLI.

Only download content you have the right to download. The application does not bypass DRM or
access controls.

## Quick start

```
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[desktop]"
python webui.py
```

Python 3.10 or newer is required. The base install includes yt-dlp, its default components and
Deno. The `desktop` extra adds pywebview for a native app window; without it, the app falls back
to your default browser. ffmpeg is still a system dependency and must be available on PATH.

Page rendering for sites that load media dynamically is optional:

```
python -m pip install -e ".[render]"
```

By default this opens in its own window (`--ui window`). If `pywebview` is not installed, it
automatically opens your default browser instead and tells you so. Use `--ui browser` to always
use a browser tab, or `--ui none` when developing the frontend with `npm run dev`.

Run `python webui.py --help` for all options (download folder, port, worker count,
`--sub-interval` for how often subscriptions are re-checked).

**Subscriptions**: add a channel or playlist link in the "Subscriptions" panel to have new videos
download automatically (checked every 60 minutes by default). New subscriptions only grab videos
published from then on unless you choose to also back-fill a recent batch when adding one.

First thing to do in the app: open **Diagnostics** and follow any "Install now" prompts - it
checks ffmpeg, the JavaScript runtime and yt-dlp-ejs component YouTube needs, Playwright (for
pages that load video with JavaScript), and cookies.

Application data stays local:

- Downloads, task history and subscriptions live under the selected download directory.
- Uploaded cookies are stored in the operating system's user configuration directory, not beside
  downloaded media and never exposed through `/files`.

## Updating from a zip

Unzip the release **over** your project folder and let it replace files. Then delete any older
`index-*.js` / `index-*.css` files inside `webui_dist/assets/` - each build has new file names, and
the old ones are just dead weight. The folder must end up like this (the `assets/` subfolder matters):

```
webui_dist/
  index.html
  assets/
    index-XXXXXXXX.js
    index-XXXXXXXX.css
```

If it is wrong, `python webui.py` prints a `WARNING` at startup naming the missing file, and
Diagnostics shows "Interface files" as a warning, instead of quietly showing the old page.

## Tests

```
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q
```

These need ffmpeg on PATH for the download tests; everything else runs without it.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the complete backend/frontend workflow and privacy-safe
bug reporting guidance.

## Development layout

```
grab.py          Command-line downloader. See `python grab.py --help` / `python grab.py --doctor`.
webui.py         Local web server: the API, services, and the app window/browser tab.
grab_config.py   Validated Web UI startup configuration and CLI parsing.
grab_models.py   Job and subscription state, views, and persistence schemas.
grab_state.py    Thread-safe job and subscription registries.
grab_storage.py  Atomic JSON persistence used by job history and subscriptions.
webui_dist/      The built React interface (prebuilt - you do not need Node.js to run this).
frontend/        Source for that interface (React + TypeScript + Tailwind). See frontend/README.md.
tests/           Backend tests (pytest).
```
