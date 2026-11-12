"""Auto-download (subscription) routes.

Every function takes ``app`` (the webui module) and ``h`` (the request handler).
"""

from __future__ import annotations

import re


def subscriptions_get(app, h, path: str) -> bool:
    if path == "/api/subscriptions":
        subs = app.SUBSCRIPTION_MANAGER.snapshot(newest_first=True)
        h._json({"subscriptions": [app.subscription_view(s) for s in subs],
                    "interval_seconds": app.SUB_INTERVAL_SECONDS})
        return True
    return False


def subscriptions_post(app, h, path: str, body: dict) -> bool:
    if path == "/api/subscriptions":
        url = app.http_url(body.get("url"))
        if not url:
            h._json({"error": "Please enter an http(s) URL"}, 400)
            return True
        backfill = str(body.get("backfill") or "none")
        try:
            backfill_count = int(body.get("backfill_count") or 5)
        except (TypeError, ValueError):
            backfill_count = 5
        options = body.get("options") if isinstance(body.get("options"), dict) else {}
        if options.get("mode") in ("cover", "image"):
            h._json({"error": "Subscriptions currently support video and audio only."}, 400)
            return True
        sub = app.Subscription(url, options, backfill, backfill_count, body.get("filters"))
        app.SUBSCRIPTION_MANAGER.add(sub)
        app.save_subscriptions()
        app.start_subscription_check(sub)
        h._json(app.subscription_view(sub))
        return True

    m = re.fullmatch(r"/api/subscriptions/([0-9a-f]{8})/(update|check-now|preview|remove)", path)
    if m:
        sub, action = app.SUBSCRIPTION_MANAGER.get(m.group(1)), m.group(2)
        if not sub:
            h._json({"error": "Subscription not found"}, 404)
            return True
        if action == "update":
            if isinstance(body.get("options"), dict) and body["options"].get("mode") in ("cover", "image"):
                h._json({"error": "Subscriptions currently support video and audio only."}, 400)
                return True
            if "enabled" in body:
                if not isinstance(body["enabled"], bool):
                    h._json({"error": "enabled must be true or false"}, 400)
                    return True
                sub.enabled = bool(body["enabled"])
            if "options" in body and isinstance(body["options"], dict):
                sub.options = dict(body["options"])
            if "filters" in body:
                if not isinstance(body["filters"], dict):
                    h._json({"error": "filters must be an object"}, 400)
                    return True
                sub.filters = app.normalize_subscription_filters(body["filters"])
            if body.get("backfill") in ("none", "recent"):
                sub.backfill = body["backfill"]
            if "backfill_count" in body:
                try:
                    sub.backfill_count = max(1, min(int(body["backfill_count"]), app.BACKFILL_MAX))
                except (TypeError, ValueError):
                    pass
            app.save_subscriptions()
            h._json(app.subscription_view(sub))
            return True
        if action == "check-now":
            app.start_subscription_check(sub)
            h._json({"ok": True})
            return True
        if action == "preview":
            if "filters" in body and not isinstance(body["filters"], dict):
                h._json({"error": "filters must be an object"}, 400)
                return True
            try:
                h._json(app.preview_subscription(sub, body.get("filters", sub.filters)))
            except Exception as e:  # noqa: BLE001
                h._json({"error": app.friendly_error(str(e))}, 502)
            return True
        if action == "remove":
            app.SUBSCRIPTION_MANAGER.remove(sub.id)
            app.save_subscriptions()
            h._json({"ok": True})
            return True

    return False
