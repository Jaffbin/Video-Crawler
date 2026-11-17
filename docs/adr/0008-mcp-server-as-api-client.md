# 0008. Build the MCP server as an optional, loopback-only client of the automation API

Status: Accepted (2026-11-18)

## Context

AI agents (Claude Code, Cursor and others) can call tools through the Model Context Protocol.
Letting an agent queue downloads and follow their progress is a natural extension of the existing
automation API (`/api/v1`), which is opt-in, has its own hashed token and accepts only output
choices. MCP's stdio transport is JSON-RPC 2.0 over stdin and stdout; the official Python SDK
(`mcp` 2.x) brings about 18 packages, including pydantic, starlette, uvicorn and cryptography.

Text the agent reads, such as video titles and error messages, comes from websites and can contain
prompt-injection attempts.

## Decision

- `grab_mcp.py` runs as a **separate process** started by the agent, and talks to the running app
  only through `/api/v1` over HTTP. It has no direct access to the Library, settings or files.
- It exposes three tools: `queue_download`, `get_job`, `get_queue_status`. Tool annotations mark
  the last two read-only and none as destructive.
- It sends the token **only to a loopback http address**; any other `VG_API_URL` is refused before
  a request is made. Job ids are checked against the 8-hex-character format before they are put in
  a URL.
- The tool descriptions and server instructions tell the agent that site-provided text is data,
  not instructions.
- The SDK is an **optional extra** (`.[mcp]`), like `ai` and `desktop`. The default install and
  the portable build are unchanged. The HTTP client part uses only the standard library, so its
  tests run without the SDK; CI installs the extra so the tool tests also run.
- `docs/openapi.json` documents `/api/v1`, and a test checks it against the validator and live
  responses so the two cannot drift.

## Consequences

- No new attack surface in the app: the MCP server can do exactly what the API token allows,
  and the existing tests for that boundary still apply.
- Turning the automation API off, or creating a new token, also cuts off the agent.
- The protocol details (handshake, capability negotiation, schema generation from type hints) are
  handled by the SDK, which tracks protocol changes.
- Users must install an extra package and configure the token in their agent.
- Read access to the Library is deliberately left out. Adding it later needs a separate opt-in,
  limited fields, and a new entry in the security model, because Library text would then flow to the
  agent's model provider and widen the prompt-injection surface.

## Alternatives considered

- **Implement the stdio protocol with the standard library**: no new dependencies and could ship in
  the portable build, but about 200–300 lines of protocol code to maintain as the specification
  changes.
- **Embed the MCP server in `webui.py`**: one process fewer, but it would bypass the API token
  boundary and add the SDK to the app itself.
- **Streamable HTTP transport served by the app**: would let remote agents connect, which conflicts
  with the loopback-only design until remote access has its own design.
