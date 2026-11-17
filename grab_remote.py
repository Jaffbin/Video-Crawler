"""Remote access for phones: settings, pairing codes, device tokens and request checks.

Remote access is a second, opt-in listener (see docs/adr/0009-remote-access-listener.md). It binds
to this computer only (for Tailscale Serve or another reverse proxy) or to one private IPv4 address
of this computer, never to all interfaces. Phones pair with a short-lived code and then hold a
device token in an HttpOnly cookie. Only SHA-256 hashes of device tokens are stored.

Everything here is pure logic so it can be tested without sockets; webui.py owns the listener.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
import socket
import threading
import time

DEFAULT_PORT = 8766
LOOPBACK = "loopback"
MAX_DEVICES = 10
MAX_TRUSTED_HOSTS = 10
DEVICE_NAME_MAX = 40
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
CODE_LENGTH = 8
CODE_TTL_SECONDS = 300
CODE_MAX_FAILURES = 5
TOKEN_PREFIX = "vgd_"
COOKIE = "vg_device"
COOKIE_MAX_AGE = 400 * 24 * 3600  # browsers cap cookie lifetimes at about 400 days
LAST_SEEN_INTERVAL = 60
LIBRARY_PAGE_MAX = 60
TAILSCALE_RANGE = ipaddress.ip_network("100.64.0.0/10")
HOSTNAME_RE = re.compile(r"(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+")
DEVICE_ID_RE = re.compile(r"[0-9a-f]{8}")
HEX64_RE = re.compile(r"[0-9a-f]{64}")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── Settings ──
def _private_ipv4(value) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    # 0.0.0.0 counts as "private" in the ipaddress module, but binding it would listen on every interface.
    return (address.version == 4 and address.is_private and not address.is_unspecified and not address.is_loopback
            and not address.is_link_local and not address.is_multicast and not address.is_reserved)


def _device(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    device_id, digest = raw.get("id"), raw.get("token_sha256")
    if not (isinstance(device_id, str) and DEVICE_ID_RE.fullmatch(device_id)
            and isinstance(digest, str) and HEX64_RE.fullmatch(digest)):
        return None
    return {"id": device_id, "name": device_name(raw.get("name")), "token_sha256": digest,
            "created": _timestamp(raw.get("created")), "last_seen": _timestamp(raw.get("last_seen"))}


def _timestamp(value) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def settings(raw) -> dict:
    """Saved remote access settings. Anything unexpected falls back to the safe default (off)."""
    raw = raw if isinstance(raw, dict) else {}
    bind = raw.get("bind")
    bind = bind if bind == LOOPBACK or _private_ipv4(bind) else LOOPBACK
    port = raw.get("port")
    port = port if isinstance(port, int) and not isinstance(port, bool) and 1024 <= port <= 65535 else DEFAULT_PORT
    hosts = raw.get("trusted_hosts")
    hosts = [h for h in hosts if isinstance(h, str) and HOSTNAME_RE.fullmatch(h)][:MAX_TRUSTED_HOSTS] \
        if isinstance(hosts, list) else []
    devices = [d for d in map(_device, raw.get("devices") if isinstance(raw.get("devices"), list) else []) if d]
    return {"enabled": raw.get("enabled") is True, "bind": bind, "port": port,
            "trusted_hosts": list(dict.fromkeys(hosts)), "devices": devices[:MAX_DEVICES]}


def configure(saved: dict, body: dict, addresses: list[str]) -> dict:
    """Apply a settings change from the app window. Raises ValueError with a readable reason."""
    unknown = set(body) - {"action", "bind", "port", "trusted_hosts"}
    if unknown:
        raise ValueError(f"Unsupported fields: {', '.join(sorted(unknown))}.")
    updated = dict(saved)
    if "bind" in body:
        bind = body["bind"]
        if bind != LOOPBACK and not (_private_ipv4(bind) and bind in addresses):
            raise ValueError("Choose this computer only, or one of this computer's network addresses.")
        updated["bind"] = bind
    if "port" in body:
        port = body["port"]
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            raise ValueError("The port must be a number from 1024 to 65535.")
        updated["port"] = port
    if "trusted_hosts" in body:
        hosts = body["trusted_hosts"]
        if not isinstance(hosts, list) or len(hosts) > MAX_TRUSTED_HOSTS or not all(isinstance(h, str) for h in hosts):
            raise ValueError(f"Add at most {MAX_TRUSTED_HOSTS} host names.")
        cleaned = []
        for host in hosts:
            host = host.strip().lower().rstrip(".")
            if not host:
                continue
            if not HOSTNAME_RE.fullmatch(host) or _is_ip(host):
                raise ValueError(f"{host[:80]} is not a host name such as mypc.tailnet.ts.net.")
            cleaned.append(host)
        updated["trusted_hosts"] = list(dict.fromkeys(cleaned))
    return updated


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def local_addresses() -> list[str]:
    """This computer's private IPv4 addresses, best effort and without sending any traffic."""
    found = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # UDP connect only picks a route; no packet is sent
        found.add(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    return sorted((a for a in found if _private_ipv4(a)), key=lambda a: ipaddress.ip_address(a))


def bind_address(bind: str) -> str:
    return "127.0.0.1" if bind == LOOPBACK else bind


def urls(saved: dict, port: int) -> list[str]:
    """Addresses to open on the phone."""
    out = [] if saved["bind"] == LOOPBACK else [f"http://{saved['bind']}:{port}/"]
    return out + [f"https://{host}/" for host in saved["trusted_hosts"]]


# ── Request checks ──
def host_allowed(host_header: str | None, saved: dict) -> bool:
    """DNS-rebinding guard: the Host name must be the bound address or a trusted name."""
    host = (host_header or "").strip().lower()
    match = re.fullmatch(r"(\[[0-9a-f:]+\]|[a-z0-9.-]+)(:\d{1,5})?", host)
    if not match:
        return False
    name = match.group(1).rstrip(".")
    allowed = set(saved["trusted_hosts"])
    allowed |= {"127.0.0.1", "localhost"} if saved["bind"] == LOOPBACK else {saved["bind"]}
    return name in allowed


def client_allowed(client_ip: str, saved: dict) -> bool:
    """On a LAN bind, refuse clients from the internet (for example through a port forward)."""
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    if saved["bind"] == LOOPBACK:
        return address.is_loopback
    return address.is_private or address.is_loopback or address.is_link_local or (
        address.version == 4 and address in TAILSCALE_RANGE)


# ── Pairing ──
def normalize_code(value) -> str:
    return re.sub(r"[\s-]", "", value).upper() if isinstance(value, str) else ""


def format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


class Pairing:
    """One pairing code at a time, in memory only: single use, short-lived, few attempts."""

    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._code = ""
        self._expires = 0.0
        self._failures = 0

    def new_code(self) -> dict:
        with self._lock:
            self._code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            self._expires = self._clock() + CODE_TTL_SECONDS
            self._failures = 0
            return {"code": format_code(self._code), "expires": self._expires}

    def clear(self) -> None:
        with self._lock:
            self._code, self._expires, self._failures = "", 0.0, 0

    def active(self) -> dict | None:
        with self._lock:
            if self._code and self._clock() < self._expires:
                return {"code": format_code(self._code), "expires": self._expires}
            return None

    def redeem(self, value) -> bool:
        """True once for the right code; a wrong code counts toward discarding the current one."""
        candidate = normalize_code(value)
        with self._lock:
            if not self._code or self._clock() >= self._expires:
                self._code = ""
                return False
            if len(candidate) == CODE_LENGTH and hmac.compare_digest(candidate, self._code):
                self._code, self._expires, self._failures = "", 0.0, 0
                return True
            self._failures += 1
            if self._failures >= CODE_MAX_FAILURES:
                self._code, self._expires = "", 0.0
            return False


# ── Devices ──
def device_name(value) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]", "", value).strip() if isinstance(value, str) else ""
    return text[:DEVICE_NAME_MAX] or "Phone"


def new_device(name, existing: list[dict], now: float) -> tuple[str, dict]:
    """(token for the cookie, record to store). Raises ValueError when the device list is full."""
    if len(existing) >= MAX_DEVICES:
        raise ValueError(f"At most {MAX_DEVICES} devices can be paired. Remove one in Video Grabber first.")
    used = {device["id"] for device in existing}
    device_id = secrets.token_hex(4)
    while device_id in used:
        device_id = secrets.token_hex(4)
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, {"id": device_id, "name": device_name(name), "token_sha256": hash_token(token),
                   "created": now, "last_seen": now}


def find_device(token, devices: list[dict]) -> dict | None:
    if not isinstance(token, str) or not token.startswith(TOKEN_PREFIX) or len(token) > 200:
        return None
    digest = hash_token(token)
    for device in devices:
        if hmac.compare_digest(digest, device["token_sha256"]):
            return device
    return None


def device_view(device: dict) -> dict:
    return {key: device[key] for key in ("id", "name", "created", "last_seen")}


def cookie_header(token: str) -> str:
    return f"{COOKIE}={token}; Path=/; Max-Age={COOKIE_MAX_AGE}; HttpOnly; SameSite=Strict"


def clear_cookie_header() -> str:
    return f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"


# ── Library (read-only) ──
LIBRARY_FIELDS = ("name", "path", "title", "source", "kind", "size", "downloaded", "thumbnail")


def library_page(files: list[dict], query: str = "", kind: str = "", offset: int = 0,
                 limit: int = 30) -> dict:
    """A page of Library entries with only the fields a phone needs; no notes, tags or source URLs."""
    query = query.strip().lower()[:200]
    limit = max(1, min(limit, LIBRARY_PAGE_MAX))
    offset = max(0, offset)
    matches = [f for f in files if f.get("complete", True)
               and (not kind or f.get("kind") == kind)
               and (not query or query in str(f.get("title") or "").lower() or query in str(f.get("name") or "").lower())]
    items = [{field: item.get(field) for field in LIBRARY_FIELDS} for item in matches[offset:offset + limit]]
    return {"items": items, "total": len(matches), "offset": offset}
