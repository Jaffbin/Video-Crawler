import webui
from test_webui import call, isolated, server  # noqa: F401


def test_audio_progress_is_bound_to_the_current_library(request):
    base = request.getfixturevalue("server")
    (webui.ROOT / "song.mp3").write_bytes(b"audio fixture")
    body = {"path": "song.mp3", "position": 15, "duration": 120, "root": str(webui.ROOT)}
    assert call(base, "/api/library/playback", body)[0] == 200
    before = webui.LIBRARY.load()
    assert call(base, "/api/library/playback", {**body, "root": "another-library", "position": 55})[0] == 400
    assert webui.LIBRARY.load() == before
    # Existing clients that do not send the optional library binding retain their API.
    assert call(base, "/api/library/playback", {key: value for key, value in body.items() if key != "root"})[0] == 200
