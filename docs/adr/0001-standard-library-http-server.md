# 0001. Serve the app with the standard-library HTTP server on loopback

Status: Accepted

## Context

The app is a Windows desktop tool for non-technical users, shipped as a portable ZIP with an
embedded Python. The only required runtime dependency is yt-dlp. The server handles one user, a
handful of concurrent requests (UI polling, media range requests, the extension) and long-running
download threads that share in-process state with the HTTP handlers.

## Decision

Use `http.server.ThreadingHTTPServer` with a single `BaseHTTPRequestHandler` that dispatches to
route modules (`webui_routes_*.py`). Bind to `127.0.0.1` only. Downloads run in worker threads in
the same process; shared state lives in thread-safe stores (`grab_state.py`).

## Consequences

- No web framework or ASGI server to install, pin, audit or bundle; the portable bootstrap stays
  within the standard library.
- Downloads and HTTP handlers share memory directly, so there is no job queue or IPC to operate.
- Security headers, body limits, range requests and routing are hand-written and must be tested
  here. For example, `_discard_rejected_body` exists because of a socket behaviour a framework
  might have hidden (see [the write-up](../engineering/windows-rejected-post-resets.md)).
- `webui.py` grew large; routes were later split into `webui_routes_*.py` modules.
- Not suited to many concurrent remote users. That is not a goal today.

## Alternatives considered

- **Flask / FastAPI + uvicorn**: nicer routing and validation, but adds dependencies to the
  portable build and does not remove the need for the custom Host and token checks.
- **Electron or Tauri shell with IPC instead of HTTP**: removes the local port, but means a second
  runtime and a rewrite of the backend boundary.
