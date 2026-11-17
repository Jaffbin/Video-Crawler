# Architecture decision records

Short records of decisions that shape the code, with the context and trade-offs behind them.
Records 0001–0007 were written after the fact, from the code, commit history and milestone notes,
to explain choices that already exist. New decisions get a new numbered file.

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-standard-library-http-server.md) | Serve the app with the standard-library HTTP server on loopback | Accepted |
| [0002](0002-launch-secret-and-page-token.md) | Protect the local server with a launch secret, a session cookie and a per-run page token | Accepted |
| [0003](0003-sqlite-with-json-mirror.md) | Store Library metadata in SQLite with a JSON mirror | Accepted |
| [0004](0004-recovery-instead-of-delete.md) | Move files to Recovery instead of deleting them | Accepted |
| [0005](0005-hooks-from-hand-edited-file.md) | Configure hooks and notifications only in a hand-edited file | Accepted |
| [0006](0006-validate-on-both-sides.md) | Validate input in both Python and TypeScript | Accepted |
| [0007](0007-commit-the-built-frontend.md) | Commit the built frontend and verify it in CI | Accepted |
| [0008](0008-mcp-server-as-api-client.md) | Build the MCP server as an optional, loopback-only client of the automation API | Accepted |
| [0009](0009-remote-access-listener.md) | Remote access through a separate listener with paired devices | Accepted |

Each record follows: Context → Decision → Consequences (good and bad) → Alternatives considered.
