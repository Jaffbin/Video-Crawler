# 0007. Commit the built frontend and verify it in CI

Status: Accepted

## Context

The UI is a React, TypeScript and Vite app. End users, and people running from source, should not
need Node.js to start the app.

## Decision

Commit the production build in `webui_dist/`. The Python server serves it and fills in the per-run
token. CI builds the frontend and fails if the committed `webui_dist/` differs from a fresh build.

## Consequences

- `python webui.py` works from a clean clone with only Python dependencies.
- Changes to the UI also change hashed asset files, which makes diffs noisier.
- CI guarantees the committed build matches the source, so it cannot silently drift.

## Alternatives considered

- **Build during install**: running from source would need Node.js.
- **Release-only build artifact**: the source tree would not run without a build step.
