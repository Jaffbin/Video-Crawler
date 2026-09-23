# Video Grabber - frontend

This is the React + TypeScript + Tailwind interface for `webui.py`. It talks to the same
`/api/*` endpoints as the built-in fallback page, so the Python backend never needs to change
when this UI changes.

You do **not** need Node.js to run the program day to day: the built output already lives in
`../webui_dist/` and is committed alongside the Python files. Node is only needed if you want to
change the interface itself.

## Rebuilding after a change

```
cd frontend
npm install
npm run build      # writes ../webui_dist/ - webui.py serves it automatically
```

`webui.py` prefers `webui_dist/` when it exists and falls back to its own plain built-in page
otherwise, so the program still works if the folder is ever deleted or out of date.

## Developing with live reload

Run the backend and the Vite dev server side by side:

```
python ../webui.py --ui none --port 8765     # starts the API, opens nothing
cd frontend && npm run dev                    # http://127.0.0.1:5173, proxies /api and /files
```

The backend prints its random token on the built page, but the dev server serves its own
`index.html` (unbuilt), so the token placeholder is never replaced. Open
`http://127.0.0.1:5173/?t=<token>` once - grab `<token>` by running
`python -c "import webui; print(webui.TOKEN)"` right after starting the backend, or just watch
the backend's first request in its terminal output. The token is cached in memory for the rest of
the session (see `src/api/client.ts`).

## Testing

```
npm run typecheck   # tsc, no emit
npm test            # vitest
npm run format      # prettier --write src
```

## Project layout

```
src/
  api/client.ts          fetch wrapper, token handling, one function per endpoint
  types/api.ts            shapes returned by webui.py
  lib/                     pure helpers (url extraction, option validation, formatting) - unit tested
  hooks/                   polling, notifications, drag/paste import, restart handling
  components/
    layout/                header, banners, restart overlay
    download/               the "new download" form, advanced settings, cookies box
    queue/                  the job list and a single job card
    files/                  the downloaded-files list
    diagnostics/            the Diagnostics and Update dialogs
    ui/                     generic Button / Modal / Toast / Segmented control
  App.tsx                   wires it all together
```

## Notes for anyone continuing this

- `sanitizeOptions()` (`src/lib/options.ts`) is the single place that turns whatever is in
  `localStorage` or a `<select>` into something the backend will accept - never send raw form
  state to `/api/jobs` or `/api/probe` without going through it.
- `useStatePolling` never stops polling when the tab is hidden (it only slows down); that is
  exactly when "did my download finish" matters most.
- Desktop notifications go through two different code paths: `useCompletionNotifier` calls the
  Web Notifications API directly in a normal browser tab or on Windows (WebView2 supports it),
  but posts to `/api/notify` instead when `state.desktop_notifications` is true - that happens on
  macOS/Linux in window mode, where the embedded WebView typically does not implement it.
- `state.window` switches file-opening between an `<a href>` (browser tab) and a POST to
  `/api/open-file` (window mode, where a link can't hand a file to an external player).
