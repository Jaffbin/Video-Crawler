"""Download schedule: a daily window for starting downloads and busy hours with a speed limit.

All times are local wall-clock "HH:MM". A range whose end is earlier than its start crosses midnight
(23:00–07:00). Only the start of a task is scheduled: a running download is never paused or
re-limited, because yt-dlp fixes the rate limit when a download begins.
"""
from __future__ import annotations

import datetime
import re

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
RATE_RE = re.compile(r"^\d+(\.\d+)?[KkMmGg]?$")
DEFAULT = {"enabled": False, "window": None, "limit": None}


def _minutes(value, label: str) -> int:
    if not isinstance(value, str) or not TIME_RE.match(value):
        raise ValueError(f"Enter {label} as HH:MM, for example 23:00.")
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _range(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"Choose a start and end time for {label}.")
    start, end = value.get("start"), value.get("end")
    if _minutes(start, "the start time") == _minutes(end, "the end time"):
        raise ValueError(f"The {label} start and end times must differ.")
    return {"start": start, "end": end}


def checked(value) -> dict:
    """Validate a schedule from the settings file or the app. Raises ValueError with a UI message."""
    if not isinstance(value, dict) or set(value) - {"enabled", "window", "limit"}:
        raise ValueError("Invalid download schedule.")
    enabled = value.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("Invalid download schedule.")
    window = _range(value["window"], "download window") if value.get("window") is not None else None
    limit = None
    if value.get("limit") is not None:
        limit = _range(value["limit"], "speed limit")
        rate = value["limit"].get("rate")
        if not isinstance(rate, str) or not RATE_RE.match(rate.strip()) or float(re.sub(r"\D*$", "", rate)) <= 0:
            raise ValueError("Enter a speed such as 2M or 500K.")
        limit["rate"] = rate.strip().upper()
    if enabled and window is None and limit is None:
        raise ValueError("Choose a download window, a speed limit, or both.")
    return {"enabled": enabled, "window": window, "limit": limit}


def load(raw) -> dict:
    """A saved schedule, or the default when the file is missing or no longer valid."""
    try:
        return checked(raw)
    except ValueError:
        return dict(DEFAULT)


def inside(span: dict, now: datetime.datetime) -> bool:
    start, end = _minutes(span["start"], "start"), _minutes(span["end"], "end")
    current = now.hour * 60 + now.minute
    return start <= current < end if start < end else current >= start or current < end


def may_start(schedule: dict, now: datetime.datetime) -> bool:
    return not schedule["enabled"] or schedule["window"] is None or inside(schedule["window"], now)


def rate_limit(schedule: dict, now: datetime.datetime) -> str | None:
    if schedule["enabled"] and schedule["limit"] and inside(schedule["limit"], now):
        return schedule["limit"]["rate"]
    return None


def next_start(schedule: dict, now: datetime.datetime) -> datetime.datetime | None:
    """When waiting tasks may start next, or None if they may start now."""
    if may_start(schedule, now):
        return None
    hours, minutes = map(int, schedule["window"]["start"].split(":"))
    candidate = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    return candidate if candidate > now else candidate + datetime.timedelta(days=1)


def view(schedule: dict, now: datetime.datetime) -> dict:
    """What the Queue shows: the saved schedule plus whether it is holding tasks right now."""
    upcoming = next_start(schedule, now)
    return {**schedule, "holding": upcoming is not None,
            "next_start": upcoming.timestamp() if upcoming else None,
            "limit_active": rate_limit(schedule, now)}
