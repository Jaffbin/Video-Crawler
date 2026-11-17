# 0009. Remote access through a separate listener with paired devices

Status: Accepted (2026-11-18)

## Context

Users want to add downloads and watch the queue from a phone, and to play Library media there. The
main server ([0001](0001-standard-library-http-server.md)) listens on `127.0.0.1` only, and its
protection ([0002](0002-launch-secret-and-page-token.md)) assumes loopback: a Host allowlist of
`127.0.0.1`/`localhost`, a launch secret only the app can hand out, and a page token that unlocks
every route, including settings. None of that can be extended to another device without
weakening it.

Two ways to reach the computer from a phone are in scope:

- **Tailscale Serve** (or a similar reverse proxy) publishes a local port as
  `https://<machine>.<tailnet>.ts.net` with a trusted certificate, reachable only inside the
  user's tailnet. HTTPS is also what browsers require for PWA installation and the share sheet.
- **Plain HTTP on the home network**, which needs no extra software but can be read by anyone on
  the same Wi-Fi.

## Decision

### A second listener, off by default

- Remote access is a **separate `ThreadingHTTPServer`** with its own handler. The main server,
  its Host check, its tokens and its routes are unchanged.
- It binds to one of two places the user chooses:
  - **This computer only** (`127.0.0.1`): for Tailscale Serve or another reverse proxy.
  - **One private IPv4 address of this computer** (for example `192.168.1.20`): for the home
    network. Never `0.0.0.0`.
- Default port 8766, configurable. It starts and stops with the setting.

### Host and client checks

- The Host header's name must be the bound address, `127.0.0.1`/`localhost` for the loopback bind,
  or a name the user added to **trusted host names** (such as `box.tailnet.ts.net`). This keeps
  DNS-rebinding protection; the list is empty by default.
- On a LAN bind, the client address must be private, loopback, link-local or in `100.64.0.0/10`
  (Tailscale). A port forwarded from the internet is refused.

### Pairing and device tokens

- The desktop app creates a **pairing code**: 8 characters from a 31-character alphabet (about
  40 bits), valid for 5 minutes, single use, kept only in memory. After 5 wrong attempts the code is
  discarded and a new one must be created.
- The phone sends the code with a device name. The app creates a **device token**, stores only its
  SHA-256 hash with the name and dates, and returns the token in an `HttpOnly; SameSite=Strict`
  cookie. Media elements need a cookie anyway, and script on the page never sees the token.
- Each device can be revoked from the desktop; a phone can also forget itself. At most 10 devices.
- Management (turning remote access on, pairing codes, the device list, trusted names) is available
  only to the app's own window, with the session cookie, like the automation API settings. The
  Chrome extension cannot reach it.

### What a paired device can do

| Allowed | Not allowed |
| --- | --- |
| Add downloads (same options and validation as `/api/v1`) | Settings, hooks, notifications, cookies |
| See the queue; cancel and retry tasks | Backup and restore, automation API token |
| Browse the Library read-only (title, type, size, date, cover) and play media | Delete, rename, move, tag or recycle files |
| Forget its own pairing | Pair other devices or see other devices |

### Request rules

- State-changing requests must be `POST` with `application/json` and an `X-VG-Remote: 1` header,
  and a present `Origin` must match the Host. Together with `SameSite=Strict` this blocks
  cross-site requests even on plain HTTP.
- Bodies use the same 1 MB limit and bounded rejection draining as the main server.
- The phone page is static HTML, CSS and JavaScript from the app, with a CSP of `default-src 'self'`
  and `frame-ancestors 'none'`.

## Consequences

- The loopback design of the main server is untouched, so existing tests and guarantees hold.
- A stolen device token gives only the allowed column above, until it is revoked.
- **Plain HTTP on the LAN exposes the device cookie and media to anyone who can capture traffic on
  that network.** The settings say so and recommend Tailscale outside a trusted home network.
- Behind Tailscale Serve the app sees plain HTTP from `127.0.0.1`, so it cannot mark the cookie
  `Secure`. Tailscale Serve itself only answers over HTTPS inside the tailnet.
- Two listeners mean two handlers to keep consistent; shared helpers (`_send`, `_json`, `_body`,
  `_file`) come from the main handler class.
- Phone UX is basic in this step; PWA installation and the share sheet need HTTPS and come later.

## Alternatives considered

- **Bind the main server to `0.0.0.0` and reuse the page token**: one token would unlock settings and
  hooks from the network, and the launch-secret model would no longer hold.
- **Allow trusted host names on the main server** for Tailscale: the phone still could not get the
  page token without the launch secret, and widening it would expose every route.
- **Self-signed HTTPS inside the app**: needs a new dependency to create certificates and asks users
  to install a CA on the phone; Tailscale gives a trusted certificate with less risk.
- **Device token in `localStorage` with an `Authorization` header**: readable by any script on the
  page and unusable for `<video>` and `<img>`, which cannot send headers.
- **Passwords**: weaker than random device tokens and adds password storage.
