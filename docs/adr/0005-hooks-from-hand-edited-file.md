# 0005. Configure hooks and notifications only in a hand-edited file

Status: Accepted

## Context

Power users want to run a program after a download (move files, tag music, refresh a media server)
and to get Discord, Telegram, ntfy or webhook notifications. A hook is arbitrary code execution, and
notification URLs often contain secrets. The Chrome extension, once the user allows it, holds the
page token ([0002](0002-launch-secret-and-page-token.md)), so anything settable over HTTP is
settable by the extension.

## Decision

Hook commands and notification channels are read only from a settings file the user edits by hand.
No HTTP route can create or change them. Hooks run without a shell, with at most 32 command parts
and a timeout (default 60 s, maximum 600 s). Event details reach the program through stdin JSON and
`VG_*` environment variables, never the command line. Callers see notification channels only by
type and host.

## Consequences

- Anything that obtains the page token still cannot gain code execution.
- Titles and URLs from download sites cannot inject shell syntax or arguments.
- Less convenient: users edit a file rather than a form.

## Alternatives considered

- **Settings form in the UI**: friendlier, but turns any token compromise into code execution.
- **Shell command strings**: easier to write, but invite quoting bugs and injection.
