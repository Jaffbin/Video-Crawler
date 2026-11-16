"""Send download notifications to Discord, Telegram, ntfy or a JSON webhook (standard library only).

Channels come from the same hand-edited settings file as download hooks, because their URLs and
tokens are secrets. Nothing here returns a URL or token to callers; ``describe`` gives only the
channel type and host, and error details never include the request URL.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

TYPES = ("discord", "telegram", "ntfy", "webhook")
CHANNEL_KEYS = {"discord": {"url"}, "telegram": {"bot_token", "chat_id"}, "ntfy": {"url", "token"},
                "webhook": {"url", "headers"}}
LANGUAGES = ("en", "zh-CN", "zh-TW", "ja")
MAX_CHANNELS = 10
MAX_HEADERS = 10
MAX_URL_LENGTH = 2048
SEND_TIMEOUT_SECONDS = 10
TELEGRAM_TOKEN_RE = re.compile(r"^\d{1,20}:[A-Za-z0-9_-]{20,100}$")
HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
USER_AGENT = "VideoGrabber-Notifications"

COPY = {
    "en": ("Download complete", "Download failed", "Test notification", "Notifications from Video Grabber work."),
    "zh-CN": ("下载完成", "下载失败", "测试通知", "Video Grabber 的通知设置正常。"),
    "zh-TW": ("下載完成", "下載失敗", "測試通知", "Video Grabber 的通知設定正常。"),
    "ja": ("ダウンロード完了", "ダウンロード失敗", "テスト通知", "Video Grabber の通知は正常に動作しています。"),
}


class ChannelConfigError(ValueError):
    pass


def _url(value, where: str, *, https_only: bool) -> str:
    schemes = ("https",) if https_only else ("http", "https")
    if (not isinstance(value, str) or not value or len(value) > MAX_URL_LENGTH
            or any(char.isspace() for char in value)):
        raise ChannelConfigError(f"{where}.url must be a web address.")
    parts = urlsplit(value)
    if parts.scheme not in schemes or not parts.hostname:
        raise ChannelConfigError(f"{where}.url must start with {' or '.join(s + '://' for s in schemes)}.")
    return value


def _events(value, where: str, events: tuple[str, ...]) -> list[str]:
    if value is None:
        return list(events)
    if (not isinstance(value, list) or not value or len(set(value)) != len(value)
            or not all(event in events for event in value)):
        raise ChannelConfigError(f"{where}.events must list one or more of: {', '.join(events)}.")
    return list(value)


def _validate_channel(index: int, raw, events: tuple[str, ...]) -> dict:
    where = f"notifications[{index}]"
    if not isinstance(raw, dict):
        raise ChannelConfigError(f"{where} must be an object.")
    kind = raw.get("type")
    if kind not in TYPES:
        raise ChannelConfigError(f"{where}.type must be one of: {', '.join(TYPES)}.")
    allowed = {"type", "events"} | CHANNEL_KEYS[kind]
    unknown = {key for key in raw if not key.startswith("_")} - allowed
    if unknown:
        raise ChannelConfigError(f"{where} has unknown keys for {kind}: {', '.join(sorted(unknown))}.")
    channel = {"type": kind, "events": _events(raw.get("events"), where, events)}
    if kind == "discord":
        channel["url"] = _url(raw.get("url"), where, https_only=True)
    elif kind == "telegram":
        token, chat = raw.get("bot_token"), raw.get("chat_id")
        if not isinstance(token, str) or not TELEGRAM_TOKEN_RE.match(token):
            raise ChannelConfigError(f"{where}.bot_token must be the token BotFather gave you, like 123456:ABC-DEF….")
        if isinstance(chat, bool) or not (isinstance(chat, int) or (isinstance(chat, str) and chat.strip()
                                                                       and len(chat) <= 64)):
            raise ChannelConfigError(f"{where}.chat_id must be a chat ID number or an @channel name.")
        channel.update(bot_token=token, chat_id=chat)
    elif kind == "ntfy":
        channel["url"] = _url(raw.get("url"), where, https_only=False)
        parts = urlsplit(channel["url"])
        if not parts.path.strip("/") or parts.query or parts.fragment:
            raise ChannelConfigError(f"{where}.url must be a topic address, like https://ntfy.sh/my-topic.")
        token = raw.get("token")
        if token is not None and (not isinstance(token, str) or not token or not token.isprintable()):
            raise ChannelConfigError(f"{where}.token must be an access token.")
        if token:
            channel["token"] = token
    else:
        channel["url"] = _url(raw.get("url"), where, https_only=False)
        headers = raw.get("headers", {})
        if (not isinstance(headers, dict) or len(headers) > MAX_HEADERS
                or not all(isinstance(k, str) and HEADER_NAME_RE.match(k) and isinstance(v, str) and v.isprintable()
                           and len(v) <= 4096 for k, v in headers.items())):
            raise ChannelConfigError(f"{where}.headers must map up to {MAX_HEADERS} header names to text values.")
        channel["headers"] = dict(headers)
    return channel


def parse_channels(raw, events: tuple[str, ...]) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > MAX_CHANNELS:
        raise ChannelConfigError(f"notifications must be a list of up to {MAX_CHANNELS} channels.")
    return [_validate_channel(index, item, events) for index, item in enumerate(raw)]


def parse_language(raw) -> str:
    if raw is None:
        return "en"
    if raw not in LANGUAGES:
        raise ChannelConfigError(f"language must be one of: {', '.join(LANGUAGES)}.")
    return raw


def describe(channel: dict) -> dict:
    """What the settings panel may show: no URL path, query or token."""
    host = urlsplit(channel["url"]).hostname if "url" in channel else "api.telegram.org"
    return {"type": channel["type"], "target": host or "", "events": list(channel["events"])}


DISPLAY_NAMES = {"discord": "Discord", "telegram": "Telegram", "ntfy": "ntfy", "webhook": "Webhook"}


def target_label(channel: dict) -> str:
    """Matches how the settings panel lists the channel, e.g. "Discord (discord.com)"."""
    info = describe(channel)
    return f"{DISPLAY_NAMES[info['type']]} ({info['target']})"


def message(event: str, payload: dict, language: str) -> tuple[str, str]:
    text = COPY.get(language, COPY["en"])
    job = payload["job"]
    title = text[0] if event == "download_completed" else text[1]
    body = str(job.get("title") or job.get("url") or "")[:500]
    if event == "download_failed" and job.get("error"):
        body = f"{body}\n{str(job['error'])[:300]}"
    return title, body


SIGNIN_COPY = {
    "en": ("YouTube sign-in expired", "YouTube no longer accepts the cookies Video Grabber uses. "
           "Export a fresh cookies.txt and upload it in Advanced settings."),
    "zh-CN": ("YouTube 登录已失效", "YouTube 不再接受 Video Grabber 使用的 cookie。请导出新的 cookies.txt 并在高级设置中上传。"),
    "zh-TW": ("YouTube 登入已失效", "YouTube 不再接受 Video Grabber 使用的 cookie。請匯出新的 cookies.txt 並在進階設定中上傳。"),
    "ja": ("YouTube のログインが切れました", "YouTube が Video Grabber の Cookie を受け付けなくなりました。"
           "新しい cookies.txt を書き出し、詳細設定でアップロードしてください。"),
}


def signin_message(language: str) -> tuple[str, str]:
    return SIGNIN_COPY.get(language, SIGNIN_COPY["en"])


def test_message(language: str) -> tuple[str, str]:
    text = COPY.get(language, COPY["en"])
    return text[2], text[3]


def build_request(channel: dict, title: str, body: str, payload: dict | None) -> urllib.request.Request:
    """Plain text only: no Markdown parsing and no Discord mentions, so video titles cannot ping anyone."""
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json; charset=utf-8"}
    kind = channel["type"]
    if kind == "discord":
        url = channel["url"]
        data = {"content": f"{title}\n{body}"[:2000], "allowed_mentions": {"parse": []}}
    elif kind == "telegram":
        url = f"https://api.telegram.org/bot{channel['bot_token']}/sendMessage"
        data = {"chat_id": channel["chat_id"], "text": f"{title}\n{body}"[:4096], "disable_web_page_preview": True}
    elif kind == "ntfy":
        # JSON publishing to the server root keeps non-ASCII titles out of HTTP headers.
        parts = urlsplit(channel["url"])
        base_path, _, topic = parts.path.rstrip("/").rpartition("/")
        url = f"{parts.scheme}://{parts.netloc}{base_path}/"
        data = {"topic": topic, "title": title, "message": body or title}
        if channel.get("token"):
            headers["Authorization"] = f"Bearer {channel['token']}"
    else:
        url = channel["url"]
        data = {**(payload or {"version": 1, "event": "test"}), "message": {"title": title, "body": body}}
        headers.update(channel.get("headers", {}))
    return urllib.request.Request(url, data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                                  headers=headers, method="POST")


def _secrets(channel: dict) -> list[str]:
    values = [channel.get("url", ""), channel.get("bot_token", ""), channel.get("token", "")]
    values += list(channel.get("headers", {}).values())
    return [value for value in values if value]


def send(channel: dict, title: str, body: str, payload: dict | None = None, opener=urllib.request.urlopen) -> str:
    """Send once. Returns "" on success, otherwise a short reason that never contains a secret."""
    try:
        with opener(build_request(channel, title, body, payload), timeout=SEND_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            if not 200 <= status < 300:
                return f"The service answered HTTP {status}."
    except urllib.error.HTTPError as error:
        error.close()
        return f"The service answered HTTP {error.code}."
    except (urllib.error.URLError, OSError, ValueError) as error:
        detail = str(getattr(error, "reason", error))
        for secret in _secrets(channel):
            detail = detail.replace(secret, "…")
        return f"Could not reach the service: {detail}"[:300]
    return ""
