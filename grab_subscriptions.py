"""Pure rules for Auto-download: which listed videos are new, wanted and worth queueing.

Nothing here touches the network, the queue or the disk, so each rule can be tested on its own.
"""

from __future__ import annotations

from grab_models import http_url, normalize_subscription_filters


def normalize_flat_entries(info: dict, fallback_url: str) -> list[dict]:
    """Keep only entries with a usable web URL; flat extractors sometimes put a bare ID in ``url``."""
    is_playlist = info.get("_type") == "playlist"
    entries = list(info.get("entries") or []) if is_playlist else [info]
    normalized = []
    for entry in entries:
        if not entry or not entry.get("id"):
            continue
        entry_url = http_url(entry.get("webpage_url")) or http_url(entry.get("url"))
        if not entry_url and not is_playlist:
            entry_url = fallback_url
        if entry_url:
            try:
                duration = max(0, int(float(entry.get("duration")))) if entry.get("duration") is not None else None
            except (TypeError, ValueError):
                duration = None
            candidate_urls = " ".join(str(entry.get(key) or "") for key in ("url", "webpage_url", "original_url"))
            live_status = str(entry.get("live_status") or "").lower()
            normalized.append({
                "id": str(entry["id"]), "url": entry_url, "title": entry.get("title") or "",
                "duration": duration,
                "is_live": bool(entry.get("is_live")) or live_status in {"is_live", "is_upcoming"},
                "is_short": "/shorts/" in candidate_urls.lower(),
            })
    return normalized


def subscription_filter_reason(entry: dict, filters: dict) -> str | None:
    """Return a stable reason code for a rejected entry, or None when it matches."""
    included = [word.casefold() for word in filters["include_keywords"]]
    excluded = [word.casefold() for word in filters["exclude_keywords"]]
    title = str(entry.get("title") or "").casefold()
    duration = entry.get("duration")
    if included and not any(word in title for word in included):
        return "include_keywords"
    if any(word in title for word in excluded):
        return "exclude_keywords"
    if filters["exclude_live"] and entry.get("is_live"):
        return "live"
    if filters["exclude_shorts"] and entry.get("is_short"):
        return "shorts"
    if filters["min_duration"] and duration is not None and duration < filters["min_duration"]:
        return "min_duration"
    if filters["max_duration"] and duration is not None and duration > filters["max_duration"]:
        return "max_duration"
    return None


def filter_subscription_entries(entries: list[dict], filters: dict) -> tuple[list[dict], list[dict]]:
    filters = normalize_subscription_filters(filters)
    accepted, skipped = [], []
    for entry in entries:
        (skipped if subscription_filter_reason(entry, filters) else accepted).append(entry)
    return accepted, skipped


def split_backfill(entries: list[dict], count: int) -> tuple[list[dict], list[dict]]:
    """(entries to queue now, the rest) - assumes newest-first order, which is what channel/playlist
    listings normally are; if a site instead lists oldest-first, backfill still just picks the first
    `count` entries returned rather than the true most-recent ones."""
    return entries[:count], entries[count:]
