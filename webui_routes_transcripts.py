"""Transcription and transcript search routes.

Every function takes ``app`` (the webui module) and ``h`` (the request handler).
"""

from __future__ import annotations

import grab_transcribe


def transcripts_get(app, h, path: str, q: dict) -> bool:
    if path == "/api/transcripts":
        h._json(app.TRANSCRIBER.status())
        return True
    if path == "/api/transcripts/search":
        query = (q.get("q") or [""])[0][:200]
        h._json({"query": query, "results": app.search_transcripts(query)})
        return True
    return False


def transcripts_post(app, h, path: str, body: dict) -> bool:
    if path != "/api/transcripts":
        return False
    action = body.get("action")
    try:
        if action == "start":
            result = app.TRANSCRIBER.enqueue(body.get("paths"))
        elif action == "cancel":
            app.TRANSCRIBER.cancel()
            result = {}
        elif action == "model":
            app.save_transcription_model(body.get("model"))
            result = {}
        elif action == "automation":
            app.save_transcription_automation(body.get("auto"), body.get("reuse_subtitles"))
            result = {}
        else:
            raise ValueError("Choose start, cancel, model or automation.")
    except ValueError as error:
        h._json({"error": str(error)}, 400)
        return True
    except OSError:
        h._json({"error": "Could not save transcription settings."}, 500)
        return True
    h._json({**result, **app.TRANSCRIBER.status()})
    return True


def kind_check(app, relative: str):
    """Resolve a Library path that may be transcribed: complete audio or video only."""
    media = app.LIBRARY.media_path(relative)
    if app.media_kind(media.suffix.lower()) not in ("audio", "video"):
        raise ValueError("Only audio and video can be transcribed.")
    return media


__all__ = ["transcripts_get", "transcripts_post", "kind_check", "grab_transcribe"]
