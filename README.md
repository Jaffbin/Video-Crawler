# Video Grabber

A local tool for downloading video/audio from the web (yt-dlp + ffmpeg), with a desktop-style UI.

## Layout

```
grab.py          Command-line downloader. See `python grab.py --help` / `python grab.py --doctor`.
webui.py         Local web server: the API, job queue, and the app window/browser tab.
webui_dist/      The built React interface (prebuilt - you do not need Node.js to run this).
frontend/        Source for that interface (React + TypeScript + Tailwind). See frontend/README.md.
tests/           Backend tests (pytest). Safe to delete once you no longer need them.
```

## Running it

```
pip install -U "yt-dlp[default,deno]"      # yt-dlp plus YouTube's JS challenge solver and Deno
                                             # (winget install DenoLand.Deno also works on Windows)
pip install pywebview                       # optional: gives the app its own window instead of a browser tab
python webui.py
```

By default this opens in its own window (`--ui window`). If `pywebview` is not installed, it
automatically opens your default browser instead and tells you so. Use `--ui browser` to always
use a browser tab, or `--ui none` when developing the frontend with `npm run dev`.

Run `python webui.py --help` for all options (download folder, port, worker count).

First thing to do in the app: open **Diagnostics** and follow any "Install now" prompts - it
checks ffmpeg, the JavaScript runtime and yt-dlp-ejs component YouTube needs, Playwright (for
pages that load video with JavaScript), and cookies.

## Tests

```
pip install pytest
pytest -q
```

These need ffmpeg on PATH for the download tests; everything else runs without it.
