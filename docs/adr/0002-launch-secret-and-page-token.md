# 0002. Protect the local server with a launch secret, a session cookie and a per-run page token

Status: Accepted

## Context

Any web page the user opens can send requests to `127.0.0.1`. Other programs on the computer can
too. The UI runs in either a pywebview window or a normal browser tab, and media elements
(`<video>`, `<audio>`) cannot attach custom headers.

## Decision

Three secrets, each created with `secrets.token_urlsafe`:

1. **Launch secret** (`?n=`): only in the link the app opens itself. It unlocks the start page and
   sets the session cookie.
2. **Session cookie** (`HttpOnly; SameSite=Strict`): lets the same tab reload, and authorises
   `/files/` media requests that cannot send headers. Its secret is handed to a restarted app so
   open tabs keep working.
3. **Page token**: embedded in the start page and sent as `X-Token` on every API call.

All comparisons use `hmac.compare_digest`. Every request first passes a Host allowlist
(`127.0.0.1`, `localhost`) against DNS rebinding. The start page is served only with the launch
secret, the session cookie, or (when the user opts in) to the Chrome extension; other clients get a
static locked page. The automation API has its own, separate token.

## Consequences

- Cross-site pages cannot read the token (same-origin policy) or send it (a custom header needs a
  CORS preflight the server never answers).
- No login screen for the user.
- Several secrets with distinct scopes must be kept straight; tests cover each path.
- The extension, once allowed, holds the page token, which limits what HTTP routes may do
  (see [0005](0005-hooks-from-hand-edited-file.md)).

## Alternatives considered

- **Token in the URL only**: leaks through history, logs and referrers; kept only as read-only
  legacy `GET` access.
- **Origin header checks alone**: do not stop other local programs from loading the page.
- **User password**: friction for a single-user desktop app with no network exposure.
