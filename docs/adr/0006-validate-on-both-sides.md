# 0006. Validate input in both Python and TypeScript

Status: Accepted

## Context

Download options, smart collection rules, presets and backup documents are edited in the React
UI and persisted by the Python server. Backups can also be hand-edited or come from older versions.

## Decision

Validate in both places on purpose. TypeScript (`frontend/src/lib/`) validates for immediate
feedback and live previews. Python validates again before persisting, because the server is the
trust boundary for anything sent over HTTP or read from disk. Rule validation is bounded and
rejects unsupported conditions rather than ignoring them.

## Consequences

- A UI bug, an old backup or a direct API call cannot persist invalid options or rules.
- Two implementations can drift; tests on both sides reduce this. Removing one side to
  "deduplicate" is explicitly ruled out (see `docs/PERFORMANCE_REVIEW.md`).

## Alternatives considered

- **Server-only validation**: slower feedback and no live preview without a round trip.
- **Generating both from one schema**: adds a build step and a dependency for a small set of rules.
